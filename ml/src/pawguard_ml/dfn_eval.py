"""Real-data evaluation of the deployed PawID model on DogFaceNet — evaluation only, the model stays frozen.

DogFaceNet (Zenodo 12578449, CC BY 4.0) contains aligned FACE crops of PET dogs. It says nothing about full-body
photos of Indian community dogs in the field; every output repeats this.

Pipeline (each step writes its own artefact; reruns are deterministic for the fixed seed):
  clean  → decode, drop unreadable, drop exact duplicates (SHA-256), group near-duplicates (pHash ≤ 6),
           exclude near-duplicates shared by two identities (label conflicts), keep identities with ≥ 3 images.
  split  → identity-disjoint, open-set. Only identities the deployed model's head never trained on are eligible:
           validation group ⊂ v1 validation identities (used before only for tuning), test group ⊂ v1 test
           identities (never used for training or tuning). Inside each group 75 % known (2 gallery images, the rest
           queries, no near-duplicate of a gallery image as a query) and 25 % unknown (all images are queries).
  eval   → embeddings from the deployed ONNX model through the worker's own preprocessing (no detector: the images
           are already face crops), exact cosine search, aggregation rule + threshold chosen on validation only,
           test evaluated once with identity-bootstrap CIs, baselines, timings, charts and a local error gallery.
"""

import csv
import hashlib
import json
import random
import subprocess
import time
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

import cv2
import numpy as np

from pawguard_ml import datasets as ds
from pawguard_ml import retrieval as rv

ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / "data/raw/dogfacenet/after_4_bis"
OUT = ROOT / "ml/eval/dogfacenet"  # tracked: numbers, manifests, charts (no images of dogs)
LOCAL = ROOT / "data/derived/eval/dogfacenet"  # ignored: embeddings cache, error gallery
V1 = ROOT / "data/manifests/datasets/dogfacenet-224-v1.json"
MODEL_MANIFEST = ROOT / "data/manifests/models/dinov2_small_arcface_head-v1.json"
SEED = 20261007
MIN_IMAGES = 3
CAVEAT = ("DogFaceNet: aligned face crops of pet dogs (web photos). Not full-body photos of Indian community dogs "
          "in the field; no capture-session information, so same-session look-alike photos cannot be fully ruled "
          "out; small sample. Not evidence of street-dog accuracy.")


def write_lf(p: Path, text: str) -> None:
    """Write with LF line endings on every OS, so recorded hashes match the files committed to Git."""
    p.write_bytes(text.encode("utf-8"))


def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def commit_hash() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True,  # noqa: S607
                              check=True).stdout.strip()
    except Exception:
        return "unknown"


# ---- Step 2: clean -----------------------------------------------------------------------------------------------

def clean() -> dict:
    samples = ds.ingest(RAW, RAW.parent)
    steps = [{"step": "all files", "identities": len({s.identity for s in samples}), "images": len(samples)}]
    status: dict[str, str] = {}

    def stage(name: str) -> None:
        kept = [s for s in samples if s.key not in status]
        steps.append({"step": name, "identities": len({s.identity for s in kept}), "images": len(kept)})

    for s in samples:
        if "decode_failed" in s.flags:
            status[s.key] = "unreadable"
        elif "too_small" in s.flags:
            status[s.key] = "too_small"
    stage("after dropping unreadable / too small")
    seen: dict[str, str] = {}
    for s in samples:
        if s.key in status:
            continue
        if s.sha256 in seen:
            status[s.key] = f"exact_duplicate_of:{seen[s.sha256]}"
        else:
            seen[s.sha256] = s.key
    stage("after removing exact duplicates (SHA-256)")
    kept = [s for s in samples if s.key not in status]
    dup = ds.duplicate_groups(kept)
    groups = defaultdict(set)
    for s in kept:
        groups[s.dup_group].add(s.identity)
    for s in kept:
        if len(groups[s.dup_group]) > 1:
            status[s.key] = "near_duplicate_shared_by_two_identities"
    stage("after excluding near-duplicates shared by two identities")
    per_id = Counter(s.identity for s in samples if s.key not in status)
    for s in samples:
        if s.key not in status and per_id[s.identity] < MIN_IMAGES:
            status[s.key] = f"identity_has_fewer_than_{MIN_IMAGES}_images"
    stage(f"after keeping identities with ≥ {MIN_IMAGES} images")
    rows = [{"key": s.key, "identity": s.identity, "sha256": s.sha256, "phash": s.phash, "dup_group": s.dup_group,
             "flags": ";".join(s.flags), "status": "excluded" if s.key in status else "kept",
             "reason": status.get(s.key, "")} for s in samples]
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "clean_manifest.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    summary = {"source": "Zenodo 12578449 DogFaceNet_224resized.zip (md5 010c207e202bb499039452aa7363b015)",
               "steps": steps, "near_duplicate_stats": dup, "excluded_by_reason": dict(Counter(
                   r["reason"].split(":")[0] for r in rows if r["status"] == "excluded")),
               "manifest": "ml/eval/dogfacenet/clean_manifest.csv",
               "manifest_sha256": sha256_file(OUT / "clean_manifest.csv")}
    write_lf(OUT / "clean_summary.json", json.dumps(summary, indent=1) + "\n")
    return summary


