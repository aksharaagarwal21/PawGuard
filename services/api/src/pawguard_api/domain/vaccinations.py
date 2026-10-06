"""Vaccination evidence ledger.

State machine: draft → submitted → verified | rejected | needs_correction; a correction creates a new event
that supersedes the old one (the old event and its evidence stay). Only an authorised veterinary reviewer
(capability + active professional approval + live session) who did not submit the event can review it.
"verified" means "a vaccine was recorded as given and the evidence was accepted" — nothing more.
"""

from datetime import date, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from pawguard_api.capabilities import Cap
from pawguard_api.contracts import (
    AreaRef,
    EvidenceOut,
    ReviewCreate,
    ReviewOut,
    VaccinationAmend,
    VaccinationCreate,
    VaccinationOut,
)
from pawguard_api.deps import OrgContext
from pawguard_api.domain import reminders
from pawguard_api.domain.animals import ensure_area, load_animal
from pawguard_api.domain.common import (
    decode_cursor,
    emit,
    encode_cursor,
    expect_version,
    record_audit,
    require_reason,
)
from pawguard_api.domain.geo import point
from pawguard_api.errors import Conflict, FieldError, Forbidden, NotFound, Unprocessable
from pawguard_api.models import (
    DataQualityIssue,
    FieldTask,
    MediaAsset,
    Membership,
    VaccinationEvent,
    VaccinationEvidence,
    VaccinationReview,
    VaccineLot,
    VaccineProduct,
)

EVIDENCE_USABLE = ("uploaded", "validating", "approved")


def _normalise_date(data: VaccinationCreate, tz: str) -> tuple[date | None, Any]:
    if data.date_precision == "unknown":
        return None, None
    if data.date_precision == "exact_time":
        assert data.administered_at is not None
        return data.administered_at.astimezone(ZoneInfo(tz)).date(), data.administered_at
    assert data.administered_on is not None
    d = data.administered_on
    if data.date_precision == "month":
        d = d.replace(day=1)
    elif data.date_precision == "year":
        d = d.replace(month=1, day=1)
    return d, None


def _check_references(db: Session, data: VaccinationCreate) -> tuple[VaccineProduct | None, VaccineLot | None]:
    product = db.get(VaccineProduct, data.product_id) if data.product_id else None
    if data.product_id and product is None:
        raise Unprocessable("Unknown vaccine product.", fields=[FieldError(field="product_id", code="invalid_reference",
                                                                           message="Unknown product.")])
    lot = db.get(VaccineLot, data.lot_id) if data.lot_id else None
    if data.lot_id and lot is None:
        raise Unprocessable("Unknown lot.", fields=[FieldError(field="lot_id", code="invalid_reference",
                                                               message="Unknown lot.")])
    if lot and product and lot.product_id != product.id:
        raise Unprocessable("This lot belongs to a different product.",
                            fields=[FieldError(field="lot_id", code="lot_product_mismatch",
                                               message="Lot does not match the product.")])
    if lot and not product:
        product = db.get(VaccineProduct, lot.product_id)
    return product, lot


def _attach_evidence(db: Session, ctx: OrgContext, event_id: UUID, media_ids: list[UUID]) -> None:
    for media_id in dict.fromkeys(media_ids):
        media = db.get(MediaAsset, media_id)
        if media is None or media.state not in EVIDENCE_USABLE:
            raise Unprocessable("An evidence file is missing, still uploading or failed validation.",
                                fields=[FieldError(field="evidence_media_ids", code="media_not_ready",
                                                   message="Evidence file not available.")])
        db.add(VaccinationEvidence(org_id=ctx.org_id, created_by=ctx.user_id, event_id=event_id, media_id=media_id))


def _detect_conflicts(db: Session, ctx: OrgContext, event: VaccinationEvent, product: VaccineProduct | None,
                      lot: VaccineLot | None) -> list[str]:
    """Flag (never auto-resolve) evidence that needs a reviewer's attention."""
    issues: list[tuple[str, str, str]] = []
    if event.administered_on is not None:
        window = 3 if event.date_precision in ("day", "exact_time") else 31
        near = db.execute(text("""
            select id from app.animal_vaccination_events
            where animal_id = :a and id <> :id and state in ('submitted','verified','needs_correction')
              and administered_on between :d1 and :d2 limit 5"""),
            {"a": event.animal_id, "id": event.id, "d1": event.administered_on - timedelta(days=window),
             "d2": event.administered_on + timedelta(days=window)}).scalars().all()
        if near:
            issues.append(("possible_duplicate_vaccination", "warning",
                           f"{len(near)} other record(s) for this animal within {window} days."))
        if lot and lot.expiry_date and lot.expiry_date < event.administered_on:
            issues.append(("lot_expired_at_administration", "warning",
                           "The lot's recorded expiry date is before the administration date."))
    if product and event.animal_id:
        species = db.execute(text("select species from app.animals where id = :a"), {"a": event.animal_id}).scalar()
        if species not in ("unknown", None) and species not in (product.species or []):
            issues.append(("product_species_mismatch", "warning",
                           "The product is not recorded as applicable to this species."))
    for rule, severity, explanation in issues:
        db.add(DataQualityIssue(org_id=ctx.org_id, created_by=ctx.user_id, resource_type="vaccination_event",
                                resource_id=event.id, rule=rule, severity=severity, explanation=explanation))
    if issues:
        event.has_conflict = True
    return [i[0] for i in issues]


