"""API contracts for the 'This pet bit someone' check (bite reports, observation, share links)."""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from pawguard_api.contracts import Out, StrictModel

CheckinState = Literal["normal", "not_eating", "unusual_behaviour", "missing", "died", "other"]
DayStatus = Literal["normal", "change", "no_update", "awaiting"]
PeriodStatus = Literal["active", "completed", "completed_with_gaps", "change_reported"]


class RabiesRecordOut(Out):
    vaccine: str | None
    given_on: date | None
    next_due_on: date | None
    certificate: str | None  # signed QR text (PG1:…) for the in-browser check, if issued


class BitePetOut(Out):
    pet_name: str
    species: str
    clinic_name: str
    clinic_email: str | None
    clinic_phone: str | None
    is_demo: bool
    rabies: RabiesRecordOut | None


class BiteReportIn(StrictModel):
    bite_date: date
    bite_time: str | None = Field(default=None, pattern=r"^([01][0-9]|2[0-3]):[0-5][0-9]$")
    bitten: Literal["person", "animal"]
    area: str | None = Field(default=None, max_length=80)
    note: str | None = Field(default=None, max_length=500)
    contact_email: str | None = Field(default=None, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    consent_updates: bool = False
    consent_share_with_owner: bool = False


class BiteReportCreatedOut(Out):
    reference: str
    tracking_path: str  # private link for the reporter: /bite/<token> (shown once)
    duplicate: bool  # another report of the same pet and day exists; both follow the same observation
    contact_saved: bool


class TimelineDayOut(Out):
    day: int
    date: date
    status: DayStatus
    owner_state: CheckinState | None
    vet_state: CheckinState | None


class BiteObservationOut(Out):
    bite_date: date
    length_days: int
    status: PeriodStatus
    policy_note: str
    current_day: int  # 0 = the day of the bite
    ended: bool
    timeline: list[TimelineDayOut]
    urgent: bool  # any change reported (owner or vet)
    missed_days: int


class DoctorLinkOut(Out):
    id: UUID
    expires_at: datetime
    created_at: datetime
    views: int


class ShareViewOut(Out):
    purpose: Literal["reporter", "doctor"]
    reference: str
    bite_date: date
    bite_time: str | None
    bitten: Literal["person", "animal"]
    pet_name: str
    species: str
    clinic_name: str
    clinic_email: str | None
    clinic_phone: str | None
    is_demo: bool
    expires_at: datetime
    observation: BiteObservationOut
    rabies: RabiesRecordOut | None
    doctor_links: list[DoctorLinkOut] | None  # reporter view only


class NewDoctorLinkOut(Out):
    path: str
    expires_at: datetime


class RevokedOut(Out):
    revoked: int


class OwnerReportOut(Out):
    reference: str
    bite_time: str | None
    bitten: Literal["person", "animal"]
    area: str | None
    status: str
    possible_duplicate: bool
    contact: str | None  # only when the reporter chose to share it


class OwnerCaseOut(Out):
    period_id: UUID
    animal_id: UUID
    pet_name: str
    clinic_name: str
    clinic_email: str | None
    clinic_phone: str | None
    observation: BiteObservationOut
    reports: list[OwnerReportOut]
    disputed: bool
    today_needed: bool


class CheckinIn(StrictModel):
    state: CheckinState
    note: str | None = Field(default=None, max_length=300)


class DisputeIn(StrictModel):
    reason: str = Field(min_length=10, max_length=500)


class ClinicBiteCaseOut(Out):
    period_id: UUID
    pet_name: str
    observation: BiteObservationOut
    reports: int
    possible_duplicate: bool
    disputed: bool
    last_update: date | None
