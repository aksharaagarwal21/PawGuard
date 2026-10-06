# Model cards

## 1. Dog detector — `yolox_s_coco` / `0.1.1rc0-onnx` (active, assistive)

| Field | Value |
|---|---|
| Task | Locate dogs (and people, for a privacy notice) in a validated photo |
| Not for | Identifying individual animals; judging health, behaviour, rabies or vaccination status |
| Artefact | Official YOLOX-S ONNX export, YOLOX GitHub release 0.1.1rc0 (`yolox_s.onnx`, 35,858,002 bytes, sha256 `c5c2d13e…8063`) |
| Licence | Apache-2.0 (YOLOX repository and release artefacts) |
| Training data | COCO 2017 train (by the original authors); not retrained by PawGuard |
| Preprocessing | Letterbox 640×640 top-left, pad 114, BGR, raw 0–255 float32 (verified; see EVALUATION.md) |
| Decoding | YOLOX grid decode (strides 8/16/32), score = objectness × class prob, NMS IoU 0.45, score ≥ 0.35 |
| Runtime | ONNX Runtime CPU in the worker (`media.analyse` job); weights checked against the registry checksum before use |
| Evaluation | COCO val2017 licence-filtered sample: precision 0.93 (0.82–1.00), recall 0.68 (0.49–0.86), 0/25 false dog images; ~150 ms CPU |
| Known gaps | Not evaluated on Indian street/community dogs, night photos or phone-camera field conditions; misses ~1/3 of dogs in COCO scenes |
| Human oversight | Boxes are suggestions; the person picks the subject or "none of these"; nothing is preselected when several dogs are found |
| Failure behaviour | Missing weights, checksum mismatch or errors → analysis state `failed`/`unavailable`; the photo and the manual workflow are unaffected |
| Promotion | Registered via `pawguard-admin models register`; activated with an evaluation report and recorded reason; previous active version retired, not deleted (rollback = re-activate) |

## 2. Identity embedding — `dinov2_small_arcface_head` / `ed25f3a3-resize224-head-v1` (staged; research preview in demo organisations only)

| Field | Value |
|---|---|
| Task | Turn a photo crop of one animal into a 384-D vector so *possible matches* in the same organisation can be shown to a person |
| Not for | Identifying an animal on its own; any decision without a person comparing photos; health, behaviour, rabies or vaccination status; comparing vectors across model versions |
| Status | **Staged, release gate not passed.** Offered only as a labelled research preview in demo organisations (`research_preview`); real organisations see "unavailable" and use manual search. The database refuses to activate it. |
| Backbone | `facebook/dinov2-small` @ `ed25f3a31f01632728cabb09d1542f84ab7b0056`, safetensors (sha256 `ae1e99fc…14be1`, verified against the Hub LFS hash), frozen; Apache-2.0 |
| Head | Linear 768→384 (input: L2(CLS) ‖ L2(mean patch token)), ArcFace objective (s = 30, m = 0.3), L2-normalised output. Trained by PawGuard on DogFaceNet 224 v1 *train* (974 identities, 5,871 images); AdamW 1e-3, wd 0.05, 2-epoch warm-up + cosine, 16 identities × 4 images, seed 20261006, early stopping on validation (best epoch 25 of 33), 17 s on CPU |
| Artefact | ONNX (TorchScript exporter, opset 18), 89,601,565 bytes, sha256 `ec0c294f…`; outputs `cls`, `patch_mean`, `embedding` |
| Preprocessing | RGB, bicubic resize to 224 × 224 (no crop; chosen on validation), /255, ImageNet mean/std; subject box + 10% margin from the person's chosen detection |
| Search | Exact cosine within the organisation's gallery for this model version; identity score = similarity to the mean of that animal's gallery embeddings (centroid rule, chosen on validation); candidates with score ≥ 0.538 (validation FPIR ≤ 0.10), at most 3, each with 2 supporting photos |
| Evaluation (test, once) | DogFaceNet 224 v1 test split, 147 enrolled identities (387 gallery images, 479 queries) + 63 unknown identities (336 queries). Top-1 0.954 [0.929–0.976], top-3 0.988, image mAP 0.922; at the validation threshold: unknown-query false-suggestion rate 0.107 [0.056–0.169], right animal among the shown candidates 0.887 [0.852–0.920], no suggestion for an enrolled animal 0.111. Frozen baseline for comparison: coverage 0.800, FPIR 0.167. |
| Real-data evaluation (6 Oct 2026) | DogFaceNet held-out identities, frozen model, threshold chosen on validation: test top-1 0.943, top-3 0.990; at threshold 0.5125: unknown-dog false matches 0.160 [0.068–0.252] (target 0.05 not met), known dogs correct and confident 0.853. Colour-histogram baseline top-1 0.373, chance 0.004. Pet dog face photos only — **not yet validated on street dogs** (`ml/eval/dogfacenet/results.json`, EVALUATION.md) |
| Parity | ONNX vs PyTorch on all 1,264 validation images: max abs difference 2.9e-5 (CLS), embedding cosine 1.0, identical ranks and metrics |
| Cost | 103 ms median / 134 ms p95 per image on a laptop CPU (2 threads, decode + preprocess + inference); +102 MB resident after loading |
| Known gaps | Only aligned **face crops of pet dogs** with unreviewed labels (≥ 1.7% of identities affected by duplicate photos); no field photos, no community dogs, no full-body crops, no subgroup metadata (coat, site, light, pose); false suggestions rise as the gallery grows (validation: FPIR 0.013 → 0.101 from 36 to 146 enrolled identities at a fixed threshold); a masking probe showed strong reliance on the outer image region (ears, fur and background cannot be separated in face crops) |
| Human oversight | Results are labelled "possible match"; no percentages; the person compares photos and details and chooses same / none / not sure; linking needs a separate confirmation; every decision is recorded with the rank of the chosen animal (correction feedback, shown on the System page) |
| Failure behaviour | Missing/mismatched weights → search `failed`; incomplete gallery index → `stale_index`; small subject → `insufficient_quality`; nothing above threshold → `no_candidate` with a reminder that this does not prove the animal is new. Manual search and registration always remain. |
| Lineage | `app.training_runs` rows for selection, training and test reports; reproduction steps in `ML_PLAN.md` |
