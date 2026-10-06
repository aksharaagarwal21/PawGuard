"""Shared response models."""

from uuid import UUID

from pydantic import BaseModel, Field

from pawguard_api.contracts import Out


class MembershipOut(Out):
    membership_id: UUID
    org_id: UUID
    org_name: str
    org_is_demo: bool
    timezone: str
    role: str
    capabilities: list[str]
    professional_scopes: list[str]


class EnvironmentOut(Out):
    env: str
    demo_mode: bool


class ActiveOrgOut(Out):
    user_id: UUID
    org_id: UUID
    org_name: str
    membership_id: UUID
    role: str
    capabilities: list[str]


class MeOut(Out):
    user_id: UUID
    email: str | None
    preferred_name: str | None
    locale: str
    memberships: list[MembershipOut]
    environment: EnvironmentOut
    profile_row_version: int


class MeUpdate(BaseModel):
    preferred_name: str | None = Field(default=None, max_length=120)
    locale: str | None = Field(default=None, pattern="^(en|ta|hi)$")
    row_version: int = Field(description="The profile row_version you last read (optimistic concurrency).")
