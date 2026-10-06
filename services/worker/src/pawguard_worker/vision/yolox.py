"""YOLOX ONNX inference (detection only — it says where an animal is, never which animal or anything about health).

Pre/post-processing follows the YOLOX ONNXRuntime demo for the official export: letterbox to 640×640 with pad
value 114 (top-left aligned), NCHW float32, optional legacy normalisation (BGR→RGB, /255, ImageNet mean/std) for
pre-0.2.0 exports, grid decoding over strides 8/16/32, score = objectness × class probability, per-class NMS.
Which normalisation the shipped artefact needs is a property of the artefact, recorded in its manifest and verified
empirically (ml/ detector verification), not assumed.
"""

import hashlib
import time
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort

COCO_DOG = 16
COCO_PERSON = 0
IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


@dataclass(frozen=True)
class YoloxConfig:
    input_size: tuple[int, int] = (640, 640)  # (height, width)
    pad_value: int = 114
    legacy_normalization: bool = False
    strides: tuple[int, ...] = (8, 16, 32)
    score_threshold: float = 0.35
    nms_iou: float = 0.45
    classes: dict[int, str] = field(default_factory=lambda: {COCO_DOG: "dog", COCO_PERSON: "person"})

    @classmethod
    def from_manifest(cls, pre: dict, thresholds: dict) -> "YoloxConfig":
        return cls(input_size=tuple(pre.get("input_size", (640, 640))),  # type: ignore[arg-type]
                   pad_value=int(pre.get("pad_value", 114)),
                   legacy_normalization=bool(pre.get("legacy_normalization", False)),
                   score_threshold=float(thresholds.get("score", 0.35)),
                   nms_iou=float(thresholds.get("nms_iou", 0.45)))


@dataclass(frozen=True)
class Detection:
    label: str
    score: float
    x: float  # top-left, in the coordinate space of the image passed to detect()
    y: float
    w: float
    h: float

    def as_dict(self, scale: float = 1.0) -> dict:
        return {"label": self.label, "score": round(self.score, 4), "x": round(self.x * scale, 1),
                "y": round(self.y * scale, 1), "w": round(self.w * scale, 1), "h": round(self.h * scale, 1)}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class YoloxDetector:
    def __init__(self, model_path: Path, config: YoloxConfig, expected_sha256: str | None = None,
                 threads: int = 2) -> None:
        if not model_path.is_file():
            raise FileNotFoundError(f"detector weights not found at {model_path}")
        if expected_sha256 and sha256_file(model_path) != expected_sha256:
            raise ValueError("detector weights checksum mismatch")
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = threads
        self.session = ort.InferenceSession(str(model_path), sess_options=opts, providers=["CPUExecutionProvider"])
        self.input_name = self.session.get_inputs()[0].name
        self.config = config
        self._grids, self._strides = self._make_grids()

    def _make_grids(self) -> tuple[np.ndarray, np.ndarray]:
        h, w = self.config.input_size
        grids, strides = [], []
        for s in self.config.strides:
            hs, ws = h // s, w // s
            xv, yv = np.meshgrid(np.arange(ws), np.arange(hs))
            grid = np.stack((xv, yv), 2).reshape(1, -1, 2)
            grids.append(grid)
            strides.append(np.full((1, grid.shape[1], 1), s))
        return np.concatenate(grids, 1).astype(np.float32), np.concatenate(strides, 1).astype(np.float32)

    def preprocess(self, bgr: np.ndarray) -> tuple[np.ndarray, float]:
        h, w = self.config.input_size
        ratio = min(h / bgr.shape[0], w / bgr.shape[1])
        resized = cv2.resize(bgr, (int(bgr.shape[1] * ratio), int(bgr.shape[0] * ratio)),
                             interpolation=cv2.INTER_LINEAR)
        padded = np.full((h, w, 3), self.config.pad_value, dtype=np.uint8)
        padded[: resized.shape[0], : resized.shape[1]] = resized
        img = padded.astype(np.float32)
        if self.config.legacy_normalization:
            img = (img[:, :, ::-1] / 255.0 - IMAGENET_MEAN) / IMAGENET_STD
        return np.ascontiguousarray(img.transpose(2, 0, 1)[None]).astype(np.float32), ratio

    def detect(self, bgr: np.ndarray) -> tuple[list[Detection], float]:
        """Returns detections (in the input image's pixel coordinates) and inference milliseconds."""
        tensor, ratio = self.preprocess(bgr)
        t0 = time.perf_counter()
        out = self.session.run(None, {self.input_name: tensor})[0][0].copy()
        ms = (time.perf_counter() - t0) * 1000
        out[:, :2] = (out[:, :2] + self._grids[0]) * self._strides[0]
        out[:, 2:4] = np.exp(out[:, 2:4]) * self._strides[0]
        boxes = out[:, :4].copy()
        boxes[:, 0] -= boxes[:, 2] / 2
        boxes[:, 1] -= boxes[:, 3] / 2
        boxes /= ratio
        dets: list[Detection] = []
        for cls_id, label in self.config.classes.items():
            scores = out[:, 4] * out[:, 5 + cls_id]
            keep = scores >= self.config.score_threshold
            if not keep.any():
                continue
            b, sc = boxes[keep], scores[keep]
            idx = cv2.dnn.NMSBoxes(b.tolist(), sc.tolist(), self.config.score_threshold, self.config.nms_iou)
            for i in np.array(idx).flatten():
                x, y, bw, bh = (float(v) for v in b[i])
                x0, y0 = max(0.0, x), max(0.0, y)
                x1, y1 = min(float(bgr.shape[1]), x + bw), min(float(bgr.shape[0]), y + bh)
                if x1 > x0 and y1 > y0:
                    dets.append(Detection(label, float(sc[i]), x0, y0, x1 - x0, y1 - y0))
        dets.sort(key=lambda d: d.score, reverse=True)
        return dets, ms
