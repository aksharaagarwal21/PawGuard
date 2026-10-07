"""Read a vaccination certificate photo into a draft (OCR + parsing). Draft only: a person checks it, a vet verifies.

Owners may read only certificates they uploaded themselves; clinic staff see stored drafts beside the image in the
review workbench. Photos are read from the metadata-free "display" copy; PDFs are not read (type the details).
"""

import time
from collections import defaultdict, deque
from datetime import datetime
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import text

from pawguard_api.auth import Principal
from pawguard_api.capabilities import Cap
from pawguard_api.deps import OrgContext
from pawguard_api.domain import petcare
from pawguard_api.domain.certificate_parse import parse
from pawguard_api.errors import ApiError, Forbidden, NotFound
from pawguard_api.integrations import ocr
from pawguard_api.settings import get_settings

PER_HOUR = 20
MAX_BYTES = 8 * 1024 * 1024
_recent: dict[str, deque[float]] = defaultdict(deque)


def status() -> dict[str, Any]:
    return ocr.status(get_settings())


def _rate_limit(user_id: str) -> None:
    now = time.monotonic()
    q = _recent[user_id]
    while q and now - q[0] > 3600:
        q.popleft()
    if len(q) >= PER_HOUR:
        raise ApiError("You've read many certificates this hour. Try again later.", code="rate_limited",
                       status_code=429)
    q.append(now)


def _draft_out(row: Any) -> dict[str, Any]:
    return {"media_id": row.media_id, "engine": row.engine, "languages": list(row.languages or []),
            "administered_on": row.administered_on, "next_due_on": row.next_due_on, "product_id": row.product_id,
            "product_text": row.product_text, "lot_text": row.lot_text, "confidence": row.confidence,
            "warnings": list(row.warnings or [])}


def read_own(p: Principal, media_id: UUID, request_id: str | None = None) -> dict[str, Any]:
    """Owner: read a certificate they uploaded (in any clinic they belong to) and return the draft."""
    s = get_settings()
    for ctx in petcare.owner_contexts(p, request_id):
        with ctx.tx() as db:
            media = db.execute(text("""select id, uploader_user_id, purpose, state, detected_mime, derivatives
                                       from app.media_assets where id = :m"""), {"m": media_id}).one_or_none()
            if media is None or media.uploader_user_id != ctx.user_id:
                continue
            return _read(db, ctx, media, s)
    raise NotFound("Certificate not found.", code="media_not_found")


def _read(db: Any, ctx: OrgContext, media: Any, s: Any) -> dict[str, Any]:
    if media.purpose != "vaccination_evidence":
        raise ApiError("This file isn't a certificate.", code="not_a_certificate", status_code=422)
    if media.state != "approved":
        raise ApiError("The file is still being checked — try again in a few seconds.", code="media_not_ready",
                       status_code=409)
    from pawguard_api.domain.evidence_check import page_image  # photo display copy, or page 1 of a PDF

    _rate_limit(str(ctx.user_id))
    image = page_image(media)
    if not image:
        raise ApiError("This file can't be read.", code="no_display_copy", status_code=422)
    return draft_from_image(db, ctx, media.id, image, s)


def draft_from_image(db: Any, ctx: OrgContext, media_id: Any, image: bytes, s: Any) -> dict[str, Any]:
    """Read one certificate image (a photo, or a PDF page rendered by the caller) into a stored draft."""
    demo = bool(db.execute(text("select is_demo from app.organisations where id = :o"), {"o": ctx.org_id}).scalar())
    try:
        result = ocr.extract(s, image, demo_org=demo)
    except ocr.OcrUnavailable as err:
        raise ApiError(err.detail, code=err.code, status_code=503 if err.code != "gemini_demo_only" else 409) from err
    products = [(r.id, r.name) for r in db.execute(text("select id, name from app.vaccine_products where active"))]
    today = datetime.now(ZoneInfo(ctx.timezone)).date()
    draft = parse(result.text, products, today)
    warnings = list(draft.warnings)
    if result.confidence is not None and result.confidence < 0.6:
        warnings.append("The text was hard to read — check every field.")
    row = db.execute(text("""
        insert into app.certificate_drafts (media_id, org_id, engine, languages, administered_on, next_due_on,
          product_id, product_text, lot_text, confidence, warnings, created_by)
        values (:m, :o, :e, :l, :a, :n, :pid, :pt, :lot, :c, :w, :u)
        on conflict (media_id) do update set engine = excluded.engine, languages = excluded.languages,
          administered_on = excluded.administered_on, next_due_on = excluded.next_due_on,
          product_id = excluded.product_id, product_text = excluded.product_text, lot_text = excluded.lot_text,
          confidence = excluded.confidence, warnings = excluded.warnings, created_at = now()
        returning *"""),
        {"m": media_id, "o": ctx.org_id, "e": result.engine, "l": list(result.languages),
         "a": draft.administered_on, "n": draft.next_due_on, "pid": draft.product_id,
         "pt": draft.product_name or draft.vaccine_keyword, "lot": draft.lot_text, "c": result.confidence,
         "u": ctx.user_id, "w": warnings}).one()
    return _draft_out(row)


def drafts_for_event(db: Any, ctx: OrgContext, event_id: UUID) -> list[dict[str, Any]]:
    """Clinic staff: drafts for the certificates attached to a vaccination record."""
    if not (ctx.can(Cap.ANIMAL_READ) or ctx.can(Cap.VACCINATION_REVIEW)):
        raise Forbidden("Clinic staff only.", code="staff_only")
    rows = db.execute(text("""select d.* from app.certificate_drafts d
                              join app.vaccination_evidence v on v.media_id = d.media_id
                              where v.event_id = :e order by d.created_at"""), {"e": event_id}).all()
    return [_draft_out(r) for r in rows]
