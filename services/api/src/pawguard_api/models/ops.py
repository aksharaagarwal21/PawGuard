from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from pawguard_api.models.base import Base, uuid_pk


class OutboxEvent(Base):
    __tablename__ = "outbox_events"
    id: Mapped[UUID] = uuid_pk()
    org_id: Mapped[UUID]
    event_type: Mapped[str]
    aggregate_type: Mapped[str]
    aggregate_id: Mapped[UUID]
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    state: Mapped[str] = mapped_column(server_default=text("'pending'"))
    attempts: Mapped[int] = mapped_column(server_default=text("0"))
    available_at: Mapped[datetime] = mapped_column(server_default=func.now())
    dispatched_at: Mapped[datetime | None]
    last_error: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    id: Mapped[UUID] = uuid_pk()
    org_id: Mapped[UUID]
    actor_user_id: Mapped[UUID]
    route: Mapped[str]
    idempotency_key: Mapped[str]
    request_hash: Mapped[str]
    status_code: Mapped[int | None]
    response_body: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    resource_type: Mapped[str | None]
    resource_id: Mapped[UUID | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(server_default=text("now() + interval '7 days'"))


class BackgroundJob(Base):
    __tablename__ = "background_jobs"
    id: Mapped[UUID] = uuid_pk()
    org_id: Mapped[UUID]
    job_type: Mapped[str]
    target_type: Mapped[str]
    target_id: Mapped[UUID]
    state: Mapped[str] = mapped_column(server_default=text("'queued'"))
    attempts: Mapped[int] = mapped_column(server_default=text("0"))
    max_attempts: Mapped[int] = mapped_column(server_default=text("3"))
    last_error_code: Mapped[str | None]
    result: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    locked_by: Mapped[str | None]
    locked_until: Mapped[datetime | None]
    queued_at: Mapped[datetime] = mapped_column(server_default=func.now())
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]
    created_by: Mapped[UUID | None]
    row_version: Mapped[int] = mapped_column(server_default=text("1"))
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())
