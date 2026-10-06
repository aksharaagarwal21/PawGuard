"""Gallery enrolment (``identity.enrol``) and candidate search (``identity.search``).

Exact cosine search within the job's organisation (RLS) and one model version — no approximate index. Candidates
are animals whose aggregated similarity reaches the model's validated threshold; at most ``candidate_list_size``
are kept, each with its two most similar gallery photos. Merged aliases count toward their canonical animal;
archived animals are never suggested. A search never links anything: a person decides.
"""

import hashlib
import json
import time
from functools import lru_cache
from typing import Any
from uuid import UUID

import cv2
import numpy as np
from sqlalchemy import Connection, text

from pawguard_api.integrations.storage import get_storage
from pawguard_worker.analysis import _model_dir
from pawguard_worker.jobs import JobContext, TerminalJobError
from pawguard_worker.vision.embed import EmbedConfig, OnnxEmbedder, crop_subject

WANTED = "task = 'identity_embedding' and (state = 'active' or research_preview or index_wanted)"
STALE_BELOW = 0.9  # share of eligible gallery photos that must be embedded for the model in use


@lru_cache(maxsize=3)
def _embedder(model_id: UUID, path: str, sha: str, pre: str) -> OnnxEmbedder:
    return OnnxEmbedder(_model_dir() / path, EmbedConfig.from_manifest(json.loads(pre)), expected_sha256=sha)


def _model_embedder(model: Any) -> OnnxEmbedder:
    try:
        return _embedder(model.id, model.artifact_path, model.sha256, json.dumps(model.preprocessing))
    except (FileNotFoundError, ValueError) as exc:
        raise TerminalJobError("model_unavailable") from exc


def _image(media: Any) -> tuple[np.ndarray, float]:
    """Display derivative as BGR and the factor from original-image pixels to derivative pixels."""
    key = (media.derivatives or {}).get("display")
    if not key:
        raise TerminalJobError("no_display_derivative")
    bgr = cv2.imdecode(np.frombuffer(get_storage().download(key, max_bytes=20 * 1024 * 1024), np.uint8),
                       cv2.IMREAD_COLOR)
    if bgr is None:
        raise TerminalJobError("decode_failed")
    return bgr, (bgr.shape[1] / media.width) if media.width else 1.0


def _scaled(box: dict | None, f: float) -> dict | None:
    return {k: float(box[k]) * f for k in ("x", "y", "w", "h")} if box else None


def crop_key(box: dict | None) -> str:
    return hashlib.sha256(json.dumps(box, sort_keys=True).encode()).hexdigest()[:16] if box else "full"


def _vec(v: np.ndarray) -> str:
    return "[" + ",".join(f"{x:.7f}" for x in v.tolist()) + "]"


def _queue(c: Connection, org_id: UUID, job_type: str, target_type: str, target_id: UUID) -> None:
    job = c.execute(text("""insert into app.background_jobs (org_id, job_type, target_type, target_id, max_attempts)
                            values (:o, :t, :tt, :id, 2) on conflict do nothing returning id"""),
                    {"o": org_id, "t": job_type, "tt": target_type, "id": target_id}).scalar()
    if job:
        c.execute(text("""insert into app.outbox_events (org_id, event_type, aggregate_type, aggregate_id, payload)
                          values (:o, 'job.queued', 'background_job', :j, cast(:p as jsonb))"""),
                  {"o": org_id, "j": job, "p": json.dumps({"job_type": job_type})})


def queue_enrolment_for_media(ctx: JobContext) -> None:
    """Called once a photo is approved: enrol it wherever it is already a chosen subject of a linked sighting."""
    with ctx.tx() as c:
        if not c.execute(text(f"select exists (select 1 from app.model_versions where {WANTED})")).scalar():  # noqa: S608
            return
        rows = c.execute(text("""select om.id, om.org_id from app.observation_media om
                                   join app.animal_observations o on o.id = om.observation_id
                                  where om.media_id = :m and o.animal_id is not null
                                    and jsonb_typeof(om.subject_bbox) = 'object'"""), {"m": ctx.target_id}).all()
        for r in rows:
            _queue(c, r.org_id, "identity.enrol", "observation_media", r.id)


def enrol(ctx: JobContext) -> dict[str, Any]:
    with ctx.tx() as c:
        row = c.execute(text("""
            select om.id, om.org_id, om.media_id, om.subject_bbox, o.animal_id, a.profile_state,
                   m.state, m.width, m.derivatives
            from app.observation_media om
            join app.animal_observations o on o.id = om.observation_id
            join app.media_assets m on m.id = om.media_id
            left join app.animals a on a.id = o.animal_id
            where om.id = :id"""), {"id": ctx.target_id}).one_or_none()
        models = c.execute(text(f"select * from app.model_versions where {WANTED}")).all()  # noqa: S608
    if row is None or row.animal_id is None or not isinstance(row.subject_bbox, dict):
        return {"skipped": "not a chosen subject of a linked sighting"}
    if row.state != "approved" or row.profile_state == "archived":
        return {"skipped": f"photo {row.state}, animal {row.profile_state}"}
    bgr, f = _image(row)
    done = 0
    for model in models:
        emb = _model_embedder(model)
        try:
            crop = crop_subject(bgr, _scaled(row.subject_bbox, f), emb.config.crop_margin)
        except ValueError as exc:
            raise TerminalJobError("subject_too_small") from exc
        vec, _ = emb.embed(crop)
        with ctx.tx() as c:
            done += c.execute(text("""
                insert into app.animal_embeddings (org_id, animal_id, observation_media_id, media_id, crop_key,
                  model_version_id, embedding)
                values (:o, :a, :om, :m, :k, :mv, cast(:v as extensions.vector))
                on conflict (media_id, crop_key, model_version_id) do nothing"""),
                {"o": row.org_id, "a": row.animal_id, "om": row.id, "m": row.media_id,
                 "k": crop_key(row.subject_bbox), "mv": model.id, "v": _vec(vec)}).rowcount
    return {"embedded": done, "models": len(models)}


