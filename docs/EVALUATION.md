# Evaluation

Every number below was produced by a command in this repository on the stated data. Synthetic fixtures are never
used as evidence of real-world performance. Targets are written down *before* results where they exist.

## Success-measure definitions (Prevention)

| Measure | Definition | Denominator | Window | Missingness handling |
|---|---|---|---|---|
| Identity retrieval (top-k) | Share of enrolled-animal queries whose true identity is in the top k candidates | Queries of animals present in the gallery | Per evaluation run | Queries that fail processing are counted as misses and reported separately |
| False suggestion rate | Share of *unknown-animal* queries that produce any candidate above the decision threshold | Queries of animals absent from the gallery | Per run | — |
| Duplicate resolution | Merge proposals decided (executed/rejected) within 14 days | Proposals created | Rolling 90 days | Open proposals reported as open |
| Time to find a record | Median seconds from opening search to opening the correct profile (observed sessions) | Observed search sessions | Pilot | Needs pilot observation; not yet measured |
| Completeness of verified vaccination events | Verified events with product, lot, date ≥ day precision and evidence | Verified events | Rolling 90 days | "Not recorded" fields counted as incomplete |
| Field-task completion | Tasks completed by due date | Tasks due in window (excl. cancelled with reason) | Monthly | Blocked tasks reported separately with reasons |
| Sync reliability | Offline operations accepted without manual intervention | Operations received | Monthly | Conflicts/rejections reported by reason (Phase 8) |
| Staff workload | Reviewer queue age (median, p90) and items per reviewer-day | Submitted events | Weekly | — |

None of these has been measured with real users yet (no pilot).

## Detector (Phase 5) — YOLOX-S COCO ONNX, dog class

**Purpose:** locate dogs in a photo so a person can choose the subject. It never identifies an animal or assesses
health, and its failure never blocks manual entry.

