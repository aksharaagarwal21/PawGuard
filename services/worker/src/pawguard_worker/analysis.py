"""Photo analysis job (``media.analyse``): OpenCV quality measurements + dog detection with the active model.

Advisory only. The photo is already approved by validation; analysis never changes that, and if the detector is
missing or fails the person simply continues without automatic boxes. Coordinates are stored in the oriented
original image's pixel space (detection runs on the display derivative and is scaled back).
"""

import json
from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import UUID

import cv2
import numpy as np
from sqlalchemy import text

from pawguard_api.integrations.storage import get_storage
from pawguard_api.settings import get_settings
from pawguard_worker.jobs import JobContext, TerminalJobError
from pawguard_worker.vision import quality
from pawguard_worker.vision.yolox import YoloxConfig, YoloxDetector

PIPELINE_VERSION = "analyse-1"
REPO = Path(__file__).resolve().parents[4]


def _model_dir() -> Path:
    d = Path(get_settings().model_dir)
    return d if d.is_absolute() else REPO / d


@lru_cache(maxsize=2)
def _detector(model_id: UUID, path: str, sha: str, pre: str, thr: str) -> YoloxDetector:
    return YoloxDetector(_model_dir() / path, YoloxConfig.from_manifest(json.loads(pre), json.loads(thr)),
                         expected_sha256=sha)


def analyse(ctx: JobContext) -> dict[str, Any]:
    with ctx.tx() as c:
        m = c.execute(text("select * from app.media_assets where id = :id"), {"id": ctx.target_id}).one_or_none()
        model = c.execute(text("select * from app.model_versions "
                               "where task = 'dog_detection' and state = 'active'")).one_or_none()
    if m is None or m.state != "approved" or m.purpose != "animal_photo":
        return {"skipped": "not an approved animal photo"}
    key = (m.derivatives or {}).get("display")
    if not key:
        raise TerminalJobError("no_display_derivative")
    data = get_storage().download(key, max_bytes=20 * 1024 * 1024)
    bgr = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if bgr is None:
        raise TerminalJobError("decode_failed")
    scale = (m.width / bgr.shape[1]) if m.width else 1.0
    full_q = quality.measure(bgr)
    dets: list = []
    ms = None
    status = "unavailable"
    if model is not None:
        try:
            det = _detector(model.id, model.artifact_path, model.sha256, json.dumps(model.preprocessing),
                            json.dumps(model.thresholds))
        except (FileNotFoundError, ValueError) as exc:
            raise TerminalJobError("detector_unavailable") from exc
        dets, ms = det.detect(bgr)
        dogs = [d for d in dets if d.label == "dog"]
        status = "completed" if dogs else "no_animal"
    dogs = [d for d in dets if d.label == "dog"]
    subject_q = quality.measure(bgr, (dogs[0].x, dogs[0].y, dogs[0].w, dogs[0].h)) if dogs else None
    with ctx.tx() as c:
        for q, region in ((full_q, "full"), (subject_q, "top_dog")):
            if q is None:
                continue
            c.execute(text("""
                insert into app.image_quality_results (org_id, media_id, region_key, pipeline_version, sharpness,
                  brightness, contrast, width, height, warnings, decision)
                values (:o, :m, :r, :pv, :s, :b, :c, :w, :h, :warn, :d)
                on conflict (media_id, region_key, pipeline_version) do nothing"""),
                {"o": m.org_id, "m": m.id, "r": region, "pv": quality.PIPELINE_VERSION, "s": q.sharpness,
                 "b": q.brightness, "c": q.contrast, "w": round(q.width * scale), "h": round(q.height * scale),
                 "warn": q.warnings, "d": q.decision})
        if model is not None:
            c.execute(text("""
                insert into app.detection_results (org_id, media_id, model_version_id, pipeline_version, status,
                  detections, dog_count, person_count, image_width, image_height, inference_ms)
                values (:o, :m, :mv, :pv, :st, cast(:d as jsonb), :dc, :pc, :w, :h, :ms)
                on conflict (media_id, model_version_id) do nothing"""),
                {"o": m.org_id, "m": m.id, "mv": model.id, "pv": PIPELINE_VERSION, "st": status,
                 "d": json.dumps([d.as_dict(scale) for d in dets]), "dc": len(dogs),
                 "pc": sum(1 for d in dets if d.label == "person"), "w": m.width, "h": m.height,
                 "ms": round(ms, 1) if ms else None})
    return {"status": status, "dogs": len(dogs), "pipeline": PIPELINE_VERSION}


def queue_analysis(ctx: JobContext) -> None:
    """Queue the advisory analysis job for an approved animal photo. Runs inside the (still claimed) validation
    job's tenant context; a duplicate live job is prevented by the unique index."""
    with ctx.tx() as c:
        job = c.execute(text("""
            insert into app.background_jobs (org_id, job_type, target_type, target_id, max_attempts)
            select org_id, 'media.analyse', 'media', id, 2 from app.media_assets
            where id = :m and purpose = 'animal_photo'
            on conflict do nothing returning id, org_id"""), {"m": ctx.target_id}).one_or_none()
        if job:
            c.execute(text("""insert into app.outbox_events (org_id, event_type, aggregate_type, aggregate_id, payload)
                              values (:o, 'job.queued', 'background_job', :j, '{"job_type": "media.analyse"}')"""),
                      {"o": job.org_id, "j": job.id})