# ---- Step 3: split -----------------------------------------------------------------------------------------------

def _v1_splits() -> dict[str, str]:
    m = json.loads(V1.read_text(encoding="utf-8"))
    by_id: dict[str, set[str]] = defaultdict(set)
    for s in m["samples"]:
        by_id[s["identity"]].add(s["split"])
    return {i: ("train" if "train" in sp else "val" if "val" in sp else "test" if "test" in sp else "excluded")
            for i, sp in by_id.items()}


def split(max_identities: int = 300) -> dict:
    rows = list(csv.DictReader((OUT / "clean_manifest.csv").open(encoding="utf-8")))
    kept = [r for r in rows if r["status"] == "kept"]
    by_id: dict[str, list[dict]] = defaultdict(list)
    for r in kept:
        by_id[r["identity"]].append(r)
    v1 = _v1_splits()
    trained_on = sorted(i for i in by_id if v1.get(i) == "train")
    pool_val = sorted(i for i in by_id if v1.get(i) == "val")
    pool_test = sorted(i for i in by_id if v1.get(i) == "test")
    rng = random.Random(SEED)
    n_val = min(len(pool_val), round(max_identities * 0.3))
    n_test = min(len(pool_test), max_identities - n_val)
    groups = {"validation": sorted(rng.sample(pool_val, n_val)), "test": sorted(rng.sample(pool_test, n_test))}
    assign: list[dict] = []
    counts: dict[str, dict] = {}
    for gname, ids in groups.items():
        ids = ids[:]
        rng.shuffle(ids)
        n_known = round(len(ids) * 0.75)
        known, unknown = sorted(ids[:n_known]), sorted(ids[n_known:])
        c = Counter()
        for ident in known:
            imgs = sorted(by_id[ident], key=lambda r: r["key"])
            gallery = rng.sample(imgs, 2)
            gal_groups = {g["dup_group"] for g in gallery}
            for r in imgs:
                if r in gallery:
                    role = "gallery"
                elif r["dup_group"] in gal_groups:
                    role = "excluded_near_duplicate_of_gallery"
                else:
                    role = "known_query"
                c[role] += 1
                assign.append({**r, "group": gname, "dog": "known", "role": role})
        for ident in unknown:
            for r in sorted(by_id[ident], key=lambda r: r["key"]):
                c["unknown_query"] += 1
                assign.append({**r, "group": gname, "dog": "unknown", "role": "unknown_query"})
        counts[gname] = {"identities": len(ids), "known_identities": len(known), "unknown_identities": len(unknown),
                         **dict(c)}
    leakage = check_split(assign, set(trained_on))
    body = {"seed": SEED, "max_identities": max_identities, "eligible": {
                "validation_pool (v1 val identities)": len(pool_val), "test_pool (v1 test identities)": len(pool_test),
                "excluded_trained_on_by_head (v1 train identities)": len(trained_on)},
            "counts": counts, "leakage_check": leakage, "assignments": assign}
    text = json.dumps(body, indent=1) + "\n"
    write_lf(OUT / "split_manifest.json", text)
    split_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if not leakage["passed"]:
        raise SystemExit(f"LEAKAGE CHECK FAILED: {leakage['problems'][:5]}")
    return {"split_sha256": split_hash, **{k: v for k, v in body.items() if k != "assignments"}}


