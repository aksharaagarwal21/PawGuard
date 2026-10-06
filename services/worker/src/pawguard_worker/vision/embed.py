"""Image embeddings for identity *candidates* (DINOv2 ViT-S/14 family). An embedding never identifies an animal by
itself: search returns possible matches with their photos, and a person decides.

The preprocessing contract is part of a model version (recorded in its manifest) and shared verbatim with the ml/
evaluation code, so evaluation measures exactly what the worker runs. 224 × 224 input = 16 × 16 patches of 14 px.
Vectors from different model versions are different spaces and must never be compared.
"""

import time
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort

from pawguard_worker.vision.yolox import IMAGENET_MEAN, IMAGENET_STD, sha256_file

RESIZE_MODES = ("resize224", "short256_center224")
POOLINGS = ("cls", "patch_mean", "cls_plus_patch_mean", "head")  # head = graph outputs `embedding`
EMBED_DIM = 384


@dataclass(frozen=True)
class EmbedConfig:
    resize_mode: str = "resize224"
    pooling: str = "cls"
    crop_margin: float = 0.1  # extra context around a subject box, as a fraction of its size

    def __post_init__(self) -> None:
        if self.resize_mode not in RESIZE_MODES or self.pooling not in POOLINGS:
            raise ValueError(f"unsupported embedding config {self}")

    @classmethod
    def from_manifest(cls, pre: dict) -> "EmbedConfig":
        return cls(resize_mode=pre["resize_mode"], pooling=pre["pooling"],
                   crop_margin=float(pre.get("crop_margin", 0.1)))


def preprocess(bgr: np.ndarray, resize_mode: str) -> np.ndarray:
    """BGR uint8 image → NCHW float32 (RGB, /255, ImageNet mean/std), bicubic resampling."""
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    if resize_mode == "resize224":
        img = cv2.resize(rgb, (224, 224), interpolation=cv2.INTER_CUBIC)
    elif resize_mode == "short256_center224":
        h, w = rgb.shape[:2]
        s = 256 / min(h, w)
        img = cv2.resize(rgb, (max(224, round(w * s)), max(224, round(h * s))), interpolation=cv2.INTER_CUBIC)
        top, left = (img.shape[0] - 224) // 2, (img.shape[1] - 224) // 2
        img = img[top:top + 224, left:left + 224]
    else:
        raise ValueError(resize_mode)
    x = (img.astype(np.float32) / 255.0 - IMAGENET_MEAN) / IMAGENET_STD
    return np.ascontiguousarray(x.transpose(2, 0, 1)[None])


def pool(cls_tok: np.ndarray, patch_mean: np.ndarray, pooling: str) -> np.ndarray:
    """Combine backbone outputs into one L2-normalised 384-D vector per row."""
    v = {"cls": cls_tok, "patch_mean": patch_mean,
         "cls_plus_patch_mean": _l2(cls_tok) + _l2(patch_mean)}[pooling]
    return _l2(v.astype(np.float32))


def _l2(v: np.ndarray) -> np.ndarray:
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-12)


def crop_subject(bgr: np.ndarray, box: dict | None, margin: float) -> np.ndarray:
    """Crop the chosen subject box (original-image pixels) with a margin; whole image when no box was chosen."""
    if not box:
        return bgr
    h, w = bgr.shape[:2]
    mx, my = box["w"] * margin, box["h"] * margin
    x0, y0 = max(0, int(box["x"] - mx)), max(0, int(box["y"] - my))
    x1, y1 = min(w, int(box["x"] + box["w"] + mx)), min(h, int(box["y"] + box["h"] + my))
    if x1 - x0 < 16 or y1 - y0 < 16:
        raise ValueError("subject box too small to embed")
    return bgr[y0:y1, x0:x1]


class OnnxEmbedder:
    """Runs an exported backbone whose outputs are ``cls`` and ``patch_mean`` (both [N, 384], post-layernorm) and,
    for adapted models (pooling ``head``), ``embedding`` — the trained projection's L2-normalised output."""

    def __init__(self, model_path: Path, config: EmbedConfig, expected_sha256: str | None = None,
                 threads: int = 2) -> None:
        if not model_path.is_file():
            raise FileNotFoundError(f"embedding weights not found at {model_path}")
        if expected_sha256 and sha256_file(model_path) != expected_sha256:
            raise ValueError("embedding weights checksum mismatch")
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = threads
        self.session = ort.InferenceSession(str(model_path), sess_options=opts, providers=["CPUExecutionProvider"])
        self.input_name = self.session.get_inputs()[0].name
        self.config = config

    def raw(self, batch: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        cls_tok, patch_mean = self.session.run(["cls", "patch_mean"], {self.input_name: batch})
        return cls_tok, patch_mean

    def embed(self, bgr: np.ndarray) -> tuple[np.ndarray, float]:
        """One image → (L2-normalised 384-D float32 vector, inference milliseconds)."""
        x = preprocess(bgr, self.config.resize_mode)
        t0 = time.perf_counter()
        if self.config.pooling == "head":
            (e,) = self.session.run(["embedding"], {self.input_name: x})
            ms = (time.perf_counter() - t0) * 1000
            return _l2(e.astype(np.float32))[0], ms
        c, p = self.raw(x)
        ms = (time.perf_counter() - t0) * 1000
        return pool(c, p, self.config.pooling)[0], ms
