"""Request/response contracts for the Prevention API. Field names and wording follow docs/DATA_DICTIONARY.md;
'unknown' is always an explicit value, never inferred from a missing field."""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Species = Literal["dog", "cat", "other", "unknown"]
Sex = Literal["female", "male", "unknown"]
Sterilisation = Literal["sterilised", "not_sterilised", "unknown"]
AgeBand = Literal["puppy", "young", "adult", "senior", "unknown"]
Ownership = Literal["owned", "community", "unowned", "shelter", "unknown"]
ProfileState = Literal["provisional", "reviewed", "active", "disputed", "merged_alias", "archived"]
LocationMethod = Literal["gps", "map_pick", "area_only", "described", "unknown"]
TimePrecision = Literal["exact", "day", "month", "unknown"]
DatePrecision = Literal["exact_time", "day", "month", "year", "unknown"]
VaccinationState = Literal["draft", "submitted", "verified", "rejected", "needs_correction", "superseded"]
ReviewOutcome = Literal["verified", "rejected", "needs_correction"]
TaskState = Literal["unassigned", "assigned", "in_progress", "completed", "blocked", "cancelled"]
TaskType = Literal["vaccination_round", "survey", "animal_followup", "evidence_correction", "identity_review", "other"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Out(BaseModel):
    """Response model: fields with defaults are always present in responses, so the published schema marks them
    required (generated clients then need no undefined-checks)."""

    model_config = ConfigDict(json_schema_serialization_defaults_required=True)


class LocationIn(StrictModel):
    """Explicit latitude/longitude names avoid axis-order mistakes (PostGIS stores lon, lat)."""

    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    accuracy_m: float | None = Field(default=None, ge=0, le=100000)
    method: LocationMethod = "gps"


class LocationOut(Out):
    lat: float
    lon: float
    accuracy_m: float | None = None
    precision: Literal["exact", "approximate"]


class AreaRef(Out):
    id: UUID
    code: str
    name: str


# ---- animals ---------------------------------------------------------------------------------------------------

class AnimalFields(StrictModel):
    species: Species = "dog"
    nickname: str | None = Field(default=None, max_length=80)
    sex: Sex = "unknown"
    sterilisation_status: Sterilisation = "unknown"
    age_band: AgeBand = "unknown"
    coat_description: str | None = Field(default=None, max_length=300)
    identifying_marks: str | None = Field(default=None, max_length=500)
    breed_note: str | None = Field(default=None, max_length=120)
    ownership_category: Ownership = "unknown"
    home_area_id: UUID | None = None


class BoxIn(StrictModel):
    """Pixel box in the oriented original image (as returned by the analysis endpoint)."""

    x: float = Field(ge=0)
    y: float = Field(ge=0)
    w: float = Field(gt=0)
    h: float = Field(gt=0)


class SubjectIn(StrictModel):
    media_id: UUID
    source: Literal["detector", "none"] = "none"
    box: BoxIn | None = None
    dog_count: int | None = Field(default=None, ge=0, le=100)


class ObservationIn(StrictModel):
    observed_at: datetime | None = None
    observed_on: date | None = None
    time_precision: TimePrecision = "day"
    location: LocationIn | None = None
    area_id: UUID | None = None
    notes: str | None = Field(default=None, max_length=1000, description="Non-diagnostic notes only.")
    media_ids: list[UUID] = Field(default_factory=list, max_length=10)
    subjects: list[SubjectIn] = Field(default_factory=list, max_length=10,
                                      description="Which detected animal each photo is about (optional).")
    quality_override_reason: str | None = Field(default=None, max_length=500,
                                                description="Required when an attached photo has quality warnings.")
    field_task_id: UUID | None = None

    @model_validator(mode="after")
    def _time(self) -> "ObservationIn":
        if self.time_precision == "exact" and self.observed_at is None:
            raise ValueError("observed_at is required when time_precision is 'exact'")
        if self.time_precision in ("day", "month") and self.observed_on is None and self.observed_at is None:
            raise ValueError("observed_on is required for day/month precision")
        return self


class AnimalCreate(AnimalFields):
    first_observation: ObservationIn | None = None
    client_operation_id: UUID | None = None


class AnimalUpdate(StrictModel):
    nickname: str | None = Field(default=None, max_length=80)
    sex: Sex | None = None
    sterilisation_status: Sterilisation | None = None
    age_band: AgeBand | None = None
    coat_description: str | None = Field(default=None, max_length=300)
    identifying_marks: str | None = Field(default=None, max_length=500)
    breed_note: str | None = Field(default=None, max_length=120)
    ownership_category: Ownership | None = None
    home_area_id: UUID | None = None
    row_version: int


class ProfileTransition(StrictModel):
    to_state: Literal["reviewed", "active", "disputed", "archived"]
    reason: str | None = Field(default=None, max_length=1000)
    row_version: int


class VaccinationSummary(Out):
    """Derived at read time. Never a 'vaccinated' boolean (docs/DESIGN_SYSTEM.md, evidence wording)."""

    status: Literal["verified_record", "submitted_only", "no_verified_record"]
    last_verified_on: date | None = None
    last_verified_precision: DatePrecision | None = None
    pending_review_count: int = 0
    next_review_on: date | None = None
    next_review_source: str | None = None


class PhotoRef(Out):
    media_id: UUID
    url: str | None = None  # short-lived signed URL, absent if not yet approved


class AnimalOut(Out):
    id: UUID
    reference_code: str
    species: Species
    nickname: str | None
    sex: Sex
    sterilisation_status: Sterilisation
    age_band: AgeBand
    coat_description: str | None
    identifying_marks: str | None
    breed_note: str | None
    ownership_category: Ownership
    profile_state: ProfileState
    merged_into_reference: str | None = None
    home_area: AreaRef | None = None
    last_observed_at: datetime | None
    vaccination: VaccinationSummary
    photo: PhotoRef | None = None
    open_task_count: int = 0
    is_demo: bool
    created_at: datetime
    row_version: int


class AnimalPage(Out):
    items: list[AnimalOut]
    next_cursor: str | None
    total_matching: int | None = Field(default=None, description="Exact count for this organisation's filter.")


class ObservationOut(Out):
    id: UUID
    animal_id: UUID | None
    reported_animal_reference: str | None
    observer_user_id: UUID
    observer_name: str | None = None
    observed_at: datetime | None
    observed_on: date | None
    time_precision: TimePrecision
    location: LocationOut | None
    location_method: LocationMethod
    area: AreaRef | None
    notes: str | None
    media_ids: list[UUID]
    created_at: datetime


class ObservationCreate(ObservationIn):
    animal_id: UUID | None = None
    reported_animal_reference: str | None = Field(default=None, max_length=40)
    client_operation_id: UUID | None = None


# ---- vaccination -----------------------------------------------------------------------------------------------

class VaccinationCreate(StrictModel):
    animal_id: UUID
    date_precision: DatePrecision
    administered_on: date | None = None
    administered_at: datetime | None = None
    product_id: UUID | None = None
    product_text: str | None = Field(default=None, max_length=200)
    lot_id: UUID | None = None
    lot_text: str | None = Field(default=None, max_length=40)
    administered_by_name: str | None = Field(default=None, max_length=200)
    administered_by_registration: str | None = Field(default=None, max_length=100)
    area_id: UUID | None = None
    location: LocationIn | None = None
    source_type: Literal["field_entry", "certificate_upload", "partner_record"] = "field_entry"
    source_reference: str | None = Field(default=None, max_length=200)
    submitter_note: str | None = Field(default=None, max_length=1000)
    evidence_media_ids: list[UUID] = Field(default_factory=list, max_length=10)
    save_as_draft: bool = False
    client_operation_id: UUID | None = None

    @field_validator("lot_text")
    @classmethod
    def _lot(cls, v: str | None) -> str | None:
        if v is not None and not v.replace("-", "").replace("/", "").replace(".", "").replace(" ", "").isalnum():
            raise ValueError("Lot numbers may contain letters, digits, spaces, '-', '/' and '.' only")
        return v

    @model_validator(mode="after")
    def _date(self) -> "VaccinationCreate":
        if self.date_precision == "unknown":
            if self.administered_on or self.administered_at:
                raise ValueError("Leave the date empty when precision is 'unknown'")
        elif self.date_precision == "exact_time":
            if self.administered_at is None:
                raise ValueError("administered_at is required for 'exact_time'")
        elif self.administered_on is None:
            raise ValueError("administered_on is required for this precision")
        if self.product_id and self.product_text:
            raise ValueError("Give either product_id or product_text, not both")
        if self.lot_id and self.lot_text:
            raise ValueError("Give either lot_id or lot_text, not both")
        return self


class VaccinationAmend(VaccinationCreate):
    row_version: int = Field(description="row_version of the event being corrected")


class ReviewCreate(StrictModel):
    outcome: ReviewOutcome
    reason: str | None = Field(default=None, max_length=2000)
    row_version: int


class ReviewOut(Out):
    id: UUID
    reviewer_user_id: UUID
    reviewer_name: str | None = None
    outcome: ReviewOutcome
    reason: str | None
    created_at: datetime


class EvidenceOut(Out):
    media_id: UUID
    state: str
    purpose: str
    detected_mime: str | None
    url: str | None = None


class VaccinationOut(Out):
    id: UUID
    animal_id: UUID
    animal_reference: str
    original_animal_id: UUID
    date_precision: DatePrecision
    administered_on: date | None
    administered_at: datetime | None
    product_id: UUID | None
    product_name: str | None
    product_text: str | None
    lot_id: UUID | None
    lot_number: str | None
    lot_text: str | None
    lot_expiry_date: date | None = None
    administered_by_name: str | None
    administered_by_registration: str | None
    area: AreaRef | None
    source_type: str
    source_reference: str | None
    submitter_note: str | None
    state: VaccinationState
    has_conflict: bool
    conflicts: list[str] = []
    supersedes_event_id: UUID | None
    superseded_by_event_id: UUID | None
    next_review_on: date | None
    next_review_source: str | None
    submitted_by: UUID | None
    submitted_by_name: str | None = None
    submitted_at: datetime | None
    verified_by: UUID | None
    verified_at: datetime | None
    evidence: list[EvidenceOut] = []
    reviews: list[ReviewOut] = []
    is_demo: bool
    row_version: int


class VaccinationPage(Out):
    items: list[VaccinationOut]
    next_cursor: str | None


# ---- media -----------------------------------------------------------------------------------------------------

AllowedMime = Literal["image/jpeg", "image/png", "image/webp", "application/pdf"]


class UploadIntentCreate(StrictModel):
    purpose: Literal["animal_photo", "vaccination_evidence", "document"]
    content_type: AllowedMime
    byte_size: int = Field(gt=0, le=15 * 1024 * 1024)
    source_rights: Literal["own_photo", "organisation", "partner", "unknown"] = "organisation"
    consent_scope: Literal["operational", "operational_and_training"] = "operational"


class UploadIntentOut(Out):
    media_id: UUID
    upload_url: str
    method: Literal["PUT"] = "PUT"
    headers: dict[str, str]
    expires_in_seconds: int


class MediaOut(Out):
    id: UUID
    purpose: str
    state: str
    rejection_code: str | None
    detected_mime: str | None
    width: int | None
    height: int | None
    byte_size: int | None
    created_at: datetime
    validated_at: datetime | None
    job_state: str | None = None


class DetectionOut(Out):
    label: Literal["dog", "person"]
    x: float
    y: float
    w: float
    h: float


class QualityOut(Out):
    region: str
    warnings: list[str]
    decision: Literal["ok", "warn", "reject"]
    sharpness: float | None
    brightness: float | None


class MediaAnalysisOut(Out):
    """Advisory analysis of a validated animal photo. Detection only locates animals (and people, for privacy);
    it does not identify individuals and says nothing about health."""

    state: Literal["pending", "completed", "no_animal", "unavailable", "failed", "not_applicable"]
    failure_code: str | None = None
    dogs: list[DetectionOut] = []
    person_count: int = 0
    image_width: int | None = None
    image_height: int | None = None
    quality: list[QualityOut] = []
    model_name: str | None = None
    model_version: str | None = None
    pipeline_version: str | None = None


class SignedUrlOut(Out):
    url: str
    expires_in_seconds: int


# ---- tasks -----------------------------------------------------------------------------------------------------

class TaskCreate(StrictModel):
    task_type: TaskType
    title: str = Field(min_length=1, max_length=200)
    instructions: str | None = Field(default=None, max_length=2000)
    area_id: UUID | None = None
    animal_id: UUID | None = None
    assignee_membership_id: UUID | None = None
    campaign_id: UUID | None = None
    due_on: date | None = None
    planned_start: datetime | None = None
    planned_end: datetime | None = None
    priority: Literal["low", "normal", "high"] = "normal"
    priority_rationale: str | None = Field(default=None, max_length=500)


class TaskTransition(StrictModel):
    action: Literal["assign", "start", "complete", "block", "cancel", "reopen"]
    assignee_membership_id: UUID | None = None
    note: str | None = Field(default=None, max_length=1000)
    row_version: int


class TaskOut(Out):
    id: UUID
    task_type: TaskType
    title: str
    instructions: str | None
    state: TaskState
    priority: str
    priority_rationale: str | None
    area: AreaRef | None
    animal_id: UUID | None
    animal_reference: str | None
    assignee_membership_id: UUID | None
    assignee_name: str | None
    team_id: UUID | None = None
    team_name: str | None = None
    assigned_to_me: bool = False
    campaign_id: UUID | None
    due_on: date | None
    planned_start: datetime | None
    planned_end: datetime | None
    outcome_note: str | None
    blocked_reason: str | None
    cancelled_reason: str | None
    completed_at: datetime | None
    source_event_type: str | None
    source_event_id: UUID | None
    is_demo: bool
    created_at: datetime
    row_version: int


class TaskPage(Out):
    items: list[TaskOut]
    next_cursor: str | None


# ---- merges ----------------------------------------------------------------------------------------------------

class MergePropose(StrictModel):
    source_animal_id: UUID
    target_animal_id: UUID
    reason: str = Field(min_length=3, max_length=1000)


class MergeDecision(StrictModel):
    reason: str = Field(min_length=3, max_length=1000)


class MergePreview(Out):
    source: AnimalOut
    target: AnimalOut
    moves: dict[str, int]
    conflicts: list[str]


class MergeOut(Out):
    id: UUID
    source_animal_id: UUID
    source_reference: str
    target_animal_id: UUID
    target_reference: str
    state: Literal["proposed", "executed", "reversed", "rejected"]
    reason: str
    proposed_by: UUID
    decided_by: UUID | None
    executed_at: datetime | None
    moved: dict[str, int]
    reversed_at: datetime | None
    reversal_reason: str | None
    created_at: datetime
    row_version: int


# ---- assisted identification ------------------------------------------------------------------------------------

IdentityMode = Literal["assisted", "research_preview", "unavailable"]


class IdentityStatusOut(Out):
    """Whether photo-based candidate search can be offered here, and why not when it cannot."""

    mode: IdentityMode
    reason: str | None = None  # no_model | research_only | model_files_missing
    model_label: str | None = None
    release_gate_passed: bool = False
    gallery_animals: int = 0
    gallery_photos: int = 0
    index_coverage: float | None = None


class IdentitySearchIn(StrictModel):
    media_id: UUID
    box: BoxIn | None = None


class CandidateAnimalOut(Out):
    id: UUID
    reference_code: str
    nickname: str | None
    coat_description: str | None
    identifying_marks: str | None
    profile_state: str
    home_area_name: str | None
    last_observed_at: datetime | None


class IdentityCandidateOut(Out):
    """A *possible match*: rank and supporting photos only. Similarity is not a probability and is not shown."""

    rank: int
    animal: CandidateAnimalOut
    photos: list[PhotoRef] = []


class IdentitySearchOut(Out):
    id: UUID
    mode: IdentityMode
    state: Literal["pending", "completed", "no_candidate", "unavailable", "failed", "insufficient_quality",
                   "stale_index", "cancelled"]
    failure_code: str | None = None
    candidates: list[IdentityCandidateOut] = []
    gallery_animals: int | None = None
    index_coverage: float | None = None
    model_label: str | None = None
    decision: str | None = None
    decided_animal_id: UUID | None = None
    created_at: datetime


class IdentityDecisionIn(StrictModel):
    decision: Literal["same_animal", "new_animal", "not_sure"]
    animal_id: UUID | None = None
    reason: str | None = Field(default=None, max_length=500)


class IdentityFeedbackOut(Out):
    """Correction feedback: how often people chose a suggested animal, a different one, or none."""

    searches: int
    decisions: int
    chose_top1: int
    chose_other_suggestion: int
    chose_unsuggested_animal: int
    new_animal: int
    not_sure: int


# ---- offline sync ---------------------------------------------------------------------------------------------

class OfflineTaskPayload(StrictModel):
    action: Literal["start", "complete", "block"]
    note: str | None = Field(default=None, max_length=1000)


class OfflineSightingPayload(StrictModel):
    animal_id: UUID
    observed_on: date
    area_id: UUID | None = None
    notes: str | None = Field(default=None, max_length=1000)
    field_task_id: UUID | None = None


class SyncOperationIn(StrictModel):
    """One change made on a device while offline. Replayed with the *current* permissions of the sender."""

    operation_id: UUID
    operation_type: Literal["task.transition", "observation.create"]
    actor_user_id: UUID
    org_id: UUID
    target_id: UUID | None = None
    base_row_version: int | None = None
    client_created_at: datetime | None = None
    task: OfflineTaskPayload | None = None
    sighting: OfflineSightingPayload | None = None

    @model_validator(mode="after")
    def _payload(self) -> "SyncOperationIn":
        if self.operation_type == "task.transition" and (self.task is None or self.target_id is None
                                                          or self.base_row_version is None):
            raise ValueError("task.transition needs target_id, base_row_version and task")
        if self.operation_type == "observation.create" and self.sighting is None:
            raise ValueError("observation.create needs sighting")
        return self


class SyncBatchIn(StrictModel):
    device_id: str = Field(min_length=8, max_length=64)
    operations: list[SyncOperationIn] = Field(min_length=1, max_length=100)


class SyncResultOut(Out):
    operation_id: UUID
    state: Literal["accepted", "conflict", "rejected"]
    duplicate: bool = False
    result_code: str | None = None
    message: str | None = None
    target_id: UUID | None = None
    server_state: str | None = None
    server_row_version: int | None = None


class SyncBatchOut(Out):
    results: list[SyncResultOut]


# ---- surveys and campaign planning -----------------------------------------------------------------------------

HHMM = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")


class SurveyIn(StrictModel):
    area_id: UUID
    observed_on: date
    dogs_counted: int = Field(ge=0, le=100000)
    marked_count: int = Field(default=0, ge=0)
    puppies_count: int = Field(default=0, ge=0)
    method: Literal["street_count", "household", "other"] = "street_count"
    notes: str | None = Field(default=None, max_length=1000)
    campaign_id: UUID | None = None
    field_task_id: UUID | None = None
    client_operation_id: UUID | None = None

    @model_validator(mode="after")
    def _counts(self) -> "SurveyIn":
        if self.marked_count > self.dogs_counted or self.puppies_count > self.dogs_counted:
            raise ValueError("marked and puppy counts cannot exceed the dogs counted")
        return self


class SurveyOut(Out):
    id: UUID
    area_id: UUID
    observed_on: date
    dogs_counted: int
    marked_count: int
    puppies_count: int
    method: str


class TeamIn(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    shift_start: str = HHMM
    shift_end: str = HHMM
    doses_per_day: int = Field(ge=0, le=10000)
    start_area_id: UUID | None = None


class TeamOut(Out):
    id: UUID
    name: str
    shift_start: str
    shift_end: str
    doses_per_day: int
    start_area_id: UUID | None
    member_count: int
    row_version: int


class CampaignIn(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    activity: Literal["vaccination", "survey"] = "vaccination"
    starts_on: date | None = None
    ends_on: date | None = None
    area_ids: list[UUID] = Field(default_factory=list, max_length=200)


class CampaignAreaIn(StrictModel):
    est_animals: int | None = Field(default=None, ge=0, le=100000)
    service_minutes_per_animal: float = Field(default=4, gt=0, le=120)
    access_start: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    access_end: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    accessible: bool = True
    access_note: str | None = Field(default=None, max_length=300)
    priority: int = Field(default=2, ge=1, le=3)
    row_version: int


class CampaignAreaOut(Out):
    area_id: UUID
    code: str
    name: str
    has_location: bool
    est_animals: int | None
    est_source: str | None
    suggested_animals: int | None
    suggested_source: str | None
    suggested_observed_on: date | None = None  # date of the street count behind a "survey" suggestion
    service_minutes_per_animal: float
    access_start: str | None
    access_end: str | None
    accessible: bool
    access_note: str | None
    priority: int
    row_version: int


class CampaignOut(Out):
    id: UUID
    name: str
    activity: str
    state: str
    starts_on: date | None
    ends_on: date | None
    areas: list[CampaignAreaOut] = []
    row_version: int


class PlanTeamIn(StrictModel):
    team_id: UUID
    shift_start: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    shift_end: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    doses: int | None = Field(default=None, ge=0, le=10000)


class PlanIn(StrictModel):
    plan_date: date
    teams: list[PlanTeamIn] = Field(min_length=1, max_length=50)
    speed_kmh: float = Field(default=15, gt=1, le=80)
    detour_factor: float = Field(default=1.3, ge=1, le=3)
    pinned: dict[UUID, UUID] = Field(default_factory=dict, description="area_id → team_id")
    excluded: list[UUID] = Field(default_factory=list)


class PlanDecisionIn(StrictModel):
    row_version: int
    note: str | None = Field(default=None, max_length=500)


class PlanOut(Out):
    id: UUID
    campaign_id: UUID
    version: int
    plan_date: date
    state: str
    travel_basis: str
    inputs: dict
    result: dict
    failure_code: str | None
    created_at: datetime
    approved_by_name: str | None
    approved_at: datetime | None
    approval_note: str | None
    published_at: datetime | None
    task_count: int
    row_version: int