def check_split(assign: list[dict], trained_on: set[str]) -> dict:
    """Fails if an identity crosses validation/test, appears as both known and unknown, was used to train the head,
    or if a gallery image has an exact or near duplicate (pHash ≤ 6) among the queries of its group."""
    problems: list[str] = []
    groups_of: dict[str, set[str]] = defaultdict(set)
    dogs_of: dict[str, set[str]] = defaultdict(set)
    for a in assign:
        groups_of[a["identity"]].add(a["group"])
        dogs_of[a["identity"]].add(a["dog"])
    problems += [f"identity {i} in {sorted(g)}" for i, g in groups_of.items() if len(g) > 1]
    problems += [f"identity {i} both known and unknown" for i, d in dogs_of.items() if len(d) > 1]
    problems += [f"identity {i} was used to train the head" for i in groups_of if i in trained_on]
    for g in ("validation", "test"):
        gal = [a for a in assign if a["group"] == g and a["role"] == "gallery"]
        qry = [a for a in assign if a["group"] == g and a["role"] in ("known_query", "unknown_query")]
        gal_sha, gal_dup = {a["sha256"] for a in gal}, {a["dup_group"] for a in gal}
        problems += [f"{g}: query {q['key']} duplicates a gallery image" for q in qry
                     if q["sha256"] in gal_sha or q["dup_group"] in gal_dup]
        if gal and qry:
            h = np.array([int(a["phash"], 16) for a in gal], dtype=np.uint64)
            for q in qry:
                d = ds._POPCOUNT[np.bitwise_xor(np.uint64(int(q["phash"], 16)), h).view(np.uint8)].reshape(-1, 8).sum(1)
                if (d <= ds.PHASH_NEAR_DUP).any():
                    problems.append(f"{g}: query {q['key']} is a near-duplicate of a gallery image")
    return {"passed": not problems, "problem_count": len(problems), "problems": problems[:20]}


# ---- Step 4/5: embed, search, evaluate -----------------------------------------------------------------------------

def _load_split() -> tuple[dict, str]:
    raw = (OUT / "split_manifest.json").read_bytes()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def _embedder():
    from pawguard_worker.vision.embed import EmbedConfig, OnnxEmbedder

    m = json.loads(MODEL_MANIFEST.read_text(encoding="utf-8"))
    path = ROOT / "models" / m["artifact_path"]
    return OnnxEmbedder(path, EmbedConfig.from_manifest(m["preprocessing"]), expected_sha256=m["sha256"], threads=4), m


def embed_all(keys: list[str]) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray], dict]:
    """Head embedding (deployed model) and CLS (backbone only) for every key, through the worker's preprocessing.
    Returns embeddings plus timing measured on this machine."""
    from pawguard_worker.vision.embed import pool, preprocess

    emb, manifest = _embedder()
    head, cls = {}, {}
    t0 = time.perf_counter()
    for i in range(0, len(keys), 32):
        chunk = keys[i:i + 32]
        batch = np.concatenate([preprocess(cv2.imread(str(RAW.parent / k)), emb.config.resize_mode) for k in chunk])
        c, p, e = emb.session.run(["cls", "patch_mean", "embedding"], {emb.input_name: batch})
        e = pool(e, e, "cls")  # L2 normalise (the head already normalises; idempotent)
        c = pool(c, p, "cls")
        for j, k in enumerate(chunk):
            head[k], cls[k] = e[j], c[j]
    batch_s = time.perf_counter() - t0
    single = []
    for k in keys[: min(50, len(keys))]:
        t = time.perf_counter()
        emb.embed(cv2.imread(str(RAW.parent / k)))
        single.append((time.perf_counter() - t) * 1000)
    timing = {"images": len(keys), "batched_total_s": round(batch_s, 2),
              "batched_ms_per_image": round(batch_s * 1000 / max(1, len(keys)), 1),
              "single_image_ms_median": round(float(np.median(single)), 1),
              "single_image_ms_mean": round(float(np.mean(single)), 1), "single_image_n": len(single),
              "single_image_includes": "JPEG decode + preprocessing + ONNX inference, 4 threads"}
    return head, cls, {"timing": timing, "model": manifest}


def color_histogram(keys: list[str]) -> dict[str, np.ndarray]:
    """Baseline: HSV histogram (16×4×4 bins), Hellinger-normalised so cosine = Bhattacharyya coefficient."""
    out = {}
    for k in keys:
        hsv = cv2.cvtColor(cv2.imread(str(RAW.parent / k)), cv2.COLOR_BGR2HSV)
        h = cv2.calcHist([hsv], [0, 1, 2], None, [16, 4, 4], [0, 180, 0, 256, 0, 256]).flatten()
        h = np.sqrt(h / max(h.sum(), 1))
        out[k] = (h / max(np.linalg.norm(h), 1e-12)).astype(np.float32)
    return out


