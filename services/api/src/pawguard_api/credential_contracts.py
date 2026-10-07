"""API contracts for signed vaccination certificates (ADR 0010)."""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from pawguard_api.contracts import Out, StrictModel


class VaccinationCorrect(StrictModel):
    """A vet's correction of a verified record (the old record is kept as superseded)."""
    row_version: int
    reason: str = Field(min_length=3, max_length=500)
    administered_on: date | None = None
    product_id: UUID | None = None
    lot_text: str | None = Field(default=None, max_length=40)
    next_due_on: date | None = None


class CertificateOut(Out):
    event_id: UUID
    vaccine: str | None
    administered_on: date | None
    next_due_on: date | None
    next_due_source: str | None
    is_rabies: bool
    credential_id: UUID | None  # null: verified, but no certificate issued yet (ask the clinic)
    qr_text: str | None
    qr_svg: str | None
    issued_at: datetime | None


class PetCertificatesOut(Out):
    featured_event_id: UUID | None  # latest verified rabies vaccination with a certificate
    items: list[CertificateOut]
    unverified_count: int  # owner-entered or awaiting review: never signed


class SignedListOut(Out):
    format: Literal["PG-TL1", "PG-RL1"]
    version: int
    cose: str  # base64 COSE_Sign1 signed by the platform root key


class CredentialPhotoOut(Out):
    photo_url: str | None


class IssuedOut(Out):
    credential_id: UUID


class DemoSampleOut(Out):
    qr_text: str | None
    qr_svg: str | None


class DemoSamplesOut(Out):
    genuine: DemoSampleOut
    altered: DemoSampleOut
    cancelled: DemoSampleOut


class SignedSummaryOut(Out):
    pet_reference: str | None
    pet_name: str | None
    vaccine: str | None
    given_on: str | None
    next_due_on: str | None
    clinic: str | None
    vet: str | None


class EvidenceCheckItemOut(Out):
    kind: Literal["file", "signature", "reading", "date", "vaccine", "batch", "reuse"]
    status: Literal["ok", "warn", "bad", "info", "unavailable"]
    message: str
    certificate: SignedSummaryOut | None = None
    owner_message: str | None = None  # wording safe to show the submitter (names no other pet or record)


class EvidenceFileOut(Out):
    media_id: UUID
    kind: Literal["photo", "pdf"]
    checks: list[EvidenceCheckItemOut]


class EvidenceCheckOut(Out):
    summary: Literal["problems", "check", "partial", "consistent"]
    files: list[EvidenceFileOut]
