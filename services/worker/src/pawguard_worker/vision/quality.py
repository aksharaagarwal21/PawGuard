"""Image quality measurements with OpenCV.

These are *advisory* signals. They never reject a photo: the person can always continue (with a reason) or record
the animal manually. Thresholds are provisional until calibrated against labelled quality examples
(docs/ML_PLAN.md); every result records the pipeline version so recalibration is traceable.

Design choices to avoid penalising dark-coated animals:
- Sharpness is the variance of the Laplacian on the *subject* region resized to a fixed width, divided by the
  region's intensity variance. Raw Laplacian variance scales with contrast², so a low-contrast black coat would
  otherwise look "blurry".
- Darkness and over-exposure are judged on the whole frame (clipped-pixel fractions), not on the subject: a dark
  animal in good light is fine.
"""

from dataclasses import dataclass

import cv2
import numpy as np

PIPELINE_VERSION = "quality-1-provisional"
NORMALISED_WIDTH = 512
THRESHOLDS = {  # provisional, uncalibrated
    "sharpness_ratio_min": 0.035,
    "subject_min_side_px": 96,
    "image_min_side_px": 320,
    "dark_clip_fraction": 0.55,
    "dark_mean": 40.0,
    "bright_clip_fraction": 0.35,
}


@dataclass
class QualityResult:
    region: str
    sharpness: float  # normalised Laplacian ratio
    brightness: float
    contrast: float
    width: int
    height: int
    warnings: list[str]

    @property
    def decision(self) -> str:
        return "warn" if self.warnings else "ok"


def _gray(bgr: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)


def measure(bgr: np.ndarray, box: tuple[float, float, float, float] | None = None) -> QualityResult:
    """box = (x, y, w, h) in bgr's pixel coordinates; None measures the whole frame."""
    full_gray = _gray(bgr)
    warnings: list[str] = []
    if min(bgr.shape[:2]) < THRESHOLDS["image_min_side_px"]:
        warnings.append("low_resolution")
    dark_frac = float((full_gray < 12).mean())
    bright_frac = float((full_gray > 245).mean())
    if dark_frac > THRESHOLDS["dark_clip_fraction"] and float(full_gray.mean()) < THRESHOLDS["dark_mean"]:
        warnings.append("very_dark")
    if bright_frac > THRESHOLDS["bright_clip_fraction"]:
        warnings.append("overexposed")

    if box is not None:
        x, y, w, h = (round(v) for v in box)
        x, y = max(0, x), max(0, y)
        region = bgr[y : y + max(1, h), x : x + max(1, w)]
        region_name = "subject"
        if min(region.shape[:2]) < THRESHOLDS["subject_min_side_px"]:
            warnings.append("subject_small")
    else:
        region, region_name = bgr, "full"
    gray = _gray(region)
    scale = NORMALISED_WIDTH / max(1, gray.shape[1])
    norm = cv2.resize(gray, (NORMALISED_WIDTH, max(1, int(gray.shape[0] * scale))), interpolation=cv2.INTER_AREA)
    lap_var = float(cv2.Laplacian(norm, cv2.CV_64F).var())
    intensity_var = float(norm.var())
    ratio = lap_var / (intensity_var + 1e-6)
    if ratio < THRESHOLDS["sharpness_ratio_min"]:
        warnings.append("possibly_blurry")
    return QualityResult(region=region_name, sharpness=round(ratio, 5), brightness=round(float(gray.mean()), 2),
                         contrast=round(float(gray.std()), 2), width=int(region.shape[1]), height=int(region.shape[0]),
                         warnings=warnings)
