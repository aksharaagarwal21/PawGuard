"""Building blocks shared by domain commands.

A command runs inside one ``ctx.tx()`` transaction and must:
1. check the capability and record scope,
2. validate the state transition (and the caller's expected ``row_version`` for updates),
3. mutate,
4. write an audit event and (if anything downstream reacts) an outbox event,
all before commit. Nothing here commits; the transaction boundary belongs to the router.
"""

import base64
import hashlib
import json
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from pawguard_api.deps import OrgContext
from pawguard_api.domain import audit
from pawguard_api.errors import ApiError, Conflict, FieldError, Unprocessable
from pawguard_api.models import BackgroundJob, OutboxEvent


def record_audit(db: Session, ctx: OrgContext, action: str, target_type: str, target_id: UUID,
                 summary: dict[str, Any] | None = None, reason: str | None = None) -> None:
    audit.record(db, action=action, org_id=ctx.org_id, actor_user_id=ctx.user_id, target_type=target_type,
                 target_id=target_id, request_id=ctx.request_id, reason=reason, summary=summary)


def emit(db: Session, ctx: OrgContext, event_type: str, aggregate_type: str, aggregate_id: UUID,
         payload: dict[str, Any] | None = None) -> None:
    """Outbox event in the same transaction as the change. Payload holds identifiers only."""
    db.add(OutboxEvent(org_id=ctx.org_id, event_type=event_type, aggregate_type=aggregate_type,
                       aggregate_id=aggregate_id, payload={k: str(v) for k, v in (payload or {}).items()}))


def enqueue_job(db: Session, ctx: OrgContext, job_type: str, target_type: str, target_id: UUID,
                max_attempts: int = 3) -> UUID:
    """Create (or reuse) the live job for a target and announce it through the outbox."""
    existing = db.execute(text("select id from app.background_jobs where job_type = :t and target_id = :id "
                               "and state in ('queued','processing')"), {"t": job_type, "id": target_id}).scalar()
    if existing:
        return existing
    job = BackgroundJob(org_id=ctx.org_id, job_type=job_type, target_type=target_type, target_id=target_id,
                        max_attempts=max_attempts, created_by=ctx.user_id)
    db.add(job)
    db.flush()
    emit(db, ctx, "job.queued", "background_job", job.id, {"job_type": job_type})
    return job.id


def expect_version(current: int, expected: int | None, resource: str) -> None:
    if expected is None:
        raise ApiError("Send the row_version you last read so concurrent changes are not lost.",
                       code="row_version_required", status_code=428)
    if current != expected:
        raise Conflict(f"This {resource} was changed by someone else. Reload to see the latest version.",
                       code="stale_row_version", details={"current_row_version": current})


def require_reason(reason: str | None, field: str = "reason") -> str:
    if not reason or len(reason.strip()) < 3:
        raise Unprocessable("A reason is required.", fields=[FieldError(field=field, code="required",
                                                                         message="Explain the reason.")])
    return reason.strip()




# ---- cursor pagination --------------------------------------------------------------------------------------

def encode_cursor(*values: Any) -> str:
    raw = json.dumps([v.isoformat() if isinstance(v, datetime) else str(v) if isinstance(v, UUID) else v
                      for v in values]).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str | None, n: int) -> list[Any] | None:
    if not cursor:
        return None
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        values = json.loads(raw)
    except (ValueError, json.JSONDecodeError) as exc:
        raise Unprocessable("Invalid cursor.", code="invalid_cursor") from exc
    if not isinstance(values, list) or len(values) != n:
        raise Unprocessable("Invalid cursor.", code="invalid_cursor")
    return values


def request_hash(body: Any) -> str:
    return hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()
