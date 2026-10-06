"""Pet owners: their pets, vaccination timeline, owner-entered records and reminders.

Owners hold ``pet.own`` (role ``resident``) in one or more clinics (organisations). They never get registry-wide
``animal.read``: every query here is restricted to animals linked to the caller through an ``animal_caregivers``
row with relationship 'owner'. Existing commands (create animal, submit vaccination) are reused with a context
elevated for that one call, and only *after* the ownership check. Owner-entered records are created as
``submitted`` (unverified) and go to the clinic's vet workbench like any other evidence.
"""

import dataclasses
from datetime import date, datetime, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.orm import Session

from pawguard_api.auth import Principal
from pawguard_api.capabilities import Cap
from pawguard_api.contracts import AnimalCreate, ObservationCreate, VaccinationCreate
from pawguard_api.db import user_tx
from pawguard_api.deps import OrgContext, load_org_context
from pawguard_api.domain import animals, reminders, vaccinations
from pawguard_api.domain.common import record_audit
from pawguard_api.errors import FieldError, Forbidden, NotFound, Unprocessable
from pawguard_api.models import Animal, AnimalCaregiver, MediaAsset
from pawguard_api.pet_contracts import (
    ClinicOut,
    OwnerVaccinationIn,
    PetCardOut,
    PetCreate,
    PetDetailOut,
    ProductOptionOut,
    ReminderOut,
    ReminderPreviewOut,
    TimelineEntryOut,
)

LIVE_OWNER = """c.relationship = 'owner' and c.linked_user_id = :u
                and (c.valid_to is null or c.valid_to > current_date)"""

_PETS = f"""
select a.id, a.reference_code, coalesce(a.nickname, a.reference_code) as name, a.species, a.sex, a.date_of_birth,
       a.age_band, a.is_demo, a.org_id, ph.id as photo_media_id, ph.derivatives as photo_derivatives
from app.animals a
join app.animal_caregivers c on c.animal_id = a.id and {LIVE_OWNER}
left join lateral (
  select ma.id, ma.derivatives from app.observation_media om
  join app.animal_observations o on o.id = om.observation_id
  join app.media_assets ma on ma.id = om.media_id
  where o.animal_id = a.id and ma.state = 'approved' and ma.purpose = 'animal_photo'
  order by o.created_at desc limit 1) ph on true
where a.profile_state not in ('archived','merged_alias')
"""  # noqa: S608 - constant fragments only; values are bound parameters


# ---- contexts ----------------------------------------------------------------------------------------------------

def owner_contexts(p: Principal, request_id: str | None = None) -> list[OrgContext]:
    """Every clinic (organisation) where this person is an active member with pet-owner rights."""
    with user_tx(p.user_id) as db:
        org_ids = db.execute(text("""
            select m.org_id from app.memberships m join app.organisations o on o.id = m.org_id
            where m.user_id = :u and m.status = 'active' and 'pet.own' = any(m.capabilities)
            order by o.name"""), {"u": p.user_id}).scalars().all()
    ctxs = []
    for org_id in org_ids:
        try:
            ctxs.append(load_org_context(p, org_id, request_id))
        except Forbidden:
            continue
    return ctxs


def elevated(ctx: OrgContext, *caps: Cap) -> OrgContext:
    """A copy of ``ctx`` with extra capabilities for one reused command, used only after an ownership check."""
    return dataclasses.replace(ctx, capabilities=ctx.capabilities | {c.value for c in caps})


def owns(db: Session, user_id: UUID, animal_id: UUID) -> bool:
    return bool(db.execute(text(f"""select exists (select 1 from app.animal_caregivers c join app.animals a
                                     on a.id = c.animal_id where c.animal_id = :a and {LIVE_OWNER}
                                     and a.profile_state not in ('archived','merged_alias'))"""),  # noqa: S608
                           {"a": animal_id, "u": user_id}).scalar())


def owned_context(p: Principal, animal_id: UUID, request_id: str | None = None) -> OrgContext:
    """The clinic context in which the caller owns this pet; 404 otherwise (no hint that the pet exists)."""
    for ctx in owner_contexts(p, request_id):
        with ctx.tx() as db:
            if owns(db, ctx.user_id, animal_id):
                return ctx
    raise NotFound("Pet not found.", code="pet_not_found")


