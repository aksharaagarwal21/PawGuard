# ML plan

## Pipeline (as built)

permitted upload → quarantine → **validation from bytes** (decode, type, pixel budget, EXIF orientation,
metadata-free derivatives) → **analysis** (OpenCV quality on full frame and top dog region; YOLOX dog detection)
→ person chooses subject or "none" → (Phase 7) crop → embedding → tenant-scoped gallery search → candidates →
**human decision** → audited link. Every step has a typed failure state and none blocks manual entry.

## Components and status

| Component | Status | Evidence |
|---|---|---|
| Media validation (Pillow) | Built, tested | `services/api/tests/test_media.py` (7 tests) |
| Quality measurements (OpenCV) | Built; thresholds **provisional, uncalibrated** | Bias check in EVALUATION.md |
| Dog detection (YOLOX-S ONNX) | Built, evaluated on COCO sample, **active as assistive step** | EVALUATION.md, MODEL_CARD.md |
| Model registry | Built (staged → active → retired, checksum, evaluation report required) | migration 0007, `pawguard-admin models` |
| Dataset tooling (ingest, sha256 + pHash duplicate graph, label-conflict exclusion, identity-disjoint open-set split, leakage checks, manifests, annotation round-trip) | Built, tested on synthetic fixture | `ml/tests/test_datasets.py` (3 tests), migration 0008 |
| DogFaceNet 224 v1 research benchmark | Prepared, frozen, registered; 12 label-conflict groups pending human adjudication | `data/manifests/datasets/dogfacenet-224-v1.json`, EVALUATION.md |
| Partner CSV import (dry run → apply → rollback) | Built, tested | `services/api/tests/test_imports.py`, `tests/e2e/imports.spec.ts` |
| Identity retrieval (DINOv2-S frozen, ONNX) | Built; evaluated on DogFaceNet research benchmark only; **research preview in demo organisations, unavailable elsewhere** | EVALUATION.md, MODEL_CARD.md, ADR 0008 |
| Gallery embeddings, search, decisions, feedback, re-index/rollback | Built, tested | migration 0009, `services/api/tests/test_identity.py`, `tests/e2e/identity.spec.ts` |

## Quality thresholds — calibration plan

Current thresholds (`pawguard_worker/vision/quality.py`) are provisional. Calibration needs ~200+ field photos
labelled "usable for identification / not usable" by two reviewers, stratified by coat colour (dark / mid / light),
device and lighting. Choose thresholds to keep the false-warning rate on usable photos ≤ 10% per coat stratum;
report per-stratum rates. Until then warnings are advisory and a recorded reason allows continuing.

## Partner collection brief (draft — nothing has been requested from anyone)

**Why it is needed.** Every identity result so far can only come from DogFaceNet: aligned face crops of
web-collected pet dogs with unreviewed labels. That cannot show whether assisted matching works for community dogs
photographed in the field. The release gate below can only be evaluated on permissioned photos of the target
population. Until such data exists, assisted identification stays **research only / unavailable** in the product.

**What we would ask a partner for** (an animal-welfare organisation already running an ABC/vaccination programme):

| Item | Minimum | Preferred | Why |
|---|---|---|---|
| Individually verified animals | 50 | 100–150 | Enough enrolled identities for a gallery and unknown queries |
| Encounters per animal | 2 on different days | 3+ across weeks | Session-disjoint gallery vs query (same-session photos inflate results) |
| Photos per encounter | 2 (side + front/three-quarter) | 3–5 incl. any distinctive mark | Viewpoint variation as seen in real use |
| Identity ground truth | Ear notch/tag/collar ID or catch-neuter-release record linked by staff | Plus a second staff confirmation | Labels must not come from appearance alone |
| Metadata per photo | animal id, encounter date, site/area code, photographer role | device model, light (day/dusk) | Session grouping; subgroup reporting (coat colour, site, device) |
| Coat-colour label | dark / mid / light / patterned | — | Required for per-subgroup results |
| Negative examples | 20+ animals photographed once (unknown queries) | 50+ | Measures false-suggestion rate |
| Quality labels (optional) | "usable / not usable for identification", two reviewers, ~200 photos | — | Calibrates the quality thresholds (see above) |

