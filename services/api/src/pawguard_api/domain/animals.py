"""Animal registry and observations."""

from datetime import date, datetime, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from pawguard_api.capabilities import Cap
from pawguard_api.contracts import (
    AnimalCreate,
    AnimalOut,
    AnimalUpdate,
    AreaRef,
    ObservationCreate,
    ObservationOut,
    PhotoRef,
    ProfileTransition,
    VaccinationSummary,
)
from pawguard_api.deps import OrgContext
from pawguard_api.domain.common import (
    decode_cursor,
    emit,
    encode_cursor,
    expect_version,
    record_audit,
    require_reason,
)
from pawguard_api.domain.geo import approx_point, location_out, point
from pawguard_api.errors import Conflict, FieldError, NotFound, Unprocessable
from pawguard_api.models import Animal, AnimalObservation, Area, MediaAsset, ObservationMedia

OPEN_TASK_STATES = ("unassigned", "assigned", "in_progress", "blocked")

# Allowed manual profile transitions (merges have their own command).
PROFILE_TRANSITIONS: dict[str, set[str]] = {
    "provisional": {"reviewed", "disputed", "archived"},
    "reviewed": {"active", "disputed", "archived"},
    "active": {"disputed", "archived"},
    "disputed": {"reviewed", "active", "archived"},
    "merged_alias": set(),
    "archived": set(),
}


def _escape_like(q: str) -> str:
    return q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def ensure_area(db: Session, area_id: UUID | None, field: str = "area_id") -> None:
    if area_id is not None and db.get(Area, area_id) is None:  # RLS: other tenants' areas are invisible
        raise Unprocessable("Choose an area from your organisation.",
                            fields=[FieldError(field=field, code="invalid_reference", message="Unknown area.")])


def load_animal(db: Session, animal_id: UUID, *, for_update: bool = False, usable: bool = False) -> Animal:
    stmt = select(Animal).where(Animal.id == animal_id)
    if for_update:
        stmt = stmt.with_for_update()
    animal = db.execute(stmt).scalar_one_or_none()
    if animal is None:
        raise NotFound("Animal record not found.", code="animal_not_found")
    if usable and animal.profile_state == "merged_alias":
        target = db.get(Animal, animal.merged_into_id)
        raise Conflict("This record was merged into another one. Use the surviving record.", code="animal_merged",
                       details={"merged_into_id": str(animal.merged_into_id),
                                "merged_into_reference": target.reference_code if target else None})
    if usable and animal.profile_state == "archived":
        raise Conflict("This record is archived.", code="animal_archived")
    return animal


# ---- commands --------------------------------------------------------------------------------------------------

def create_animal(db: Session, ctx: OrgContext, data: AnimalCreate, *, source_type: str = "field_entry",
                  source_reference: str | None = None) -> UUID:
    ctx.require(Cap.ANIMAL_WRITE)
    ensure_area(db, data.home_area_id, "home_area_id")
    values = data.model_dump(exclude={"first_observation", "client_operation_id"})
    animal_id: UUID | None = None
    for _ in range(3):  # reference codes are random (40 bits); retry on the rare collision
        try:
            with db.begin_nested():
                animal = Animal(org_id=ctx.org_id, created_by=ctx.user_id, source_type=source_type,
                                source_reference=source_reference,
                                client_operation_id=data.client_operation_id, **values)
                db.add(animal)
                db.flush()
                animal_id = animal.id
            break
        except IntegrityError as exc:
            constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", "")
            if constraint == "animals_org_id_client_operation_id_key":
                existing = db.execute(select(Animal.id).where(
                    Animal.client_operation_id == data.client_operation_id)).scalar_one()
                return existing  # replayed offline operation: same record, no duplicate
            if constraint != "animals_org_id_reference_code_key":
                raise
    if animal_id is None:
        raise Conflict("Could not allocate a reference code; try again.", code="reference_collision")
    if data.first_observation is not None:
        create_observation(db, ctx, ObservationCreate(animal_id=animal_id, **data.first_observation.model_dump()),
                           audit=False)
    record_audit(db, ctx, "animal.created", "animal", animal_id,
                 {"fields": sorted(k for k, v in values.items() if v not in (None, "unknown"))})
    emit(db, ctx, "animal.created", "animal", animal_id)
    return animal_id