def _own_media(db: Session, ctx: OrgContext, media_ids: list[UUID], field: str) -> None:
    for media_id in media_ids:
        media = db.get(MediaAsset, media_id)
        if media is None or media.uploader_user_id != ctx.user_id:
            raise Unprocessable("A file is missing.", fields=[FieldError(field=field, code="media_not_found",
                                                                         message="File not found.")])


# ---- reads -------------------------------------------------------------------------------------------------------

def photo_urls(rows: list[Any]) -> dict[str, str]:
    return animals._photo_urls(rows)  # shared helper for signed thumbnail links


def _card(row: Any, ctx: OrgContext, events: list[Any], today: date, urls: dict[str, str]) -> dict[str, Any]:
    thumb = (row.photo_derivatives or {}).get("thumb") if row.photo_media_id else None
    return {"id": row.id, "reference_code": row.reference_code, "name": row.name, "species": row.species,
            "sex": row.sex, "date_of_birth": row.date_of_birth, "age_band": row.age_band,
            "clinic_org_id": ctx.org_id, "clinic_name": ctx.org_name, "photo_url": urls.get(thumb) if thumb else None,
            "status": reminders.status_for(events, today),
            "awaiting_verification": sum(1 for e in events if e.state == "submitted"), "is_demo": row.is_demo}


def list_pets(p: Principal, request_id: str | None = None) -> list[PetCardOut]:
    out: list[PetCardOut] = []
    for ctx in owner_contexts(p, request_id):
        with ctx.tx() as db:
            today, _ = reminders.org_today(db, ctx.org_id, ctx.timezone)
            rows = db.execute(text(_PETS + " order by a.created_at"), {"u": ctx.user_id}).all()
            events = reminders.events_by_animal(db, [r.id for r in rows])
            urls = photo_urls(rows)
            out.extend(PetCardOut(**_card(r, ctx, events[r.id], today, urls)) for r in rows)
    return out


def _verification(row: Any) -> str:
    if row.state == "verified":
        return "verified_by_vet"
    if row.state == "submitted":
        return "entered_by_owner_unverified" if row.source_type == "owner_entry" else "submitted_unverified"
    return str(row.state)


def visible_reminders(db: Session, ctx: OrgContext, today: date, animal_id: UUID | None = None) -> list[ReminderOut]:
    """Reminders to show the owner today: per pet, vaccine and due date, the latest kind that has appeared."""
    rows = db.execute(text("""
        select r.*, coalesce(a.nickname, a.reference_code) as pet_name from app.vaccination_reminders r
        join app.animals a on a.id = r.animal_id
        where r.owner_user_id = :u and r.state = 'pending' and (cast(:a as uuid) is null or r.animal_id = :a)
          and a.profile_state not in ('archived','merged_alias')
        order by r.due_on"""), {"u": ctx.user_id, "a": animal_id}).all()
    groups: dict[tuple[Any, ...], list[Any]] = {}
    for r in rows:
        groups.setdefault((r.animal_id, r.vaccine_name, r.due_on), []).append(r)
    out = []
    for group in groups.values():
        r = reminders.current_reminder(group, today)
        if r is None:
            continue
        preview = reminders.preview_texts(r.pet_name, r.vaccine_name, r.due_on, ctx.org_name, today)
        out.append(ReminderOut(id=r.id, pet_id=r.animal_id, pet_name=r.pet_name, clinic_org_id=ctx.org_id,
                               clinic_name=ctx.org_name, vaccine=r.vaccine_name, due_on=r.due_on, kind=r.kind,
                               days_until_due=(r.due_on - today).days, state=r.state, snoozed_until=r.snoozed_until,
                               preview=ReminderPreviewOut(**preview)))
    return sorted(out, key=lambda x: x.due_on)