def search(ctx: JobContext) -> dict[str, Any]:
    with ctx.tx() as c:
        s = c.execute(text("select * from app.identity_searches where id = :id"), {"id": ctx.target_id}).one_or_none()
        if s is None or s.state != "pending":
            return {"skipped": "not pending"}
        model = c.execute(text("select * from app.model_versions where id = :id"), {"id": s.model_version_id}).one()
        media = c.execute(text("select * from app.media_assets where id = :m"), {"m": s.media_id}).one()
    emb = _model_embedder(model)
    bgr, f = _image(media)
    try:
        crop = crop_subject(bgr, _scaled(s.subject_bbox, f), emb.config.crop_margin)
    except ValueError:
        _complete(ctx, "insufficient_quality", failure_code="subject_too_small")
        return {"state": "insufficient_quality"}
    vec, ms = emb.embed(crop)
    thr = model.thresholds or {}
    tau, k = float(thr.get("similarity_tau", 1.0)), int(thr.get("candidate_list_size", 3))
    agg = thr.get("aggregation", "centroid")
    score_sql = {"centroid": "1 - (avg(g.embedding) <=> cast(:q as extensions.vector))",
                 "max": "max(1 - (g.embedding <=> cast(:q as extensions.vector)))",
                 "mean": "avg(1 - (g.embedding <=> cast(:q as extensions.vector)))"}[agg]
    t0 = time.perf_counter()
    with ctx.tx() as c:
        ranked = c.execute(text(f"""
            with g as (
              select case when a.profile_state = 'merged_alias' then a.merged_into_id else a.id end as animal_id,
                     e.media_id, e.embedding
              from app.animal_embeddings e join app.animals a on a.id = e.animal_id
              where e.model_version_id = :mv and e.state = 'active' and e.media_id <> :self
                and a.profile_state <> 'archived'
            )
            select g.animal_id, {score_sql} as score,
                   (array_agg(g.media_id order by g.embedding <=> cast(:q as extensions.vector)))[1:2] as media_ids
            from g join app.animals c on c.id = g.animal_id and c.profile_state not in ('archived','merged_alias')
            group by g.animal_id order by score desc limit :lim"""),  # noqa: S608 - score_sql is from a fixed map
            {"mv": model.id, "self": media.id, "q": _vec(vec), "lim": k}).all()
        stats = c.execute(text("select * from app.identity_gallery_stats(:mv)"), {"mv": model.id}).one()
    search_ms = (time.perf_counter() - t0) * 1000
    cands = [{"rank": i + 1, "animal_id": str(r.animal_id), "score": round(float(r.score), 5),
              "media_ids": [str(m) for m in r.media_ids or []]}
             for i, r in enumerate(x for x in ranked if float(x.score) >= tau)]
    coverage = (stats.photos / stats.eligible) if stats.eligible else 1.0
    state = "stale_index" if coverage < STALE_BELOW else ("completed" if cands else "no_candidate")
    _complete(ctx, state, candidates=cands, gallery_animals=stats.animals, gallery_embeddings=stats.photos,
              coverage=coverage, inference_ms=ms, search_ms=search_ms)
    return {"state": state, "candidates": len(cands)}


def _complete(ctx: JobContext, state: str, *, failure_code: str | None = None, candidates: list | None = None,
              gallery_animals: int | None = None, gallery_embeddings: int | None = None,
              coverage: float | None = None, inference_ms: float | None = None, search_ms: float | None = None) -> None:
    with ctx.tx() as c:
        c.execute(text("""update app.identity_searches set state = :st, failure_code = :fc,
                            candidates = cast(:c as jsonb), gallery_animals = :ga, gallery_embeddings = :ge,
                            index_coverage = :cov, inference_ms = :ims, search_ms = :sms, completed_at = now()
                          where id = :id and state = 'pending'"""),
                  {"st": state, "fc": failure_code, "c": json.dumps(candidates or []), "ga": gallery_animals,
                   "ge": gallery_embeddings, "cov": round(coverage, 4) if coverage is not None else None,
                   "ims": round(inference_ms, 1) if inference_ms else None,
                   "sms": round(search_ms, 1) if search_ms else None, "id": ctx.target_id})


def search_failed(ctx: JobContext, code: str) -> None:
    _complete(ctx, "failed", failure_code=code)