def random_vectors(keys: list[str], seed: int = SEED) -> dict[str, np.ndarray]:
    """Baseline: random unit vectors per image → chance-level ranking."""
    r = np.random.default_rng(seed)
    v = r.standard_normal((len(keys), 384)).astype(np.float32)
    v /= np.linalg.norm(v, axis=1, keepdims=True)
    return {k: v[i] for i, k in enumerate(keys)}


def split_data(assign: list[dict], group: str, vec: dict[str, np.ndarray]) -> rv.SplitData:
    rows = [a for a in assign if a["group"] == group]
    g = [a for a in rows if a["role"] == "gallery"]
    q = [a for a in rows if a["role"] == "known_query"]
    u = [a for a in rows if a["role"] == "unknown_query"]

    def arr(xs: list[dict]) -> np.ndarray:
        return np.stack([vec[a["key"]] for a in xs]) if xs else np.zeros((0, 384), np.float32)

    return rv.SplitData(np.array([a["identity"] for a in g]), arr(g), np.array([a["identity"] for a in q]), arr(q),
                        np.array([a["identity"] for a in u]), arr(u))


def tradeoff_curve(sc: rv.Scored) -> list[dict]:
    pts = []
    for tau in np.linspace(min(sc.u_top1.min(), sc.top[:, 0].min()), max(sc.u_top1.max(), sc.top[:, 0].max()), 60):
        m = rv.metrics(sc, float(tau), k_list=1)
        pts.append({"tau": round(float(tau), 4), "unknown_false_match": round(m["fpir"], 4),
                    "known_correct_accepted": round(m["known_top1_correct_accepted"], 4)})
    return pts