def pet_detail(p: Principal, animal_id: UUID, request_id: str | None = None) -> PetDetailOut:
    ctx = owned_context(p, animal_id, request_id)
    with ctx.tx() as db:
        today, offset = reminders.org_today(db, ctx.org_id, ctx.timezone)
        row = db.execute(text(_PETS + " and a.id = :a"), {"u": ctx.user_id, "a": animal_id}).one()
        events = reminders.events_by_animal(db, [animal_id])[animal_id]
        timeline = [TimelineEntryOut(event_id=e.id, vaccine=e.vaccine, administered_on=e.administered_on,
                                     clinic_name=ctx.org_name, given_by=e.administered_by_name,
                                     verification=_verification(e), next_due_on=e.next_review_on,
                                     next_due_source=e.next_review_source, certificates=e.certificates,
                                     note=e.review_reason if e.state in ("rejected", "needs_correction") else None)
                    for e in events if e.state != "draft"]
        card = _card(row, ctx, events, today, photo_urls([row]))
        return PetDetailOut(**card, today=today, demo_offset_days=offset, timeline=timeline,
                            reminders=visible_reminders(db, ctx, today, animal_id))


def clinics(p: Principal, request_id: str | None = None) -> list[ClinicOut]:
    return [ClinicOut(org_id=c.org_id, name=c.org_name, is_member=True) for c in owner_contexts(p, request_id)]


def products(p: Principal, animal_id: UUID, request_id: str | None = None) -> list[ProductOptionOut]:
    """Vaccines this pet's clinic records, with any demo schedule template (labelled as such)."""
    ctx = owned_context(p, animal_id, request_id)
    with ctx.tx() as db:
        species = db.execute(text("select species from app.animals where id = :a"), {"a": animal_id}).scalar()
        rows = db.execute(text("""select id, name, template_interval_days, template_label from app.vaccine_products
                                  where active and :s = any(species) order by name"""), {"s": species}).all()
    return [ProductOptionOut(id=r.id, name=r.name, template_interval_days=r.template_interval_days,
                             template_label=r.template_label) for r in rows]


# ---- commands ----------------------------------------------------------------------------------------------------

def create_pet(p: Principal, data: PetCreate, request_id: str | None = None) -> UUID:
    ctx = next((c for c in owner_contexts(p, request_id) if c.org_id == data.clinic_org_id), None)
    if ctx is None:
        raise Forbidden("You can register pets only with clinics you are a member of.", code="not_a_member")
    with ctx.tx() as db:
        today = datetime.now(ZoneInfo(ctx.timezone)).date()
        if data.date_of_birth and data.date_of_birth > today:
            raise Unprocessable("The date of birth cannot be in the future.",
                                fields=[FieldError(field="date_of_birth", code="date_in_future",
                                                   message="Date is in the future.")])
        if data.photo_media_id:
            _own_media(db, ctx, [data.photo_media_id], "photo_media_id")
        # Reuse the registry command for the pet record; the caller gets no registry-wide rights.
        act = elevated(ctx, Cap.ANIMAL_WRITE, Cap.OBSERVATION_WRITE)
        animal_id = animals.create_animal(
            db, act, AnimalCreate(species=data.species, nickname=data.name, sex=data.sex, age_band=data.age_band,
                                  ownership_category="owned"),
            source_reference="Registered by the pet owner")
        animal = db.get(Animal, animal_id)
        assert animal is not None
        animal.date_of_birth = data.date_of_birth
        db.add(AnimalCaregiver(org_id=ctx.org_id, created_by=ctx.user_id, animal_id=animal_id, relationship="owner",
                               linked_user_id=ctx.user_id))
        db.flush()
        if data.photo_media_id:
            animals.create_observation(db, act, ObservationCreate(
                animal_id=animal_id, observed_on=today, time_precision="day", media_ids=[data.photo_media_id],
                notes="Profile photo added by the owner"), audit=False)
        record_audit(db, ctx, "pet.registered", "animal", animal_id, {"by": "owner"})
    return animal_id


def _submit_owner_record(db: Session, ctx: OrgContext, animal_id: UUID, data: OwnerVaccinationIn) -> UUID:
    if data.product_id is None and not (data.product_text or "").strip():
        raise Unprocessable("Choose the vaccine.", fields=[FieldError(field="product_id", code="required",
                                                                     message="Choose the vaccine.")])
    real_today = datetime.now(ZoneInfo(ctx.timezone)).date()
    if data.administered_on > real_today:
        raise Unprocessable("The vaccination date cannot be in the future.",
                            fields=[FieldError(field="administered_on", code="date_in_future",
                                               message="Date is in the future.")])
    _own_media(db, ctx, data.certificate_media_ids, "certificate_media_ids")
    return vaccinations.submit(db, elevated(ctx, Cap.VACCINATION_SUBMIT), VaccinationCreate(
        animal_id=animal_id, date_precision="day", administered_on=data.administered_on,
        product_id=data.product_id, product_text=None if data.product_id else data.product_text,
        administered_by_name=data.given_by, source_type="owner_entry",
        source_reference="Entered by the pet owner", evidence_media_ids=data.certificate_media_ids))


