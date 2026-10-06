"""Prevention domain models (schema owned by migration 0003; see docs/DATA_DICTIONARY.md)."""

from datetime import date, datetime
from typing import Any
from uuid import UUID

from geoalchemy2 import Geography, Geometry
from sqlalchemy import func, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TEXT
from sqlalchemy.orm import Mapped, mapped_column

from pawguard_api.models.base import Base, Timestamps, Versioned, uuid_pk

FALSE = text("false")


class _Owned(Timestamps, Versioned):
    """Organisation-owned, mutable, auditable row."""

    org_id: Mapped[UUID]
    is_demo: Mapped[bool] = mapped_column(server_default=FALSE)
    created_by: Mapped[UUID | None]


class Area(Base, _Owned):
    __tablename__ = "areas"
    id: Mapped[UUID] = uuid_pk()
    code: Mapped[str]
    name: Mapped[str]
    kind: Mapped[str] = mapped_column(server_default=text("'ward'"))
    parent_area_id: Mapped[UUID | None]
    boundary: Mapped[Any | None] = mapped_column(Geometry("MULTIPOLYGON", srid=4326, spatial_index=False))
    boundary_source: Mapped[str | None]
    boundary_version: Mapped[str | None]
    effective_from: Mapped[date] = mapped_column(server_default=func.current_date())
    effective_to: Mapped[date | None]


class Team(Base, _Owned):
    __tablename__ = "teams"
    id: Mapped[UUID] = uuid_pk()
    name: Mapped[str]
    skills: Mapped[list[str]] = mapped_column(ARRAY(TEXT), server_default=text("'{}'"))
    access_notes: Mapped[str | None]
    active: Mapped[bool] = mapped_column(server_default=text("true"))


class Animal(Base, _Owned):
    __tablename__ = "animals"
    id: Mapped[UUID] = uuid_pk()
    reference_code: Mapped[str] = mapped_column(server_default=text("app.new_reference_code()"))
    species: Mapped[str] = mapped_column(server_default=text("'dog'"))
    nickname: Mapped[str | None]
    sex: Mapped[str] = mapped_column(server_default=text("'unknown'"))
    sterilisation_status: Mapped[str] = mapped_column(server_default=text("'unknown'"))
    age_band: Mapped[str] = mapped_column(server_default=text("'unknown'"))
    date_of_birth: Mapped[date | None]
    coat_description: Mapped[str | None]
    identifying_marks: Mapped[str | None]
    breed_note: Mapped[str | None]
    ownership_category: Mapped[str] = mapped_column(server_default=text("'unknown'"))
    profile_state: Mapped[str] = mapped_column(server_default=text("'provisional'"))
    merged_into_id: Mapped[UUID | None]
    home_area_id: Mapped[UUID | None]
    last_observed_at: Mapped[datetime | None]
    archived_reason: Mapped[str | None]
    source_type: Mapped[str] = mapped_column(server_default=text("'field_entry'"))
    source_reference: Mapped[str | None]
    client_operation_id: Mapped[UUID | None]


class AnimalCaregiver(Base, _Owned):
    __tablename__ = "animal_caregivers"
    id: Mapped[UUID] = uuid_pk()
    animal_id: Mapped[UUID]
    relationship: Mapped[str]
    contact_name: Mapped[str | None]
    contact_phone: Mapped[str | None]
    contact_notes: Mapped[str | None]
    linked_user_id: Mapped[UUID | None]
    consent_record_id: Mapped[UUID | None]
    valid_from: Mapped[date] = mapped_column(server_default=func.current_date())
    valid_to: Mapped[date | None]


class AnimalObservation(Base, _Owned):
    __tablename__ = "animal_observations"
    id: Mapped[UUID] = uuid_pk()
    animal_id: Mapped[UUID | None]
    reported_animal_reference: Mapped[str | None]
    observer_user_id: Mapped[UUID]
    observed_at: Mapped[datetime | None]
    observed_on: Mapped[date | None]
    time_precision: Mapped[str]
    location: Mapped[Any | None] = mapped_column(Geography("POINT", srid=4326, spatial_index=False))
    location_approx: Mapped[Any | None] = mapped_column(Geography("POINT", srid=4326, spatial_index=False))
    location_accuracy_m: Mapped[float | None]
    location_method: Mapped[str] = mapped_column(server_default=text("'unknown'"))
    area_id: Mapped[UUID | None]
    notes: Mapped[str | None]
    source_type: Mapped[str] = mapped_column(server_default=text("'field_entry'"))
    field_task_id: Mapped[UUID | None]
    client_operation_id: Mapped[UUID | None]


