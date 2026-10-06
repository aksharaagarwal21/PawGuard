"""Trace published identity-model numbers back to saved evidence and the frozen split manifest.

Checks, without re-running any model:
1. the split manifest's sha256 equals the one recorded in the selection, training and test reports and in the
   exported model manifest's lineage;
2. query/gallery counts per split recomputed from the manifest equal the counts in the reports;
3. thresholds in the model manifest equal those chosen on validation (and the release gate is recorded as failed);
4. the headline numbers quoted in docs/EVALUATION.md and docs/MODEL_CARD.md match the test report.
Prints a summary; exits 1 on any mismatch.
"""

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data/manifests/datasets/dogfacenet-224-v1.json"
SEL = ROOT / "docs/evidence/identity-val-selection-dinov2s-v1.json"
TRAIN = ROOT / "docs/evidence/identity-train-runs-v1.json"
TEST = ROOT / "docs/evidence/identity-test-dinov2s-v1.json"
MODEL = ROOT / "data/manifests/models/dinov2_small_arcface_head-v1.json"

problems: list[str] = []


def check(ok: bool, msg: str) -> None:
    print(("  ok   " if ok else "  FAIL ") + msg)
    if not ok:
        problems.append(msg)


def load(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def main() -> int:
    raw = MANIFEST.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    m = json.loads(raw)
    sel, train, test, model = load(SEL), load(TRAIN), load(TEST), load(MODEL)
    print(f"Split manifest {MANIFEST.relative_to(ROOT).as_posix()} sha256 {sha[:16]}…")
    check(sel["dataset"]["sha256"] == sha, "selection report uses this manifest")
    check(train["lineage"]["dataset_manifest_sha256"] == sha, "training report uses this manifest")
    check(test["dataset"]["manifest_sha256"] == sha, "test report uses this manifest")

    print("Counts recomputed from the manifest:")
    for split, report in (("val", sel["dataset"]), ("test", test["dataset"])):
        rows = [s for s in m["samples"] if s["split"] == split]
        roles = Counter(s["role"] for s in rows)
        enrolled = len({s["identity"] for s in rows if s["role"] == "gallery"})
        unknown = len({s["identity"] for s in rows if s["role"] == "unknown_query"})
        print(f"  {split}: {enrolled} enrolled identities, {roles['gallery']} gallery images, {roles['query']} known "
              f"queries, {unknown} unknown identities, {roles['unknown_query']} unknown queries")
        check(report["gallery_images"] == roles["gallery"], f"{split} gallery images match the report")
        check(report["queries"] == roles["query"], f"{split} known-query count matches the report")
        check(report["unknown_queries"] == roles["unknown_query"], f"{split} unknown-query count matches the report")
        check(report["enrolled_identities"] == enrolled, f"{split} enrolled identities match the report")
        check(report["unknown_identities"] == unknown, f"{split} unknown identities match the report")
    train_ids = {s["identity"] for s in m["samples"] if s["split"] == "train"}
    test_ids = {s["identity"] for s in m["samples"] if s["split"] == "test"}
    check(not (train_ids & test_ids), "no identity in both train and test")

    print("Thresholds:")
    base_tau, head_tau = sel["selected"]["tau"], train["best_val_tau"]
    print(f"  frozen baseline τ = {base_tau} (validation FPIR ≤ {sel['selected']['fpir_target']}); "
          f"adapted head τ = {head_tau}; candidate list = {model['thresholds']['candidate_list_size']}")
    check(model["thresholds"]["similarity_tau"] == head_tau, "deployed threshold = threshold chosen on validation")
    check(test["results"]["adapted_head"]["tau_from_val"] == head_tau, "test used the validation threshold (head)")
    check(test["results"]["frozen_baseline"]["tau_from_val"] == base_tau, "test used the validation threshold (baseline)")
    check(model["release_gate"]["passed"] is False, "release gate recorded as NOT passed")

    print("Published numbers (test, once):")
    r = test["results"]["adapted_head"]["metrics"]
    b = test["results"]["frozen_baseline"]["metrics"]
    quoted = {"coverage@3": (r["coverage_at_3"], "0.887"), "FPIR": (r["fpir"], "0.107"), "top-1": (r["top1"], "0.954"),
              "baseline FPIR": (b["fpir"], "0.167"), "baseline coverage@3": (b["coverage_at_3"], "0.800")}
    docs = (ROOT / "docs/EVALUATION.md").read_text(encoding="utf-8") + (ROOT / "docs/MODEL_CARD.md").read_text(
        encoding="utf-8")
    for name, (metric, text) in quoted.items():
        value = metric["value"]
        print(f"  {name}: {value} (95% CI {metric['ci95'][0]}–{metric['ci95'][1]})")
        check(f"{value:.3f}" == text, f"{name} {value:.4f} rounds to the quoted {text}")
        check(text in docs, f"{name} {text} appears in EVALUATION/MODEL_CARD")
    print(("All checks passed." if not problems else f"{len(problems)} problem(s).") + " Limitations: research "
          "benchmark of pet-dog face crops; unreviewed labels; no field data; release gate not met.")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