def update_animal(db: Session, ctx: OrgContext, animal_id: UUID, data: AnimalUpdate) -> None:
    ctx.require(Cap.ANIMAL_WRITE)
    animal = load_animal(db, animal_id, for_update=True, usable=True)
    expect_version(animal.row_version, data.row_version, "animal record")
    changes = data.model_dump(exclude_unset=True, exclude={"row_version"})
    if "home_area_id" in changes:
        ensure_area(db, changes["home_area_id"], "home_area_id")
    changed = [k for k, v in changes.items() if getattr(animal, k) != v]
    for k in changed:
        setattr(animal, k, changes[k])
    if changed:
        record_audit(db, ctx, "animal.updated", "animal", animal_id, {"fields": changed})
        emit(db, ctx, "animal.updated", "animal", animal_id)


def transition_profile(db: Session, ctx: OrgContext, animal_id: UUID, data: ProfileTransition) -> None:
    """Identity review of the profile itself. Flagging a dispute needs animal.write; resolving or reviewing
    needs animal.merge (coordinators / veterinary reviewers)."""
    animal = load_animal(db, animal_id, for_update=True)
    if data.to_state == "disputed":
        ctx.require(Cap.ANIMAL_WRITE)
    else:
        ctx.require(Cap.ANIMAL_MERGE)
    expect_version(animal.row_version, data.row_version, "animal record")
    if data.to_state not in PROFILE_TRANSITIONS[animal.profile_state]:
        raise Conflict(f"A {animal.profile_state} record cannot become {data.to_state}.", code="invalid_transition")
    reason = data.reason
    if data.to_state in ("disputed", "archived") or animal.profile_state == "disputed":
        reason = require_reason(data.reason)
    previous = animal.profile_state
    animal.profile_state = data.to_state
    if data.to_state == "archived":
        animal.archived_reason = reason
    record_audit(db, ctx, "animal.profile_state_changed", "animal", animal_id,
                 {"from": previous, "to": data.to_state}, reason=reason)
    emit(db, ctx, "animal.profile_state_changed", "animal", animal_id)