class MediaAsset(Base, _Owned):
    __tablename__ = "media_assets"
    id: Mapped[UUID] = uuid_pk()
    bucket: Mapped[str]
    object_key: Mapped[str]
    purpose: Mapped[str]
    declared_mime: Mapped[str]
    detected_mime: Mapped[str | None]
    declared_bytes: Mapped[int]
    byte_size: Mapped[int | None]
    sha256: Mapped[str | None]
    width: Mapped[int | None]
    height: Mapped[int | None]
    state: Mapped[str] = mapped_column(server_default=text("'pending_upload'"))
    rejection_code: Mapped[str | None]
    source_rights: Mapped[str] = mapped_column(server_default=text("'organisation'"))
    consent_scope: Mapped[str] = mapped_column(server_default=text("'operational'"))
    uploader_user_id: Mapped[UUID]
    derivatives: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    retention_until: Mapped[date | None]
    uploaded_at: Mapped[datetime | None]
    validated_at: Mapped[datetime | None]


class ObservationMedia(Base, _Owned):
    __tablename__ = "observation_media"
    id: Mapped[UUID] = uuid_pk()
    observation_id: Mapped[UUID]
    media_id: Mapped[UUID]
    # SQL NULL, not JSON null, when no box
    subject_bbox: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    subject_count: Mapped[int | None]
    crop_version: Mapped[str | None]
    capture_session_id: Mapped[UUID | None]


class ImageQualityResult(Base, _Owned):
    __tablename__ = "image_quality_results"
    id: Mapped[UUID] = uuid_pk()
    media_id: Mapped[UUID]
    region_key: Mapped[str] = mapped_column(server_default=text("'full'"))
    pipeline_version: Mapped[str]
    sharpness: Mapped[float | None]
    brightness: Mapped[float | None]
    contrast: Mapped[float | None]
    width: Mapped[int | None]
    height: Mapped[int | None]
    warnings: Mapped[list[str]] = mapped_column(ARRAY(TEXT), server_default=text("'{}'"))
    decision: Mapped[str]
    override_reason: Mapped[str | None]
    overridden_by: Mapped[UUID | None]


class VaccineProduct(Base, _Owned):
    __tablename__ = "vaccine_products"
    id: Mapped[UUID] = uuid_pk()
    name: Mapped[str]
    manufacturer: Mapped[str | None]
    species: Mapped[list[str]] = mapped_column(ARRAY(TEXT), server_default=text("'{dog}'"))
    form: Mapped[str | None]
    unit: Mapped[str] = mapped_column(server_default=text("'dose'"))
    review_state: Mapped[str] = mapped_column(server_default=text("'unreviewed'"))
    active: Mapped[bool] = mapped_column(server_default=text("true"))
    template_interval_days: Mapped[int | None]
    template_label: Mapped[str | None]


class VaccineLot(Base, _Owned):
    __tablename__ = "vaccine_lots"
    id: Mapped[UUID] = uuid_pk()
    product_id: Mapped[UUID]
    lot_number: Mapped[str]
    expiry_date: Mapped[date | None]
    supplier: Mapped[str | None]
    received_on: Mapped[date | None]


class VaccinationEvent(Base, _Owned):
    __tablename__ = "animal_vaccination_events"
    id: Mapped[UUID] = uuid_pk()
    animal_id: Mapped[UUID]
    original_animal_id: Mapped[UUID]
    administered_on: Mapped[date | None]
    administered_at: Mapped[datetime | None]
    date_precision: Mapped[str]
    product_id: Mapped[UUID | None]
    product_text: Mapped[str | None]
    lot_id: Mapped[UUID | None]
    lot_text: Mapped[str | None]
    administered_by_name: Mapped[str | None]
    administered_by_registration: Mapped[str | None]
    administered_by_user_id: Mapped[UUID | None]
    area_id: Mapped[UUID | None]
    location: Mapped[Any | None] = mapped_column(Geography("POINT", srid=4326, spatial_index=False))
    source_type: Mapped[str]
    source_reference: Mapped[str | None]
    submitter_note: Mapped[str | None]
    state: Mapped[str] = mapped_column(server_default=text("'submitted'"))
    supersedes_event_id: Mapped[UUID | None]
    superseded_by_event_id: Mapped[UUID | None]
    has_conflict: Mapped[bool] = mapped_column(server_default=FALSE)
    next_review_on: Mapped[date | None]
    next_review_source: Mapped[str | None]
    submitted_by: Mapped[UUID | None]
    submitted_at: Mapped[datetime | None]
    verified_by: Mapped[UUID | None]
    verified_at: Mapped[datetime | None]
    client_operation_id: Mapped[UUID | None]