def submit(db: Session, ctx: OrgContext, data: VaccinationCreate, *, supersedes: VaccinationEvent | None = None
           ) -> UUID:
    ctx.require(Cap.VACCINATION_SUBMIT)
    if data.client_operation_id is not None:
        existing = db.execute(select(VaccinationEvent.id).where(
            VaccinationEvent.client_operation_id == data.client_operation_id)).scalar()
        if existing:
            return existing  # replay of an offline/retried submission — never a second administration
    animal = load_animal(db, data.animal_id, usable=True)
    ensure_area(db, data.area_id)
    product, lot = _check_references(db, data)
    administered_on, administered_at = _normalise_date(data, ctx.timezone)
    state = "draft" if data.save_as_draft else "submitted"
    event = VaccinationEvent(
        org_id=ctx.org_id, created_by=ctx.user_id, animal_id=animal.id,
        original_animal_id=supersedes.original_animal_id if supersedes else animal.id,
        administered_on=administered_on, administered_at=administered_at, date_precision=data.date_precision,
        product_id=data.product_id, product_text=data.product_text, lot_id=data.lot_id, lot_text=data.lot_text,
        administered_by_name=data.administered_by_name,
        administered_by_registration=data.administered_by_registration, area_id=data.area_id,
        location=point(data.location), source_type=data.source_type, source_reference=data.source_reference,
        submitter_note=data.submitter_note, state=state, supersedes_event_id=supersedes.id if supersedes else None,
        submitted_by=ctx.user_id, submitted_at=text("now()"), client_operation_id=data.client_operation_id)
    db.add(event)
    db.flush()
    _attach_evidence(db, ctx, event.id, data.evidence_media_ids)
    conflicts = _detect_conflicts(db, ctx, event, product, lot) if state == "submitted" else []
    record_audit(db, ctx, "vaccination_event.submitted" if state == "submitted" else "vaccination_event.drafted",
                 "vaccination_event", event.id,
                 {"animal_id": str(animal.id), "precision": data.date_precision,
                  "evidence": len(data.evidence_media_ids), "conflicts": conflicts,
                  "supersedes": str(supersedes.id) if supersedes else None})
    emit(db, ctx, f"vaccination_event.{state}", "vaccination_event", event.id, {"animal_id": animal.id})
    return event.id


def _lock_event(db: Session, event_id: UUID) -> VaccinationEvent:
    event = db.execute(select(VaccinationEvent).where(VaccinationEvent.id == event_id).with_for_update()).scalar()
    if event is None:
        raise NotFound("Vaccination record not found.", code="vaccination_event_not_found")
    return event