**How photos must be taken.** Only during normal programme work; no approaching worried, injured or
feeding-with-puppies animals; no restraint for photography; no close-up nose shots; people, faces, house
numbers and vehicle plates kept out of frame where possible (people detected later are flagged, not kept in
derivatives). Phone camera at normal distance is the target condition — do not use professional set-ups.

**Rights and agreements required before any transfer.**
1. Written data-sharing agreement with the partner naming PawGuard's purposes: model evaluation and, separately,
   model training (each opt-in); retention period; deletion on request; no onward sharing; no publication of
   identifiable photos without separate consent.
2. Confirmation the partner owns or is licensed to share the photos (staff/volunteer photographers assign or license
   rights to the partner).
3. Location precision agreed (area code or coarse grid only for evaluation; exact points are not needed).
4. A named contact for label questions and an annotation protocol (see `pawid annotate-export`).

**How it would be handled.** Delivered through the import path (raw file stored immutably with checksum), never by
scraping; stored in a separate tenant flagged `research`; frozen into a dataset version with a manifest
(`pawid dataset-prepare` with session ids → session-grouped, identity-disjoint open-set split); leakage checks must
pass; test split locked before any model is tuned on validation; results reported per subgroup with intervals.

**Not in scope:** PetFace (needs an access application the user must authorise; non-commercial terms), social-media
images, any photo whose rights are unclear.

## Reproducing the identity results

All commands run from `ml/` (`uv run pawid …`); outputs are written next to the inputs they describe.

1. `pawid model-fetch` — pinned `facebook/dinov2-small@ed25f3a3…` (safetensors + configs only), checked against the
   Hub's LFS sha256 / git blob ids → `data/manifests/models/dinov2-small-source.json`.
2. `pawid dataset-prepare` (Phase 6) → frozen split manifest (sha256 10a6554b…).
3. `pawid identity-select` — **validation only**: 2 preprocessing × 3 poolings × 3 multi-image aggregations;
   pre-registered rule (max coverage@3 at validation FPIR ≤ 0.10, tie-break MRR); gallery-size, enrolled-count,
   masking and margin analyses → `docs/evidence/identity-val-selection-dinov2s-v1.json`.
4. `pawid identity-train` — head-only adaptation (SupCon linear, SupCon MLP, ArcFace linear, SupCon + flip) on
   frozen features; adopted only if validation coverage@3 improves by ≥ 0.02 → `docs/evidence/identity-train-runs-v1.json`.
5. `pawid identity-test` — **once**, configurations and thresholds fixed from validation; refuses to re-run without
   `--acknowledge-reuse` → `docs/evidence/identity-test-dinov2s-v1.json` (+ local error listing under `data/derived`).
6. `pawid identity-export` — ONNX export, numerical + retrieval parity vs PyTorch on validation, CPU latency and
   memory → `data/manifests/models/dinov2-small-frozen-v1.json`.
7. Operator: `pawguard-admin models register <manifest>`; `pawguard-admin models research-preview <name> <label>
   --reason …` (demo organisations only); `pawguard-admin runs register <evidence json> --kind …`.
   `models activate` refuses identity models whose release gate has not passed.

## Release gate for assisted identification (written before any identity results)

Assisted matching may be offered in a pilot only if, on a frozen, permissioned, session-disjoint test set of the
target population: top-3 retrieval ≥ 0.80 for enrolled animals; unknown-query false-suggestion rate ≤ 0.10 at the
chosen threshold; per-subgroup (coat colour, site) results reported with intervals; licence and data rights clear.
Otherwise the integration is built but the capability stays "research only / unavailable".