def create_observation(db: Session, ctx: OrgContext, data: ObservationCreate, *, audit: bool = True) -> UUID:
    ctx.require(Cap.OBSERVATION_WRITE)
    if data.animal_id is not None:
        load_animal(db, data.animal_id, usable=True)
    ensure_area(db, data.area_id)
    if data.client_operation_id is not None:
        existing = db.execute(select(AnimalObservation.id).where(
            AnimalObservation.client_operation_id == data.client_operation_id)).scalar()
        if existing:
            return existing
    observed_on = data.observed_on
    if data.observed_at is not None and observed_on is None:
        observed_on = data.observed_at.astimezone(ZoneInfo(ctx.timezone)).date()
    if observed_on and observed_on > date.today() + timedelta(days=1):
        raise Unprocessable("The observation date cannot be in the future.",
                            fields=[FieldError(field="observed_on", code="date_in_future",
                                               message="Date is in the future.")])
    obs = AnimalObservation(
        org_id=ctx.org_id, created_by=ctx.user_id, animal_id=data.animal_id,
        reported_animal_reference=data.reported_animal_reference, observer_user_id=ctx.user_id,
        observed_at=data.observed_at, observed_on=observed_on, time_precision=data.time_precision,
        location=point(data.location), location_approx=approx_point(data.location),
        location_accuracy_m=data.location.accuracy_m if data.location else None,
        location_method=data.location.method if data.location else ("area_only" if data.area_id else "unknown"),
        area_id=data.area_id, notes=data.notes, field_task_id=data.field_task_id,
        client_operation_id=data.client_operation_id)
    db.add(obs)
    db.flush()
    subjects = {sub.media_id: sub for sub in data.subjects}
    if set(subjects) - set(data.media_ids):
        raise Unprocessable("A subject was chosen for a photo that is not attached.",
                            fields=[FieldError(field="subjects", code="unknown_media", message="Unknown photo.")])
    for media_id in data.media_ids:
        media = db.get(MediaAsset, media_id)
        usable = media is not None and media.state in ("uploaded", "validating", "approved")
        if not usable or media.purpose != "animal_photo":
            raise Unprocessable("A photo is missing, still uploading or failed validation.",
                                fields=[FieldError(field="media_ids", code="media_not_ready",
                                                   message="Photo not available.")])
        sub = subjects.get(media_id)
        bbox = crop_version = dog_count = None
        if sub is not None and sub.box is not None:
            b = sub.box
            if media.width and media.height and (b.x + b.w > media.width + 1 or b.y + b.h > media.height + 1):
                raise Unprocessable("The selected area lies outside the photo.",
                                    fields=[FieldError(field="subjects", code="box_out_of_bounds",
                                                       message="Selected area outside the photo.")])
            bbox = b.model_dump()
            crop_version = "detector-selected" if sub.source == "detector" else "manual"
        if sub is not None:
            dog_count = sub.dog_count
        warned = db.execute(text("select id from app.image_quality_results where media_id = :m and decision = 'warn'"),
                            {"m": media_id}).scalars().all()
        if warned:
            if not data.quality_override_reason or len(data.quality_override_reason.strip()) < 3:
                raise Unprocessable("This photo has quality warnings. Say why it should be used anyway.",
                                    fields=[FieldError(field="quality_override_reason", code="required",
                                                       message="Reason required for a photo with warnings.")])
            db.execute(text("update app.image_quality_results set override_reason = :r, overridden_by = :u "
                            "where id = any(:ids)"),
                       {"r": data.quality_override_reason.strip(), "u": ctx.user_id, "ids": list(warned)})
        db.add(ObservationMedia(org_id=ctx.org_id, created_by=ctx.user_id, observation_id=obs.id, media_id=media_id,
                                subject_bbox=bbox, subject_count=dog_count, crop_version=crop_version))
    if data.animal_id is not None:
        seen = data.observed_at or (datetime.combine(observed_on, datetime.min.time(), ZoneInfo(ctx.timezone))
                                    if observed_on else None)
        if seen is not None:
            db.execute(text("update app.animals set last_observed_at = greatest(coalesce(last_observed_at, :s), :s) "
                            "where id = :a"), {"s": seen, "a": data.animal_id})
    if data.animal_id is not None and data.media_ids:
        from pawguard_api.domain.identity import queue_enrolment

        db.flush()
        queue_enrolment(db, ctx, obs.id)
    if audit:
        record_audit(db, ctx, "observation.created", "observation", obs.id,
                     {"has_location": data.location is not None, "photos": len(data.media_ids)})
    emit(db, ctx, "observation.created", "observation", obs.id,
         {"animal_id": data.animal_id} if data.animal_id else None)
    return obs.id


# ---- queries ---------------------------------------------------------------------------------------------------

