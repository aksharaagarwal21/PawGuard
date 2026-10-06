"""Detector verification and evaluation on the licence-filtered COCO sample (production inference code).

1. verify-preprocessing: on the *verification* subset only, compare the artefact under both preprocessing
   conventions (raw pixels vs legacy ImageNet normalisation); the one that reproduces the published behaviour
   (clearly higher recall at IoU 0.5) is recorded in the model manifest.
2. evaluate: on the *evaluation* subset (untouched by step 1), report dog precision/recall/F1 at IoU 0.5 with
   bootstrap 95% intervals by image, false-positive images among dog-free negatives, latency, and quality-warning
   rates split by subject darkness (to check the quality rules do not systematically penalise dark coats).
"""

import json
import random
import statistics
from pathlib import Path

import cv2
import numpy as np

from pawguard_worker.vision import quality
from pawguard_worker.vision.yolox import YoloxConfig, YoloxDetector


def iou(a: list[float], b: list[float]) -> float:
    ax1, ay1, ax2, ay2 = a[0], a[1], a[0] + a[2], a[1] + a[3]
    bx1, by1, bx2, by2 = b[0], b[1], b[0] + b[2], b[1] + b[3]
    iw, ih = max(0.0, min(ax2, bx2) - max(ax1, bx1)), max(0.0, min(ay2, by2) - max(ay1, by1))
    inter = iw * ih
    union = a[2] * a[3] + b[2] * b[3] - inter
    return inter / union if union > 0 else 0.0


def match(preds: list[list[float]], gts: list[list[float]], thr: float = 0.5) -> tuple[int, int, int]:
    """Greedy one-to-one matching by IoU (preds already sorted by score). Returns tp, fp, fn."""
    used, tp = set(), 0
    for p in preds:
        best, best_j = 0.0, -1
        for j, g in enumerate(gts):
            if j not in used and (v := iou(p, g)) > best:
                best, best_j = v, j
        if best >= thr:
            used.add(best_j)
            tp += 1
    return tp, len(preds) - tp, len(gts) - tp


def _run(detector: YoloxDetector, entries: list[dict], img_dir: Path) -> list[dict]:
    rows = []
    for e in entries:
        bgr = cv2.imread(str(img_dir / e["file_name"]), cv2.IMREAD_COLOR)
        dets, ms = detector.detect(bgr)
        dogs = [[d.x, d.y, d.w, d.h] for d in dets if d.label == "dog"]
        tp, fp, fn = match(dogs, e["dog_boxes_xywh"])
        q_subject = None
        if e["dog_boxes_xywh"]:
            biggest = max(e["dog_boxes_xywh"], key=lambda b: b[2] * b[3])
            q_subject = quality.measure(bgr, tuple(biggest))  # type: ignore[arg-type]
        rows.append({"image_id": e["image_id"], "kind": e["kind"], "tp": tp, "fp": fp, "fn": fn, "ms": ms,
                     "pred_dogs": len(dogs), "gt_dogs": len(e["dog_boxes_xywh"]),
                     "persons": sum(1 for d in dets if d.label == "person"),
                     "subject_brightness": q_subject.brightness if q_subject else None,
                     "subject_warnings": q_subject.warnings if q_subject else None})
    return rows


def _prf(rows: list[dict]) -> dict:
    tp, fp, fn = (sum(r[k] for r in rows) for k in ("tp", "fp", "fn"))
    p = tp / (tp + fp) if tp + fp else float("nan")
    r = tp / (tp + fn) if tp + fn else float("nan")
    f = 2 * p * r / (p + r) if p + r else float("nan")
    return {"tp": tp, "fp": fp, "fn": fn, "precision": p, "recall": r, "f1": f}


def _bootstrap(rows: list[dict], n: int = 2000, seed: int = 7) -> dict:
    rng = random.Random(seed)
    stats = {"precision": [], "recall": [], "f1": []}
    for _ in range(n):
        sample = [rows[rng.randrange(len(rows))] for _ in rows]
        m = _prf(sample)
        for k in stats:
            if not np.isnan(m[k]):
                stats[k].append(m[k])
    return {k: [round(float(np.percentile(v, 2.5)), 3), round(float(np.percentile(v, 97.5)), 3)]
            for k, v in stats.items() if v}


def verify_preprocessing(model: Path, manifest: Path, img_dir: Path) -> dict:
    m = json.loads(manifest.read_text(encoding="utf-8"))
    verify = [e for e in m["images"] if e["split"] == "verification"]
    out = {}
    for legacy in (False, True):
        det = YoloxDetector(model, YoloxConfig(legacy_normalization=legacy))
        res = _prf(_run(det, verify, img_dir))
        out["legacy_normalization" if legacy else "raw_pixels"] = {k: (round(v, 3) if isinstance(v, float) else v)
                                                                   for k, v in res.items()}
    out["n_images"] = len(verify)
    return out


def evaluate(model: Path, manifest: Path, img_dir: Path, legacy: bool, report: Path) -> dict:
    m = json.loads(manifest.read_text(encoding="utf-8"))
    entries = [e for e in m["images"] if e["split"] == "evaluation"]
    det = YoloxDetector(model, YoloxConfig(legacy_normalization=legacy))
    _run(det, entries[:2], img_dir)  # warm-up (excluded from timing)
    rows = _run(det, entries, img_dir)
    pos = [r for r in rows if r["kind"] == "positive"]
    neg = [r for r in rows if r["kind"] == "negative"]
    overall = _prf(pos)
    lat = [r["ms"] for r in rows]
    bright = sorted(r["subject_brightness"] for r in pos if r["subject_brightness"] is not None)
    t1, t2 = (bright[len(bright) // 3], bright[2 * len(bright) // 3]) if len(bright) >= 3 else (0, 0)
    tertiles = {}
    for name, lo, hi in (("darkest_third", -1, t1), ("middle_third", t1, t2), ("brightest_third", t2, 999)):
        group = [r for r in pos if r["subject_brightness"] is not None and lo < r["subject_brightness"] <= hi]
        if group:
            tertiles[name] = {
                "images": len(group),
                "possibly_blurry_rate": round(sum("possibly_blurry" in r["subject_warnings"] for r in group) / len(group), 3),
                "very_dark_rate": round(sum("very_dark" in r["subject_warnings"] for r in group) / len(group), 3),
                "recall": round(_prf(group)["recall"], 3)}
    result = {
        "model": model.name, "preprocessing": "legacy_normalization" if legacy else "raw_pixels",
        "score_threshold": det.config.score_threshold, "nms_iou": det.config.nms_iou, "iou_match": 0.5,
        "dataset": {"name": m["name"], "version": m["version"], "positives": len(pos), "negatives": len(neg),
                    "gt_dog_boxes": sum(r["gt_dogs"] for r in pos)},
        "dog_detection": {k: (round(v, 3) if isinstance(v, float) else v) for k, v in overall.items()},
        "dog_detection_95ci_by_image_bootstrap": _bootstrap(pos),
        "negatives_with_any_dog_prediction": sum(1 for r in neg if r["pred_dogs"] > 0),
        "multi_dog_images": sum(1 for r in pos if r["gt_dogs"] > 1),
        "latency_ms": {"median": round(statistics.median(lat), 1), "p90": round(float(np.percentile(lat, 90)), 1),
                       "hardware": "CPU (Intel i7-1255U, onnxruntime CPUExecutionProvider, 2 threads)"},
        "quality_by_subject_brightness": tertiles,
        "per_image": rows,
    }
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(result, indent=2, default=float) + "\n", encoding="utf-8", newline="\n")
    return {k: v for k, v in result.items() if k != "per_image"}
