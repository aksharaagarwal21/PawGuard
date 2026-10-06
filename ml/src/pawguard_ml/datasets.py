"""Identity-dataset preparation: ingest → validate → duplicate graph → grouped open-set split → leakage checks.

Principles (docs/ML_PLAN.md, brief §6–7):
- Provenance first: every sample keeps its source path, checksum and asserted label.
- Exact duplicates (sha256) and near duplicates (perceptual hash) form a graph *before* splitting; a connected
  component (a "dup group") never straddles train/val/test or gallery/query.
- Near duplicates that span two asserted identities are label conflicts: excluded and queued for adjudication,
  never silently relabelled.
- Splits are identity-disjoint. Val/test contain enrolled identities (gallery + query from different dup groups)
  and unknown identities (absent from the gallery) for open-set evaluation.
- Nothing is deleted from the raw data; excluded samples carry a reason and are counted in the manifest.
"""

import hashlib
import json
import random
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path

import cv2
import numpy as np

TRANSFORM_VERSION = "ingest-1"
PHASH_NEAR_DUP = 6  # Hamming distance (of 64 bits) treated as near-duplicate


@dataclass
class Sample:
    key: str
    identity: str
    sha256: str
    phash: str
    width: int
    height: int
    flags: list[str] = field(default_factory=list)
    dup_group: str = ""
    split: str = ""
    role: str = ""
    exclusion: str = ""


def phash(gray: np.ndarray) -> str:
    """64-bit DCT perceptual hash (32×32 → top-left 8×8 DCT, median threshold, DC term included)."""
    small = cv2.resize(gray, (32, 32), interpolation=cv2.INTER_AREA).astype(np.float32)
    dct = cv2.dct(small)[:8, :8].flatten()
    bits = dct > np.median(dct)
    return f"{int(''.join('1' if b else '0' for b in bits), 2):016x}"


def ingest(root: Path, rel_to: Path) -> list[Sample]:
    """One folder per asserted identity; every readable image becomes a sample (unreadable → flagged)."""
    samples: list[Sample] = []
    for ident_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        for f in sorted(ident_dir.iterdir()):
            if f.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
                continue
            data = f.read_bytes()
            sha = hashlib.sha256(data).hexdigest()
            img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
            key = f.relative_to(rel_to).as_posix()
            if img is None:
                samples.append(Sample(key, ident_dir.name, sha, "", 0, 0, ["decode_failed"]))
                continue
            flags = []
            b, g, r = cv2.split(img.astype(np.int16))
            if max(int(np.abs(b - g).max()), int(np.abs(g - r).max())) <= 3:
                flags.append("grayscale")
            if min(img.shape[:2]) < 64:
                flags.append("too_small")
            samples.append(Sample(key, ident_dir.name, sha, phash(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)),
                                  img.shape[1], img.shape[0], flags))
    return samples


_POPCOUNT = np.array([bin(i).count("1") for i in range(256)], dtype=np.uint8)


def hamming_matrix_row(h: np.ndarray, i: int) -> np.ndarray:
    x = np.bitwise_xor(h[i], h)
    return _POPCOUNT[x.view(np.uint8)].reshape(-1, 8).sum(1)