_ANIMAL_SELECT = """
select a.*, ar.code as area_code, ar.name as area_name, m.reference_code as merged_into_reference,
       lv.administered_on as last_verified_on, lv.date_precision as last_verified_precision,
       lv.next_review_on, lv.next_review_source,
       (select count(*) from app.animal_vaccination_events e
         where e.animal_id = a.id and e.state = 'submitted') as pending_review_count,
       (select count(*) from app.field_tasks t
         where t.animal_id = a.id and t.state in ('unassigned','assigned','in_progress','blocked')) as open_task_count,
       ph.id as photo_media_id, ph.derivatives as photo_derivatives
from app.animals a
left join app.areas ar on ar.id = a.home_area_id
left join app.animals m on m.id = a.merged_into_id
left join lateral (
  select e.administered_on, e.date_precision, e.next_review_on, e.next_review_source
  from app.animal_vaccination_events e
  where e.animal_id = a.id and e.state = 'verified'
  order by e.administered_on desc nulls last, e.verified_at desc limit 1) lv on true
left join lateral (
  select ma.id, ma.derivatives from app.observation_media om
  join app.animal_observations o on o.id = om.observation_id
  join app.media_assets ma on ma.id = om.media_id
  where o.animal_id = a.id and ma.state = 'approved' and ma.purpose = 'animal_photo'
  order by o.created_at desc limit 1) ph on true
"""


def _summary(row: Any) -> VaccinationSummary:
    if row.last_verified_on is not None or row.last_verified_precision is not None:
        status = "verified_record"
    elif row.pending_review_count:
        status = "submitted_only"
    else:
        status = "no_verified_record"
    return VaccinationSummary(status=status, last_verified_on=row.last_verified_on,
                              last_verified_precision=row.last_verified_precision,
                              pending_review_count=row.pending_review_count, next_review_on=row.next_review_on,
                              next_review_source=row.next_review_source)


def _animal_out(row: Any, photo_urls: dict[str, str]) -> AnimalOut:
    photo = None
    if row.photo_media_id:
        thumb = (row.photo_derivatives or {}).get("thumb")
        photo = PhotoRef(media_id=row.photo_media_id, url=photo_urls.get(thumb) if thumb else None)
    return AnimalOut(
        id=row.id, reference_code=row.reference_code, species=row.species, nickname=row.nickname, sex=row.sex,
        sterilisation_status=row.sterilisation_status, age_band=row.age_band,
        coat_description=row.coat_description, identifying_marks=row.identifying_marks, breed_note=row.breed_note,
        ownership_category=row.ownership_category, profile_state=row.profile_state,
        merged_into_reference=row.merged_into_reference,
        home_area=AreaRef(id=row.home_area_id, code=row.area_code, name=row.area_name) if row.home_area_id else None,
        last_observed_at=row.last_observed_at, vaccination=_summary(row), photo=photo,
        open_task_count=row.open_task_count, is_demo=row.is_demo, created_at=row.created_at,
        row_version=row.row_version)


def _photo_urls(rows: list[Any]) -> dict[str, str]:
    keys = [(r.photo_derivatives or {}).get("thumb") for r in rows if r.photo_media_id]
    keys = [k for k in keys if k]
    if not keys:
        return {}
    from pawguard_api.integrations.storage import get_storage

    try:
        return get_storage().signed_download_urls(keys)
    except Exception:
        return {}


def get_animal(db: Session, ctx: OrgContext, animal_id: UUID) -> AnimalOut:
    ctx.require(Cap.ANIMAL_READ)
    row = db.execute(text(_ANIMAL_SELECT + " where a.id = :id"), {"id": animal_id}).one_or_none()
    if row is None:
        raise NotFound("Animal record not found.", code="animal_not_found")
    return _animal_out(row, _photo_urls([row]))


