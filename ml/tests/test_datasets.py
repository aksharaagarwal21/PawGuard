"""Pipeline mechanics on a SYNTHETIC fixture (generated noise images). This verifies the tooling only; it is not
evidence about any model or real dataset."""

from pathlib import Path

import cv2
import numpy as np
import pytest

from pawguard_ml import datasets as ds


def _img(seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    base = cv2.resize(rng.integers(0, 255, (8, 8, 3), dtype=np.uint8), (128, 128), interpolation=cv2.INTER_CUBIC)
    return base


@pytest.fixture
def synthetic_root(tmp_path: Path) -> Path:
    root = tmp_path / "ids"
    for ident in range(12):
        d = root / f"id{ident:02d}"
        d.mkdir(parents=True)
        for k in range(4):
            cv2.imwrite(str(d / f"{k}.jpg"), _img(ident * 100 + k))
    # Near-duplicate inside one identity (slight brightness change of the same picture)
    cv2.imwrite(str(root / "id00" / "dup.jpg"), np.clip(_img(0).astype(int) + 4, 0, 255).astype(np.uint8))
    # The same picture filed under a second identity → label conflict
    cv2.imwrite(str(root / "id01" / "conflict.jpg"), _img(200))  # identical to id02/0.jpg
    # Unreadable file
    (root / "id03" / "broken.jpg").write_bytes(b"not an image")
    return root


def test_pipeline_flags_duplicates_conflicts_and_splits_without_leakage(synthetic_root: Path):
    samples = ds.ingest(synthetic_root, synthetic_root.parent)
    assert any("decode_failed" in s.flags for s in samples)
    dup = ds.duplicate_groups(samples)
    assert dup["exact_duplicate_files"] >= 1
    group = {s.key: s.dup_group for s in samples}
    assert group["ids/id00/dup.jpg"] == group["ids/id00/0.jpg"]
    assert ds.flag_label_conflicts(samples) == 2
    conflicted = [s for s in samples if s.exclusion == "label_conflict_pending_adjudication"]
    assert {s.identity for s in conflicted} == {"id01", "id02"}
    stats = ds.split(samples, seed=1)
    assert stats["train"]["identities"] >= 6
    leak = ds.leakage_checks(samples)
    assert leak["passed"], leak
    # identity-disjoint
    where: dict[str, set[str]] = {}
    for s in samples:
        if s.split != "excluded":
            where.setdefault(s.identity, set()).add(s.split)
    assert all(len(v) == 1 for v in where.values())


def test_leakage_check_catches_injected_problems(synthetic_root: Path):
    samples = ds.ingest(synthetic_root, synthetic_root.parent)
    ds.duplicate_groups(samples)
    ds.flag_label_conflicts(samples)
    ds.split(samples, seed=1)
    train = next(s for s in samples if s.split == "train")
    test_sample = next(s for s in samples if s.split == "test")
    test_sample.identity = train.identity  # identity in two splits
    leak = ds.leakage_checks(samples)
    assert not leak["passed"] and any("identity" in p for p in leak["examples"])


def test_phash_is_stable_and_discriminative():
    a = cv2.cvtColor(_img(1), cv2.COLOR_BGR2GRAY)
    b = cv2.cvtColor(_img(2), cv2.COLOR_BGR2GRAY)
    assert ds.phash(a) == ds.phash(a.copy())
    assert bin(int(ds.phash(a), 16) ^ int(ds.phash(b), 16)).count("1") > ds.PHASH_NEAR_DUP
