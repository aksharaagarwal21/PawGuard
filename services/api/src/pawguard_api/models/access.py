from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import ForeignKey, func, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TEXT
from sqlalchemy.orm import Mapped, mapped_column

from pawguard_api.models.base import Base, Timestamps, Versioned, uuid_pk


class Organisation(Base, Timestamps, Versioned):
    __tablename__ = "organisations"
    id: Mapped[UUID] = uuid_pk()
    name: Mapped[str]
    org_type: Mapped[str]
    region_code: Mapped[str | None]
    contact_email: Mapped[str | None]
    timezone: Mapped[str]
    activation_state: Mapped[str]
    is_demo: Mapped[bool] = mapped_column(server_default=text("false"))
    created_by: Mapped[UUID | None]


class UserProfile(Base, Timestamps, Versioned):
    __tablename__ = "user_profiles"
    user_id: Mapped[UUID] = mapped_column(primary_key=True)
    preferred_name: Mapped[str | None]
    locale: Mapped[str]
    accessibility_prefs: Mapped[dict[str, Any]] = mapped_column(JSONB)
    is_demo: Mapped[bool] = mapped_column(server_default=text("false"))


class Membership(Base, Timestamps, Versioned):
    __tablename__ = "memberships"
    id: Mapped[UUID] = uuid_pk()
    org_id: Mapped[UUID] = mapped_column(ForeignKey("organisations.id"))
    user_id: Mapped[UUID]
    role: Mapped[str]
    capabilities: Mapped[list[str]] = mapped_column(ARRAY(TEXT))
    status: Mapped[str]
    valid_from: Mapped[datetime] = mapped_column(server_default=func.now())
    valid_until: Mapped[datetime | None]
    approved_by: Mapped[UUID | None]
    approved_at: Mapped[datetime | None]
    revoked_by: Mapped[UUID | None]
    revoked_at: Mapped[datetime | None]
    revocation_reason: Mapped[str | None]
    is_demo: Mapped[bool] = mapped_column(server_default=text("false"))
    created_by: Mapped[UUID | None]


class ProfessionalApproval(Base, Timestamps, Versioned):
    __tablename__ = "professional_approvals"
    id: Mapped[UUID] = uuid_pk()
    org_id: Mapped[UUID]
    membership_id: Mapped[UUID]
    user_id: Mapped[UUID]
    scope: Mapped[str]
    evidence_reference: Mapped[str]
    reviewer_user_id: Mapped[UUID]
    review_state: Mapped[str]
    valid_from: Mapped[datetime] = mapped_column(server_default=func.now())
    valid_until: Mapped[datetime | None]
    decided_at: Mapped[datetime | None]
    decision_reason: Mapped[str | None]
    is_demo: Mapped[bool] = mapped_column(server_default=text("false"))
    created_by: Mapped[UUID | None]


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[UUID] = uuid_pk()
    occurred_at: Mapped[datetime] = mapped_column(server_default=func.now())
    org_id: Mapped[UUID | None]
    actor_user_id: Mapped[UUID | None]
    actor_kind: Mapped[str]
    action: Mapped[str]
    target_type: Mapped[str | None]
    target_id: Mapped[UUID | None]
    request_id: Mapped[str | None]
    reason: Mapped[str | None]
    change_summary: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
