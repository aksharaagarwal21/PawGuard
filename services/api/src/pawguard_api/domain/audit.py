"""Audit trail helper. Audit rows are written in the same transaction as the change they describe.

``change_summary`` must stay redacted: field *names* and state transitions, never free-text notes, contact
details, coordinates or evidence content.

Rows are inserted without ``RETURNING``: most writers may not *read* the audit log (RLS select policy requires
``audit.read``), and PostgreSQL applies select policies to rows returned by an INSERT.
"""

from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import insert
from sqlalchemy.orm import Session

from pawguard_api.models import AuditEvent


def record(db: Session, *, action: str, org_id: UUID | None, actor_user_id: UUID | None,
           actor_kind: str = "user", target_type: str | None = None, target_id: UUID | None = None,
           request_id: str | None = None, reason: str | None = None,
           summary: dict[str, Any] | None = None) -> None:
    db.execute(insert(AuditEvent).values(
        id=uuid4(), org_id=org_id, actor_user_id=actor_user_id, actor_kind=actor_kind, action=action,
        target_type=target_type, target_id=target_id, request_id=request_id, reason=reason,
        change_summary=summary or {}))