def submit_owner_record(p: Principal, animal_id: UUID, data: OwnerVaccinationIn,
                        request_id: str | None = None) -> UUID:
    """An owner-entered vaccination (with certificate). Always unverified; it goes to the clinic's vet workbench."""
    ctx = owned_context(p, animal_id, request_id)
    with ctx.tx() as db:
        return _submit_owner_record(db, ctx, animal_id, data)


# ---- reminders ---------------------------------------------------------------------------------------------------

def my_reminders(p: Principal, request_id: str | None = None) -> list[ReminderOut]:
    out: list[ReminderOut] = []
    for ctx in owner_contexts(p, request_id):
        with ctx.tx() as db:
            today, _ = reminders.org_today(db, ctx.org_id, ctx.timezone)
            out.extend(visible_reminders(db, ctx, today))
    return sorted(out, key=lambda r: r.due_on)


def _find_reminder(p: Principal, reminder_id: UUID, request_id: str | None) -> tuple[OrgContext, Any]:
    for ctx in owner_contexts(p, request_id):
        with ctx.tx() as db:
            r = db.execute(text("""select r.*, coalesce(a.nickname, a.reference_code) as pet_name
                                   from app.vaccination_reminders r join app.animals a on a.id = r.animal_id
                                   where r.id = :id and r.owner_user_id = :u"""),
                           {"id": reminder_id, "u": ctx.user_id}).one_or_none()
            if r is not None and owns(db, ctx.user_id, r.animal_id):
                return ctx, r
    raise NotFound("Reminder not found.", code="reminder_not_found")


_GROUP = "animal_id = :a and vaccine_name = :v and due_on = :d and state = 'pending'"


def snooze(p: Principal, reminder_id: UUID, days: int, request_id: str | None = None) -> None:
    ctx, r = _find_reminder(p, reminder_id, request_id)
    with ctx.tx() as db:
        today, _ = reminders.org_today(db, ctx.org_id, ctx.timezone)
        db.execute(text(f"update app.vaccination_reminders set snoozed_until = :s where {_GROUP}"),  # noqa: S608
                   {"s": today + timedelta(days=days), "a": r.animal_id, "v": r.vaccine_name, "d": r.due_on})
        record_audit(db, ctx, "reminder.snoozed", "vaccination_reminder", r.id, {"days": days})


def mark_done(p: Principal, reminder_id: UUID, data: OwnerVaccinationIn, request_id: str | None = None) -> UUID:
    """The owner reports the vaccination was given, with a certificate. The reminders for this due date stop; the
    record stays unverified until the clinic's vet reviews it (a rejection brings the reminders back). Returns the
    pet's id."""
    ctx, r = _find_reminder(p, reminder_id, request_id)
    with ctx.tx() as db:
        event_id = _submit_owner_record(db, ctx, r.animal_id, data)
        db.execute(text(f"update app.vaccination_reminders set state = 'done', done_event_id = :e "  # noqa: S608
                        f"where {_GROUP}"), {"e": event_id, "a": r.animal_id, "v": r.vaccine_name, "d": r.due_on})
        record_audit(db, ctx, "reminder.done", "vaccination_reminder", r.id, {"event_id": str(event_id)})
    return r.animal_id  # type: ignore[no-any-return]


def reminder_ics(p: Principal, reminder_id: UUID, request_id: str | None = None) -> tuple[str, str]:
    ctx, r = _find_reminder(p, reminder_id, request_id)
    body = reminders.ics_event(f"{r.animal_id}-{r.due_on:%Y%m%d}", r.pet_name, r.vaccine_name, r.due_on,
                               ctx.org_name)
    safe = "".join(ch for ch in r.pet_name if ch.isascii() and ch.isalnum()) or "pet"
    return body, f"{safe}-vaccination-{r.due_on:%Y-%m-%d}.ics"
