"""Idempotency-Key support for retryable creations.

Within the creating transaction: claim ``(org, actor, route, key)``. A concurrent request with the same key
blocks on the unique index until the first commits, then replays its stored response. Reusing a key with a
different request body is rejected. Records expire after 7 days (cleanup job).
"""

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from pawguard_api.deps import OrgContext
from pawguard_api.domain.common import request_hash
from pawguard_api.errors import Unprocessable
from pawguard_api.models import IdempotencyRecord


@dataclass
class Replay:
    status_code: int
    body: dict[str, Any]


def claim(db: Session, ctx: OrgContext, route: str, key: str | None, body: Any) -> Replay | None:
    """Returns a stored response to replay, or None if this request should proceed."""
    if key is None:
        return None
    if not 8 <= len(key) <= 200:
        raise Unprocessable("Idempotency-Key must be 8–200 characters.", code="invalid_idempotency_key")
    h = request_hash(body)
    inserted = db.execute(
        insert(IdempotencyRecord)
        .values(org_id=ctx.org_id, actor_user_id=ctx.user_id, route=route, idempotency_key=key, request_hash=h)
        .on_conflict_do_nothing(index_elements=["org_id", "actor_user_id", "route", "idempotency_key"])
        .returning(IdempotencyRecord.id)
    ).scalar()
    if inserted:
        return None
    rec = db.execute(select(IdempotencyRecord).where(
        IdempotencyRecord.org_id == ctx.org_id, IdempotencyRecord.actor_user_id == ctx.user_id,
        IdempotencyRecord.route == route, IdempotencyRecord.idempotency_key == key)).scalar_one()
    if rec.request_hash != h:
        raise Unprocessable("This Idempotency-Key was already used for a different request.",
                            code="idempotency_key_reused")
    if rec.status_code is None or rec.response_body is None:
        # Previous attempt with this key failed and rolled back its own row — cannot happen in one transaction,
        # but treat defensively as "proceed".
        return None
    return Replay(rec.status_code, rec.response_body)


def store(db: Session, ctx: OrgContext, route: str, key: str | None, status_code: int, body: dict[str, Any],
          resource_type: str, resource_id: UUID) -> None:
    if key is None:
        return
    db.execute(update(IdempotencyRecord).where(
        IdempotencyRecord.org_id == ctx.org_id, IdempotencyRecord.actor_user_id == ctx.user_id,
        IdempotencyRecord.route == route, IdempotencyRecord.idempotency_key == key,
    ).values(status_code=status_code, response_body=body, resource_type=resource_type, resource_id=resource_id))