def duplicate_groups(samples: list[Sample], threshold: int = PHASH_NEAR_DUP) -> dict[str, int]:
    """Union-find over exact (sha256) and near (pHash ≤ threshold) duplicates. Returns stats."""
    n = len(samples)
    parent = list(range(n))

    def find(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    by_sha: dict[str, int] = {}
    exact_pairs = 0
    for i, s in enumerate(samples):
        if s.sha256 in by_sha:
            union(by_sha[s.sha256], i)
            exact_pairs += 1
        else:
            by_sha[s.sha256] = i
    valid = [i for i, s in enumerate(samples) if s.phash]
    hashes = np.array([int(samples[i].phash, 16) for i in valid], dtype=np.uint64)
    near_pairs = 0
    dist_hist = defaultdict(int)
    for k in range(len(valid)):
        d = hamming_matrix_row(hashes, k)[k + 1:]
        for t in (4, 6, 10):
            dist_hist[f"pairs_le_{t}"] += int((d <= t).sum())
        for j in np.nonzero(d <= threshold)[0]:
            union(valid[k], valid[k + 1 + int(j)])
            near_pairs += 1
    for i, s in enumerate(samples):
        s.dup_group = f"g{find(i)}"
    return {"exact_duplicate_files": exact_pairs, "near_duplicate_pairs": near_pairs, **dist_hist}


def flag_label_conflicts(samples: list[Sample]) -> int:
    """A dup group containing more than one asserted identity is a label conflict → exclude for adjudication."""
    idents = defaultdict(set)
    for s in samples:
        idents[s.dup_group].add(s.identity)
    n = 0
    for s in samples:
        if len(idents[s.dup_group]) > 1:
            s.flags.append("cross_identity_duplicate")
            s.split, s.exclusion = "excluded", "label_conflict_pending_adjudication"
            n += 1
    for s in samples:
        if "decode_failed" in s.flags or "too_small" in s.flags:
            s.split, s.exclusion = "excluded", s.flags[0]
    return n


def split(samples: list[Sample], seed: int, fractions: tuple[float, float, float] = (0.7, 0.15, 0.15),
          unknown_fraction: float = 0.3) -> dict:
    """Identity-disjoint split; open-set roles inside val/test with dup groups kept on one side."""
    usable = [s for s in samples if s.split != "excluded"]
    by_ident: dict[str, list[Sample]] = defaultdict(list)
    for s in usable:
        by_ident[s.identity].append(s)
    identities = sorted(i for i, ss in by_ident.items() if len(ss) >= 2)
    for ss in by_ident.values():
        if len(ss) < 2:
            for s in ss:
                s.split, s.exclusion = "excluded", "single_image_identity"
    rng = random.Random(seed)
    rng.shuffle(identities)
    n_train = int(len(identities) * fractions[0])
    n_val = int(len(identities) * fractions[1])
    parts = {"train": identities[:n_train], "val": identities[n_train:n_train + n_val],
             "test": identities[n_train + n_val:]}
    stats: dict = {}
    for part, idents in parts.items():
        if part == "train":
            for i in idents:
                for s in by_ident[i]:
                    s.split, s.role = "train", "training"
            stats["train"] = {"identities": len(idents), "images": sum(len(by_ident[i]) for i in idents)}
            continue
        idents = list(idents)
        n_unknown = int(len(idents) * unknown_fraction)
        unknown, enrolled = idents[:n_unknown], idents[n_unknown:]
        demoted = 0
        for i in unknown:
            for s in by_ident[i]:
                s.split, s.role = part, "unknown_query"
        for i in enrolled:
            groups: dict[str, list[Sample]] = defaultdict(list)
            for s in by_ident[i]:
                groups[s.dup_group].append(s)
            gkeys = sorted(groups)
            rng.shuffle(gkeys)
            if len(gkeys) < 2:  # cannot separate gallery from query without near-duplicate leakage
                for s in by_ident[i]:
                    s.split, s.role = part, "unknown_query"
                demoted += 1
                continue
            n_gallery = max(1, len(gkeys) // 2)
            for gi, g in enumerate(gkeys):
                for s in groups[g]:
                    s.split, s.role = part, "gallery" if gi < n_gallery else "query"
        roles = defaultdict(int)
        for s in samples:
            if s.split == part:
                roles[s.role] += 1
        stats[part] = {"identities": len(idents), "unknown_identities": len(unknown) + demoted,
                       "enrolled_identities": len(enrolled) - demoted, "images_by_role": dict(roles)}
    return stats


def leakage_checks(samples: list[Sample], threshold: int = PHASH_NEAR_DUP) -> dict:
    """Independent re-check of the split: identities, files and near-duplicates must not cross boundaries."""
    problems: list[str] = []
    ident_splits = defaultdict(set)
    for s in samples:
        if s.split != "excluded":
            ident_splits[s.identity].add(s.split)
    problems += [f"identity {i} in {sorted(v)}" for i, v in ident_splits.items() if len(v) > 1]
    sha_where = defaultdict(set)
    for s in samples:
        if s.split != "excluded":
            sha_where[s.sha256].add((s.split, s.role if s.split != "train" else "training"))
    problems += [f"file {h[:12]} in {sorted(v)}" for h, v in sha_where.items() if len(v) > 1]
    for part in ("val", "test"):
        gal = [s for s in samples if s.split == part and s.role == "gallery"]
        qry = [s for s in samples if s.split == part and s.role in ("query", "unknown_query")]
        if gal and qry:
            g = np.array([int(s.phash, 16) for s in gal], dtype=np.uint64)
            for q in qry:
                d = _POPCOUNT[np.bitwise_xor(np.uint64(int(q.phash, 16)), g).view(np.uint8)].reshape(-1, 8).sum(1)
                if (d <= threshold).any():
                    problems.append(f"near-duplicate between {part} query {q.key} and gallery")
    others = [s for s in samples if s.split in ("val", "test")]
    train = [s for s in samples if s.split == "train"]
    if others and train:
        t = np.array([int(s.phash, 16) for s in train], dtype=np.uint64)
        for s in others:
            d = _POPCOUNT[np.bitwise_xor(np.uint64(int(s.phash, 16)), t).view(np.uint8)].reshape(-1, 8).sum(1)
            if (d <= threshold).any():
                problems.append(f"near-duplicate between train and {s.split} sample {s.key}")
    return {"passed": not problems, "problem_count": len(problems), "examples": problems[:20]}


def write_manifest(samples: list[Sample], meta: dict, path: Path) -> str:
    body = {**meta, "transform_version": TRANSFORM_VERSION, "samples": [asdict(s) for s in samples]}
    text = json.dumps(body, indent=1, sort_keys=False) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