def evaluate(smoke: bool = False, reps: int = 1000, fmr_target: float = 0.05) -> dict:
    split_doc, split_hash = _load_split()
    assign = [a for a in split_doc["assignments"] if a["role"] != "excluded_near_duplicate_of_gallery"]
    if smoke:
        ids = {}
        for g in ("validation", "test"):  # 7 known + 3 unknown dogs per group
            ids[g] = set()
            for dog, n in (("known", 7), ("unknown", 3)):
                pool = sorted({a["identity"] for a in assign if a["group"] == g and a["dog"] == dog})
                ids[g] |= set(random.Random(SEED).sample(pool, n))
        assign = [a for a in assign if a["identity"] in ids[a["group"]]]
    keys = sorted({a["key"] for a in assign})
    head, cls, meta = embed_all(keys)
    hist, rnd = color_histogram(keys), random_vectors(keys)

    # Validation only: choose aggregation rule and threshold.
    choice = []
    for agg in ("max", "centroid"):
        sc = rv.score(split_data(assign, "validation", head), agg)
        tau = rv.threshold_for_fpir(sc.u_top1, fmr_target)
        m = rv.metrics(sc, tau, k_list=1)
        choice.append({"aggregation": agg, "tau": round(tau, 5), "val_unknown_false_match": round(m["fpir"], 4),
                       "val_known_correct_accepted": round(m["known_top1_correct_accepted"], 4),
                       "val_top1": round(m["top1"], 4)})
    best = max(choice, key=lambda c: (c["val_known_correct_accepted"], c["val_top1"]))
    agg, tau = best["aggregation"], best["tau"]
    val_sc = rv.score(split_data(assign, "validation", head), agg)

    # Test, once, with everything fixed.
    methods = {"pawid_dinov2s_head": head, "dinov2s_backbone_cls": cls, "color_histogram": hist, "random": rnd}
    test = {}
    for name, vec in methods.items():
        sc = rv.score(split_data(assign, "test", vec), agg)
        full = rv.bootstrap(sc, tau if name == "pawid_dinov2s_head" else None, reps=reps, seed=SEED)
        keep = ["top1", "top3", "map_image"] + (["fpir", "known_top1_correct_accepted", "false_rejection",
                                                 "known_top1_wrong_accepted"] if name == "pawid_dinov2s_head" else [])
        test[name] = {k: full[k] for k in keep}
        if name == "pawid_dinov2s_head":
            test_sc = sc
    d_test = split_data(assign, "test", head)
    t0 = time.perf_counter()
    for _ in range(5):
        rv.identity_scores(d_test.query, d_test, agg)
    search_ms = (time.perf_counter() - t0) * 1000 / (5 * max(1, len(d_test.query_ids)))
    counts = {g: {"known_identities": len(set(split_data(assign, g, head).gallery_ids)),
                  "gallery_images": len(split_data(assign, g, head).gallery_ids),
                  "known_queries": len(split_data(assign, g, head).query_ids),
                  "known_query_identities": len(set(split_data(assign, g, head).query_ids)),
                  "unknown_identities": len(set(split_data(assign, g, head).unknown_ids)),
                  "unknown_queries": len(split_data(assign, g, head).unknown_ids)} for g in ("validation", "test")}
    m = meta["model"]
    result = {
        "title": "PawID evaluation on DogFaceNet (pet dog face photos)", "caveat": CAVEAT, "smoke_test": smoke,
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"), "seed": SEED, "commit": commit_hash(),
        "command": "cd ml && uv run pawid dfn-clean && uv run pawid dfn-split && uv run pawid dfn-eval"
                   + (" --smoke" if smoke else ""),
        "model": {"name": m["name"], "version_label": m["version_label"], "artifact_sha256": m["sha256"],
                  "frozen": True, "detector": "skipped — DogFaceNet images are already face crops",
                  "embedding": "384-d, L2-normalised (DINOv2 ViT-S/14 + projection head trained on DogFaceNet v1 "
                               "train identities, which are excluded here)"},
        "dataset": {"source": "Zenodo 12578449, DogFaceNet_224resized (CC BY 4.0)", "split_sha256": split_hash,
                    "split_manifest": "ml/eval/dogfacenet/split_manifest.json", "counts": counts},
        "selection_on_validation": {"criterion": f"max known-dog top-1 correct-and-confident rate with unknown-dog "
                                                 f"false-match rate ≤ {fmr_target:.0%}; tie-break top-1",
                                    "candidates": choice, "chosen_aggregation": agg, "threshold": tau},
        "test": test,
        "metric_definitions": {
            "top1/top3": "known-dog queries whose correct dog is ranked 1st / within the first 3 (closed set)",
            "map_image": "mean average precision over gallery images (2 relevant images per known query)",
            "fpir": "unknown-dog queries wrongly given a confident match (best score ≥ threshold)",
            "known_top1_correct_accepted": "known-dog queries whose top-1 is the correct dog AND above the threshold",
            "false_rejection": "known-dog queries answered 'no confident match' (best score < threshold)",
            "known_top1_wrong_accepted": "known-dog queries confidently matched to the WRONG dog",
            "ci95": "percentile bootstrap over identities, 1,000 resamples (known and unknown dogs resampled separately)",
        },
        "timing": {**meta["timing"], "search_ms_per_query": round(search_ms, 3),
                   "search": f"exact cosine over {counts['test']['gallery_images']} test gallery images, numpy",
                   "machine": "this laptop (Intel i7-1255U, CPU only)"},
        "curves": {"validation": tradeoff_curve(val_sc), "test": tradeoff_curve(test_sc)},
    }
    name = "results_smoke.json" if smoke else "results.json"
    write_lf(OUT / name, json.dumps(result, indent=1) + "\n")
    if not smoke:
        charts(result)
        error_gallery(assign, head, agg, tau)
    return result


# ---- Step 6: charts and local error gallery ----------------------------------------------------------------------------

