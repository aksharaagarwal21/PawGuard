"""API shapes for pet vaccination tracking and reminders (owners, clinics, public card)."""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from pawguard_api.contracts import AgeBand, Out, Sex, StrictModel

PetStatus = Literal["up_to_date", "due_soon", "overdue", "unverified_record", "no_verified_record"]
Verification = Literal["verified_by_vet", "entered_by_owner_unverified", "submitted_unverified", "needs_correction",
                       "rejected", "superseded"]


class PetStatusOut(Out):
    status: PetStatus
    next_due_on: date | None = None
    next_due_source: str | None = None  # "vet" | "demo_template"
    vaccine: str | None = None
    days_until_due: int | None = None


class PetCreate(StrictModel):
    clinic_org_id: UUID
    name: str = Field(min_length=1, max_length=80)
    species: Literal["dog", "cat"]
    sex: Sex = "unknown"
    date_of_birth: date | None = None
    age_band: AgeBand = "unknown"
    photo_media_id: UUID | None = None


class PetCardOut(Out):
    id: UUID
    reference_code: str
    name: str
    species: str
    sex: str
    date_of_birth: date | None
    age_band: str
    clinic_org_id: UUID
    clinic_name: str
    photo_url: str | None = None
    status: PetStatusOut
    awaiting_verification: int = 0
    is_demo: bool


class TimelineEntryOut(Out):
    event_id: UUID
    vaccine: str
    administered_on: date | None
    clinic_name: str
    given_by: str | None
    verification: Verification
    next_due_on: date | None
    next_due_source: str | None
    certificates: int = 0
    note: str | None = None


class ReminderPreviewOut(Out):
    email_subject: str
    email_body: str
    sms: str


class ReminderOut(Out):
    id: UUID
    pet_id: UUID
    pet_name: str
    clinic_org_id: UUID
    clinic_name: str
    vaccine: str
    due_on: date
    kind: Literal["due_in_14", "due_in_7", "due_in_1", "overdue"]
    days_until_due: int
    state: Literal["pending", "done", "cancelled"]
    snoozed_until: date | None
    preview: ReminderPreviewOut


class PetDetailOut(PetCardOut):
    today: date
    demo_offset_days: int = 0
    timeline: list[TimelineEntryOut] = []
    reminders: list[ReminderOut] = []


class OwnerVaccinationIn(StrictModel):
    product_id: UUID | None = None
    product_text: str | None = Field(default=None, max_length=200)
    administered_on: date
    given_by: str | None = Field(default=None, max_length=200)
    certificate_media_ids: list[UUID] = Field(min_length=1, max_length=5)


class SnoozeIn(StrictModel):
    days: Literal[1, 3]


class DemoClockIn(StrictModel):
    offset_days: int = Field(ge=-60, le=400)


class DemoClockOut(Out):
    offset_days: int
    today: date
    real_today: date


class ClinicOut(Out):
    org_id: UUID
    name: str
    is_member: bool


class ProductOptionOut(Out):
    id: UUID
    name: str
    template_interval_days: int | None
    template_label: str | None


class CardOut(Out):
    token: str
    url_path: str
    qr_svg: str
    created_at: datetime


class PublicVaccinationOut(Out):
    vaccine: str
    administered_on: date | None
    next_due_on: date | None


class PublicCardOut(Out):
    pet_name: str
    species: str
    photo_url: str | None
    clinic_name: str
    status: PetStatusOut
    vaccinations: list[PublicVaccinationOut]
    is_demo: bool
    disclaimer: str = "This card shows recorded vaccinations. It is not a health guarantee."


class ClinicPetRowOut(Out):
    pet_id: UUID
    pet_name: str
    reference_code: str
    status: PetStatusOut
    owner_linked: bool


class AwaitingRowOut(Out):
    event_id: UUID
    pet_id: UUID
    pet_name: str
    vaccine: str
    administered_on: date | None
    submitted_at: datetime | None
    entered_by_owner: bool


class ClinicDashboardOut(Out):
    today: date
    demo_offset_days: int
    demo_clock_available: bool
    pets_total: int
    up_to_date: int
    due_this_week: list[ClinicPetRowOut]
    due_soon: list[ClinicPetRowOut]
    overdue: list[ClinicPetRowOut]
    awaiting_verification: list[AwaitingRowOut]
    no_verified_record: int
    unverified_only: int
    pets: list[ClinicPetRowOut]
    products: list[ProductOptionOut]
    coverage_note: str = "Based on pets registered in this app — not population coverage."


class ClinicVaccinationIn(StrictModel):
    animal_id: UUID
    product_id: UUID
    administered_on: date
    next_due_on: date | None = None
    lot_text: str | None = Field(default=None, max_length=40)