**Data:** `data/manifests/coco-val2017-dog-sample-v1.json` — COCO val2017 images whose per-image licence is CC BY,
CC BY-SA, "No known copyright restrictions" or US Government Work; crowd-annotated dog images excluded; seed
20261006. 44 dog images (59 boxes) + 25 dog-free images. Split: 15 dog images for *verification* (used only to
confirm the artefact's preprocessing convention) and 29 dog images + 25 negatives for *evaluation*.

**Commands:** `cd ml && uv run pawid coco-sample`, `uv run pawid detector-verify`,
`uv run pawid detector-eval --no-legacy` (report: `docs/evidence/detector-eval-yolox_s-coco-v1.json`).

**Preprocessing verification (15 images):** raw 0–255 pixels → 15/19 dogs found (recall 0.789, precision 0.938);
legacy ImageNet normalisation → 0/19. The artefact therefore uses raw pixels; recorded in its manifest.

**Results (evaluation subset; score ≥ 0.35, NMS IoU 0.45, match at IoU ≥ 0.5):**

| Metric | Value | 95% CI (bootstrap by image, 2,000 resamples) |
|---|---|---|
| Precision (dog boxes) | 0.931 (27 TP, 2 FP) | 0.818 – 1.000 |
| Recall (dog boxes) | 0.675 (27 / 40) | 0.486 – 0.857 |
| F1 | 0.783 | 0.625 – 0.912 |
| Dog-free images with any dog prediction | 0 / 25 | — |
| Recall, dogs with min side ≥ 96 px vs smaller | 0.679 (19/28) vs 0.667 (8/12) | small groups |
| Latency (CPU, i7-1255U, 2 threads) | median 150 ms, p90 160 ms | — |

**Quality-rule bias check (subject brightness tertiles, ground-truth dog boxes, 29 images):** "possibly blurry"
warning rate 0.00 (darkest third, n=10), 0.10 (middle, n=10), 0.11 (brightest, n=9); "very dark" 0.00 in all.
On this small sample the rules do not disproportionately flag darker subjects. This is not a calibration — no
labelled quality examples exist yet.

**Limitations:** tiny sample with wide intervals; COCO is mostly pet/urban Flickr photography, not Indian
community-dog field photos; val2017 is the authors' benchmark split; parity between the ONNX export and the
PyTorch checkpoint was not re-checked locally (behaviour was checked on images instead); quality thresholds are
provisional. **Status: active as an assistive step only** (manual subject choice and manual entry always remain).

## DogFaceNet 224 v1 — data preparation and label-quality audit (Phase 6)

Research benchmark only (S05). Prepared with `pawid dataset-prepare` (seed 20261006, transform `ingest-1`); manifest
`data/manifests/datasets/dogfacenet-224-v1.json` (sha256 10a6554b…), registered `frozen` in `app.dataset_versions`.

| Measure | Value |
|---|---|
| Identities / images ingested | 1,393 / 8,363 (all decoded) |
| Byte-identical files | 0 |
| Near-duplicate pairs (64-bit DCT pHash, Hamming ≤ 6) | 119 (58 at ≤ 4; 437 at ≤ 10). Threshold 6 is a conservative setting; pairs at distance 7–10 were not inspected, so some near-duplicates may remain |
| Near-duplicates spanning two asserted identities | 12 groups, 25 images → **excluded** as `label_conflict_pending_adjudication` |
| Other exclusions | 1 identity with a single image |
| Flags kept in the data | 6 greyscale images |
| Train | 974 identities, 5,871 images |
| Validation (open set) | 208 identities: 146 enrolled (gallery 407, query 481) + 62 unknown (376 unknown queries) |
| Test (open set) | 210 identities: 147 enrolled (gallery 387, query 479) + 63 unknown (336 unknown queries) |
| Independent leakage re-check (each identity in one split; each file in one split/role; no pHash ≤ 6 pair between a query and the gallery of the same split, or between train and val/test) | passed, 0 problems |

**Findings.** A visual check of one conflict group (identities 278 and 959) showed the same photograph filed under
two identities, i.e. one dog recorded twice; the other 11 groups await adjudication (`data/annotation/
dogfacenet-224-v1/review.html` + `decisions_template.csv`, imported with `pawid annotate-import`). At least 24 of
1,393 identities (1.7%) are affected by a shared photo. The source author also warns that some folders contain more
than one dog; duplicate search cannot detect that, so the true label-error rate is unknown and is likely higher.
Measured retrieval accuracy on this benchmark will therefore be pulled down by label noise, and some "unknown"
queries may in fact have a twin in the gallery.

**Limitations:** no capture-session or site metadata exists, so near-duplicate groups are the only proxy for
sessions (same-session photos of a dog may still sit on both the gallery and query side); aligned face crops of pet
dogs, so results do not transfer to full-body field photos of community dogs; labels have not been reviewed by
knowledgeable annotators. The pipeline mechanics are covered by `ml/tests/test_datasets.py` on a synthetic fixture.

## Real-data evaluation on DogFaceNet (6 Oct 2026) — frozen model, held-out identities

**What this is:** an evaluation (no training, no tuning on test) of the deployed PawID model
(`dinov2_small_arcface_head` / `ed25f3a3-resize224-head-v1`, DINOv2-S + projection head) on the public DogFaceNet dataset
(Zenodo 12578449, CC BY 4.0). **Caveat: DogFaceNet contains aligned face crops of pet dogs — not full-body photos of
Indian community dogs in the field. There is no capture-session information, so same-session look-alike photos cannot
be fully ruled out, and the sample is small. This is not evidence of street-dog or field accuracy.**

**Data and split** (`ml/eval/dogfacenet/clean_summary.json`, `split_manifest.json`, sha256 `90dd880956fe5fd7…`,
seed 20261007): 1,393 identities / 8,363 images → 0 unreadable, 0 exact duplicates → 25 images excluded as
near-duplicates shared by two identities → 1,333 identities / 8,219 images with ≥ 3 images. Only identities the
deployed head never trained on are eligible (935 training identities excluded): validation group = 90 identities
from the earlier validation identities, test group = 201 identities from the earlier test identities (fewer than the
300 planned because only 201 eligible test identities exist). In each group 75 % known dogs (2 gallery images, the rest
queries; near-duplicates of gallery images dropped as queries — 2 in validation, 5 in test) and 25 % unknown dogs (all
images are queries). Automated leakage check: passed (0 problems). The dog detector is skipped: images are already face
crops.

| Group | Known dogs | Gallery images | Known queries | Unknown dogs | Unknown queries |
|---|---|---|---|---|---|
| Validation | 68 | 136 | 274 | 22 | 133 |
| Test | 151 | 302 | 577 | 50 | 300 |

**Chosen on validation only:** aggregation **centroid** (mean of a dog's gallery embeddings) over max —
validation known-dog correct-and-confident 0.836 vs
0.829; threshold **0.5125**, the lowest giving validation
unknown-dog false matches ≤ 5 % (achieved 0.045).

**Test, once** (95 % CI: identity bootstrap, 1,000 resamples):

| Method | Top-1 | Top-3 | mAP |
|---|---|---|---|
| PawID (DINOv2-S + head) | 0.943 [0.914–0.970] | 0.990 [0.979–0.998] | 0.907 [0.864–0.944] |
| DINOv2-S backbone only (CLS) | 0.917 [0.872–0.959] | 0.974 [0.952–0.991] | 0.867 [0.814–0.912] |
| Colour histogram | 0.373 [0.302–0.452] | 0.490 [0.416–0.573] | 0.367 [0.307–0.438] |
| Random (chance) | 0.004 [0.000–0.009] | 0.017 [0.008–0.028] | 0.025 [0.021–0.029] |

| Open set at threshold 0.5125 (PawID) | Test |
|---|---|
| Unknown dogs wrongly given a confident match | 0.160 [0.068–0.252] (300 queries, 50 dogs) |
| Known dogs: correct top-1 **and** confident | 0.853 [0.782–0.922] (577 queries, 151 dogs) |
| Known dogs: "no confident match" (wrongly rejected) | 0.123 [0.060–0.192] |
| Known dogs: confident but wrong dog | 0.024 [0.007–0.046] |

**Reading:** the model ranks the right pet dog first for 94 % of known-dog face photos, far above a colour histogram
(37 %) and chance (0.3 %), and the trained head adds a little over the backbone (91.7 % top-1). But the threshold chosen
to keep validation false matches at 4.5 % gave **16 % false matches on test** — with only 22 unknown validation dogs the
threshold estimate is unstable. The 5 % target is **not** met on test; the release gate is not met.

**Cost on this laptop (CPU):** 101.8 ms per image (median, decode + preprocessing + ONNX,
single image), 72.6 ms per image batched; exact search 0.005 ms per
query over 302 gallery images.

**Artefacts:** `ml/eval/dogfacenet/results.json` (every metric, CI, count, threshold, model, split hash, seed, commit
`2cee3a6`, command), `chart_top1_top3.png`, `chart_threshold_tradeoff.png`; local-only error gallery
`data/derived/eval/dogfacenet/error-gallery/` (not committed, not in the app).

**Reproduce** (needs `data/raw/dogfacenet/after_4_bis` from Zenodo 12578449 and the model files):
```bash
cd ml
uv run pawid dfn-clean      # → clean_manifest.csv, clean_summary.json
uv run pawid dfn-split      # → split_manifest.json (+ leakage check)
uv run pawid dfn-eval --smoke   # bounded check, 10 + 10 identities
uv run pawid dfn-eval       # → results.json, charts, local error gallery
```

## Identity retrieval (Phase 7) — DINOv2-S on DogFaceNet 224 v1 (research benchmark)

**What was measured.** Open-set *identification* against an enrolled gallery (not pairwise verification). Per
query image: the rank of the true identity among enrolled identities (top-k, MRR, image-level mAP) and, at a
similarity threshold τ with at most 3 candidates shown, whether the right animal is shown (coverage@3), whether
nothing is shown for an enrolled animal (false rejection), and whether anything is shown for an animal that is not
enrolled (FPIR). 95% intervals: identity-clustered bootstrap, 1,000 resamples, gallery fixed. Decision rules were
written into the code before results were computed (`ml/src/pawguard_ml/identity_cmds.py`).

**Selection (validation only; 146 enrolled + 62 unknown identities).** 18 frozen configurations
(`docs/evidence/identity-val-selection-dinov2s-v1.json`). Best: direct 224 × 224 resize, CLS token, centroid
aggregation — coverage@3 0.751 [0.693–0.809] at FPIR 0.101, top-1 0.936. CLS beat mean-patch pooling everywhere;
centroid beat max and mean aggregation (max lets animals with more photos win more often: FPIR 0.117 vs 0.101 at
the same threshold). Gallery size: 1 → all photos per animal raised coverage@3 from 0.52 to 0.75. Enrolled
identities: at a fixed threshold FPIR rose from 0.013 (36 identities) to 0.053 (73) to 0.101 (146) — **thresholds
do not transfer to larger galleries**. Masking: keeping only the outer border still gave top-1 0.80 (centre only:
0.89), so the model uses the image periphery heavily; in aligned face crops that region mixes ears and fur with
background, so this probe cannot separate the two. The margin between the first two candidates separated right
from wrong top-1 well (AUROC 0.97) but on only 9 wrong cases; no margin rule was adopted.

**Adaptation (head only, backbone frozen; `docs/evidence/identity-train-runs-v1.json`).** Four runs selected on
validation: SupCon linear (coverage@3 0.809), SupCon MLP (0.784), **ArcFace linear (0.865)**, SupCon linear + flip
features (0.817). ArcFace gained 0.114 over the frozen baseline (rule: adopt if ≥ 0.02) → adopted. Validation was
used both for early stopping and for choosing among four heads, so its numbers are optimistic; the test split
decides.

**Test (once; 147 enrolled + 63 unknown identities, 0 images failed to process;
`docs/evidence/identity-test-dinov2s-v1.json`).**

| Metric | Frozen baseline (τ 0.748) | ArcFace head (τ 0.538) |
|---|---|---|
| Top-1 / top-3 / top-5 | 0.952 / 0.988 / 0.992 | 0.954 / 0.988 / 0.990 |
| MRR / image mAP | 0.969 / 0.908 | 0.971 / 0.922 |
| FPIR (unknown animal gets a suggestion) | 0.167 [0.095–0.254] | 0.107 [0.056–0.169] |
| Coverage@3 (right animal shown) | 0.800 [0.748–0.850] | 0.887 [0.852–0.920] |
| False rejection (nothing shown, animal enrolled) | 0.190 [0.142–0.238] | 0.111 [0.079–0.145] |

Fine-tuning the head improved open-set behaviour on test as well; closed-set ranking was already near ceiling for
both. Neither model holds FPIR ≤ 0.10 cleanly on test (the baseline clearly fails: its validation threshold did not
transfer). Subgroups: the source has no coat, site, light, pose or occlusion metadata, so none can be reported.
Error examples (identity labels and scores only) are in the test report and a local-only page under
`data/derived/error-gallery/`.

**Engineering measurements.** ONNX vs PyTorch parity on all 1,264 validation images: max abs diff 2.9e-5, cosine
1.0, identical ranks. Single-image latency 103 ms median / 134 ms p95 (laptop CPU, 2 threads, decode included);
+102 MB resident after model load. Exact SQL search on the demo gallery (≤ 9 embeddings): 8–12 ms — not
representative of large galleries (approximate indexing deferred until recall is measured on a real gallery).

**Gate (ML_PLAN, written before results): not met.** No permissioned, session-disjoint field photos of the target
population exist; DogFaceNet face crops of pet dogs are not that population, and test FPIR is 0.107 against the
≤ 0.10 target. Status: **research preview in demo organisations only; unavailable for real organisations.**