def charts(r: dict) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    labels = {"pawid_dinov2s_head": "PawID\n(DINOv2-S + head)", "dinov2s_backbone_cls": "DINOv2-S\nbackbone only",
              "color_histogram": "Colour\nhistogram", "random": "Random\n(chance)"}
    names = list(labels)
    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=150)
    x = np.arange(len(names))
    for off, metric, colour in ((-0.18, "top1", "#205c4f"), (0.18, "top3", "#8fb8a8")):
        vals = [r["test"][n][metric]["value"] for n in names]
        lo = [v - r["test"][n][metric]["ci95"][0] for v, n in zip(vals, names, strict=True)]
        hi = [r["test"][n][metric]["ci95"][1] - v for v, n in zip(vals, names, strict=True)]
        ax.bar(x + off, vals, 0.36, yerr=[lo, hi], capsize=3, color=colour, label=metric.replace("top", "Top-"))
        for xi, v in zip(x + off, vals, strict=True):
            ax.text(xi, v + 0.02, f"{v:.2f}", ha="center", fontsize=8)
    c = r["dataset"]["counts"]["test"]
    ax.set_xticks(x, [labels[n] for n in names])
    ax.set_ylim(0, 1.08)
    ax.set_ylabel("Accuracy on known-dog queries")
    ax.set_title(f"Closed-set identification, test set ({c['known_identities']} known dogs, "
                 f"{c['known_queries']} queries; 95% CI)", fontsize=10)
    ax.legend(loc="upper right", fontsize=8)
    fig.text(0.01, 0.01, "DogFaceNet pet dog FACE photos — not validated on street dogs", fontsize=7, color="#555")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(OUT / "chart_top1_top3.png")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(6.5, 4.5), dpi=150)
    for split_name, style in (("validation", "--"), ("test", "-")):
        pts = r["curves"][split_name]
        ax.plot([p["unknown_false_match"] for p in pts], [p["known_correct_accepted"] for p in pts], style,
                color="#205c4f" if split_name == "test" else "#8fb8a8", label=split_name)
    t = r["test"]["pawid_dinov2s_head"]
    ax.scatter([t["fpir"]["value"]], [t["known_top1_correct_accepted"]["value"]], color="#b3261e", zorder=5,
               label=f"chosen threshold {r['selection_on_validation']['threshold']:.3f} (from validation)")
    ax.axvline(0.05, color="#999", lw=0.8, ls=":")
    ax.set_xlabel("False-match rate on unknown dogs")
    ax.set_ylabel("Known dogs: correct top-1 and confident")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_title("Threshold trade-off (PawID)", fontsize=10)
    ax.legend(fontsize=8, loc="lower right")
    fig.text(0.01, 0.01, "DogFaceNet pet dog FACE photos — not validated on street dogs", fontsize=7, color="#555")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(OUT / "chart_threshold_tradeoff.png")
    plt.close(fig)


def error_gallery(assign: list[dict], head: dict[str, np.ndarray], agg: str, tau: float, n: int = 10) -> None:
    """Local only (data/derived, ignored by Git): query | wrong top match | a gallery photo of the true dog."""
    LOCAL.mkdir(parents=True, exist_ok=True)
    gdir = LOCAL / "error-gallery"
    gdir.mkdir(exist_ok=True)
    d = split_data(assign, "test", head)
    labels, s = rv.identity_scores(d.query, d, agg)
    q_rows = [a for a in assign if a["group"] == "test" and a["role"] == "known_query"]
    g_rows = [a for a in assign if a["group"] == "test" and a["role"] == "gallery"]
    wrong = [i for i in np.argsort(-s.max(1)) if labels[int(np.argmax(s[i]))] != d.query_ids[i]][:n]

    def tile(path: Path, caption: str) -> np.ndarray:
        img = cv2.resize(cv2.imread(str(path)), (224, 224))
        cv2.rectangle(img, (0, 0), (224, 22), (255, 255, 255), -1)
        cv2.putText(img, caption, (4, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1, cv2.LINE_AA)
        return img

    lines = []
    for k, i in enumerate(wrong, start=1):
        top = labels[int(np.argmax(s[i]))]
        wrong_img = next(a for a in g_rows if a["identity"] == top)
        true_img = next(a for a in g_rows if a["identity"] == d.query_ids[i])
        score = float(s[i].max())
        row = np.hstack([tile(RAW.parent / q_rows[i]["key"], f"query (dog {d.query_ids[i]})"),
                         tile(RAW.parent / wrong_img["key"], f"top match: dog {top} {score:.2f}"),
                         tile(RAW.parent / true_img["key"], f"true dog {d.query_ids[i]}")])
        out = gdir / f"error_{k:02d}.png"
        cv2.imwrite(str(out), row)
        lines.append(f"<p>#{k} score {score:.3f} ({'above' if score >= tau else 'below'} threshold {tau:.3f})<br>"
                     f"<img src='{out.name}'></p>")
    (gdir / "index.html").write_text("<!doctype html><meta charset=utf-8><title>PawID errors (local only)</title>"
                                     "<h1>Test-set failures — DogFaceNet pet face photos, local only</h1>"
                                     + "".join(lines), encoding="utf-8")