def review(db: Session, ctx: OrgContext, event_id: UUID, data: ReviewCreate) -> UUID:
    ctx.require(Cap.VACCINATION_REVIEW)  # capability AND approved veterinary_review scope
    ctx.require_live_session(db)
    event = _lock_event(db, event_id)
    if event.submitted_by == ctx.user_id:
        raise Forbidden("You cannot review a vaccination record you submitted.", code="cannot_review_own_submission")
    if event.state != "submitted":
        raise Conflict("This record is not awaiting review.", code="invalid_state", details={"state": event.state})
    expect_version(event.row_version, data.row_version, "vaccination record")
    reason = data.reason if data.outcome == "verified" else require_reason(data.reason)
    snapshot = {k: (str(v) if v is not None else None) for k, v in {
        "animal_id": event.animal_id, "administered_on": event.administered_on, "date_precision": event.date_precision,
        "product_id": event.product_id, "product_text": event.product_text, "lot_id": event.lot_id,
        "lot_text": event.lot_text, "administered_by_name": event.administered_by_name,
        "administered_by_registration": event.administered_by_registration, "source_type": event.source_type,
    }.items()}
    snapshot["evidence_media_ids"] = [str(m) for m in db.execute(select(VaccinationEvidence.media_id).where(
        VaccinationEvidence.event_id == event.id)).scalars()]
    rv = VaccinationReview(org_id=ctx.org_id, event_id=event.id, reviewer_user_id=ctx.user_id,
                           outcome=data.outcome, reason=reason, event_row_version=event.row_version,
                           evidence_snapshot=snapshot, is_demo=event.is_demo)
    db.add(rv)
    if (data.outcome == "verified" and data.next_due_on is not None and event.administered_on is not None
            and data.next_due_on <= event.administered_on):
        raise Unprocessable("The next due date must be after the vaccination date.",
                            fields=[FieldError(field="next_due_on", code="due_before_administration",
                                               message="Next due date is not after the vaccination date.")])
    event.state = data.outcome
    if data.outcome == "verified":
        event.verified_by = ctx.user_id
        event.verified_at = text("now()")
    db.flush()
    reminders.after_review(db, ctx.org_id, event, data.outcome, data.next_due_on)  # same transaction
    if data.outcome == "needs_correction" and event.submitted_by is not None:
        submitter = db.execute(select(Membership.id).where(Membership.user_id == event.submitted_by,
                                                           Membership.status == "active")).scalar()
        animal_ref = db.execute(text("select reference_code from app.animals where id = :a"),
                                {"a": event.animal_id}).scalar()
        db.add(FieldTask(org_id=ctx.org_id, created_by=ctx.user_id, task_type="evidence_correction",
                         title=f"Correct vaccination record for {animal_ref}", instructions=reason,
                         animal_id=event.animal_id, assignee_membership_id=submitter,
                         state="assigned" if submitter else "unassigned", priority="normal",
                         source_event_type="vaccination_event", source_event_id=event.id, is_demo=event.is_demo))
    record_audit(db, ctx, f"vaccination_event.{data.outcome}", "vaccination_event", event.id,
                 {"review_id": str(rv.id), "outcome": data.outcome}, reason=reason)
    emit(db, ctx, "vaccination_event.reviewed", "vaccination_event", event.id, {"outcome": data.outcome})
    return rv.id


def amend(db: Session, ctx: OrgContext, event_id: UUID, data: VaccinationAmend) -> UUID:
    """Submit a corrected record for one marked needs_correction (or a draft). The old record is kept."""
    ctx.require(Cap.VACCINATION_SUBMIT)
    old = _lock_event(db, event_id)
    if old.state not in ("needs_correction", "draft"):
        raise Conflict("Only records marked 'correction requested' or drafts can be amended.", code="invalid_state",
                       details={"state": old.state})
    if old.submitted_by != ctx.user_id and not ctx.can(Cap.TASK_MANAGE):
        raise Forbidden("Only the original submitter or a coordinator can correct this record.",
                        code="not_submitter")
    expect_version(old.row_version, data.row_version, "vaccination record")
    payload = VaccinationCreate(**data.model_dump(exclude={"row_version"}))
    new_id = submit(db, ctx, payload, supersedes=old)
    old.state = "superseded"
    old.superseded_by_event_id = new_id
    db.execute(text("""update app.field_tasks set state = 'completed', completed_at = now(),
                       outcome_note = 'Corrected record submitted'
                       where source_event_id = :e and task_type = 'evidence_correction'
                         and state in ('unassigned','assigned','in_progress','blocked')"""), {"e": old.id})
    record_audit(db, ctx, "vaccination_event.superseded", "vaccination_event", old.id, {"superseded_by": str(new_id)})
    return new_id


# ---- queries ---------------------------------------------------------------------------------------------------

_EVENT_SELECT = """
select e.*, a.reference_code as animal_reference, p.name as product_name, l.lot_number, l.expiry_date as lot_expiry,
       ar.code as area_code, ar.name as area_name, sp.preferred_name as submitted_by_name,
       coalesce((select array_agg(q.rule) from app.data_quality_issues q
                 where q.resource_type = 'vaccination_event' and q.resource_id = e.id and q.state = 'open'), '{}')
         as conflict_rules
from app.animal_vaccination_events e
join app.animals a on a.id = e.animal_id
left join app.vaccine_products p on p.id = e.product_id
left join app.vaccine_lots l on l.id = e.lot_id
left join app.areas ar on ar.id = e.area_id
left join app.user_profiles sp on sp.user_id = e.submitted_by
"""


