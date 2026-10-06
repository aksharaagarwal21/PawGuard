# ADR 0006 — Vision baselines and how they are served

Date: 2026-10-05 · Status: accepted (subject to Phase 5/7 evidence)

## Decision
- **Detection:** official YOLOX-S COCO ONNX export from the YOLOX GitHub release `0.1.1rc0` (Apache-2.0), run with ONNX Runtime; COCO class 16 (`dog`). Preprocessing (letterbox 640, pad 114, channel order, normalisation) is fixed in a manifest and verified empirically on a rights-cleared sample before activation.
- **Retrieval:** `facebook/dinov2-small` at revision `ed25f3a31f01632728cabb09d1542f84ab7b0056` (Apache-2.0, safetensors), loaded with the native `transformers` implementation (no `trust_remote_code`, no `torch.hub` remote code). CLS token → 384-D → L2-normalised. Exported to ONNX and checked for numerical and retrieval parity before use in the worker.
- Exact cosine search over a tenant-filtered, model-version-filtered set; HNSW only after measured need.
- Human confirmation is always required to link an identity.

## Consequences
The worker image needs only onnxruntime + OpenCV. Changing the backbone means a new `model_versions` row and a full re-embed; vectors from different versions are never compared.
