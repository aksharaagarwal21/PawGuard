"""Frozen DINOv2 backbone: loading (local safetensors only, no remote code), batched embedding of dataset samples
with an on-disk cache, and the masking transforms used for the background-dependence analysis.

Preprocessing is imported from the worker (`pawguard_worker.vision.embed`) so research numbers describe the code
that would run in production."""

import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
import torch

from pawguard_worker.vision.embed import preprocess

MODEL_REPO = "facebook/dinov2-small"
MODEL_REVISION = "ed25f3a31f01632728cabb09d1542f84ab7b0056"


class Backbone(torch.nn.Module):
    """DINOv2 → (CLS token, mean of patch tokens), both after the final layer norm. No pooling choice here."""

    def __init__(self, model_dir: Path) -> None:
        super().__init__()
        from transformers import Dinov2Model

        self.model = Dinov2Model.from_pretrained(str(model_dir), use_safetensors=True, local_files_only=True,
                                                 trust_remote_code=False)
        self.model.eval()

    def forward(self, pixel_values: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        h = self.model(pixel_values=pixel_values).last_hidden_state
        return h[:, 0], h[:, 1:].mean(dim=1)


def mask_image(bgr: np.ndarray, mode: str) -> np.ndarray:
    """Background-dependence probes. 'center_only' greys out the outer 25% border on each side (keeps the face
    centre); 'border_only' greys out the central 50% box (keeps mostly background/edges). Grey = ImageNet mean."""
    if mode == "none":
        return bgr
    out = bgr.copy()
    h, w = out.shape[:2]
    grey = np.array([104, 116, 124], dtype=np.uint8)  # BGR of the ImageNet mean
    y0, y1, x0, x1 = h // 4, h - h // 4, w // 4, w - w // 4
    if mode == "center_only":
        keep = out[y0:y1, x0:x1].copy()
        out[:] = grey
        out[y0:y1, x0:x1] = keep
    elif mode == "border_only":
        out[y0:y1, x0:x1] = grey
    else:
        raise ValueError(mode)
    return out


def embed_keys(backbone: Backbone, root: Path, keys: list[str], resize_mode: str, mask: str = "none",
               flip: bool = False, batch: int = 32) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Returns (cls [N,384], patch_mean [N,384], failed keys). Failed decodes are reported, never silently dropped."""
    cls_out, pm_out, failed = [], [], []
    buf: list[np.ndarray] = []

    def flush() -> None:
        if not buf:
            return
        with torch.inference_mode():
            c, p = backbone(torch.from_numpy(np.concatenate(buf)))
        cls_out.append(c.numpy())
        pm_out.append(p.numpy())
        buf.clear()

    for k in keys:
        img = cv2.imread(str(root / k), cv2.IMREAD_COLOR)
        if img is None:
            failed.append(k)
            buf.append(np.zeros((1, 3, 224, 224), np.float32))  # keeps row alignment; flagged in `failed`
        else:
            img = mask_image(img, mask)
            if flip:
                img = cv2.flip(img, 1)
            buf.append(preprocess(img, resize_mode))
        if len(buf) == batch:
            flush()
    flush()
    return np.concatenate(cls_out), np.concatenate(pm_out), failed


def cached_embeddings(cache_dir: Path, manifest_sha: str, backbone_factory, root: Path, keys: list[str],
                      resize_mode: str, mask: str = "none", flip: bool = False, tag: str = "") -> dict:
    """Embeddings for `keys`, cached under data/derived keyed by manifest checksum + settings + key list."""
    ident = hashlib.sha256(json.dumps([manifest_sha, MODEL_REVISION, resize_mode, mask, flip, keys]).encode())
    path = cache_dir / f"{tag or 'emb'}-{resize_mode}-{mask}{'-flip' if flip else ''}-{ident.hexdigest()[:12]}.npz"
    if path.exists():
        z = np.load(path, allow_pickle=False)
        return {"keys": list(z["keys"]), "cls": z["cls"], "patch_mean": z["patch_mean"],
                "failed": list(z["failed"]), "cache": path.as_posix()}
    c, p, failed = embed_keys(backbone_factory(), root, keys, resize_mode, mask, flip)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(path, keys=np.array(keys), cls=c, patch_mean=p, failed=np.array(failed, dtype=str))
    return {"keys": keys, "cls": c, "patch_mean": p, "failed": failed, "cache": path.as_posix()}