def _event_out(row: Any, evidence: list[EvidenceOut], reviews: list[ReviewOut]) -> VaccinationOut:
    return VaccinationOut(
        id=row.id, animal_id=row.animal_id, animal_reference=row.animal_reference,
        original_animal_id=row.original_animal_id, date_precision=row.date_precision,
        administered_on=row.administered_on, administered_at=row.administered_at, product_id=row.product_id,
        product_name=row.product_name, product_text=row.product_text, lot_id=row.lot_id, lot_number=row.lot_number,
        lot_text=row.lot_text, lot_expiry_date=row.lot_expiry, administered_by_name=row.administered_by_name,
        administered_by_registration=row.administered_by_registration,
        area=AreaRef(id=row.area_id, code=row.area_code, name=row.area_name) if row.area_id else None,
        source_type=row.source_type, source_reference=row.source_reference, submitter_note=row.submitter_note,
        state=row.state, has_conflict=row.has_conflict, conflicts=list(row.conflict_rules),
        supersedes_event_id=row.supersedes_event_id, superseded_by_event_id=row.superseded_by_event_id,
        next_review_on=row.next_review_on, next_review_source=row.next_review_source, submitted_by=row.submitted_by,
        submitted_by_name=row.submitted_by_name, submitted_at=row.submitted_at, verified_by=row.verified_by,
        verified_at=row.verified_at, evidence=evidence, reviews=reviews, is_demo=row.is_demo,
        row_version=row.row_version)


def get_event(db: Session, ctx: OrgContext, event_id: UUID, *, with_urls: bool = True) -> VaccinationOut:
    ctx.require(Cap.ANIMAL_READ)
    row = db.execute(text(_EVENT_SELECT + " where e.id = :id"), {"id": event_id}).one_or_none()
    if row is None:
        raise NotFound("Vaccination record not found.", code="vaccination_event_not_found")
    ev = db.execute(text("""select m.id, m.state, m.purpose, m.detected_mime, m.derivatives, m.object_key
                            from app.vaccination_evidence v join app.media_assets m on m.id = v.media_id
                            where v.event_id = :e order by v.created_at"""), {"e": event_id}).all()
    urls: dict[str, str] = {}
    if with_urls:
        keys = [(m.derivatives or {}).get("display") or ((m.derivatives or {}).get("original") if m.state == "approved"
                                                        else None) for m in ev if m.state == "approved"]
        from pawguard_api.integrations.storage import get_storage

        try:
            urls = get_storage().signed_download_urls([k for k in keys if k])
        except Exception:
            urls = {}
    evidence = [EvidenceOut(media_id=m.id, state=m.state, purpose=m.purpose, detected_mime=m.detected_mime,
                            url=urls.get((m.derivatives or {}).get("display") or (m.derivatives or {}).get("original")
                                         or "")) for m in ev]
    reviews = [ReviewOut(id=r.id, reviewer_user_id=r.reviewer_user_id, reviewer_name=r.preferred_name,
                         outcome=r.outcome, reason=r.reason, created_at=r.created_at)
               for r in db.execute(text("""select r.*, up.preferred_name from app.vaccination_reviews r
                                           left join app.user_profiles up on up.user_id = r.reviewer_user_id
                                           where r.event_id = :e order by r.created_at"""), {"e": event_id})]
    return _event_out(row, evidence, reviews)


def list_events(db: Session, ctx: OrgContext, *, animal_id: UUID | None, states: list[str] | None,
                submitted_by_me: bool, cursor: str | None, limit: int,
                review_queue: bool = False) -> tuple[list[VaccinationOut], str | None]:
    ctx.require(Cap.ANIMAL_READ)
    where, params = ["true"], {}
    if animal_id:
        where.append("e.animal_id = :a")
        params["a"] = animal_id
    if states:
        where.append("e.state = any(:states)")
        params["states"] = states
    if submitted_by_me:
        where.append("e.submitted_by = :me")
        params["me"] = ctx.user_id
    if review_queue:
        # Oldest first so nothing waits indefinitely; the reviewer's own submissions are excluded.
        where.append("e.state = 'submitted' and e.submitted_by <> :me")
        params["me"] = ctx.user_id
        order, cmp = "e.submitted_at asc, e.id asc", ">"
    else:
        order, cmp = "e.submitted_at desc nulls last, e.id desc", "<"
    c = decode_cursor(cursor, 2)
    if c:
        where.append(f"(e.submitted_at, e.id) {cmp} (cast(:c0 as timestamptz), cast(:c1 as uuid))")
        params.update(c0=c[0], c1=c[1])
    rows = db.execute(text(_EVENT_SELECT + " where " + " and ".join(where) +
                           f" order by {order} limit :lim"), {**params, "lim": limit + 1}).all()
    more = len(rows) > limit
    rows = rows[:limit]
    items = [_event_out(r, [], []) for r in rows]
    nxt = encode_cursor(rows[-1].submitted_at, rows[-1].id) if more and rows else None
    return items, nxt