def search_animals(db: Session, ctx: OrgContext, *, q: str | None, area_id: UUID | None,
                   profile_states: list[str] | None, vaccination_status: str | None, seen_within_days: int | None,
                   has_open_task: bool | None, include_merged: bool, cursor: str | None,
                   limit: int) -> tuple[list[AnimalOut], str | None, int]:
    ctx.require(Cap.ANIMAL_READ)
    where, params = ["true"], {}
    if q:
        where.append("(coalesce(a.nickname,'') || ' ' || a.reference_code || ' ' || coalesce(a.coat_description,'')"
                     " || ' ' || coalesce(a.identifying_marks,'')) ilike :q escape '\\'")
        params["q"] = f"%{_escape_like(q.strip())}%"
    if area_id:
        where.append("a.home_area_id = :area")
        params["area"] = area_id
    if profile_states:
        where.append("a.profile_state = any(:states)")
        params["states"] = profile_states
    elif not include_merged:
        where.append("a.profile_state not in ('merged_alias','archived')")
    if seen_within_days:
        where.append("a.last_observed_at >= now() - make_interval(days => :days)")
        params["days"] = seen_within_days
    if has_open_task is not None:
        clause = ("exists (select 1 from app.field_tasks t where t.animal_id = a.id and t.state in "
                  "('unassigned','assigned','in_progress','blocked'))")
        where.append(clause if has_open_task else f"not {clause}")
    if vaccination_status == "verified_record":
        where.append("exists (select 1 from app.animal_vaccination_events e where e.animal_id = a.id "
                     "and e.state = 'verified')")
    elif vaccination_status == "submitted_only":
        where.append("not exists (select 1 from app.animal_vaccination_events e where e.animal_id = a.id "
                     "and e.state = 'verified') and exists (select 1 from app.animal_vaccination_events e "
                     "where e.animal_id = a.id and e.state = 'submitted')")
    elif vaccination_status == "no_verified_record":
        where.append("not exists (select 1 from app.animal_vaccination_events e where e.animal_id = a.id "
                     "and e.state = 'verified')")
    filter_sql = " and ".join(where)
    total = db.execute(text(f"select count(*) from app.animals a where {filter_sql}"), params).scalar_one()  # noqa: S608
    page_where = filter_sql
    c = decode_cursor(cursor, 2)
    if c:
        page_where += (" and (coalesce(a.last_observed_at, a.created_at), a.id)"
                       " < (cast(:c0 as timestamptz), cast(:c1 as uuid))")
        params.update(c0=c[0], c1=c[1])
    rows = db.execute(text(_ANIMAL_SELECT + f" where {page_where} "
                           "order by coalesce(a.last_observed_at, a.created_at) desc, a.id desc limit :lim"),
                      {**params, "lim": limit + 1}).all()
    more = len(rows) > limit
    rows = rows[:limit]
    urls = _photo_urls(rows)
    items = [_animal_out(r, urls) for r in rows]
    next_cursor = None
    if more and rows:
        last = rows[-1]
        next_cursor = encode_cursor(last.last_observed_at or last.created_at, last.id)
    return items, next_cursor, total


def list_observations(db: Session, ctx: OrgContext, animal_id: UUID, limit: int = 50) -> list[ObservationOut]:
    ctx.require(Cap.ANIMAL_READ)
    exact = ctx.can(Cap.ANIMAL_LOCATION_EXACT)
    col = "o.location" if exact else "o.location_approx"
    rows = db.execute(text(f"""
        select o.*, st_y({col}::geometry) as lat, st_x({col}::geometry) as lon, ar.code as area_code,
               ar.name as area_name, up.preferred_name as observer_name,
               coalesce((select array_agg(om.media_id) from app.observation_media om
                         where om.observation_id = o.id), '{{}}') as media_ids
        from app.animal_observations o
        left join app.areas ar on ar.id = o.area_id
        left join app.user_profiles up on up.user_id = o.observer_user_id
        where o.animal_id = :a
        order by coalesce(o.observed_at, o.observed_on::timestamptz, o.created_at) desc limit :lim"""),  # noqa: S608
        {"a": animal_id, "lim": limit}).all()
    return [ObservationOut(
        id=r.id, animal_id=r.animal_id, reported_animal_reference=r.reported_animal_reference,
        observer_user_id=r.observer_user_id, observer_name=r.observer_name, observed_at=r.observed_at,
        observed_on=r.observed_on, time_precision=r.time_precision,
        location=location_out(r.lat, r.lon, r.location_accuracy_m, exact), location_method=r.location_method,
        area=AreaRef(id=r.area_id, code=r.area_code, name=r.area_name) if r.area_id else None, notes=r.notes,
        media_ids=list(r.media_ids), created_at=r.created_at) for r in rows]
