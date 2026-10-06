"""Capability catalogue and role templates.

Authorisation is membership + explicit capabilities (+ record relationships). A role label only selects the
*initial* capability template when an administrator creates a membership; checks are always against the
capability list stored on the membership. Professional authority (e.g. veterinary review) additionally
requires an active, independently approved ``professional_approvals`` record.
"""

from enum import StrEnum


class Cap(StrEnum):
    ANIMAL_READ = "animal.read"
    ANIMAL_WRITE = "animal.write"
    ANIMAL_MERGE = "animal.merge"
    ANIMAL_LOCATION_EXACT = "animal.location.exact"
    CAREGIVER_READ = "caregiver.read"
    CAREGIVER_WRITE = "caregiver.write"
    OBSERVATION_WRITE = "observation.write"
    MEDIA_UPLOAD = "media.upload"
    PET_OWN = "pet.own"  # self-service for pet owners: only pets linked to them
    IDENTITY_SEARCH = "identity.search"
    IDENTITY_DECIDE = "identity.decide"
    VACCINATION_SUBMIT = "vaccination.submit"
    VACCINATION_REVIEW = "vaccination.review"  # also needs professional approval scope "veterinary_review"
    TASK_WORK = "task.work"
    TASK_MANAGE = "task.manage"
    CAMPAIGN_MANAGE = "campaign.manage"
    SURVEY_WRITE = "survey.write"
    REPORT_AGGREGATE = "report.aggregate"
    MEMBER_MANAGE = "member.manage"
    PROFESSIONAL_APPROVE = "professional.approve"
    AUDIT_READ = "audit.read"
    SYSTEM_VIEW = "system.view"
    DATA_IMPORT = "data.import"
    MODEL_MANAGE = "model.manage"


class Role(StrEnum):
    RESIDENT = "resident"
    FIELD_VOLUNTEER = "field_volunteer"
    VETERINARY_REVIEWER = "veterinary_reviewer"
    PROGRAMME_COORDINATOR = "programme_coordinator"
    ORG_ADMIN = "org_admin"
    CONTENT_REVIEWER = "content_reviewer"


_FIELD = {Cap.ANIMAL_READ, Cap.ANIMAL_WRITE, Cap.OBSERVATION_WRITE, Cap.MEDIA_UPLOAD, Cap.IDENTITY_SEARCH,
          Cap.IDENTITY_DECIDE, Cap.VACCINATION_SUBMIT, Cap.TASK_WORK, Cap.SURVEY_WRITE}

ROLE_TEMPLATES: dict[Role, frozenset[Cap]] = {
    # Pet owners: their own pets only (no registry-wide read), plus uploading photos/certificates for them.
    Role.RESIDENT: frozenset({Cap.PET_OWN, Cap.MEDIA_UPLOAD}),
    Role.FIELD_VOLUNTEER: frozenset(_FIELD),
    Role.VETERINARY_REVIEWER: frozenset(_FIELD | {Cap.VACCINATION_REVIEW, Cap.ANIMAL_MERGE,
                                                  Cap.ANIMAL_LOCATION_EXACT, Cap.CAREGIVER_READ}),
    Role.PROGRAMME_COORDINATOR: frozenset(_FIELD | {Cap.TASK_MANAGE, Cap.CAMPAIGN_MANAGE, Cap.REPORT_AGGREGATE,
                                                    Cap.ANIMAL_MERGE, Cap.ANIMAL_LOCATION_EXACT,
                                                    Cap.CAREGIVER_READ, Cap.CAREGIVER_WRITE, Cap.DATA_IMPORT}),
    # Administrators manage people and settings. They do NOT get vaccination review: professional authority
    # comes only through an audited approval by someone else.
    Role.ORG_ADMIN: frozenset({Cap.ANIMAL_READ, Cap.MEMBER_MANAGE, Cap.PROFESSIONAL_APPROVE, Cap.AUDIT_READ,
                               Cap.SYSTEM_VIEW, Cap.REPORT_AGGREGATE, Cap.MODEL_MANAGE}),
    Role.CONTENT_REVIEWER: frozenset(),
}

# Capabilities whose use additionally requires an active professional approval with this scope.
PROFESSIONAL_SCOPE_FOR: dict[Cap, str] = {Cap.VACCINATION_REVIEW: "veterinary_review"}

ALL_CAPABILITIES = frozenset(Cap)