class VaccinationEvidence(Base, _Owned):
    __tablename__ = "vaccination_evidence"
    id: Mapped[UUID] = uuid_pk()
    event_id: Mapped[UUID]
    media_id: Mapped[UUID]


class VaccinationReview(Base):
    __tablename__ = "vaccination_reviews"
    id: Mapped[UUID] = uuid_pk()
    org_id: Mapped[UUID]
    event_id: Mapped[UUID]
    reviewer_user_id: Mapped[UUID]
    reviewer_scope: Mapped[str] = mapped_column(server_default=text("'veterinary_review'"))
    outcome: Mapped[str]
    reason: Mapped[str | None]
    event_row_version: Mapped[int]
    evidence_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    is_demo: Mapped[bool] = mapped_column(server_default=FALSE)


class AnimalMerge(Base, _Owned):
    __tablename__ = "animal_merge_operations"
    id: Mapped[UUID] = uuid_pk()
    source_animal_id: Mapped[UUID]
    target_animal_id: Mapped[UUID]
    state: Mapped[str] = mapped_column(server_default=text("'proposed'"))
    reason: Mapped[str]
    proposed_by: Mapped[UUID]
    decided_by: Mapped[UUID | None]
    executed_at: Mapped[datetime | None]
    manifest: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    reversed_by: Mapped[UUID | None]
    reversed_at: Mapped[datetime | None]
    reversal_reason: Mapped[str | None]


class Campaign(Base, _Owned):
    __tablename__ = "campaigns"
    id: Mapped[UUID] = uuid_pk()
    name: Mapped[str]
    purpose: Mapped[str | None]
    activity: Mapped[str] = mapped_column(server_default=text("'vaccination'"))
    starts_on: Mapped[date | None]
    ends_on: Mapped[date | None]
    coordinator_membership_id: Mapped[UUID | None]
    state: Mapped[str] = mapped_column(server_default=text("'draft'"))
    resources: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))


class FieldTask(Base, _Owned):
    __tablename__ = "field_tasks"
    id: Mapped[UUID] = uuid_pk()
    campaign_id: Mapped[UUID | None]
    task_type: Mapped[str]
    title: Mapped[str]
    instructions: Mapped[str | None]
    area_id: Mapped[UUID | None]
    animal_id: Mapped[UUID | None]
    location_approx: Mapped[Any | None] = mapped_column(Geography("POINT", srid=4326, spatial_index=False))
    assignee_membership_id: Mapped[UUID | None]
    team_id: Mapped[UUID | None]
    planned_start: Mapped[datetime | None]
    planned_end: Mapped[datetime | None]
    due_on: Mapped[date | None]
    priority: Mapped[str] = mapped_column(server_default=text("'normal'"))
    priority_rationale: Mapped[str | None]
    state: Mapped[str] = mapped_column(server_default=text("'unassigned'"))
    outcome_note: Mapped[str | None]
    blocked_reason: Mapped[str | None]
    cancelled_reason: Mapped[str | None]
    completed_at: Mapped[datetime | None]
    source_event_type: Mapped[str | None]
    source_event_id: Mapped[UUID | None]
    client_operation_id: Mapped[UUID | None]


class SyncOperation(Base, _Owned):
    __tablename__ = "sync_operations"
    id: Mapped[UUID] = uuid_pk()
    operation_id: Mapped[UUID]
    device_id: Mapped[str]
    actor_user_id: Mapped[UUID]
    operation_type: Mapped[str]
    target_type: Mapped[str | None]
    target_id: Mapped[UUID | None]
    base_row_version: Mapped[int | None]
    state: Mapped[str]
    result_code: Mapped[str | None]
    result_detail: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    client_created_at: Mapped[datetime | None]
    received_at: Mapped[datetime] = mapped_column(server_default=func.now())
    resolved_at: Mapped[datetime | None]
    resolved_by: Mapped[UUID | None]


class DataQualityIssue(Base, _Owned):
    __tablename__ = "data_quality_issues"
    id: Mapped[UUID] = uuid_pk()
    resource_type: Mapped[str]
    resource_id: Mapped[UUID]
    rule: Mapped[str]
    rule_version: Mapped[str] = mapped_column(server_default=text("'1'"))
    severity: Mapped[str]
    explanation: Mapped[str]
    state: Mapped[str] = mapped_column(server_default=text("'open'"))
    resolved_by: Mapped[UUID | None]
    resolution_note: Mapped[str | None]
    resolved_at: Mapped[datetime | None]
