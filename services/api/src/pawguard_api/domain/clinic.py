"""Clinic staff views for pet vaccinations, and the demo date control.

Clinic staff see only pets of their own clinic (tenant isolation). The demo clock moves "today" for status and
reminders in a *demo* organisation only, when demo mode is on; stored dates are never changed.
"""

from datetime import datetime
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.orm import Session

from pawguard_api.capabilities import Cap
from pawguard_api.contracts import VaccinationCreate
from pawguard_api.deps import OrgContext
from pawguard_api.domain import reminders, vaccinations
from pawguard_api.domain.common import record_audit
from pawguard_api.errors import FieldError, Forbidden, NotFound, Unprocessable
from pawguard_api.models import VaccinationEvent
from pawguard_api.pet_contracts import (
    AwaitingRowOut,
    ClinicDashboardOut,
    ClinicPetRowOut,
    ClinicVaccinationIn,
    DemoClockOut,
    ProductOptionOut,
)
from pawguard_api.settings import get_settings


def require_staff(ctx: OrgContext) -> None:
    if not (ctx.can(Cap.ANIMAL_READ) or ctx.can(Cap.VACCINATION_REVIEW)):
        raise Forbidden("Clinic staff only.", code="staff_only")


def _demo_allowed(db: Session, ctx: OrgContext) -> bool:
    is_demo = db.execute(text("select is_demo from app.organisations where id = :o"), {"o": ctx.org_id}).scalar()
    return bool(is_demo) and get_settings().demo_mode


def demo_clock(db: Session, ctx: OrgContext) -> DemoClockOut:
    require_staff(ctx)
    today, offset = reminders.org_today(db, ctx.org_id, ctx.timezone)
    return DemoClockOut(offset_days=offset, today=today, real_today=datetime.now(ZoneInfo(ctx.timezone)).date())


def set_demo_clock(db: Session, ctx: OrgContext, offset_days: int) -> DemoClockOut:
    require_staff(ctx)
    if not _demo_allowed(db, ctx):
        raise Forbidden("The demo date can only be changed in a demo organisation with demo mode on.",
                        code="not_demo")
    db.execute(text("""insert into app.demo_clock (org_id, offset_days, set_by) values (:o, :d, :u)
                       on conflict (org_id) do update set offset_days = excluded.offset_days, set_by = excluded.set_by,
                         updated_at = now()"""), {"o": ctx.org_id, "d": offset_days, "u": ctx.user_id})
    record_audit(db, ctx, "demo_clock.set", "organisation", ctx.org_id, {"offset_days": offset_days})
    return demo_clock(db, ctx)


# ---- dashboard ---------------------------------------------------------------------------------------------------

_PETS = """
select a.id, coalesce(a.nickname, a.reference_code) as name, a.reference_code,
       exists (select 1 from app.animal_caregivers c where c.animal_id = a.id and c.relationship = 'owner'
               and c.linked_user_id is not null and (c.valid_to is null or c.valid_to > current_date)) as owner_linked
from app.animals a
where a.ownership_category = 'owned' and a.profile_state not in ('archived','merged_alias')
order by coalesce(a.nickname, a.reference_code)
"""


def dashboard(db: Session, ctx: OrgContext) -> ClinicDashboardOut:
    """Registered pets of this clinic only (row security keeps other clinics out)."""
    ctx.require(Cap.ANIMAL_READ)
    today, offset = reminders.org_today(db, ctx.org_id, ctx.timezone)
    pets = db.execute(text(_PETS)).all()
    events = reminders.events_by_animal(db, [p.id for p in pets])
    rows = [ClinicPetRowOut(pet_id=p.id, pet_name=p.name, reference_code=p.reference_code,
                            status=reminders.status_for(events[p.id], today), owner_linked=p.owner_linked)
            for p in pets]
    by_due = sorted((r for r in rows if r.status.days_until_due is not None),
                    key=lambda r: r.status.days_until_due or 0)
    awaiting = db.execute(text("""
        select e.id, e.animal_id, coalesce(a.nickname, a.reference_code) as pet_name, e.administered_on,
               e.submitted_at, e.source_type, coalesce(p.name, e.product_text, 'Vaccine') as vaccine
        from app.animal_vaccination_events e join app.animals a on a.id = e.animal_id
        left join app.vaccine_products p on p.id = e.product_id
        where e.state = 'submitted' and a.ownership_category = 'owned'
        order by e.submitted_at""")).all()
    products = db.execute(text("""select id, name, template_interval_days, template_label from app.vaccine_products
                                  where active order by name""")).all()
    return ClinicDashboardOut(
        today=today, demo_offset_days=offset, demo_clock_available=_demo_allowed(db, ctx), pets_total=len(rows),
        up_to_date=sum(1 for r in rows if r.status.status == "up_to_date"),
        due_this_week=[r for r in by_due if r.status.status == "due_soon" and (r.status.days_until_due or 0) <= 7],
        due_soon=[r for r in by_due if r.status.status == "due_soon" and (r.status.days_until_due or 0) > 7],
        overdue=[r for r in by_due if r.status.status == "overdue"],
        awaiting_verification=[
            AwaitingRowOut(event_id=e.id, pet_id=e.animal_id, pet_name=e.pet_name, vaccine=e.vaccine,
                           administered_on=e.administered_on, submitted_at=e.submitted_at,
                           entered_by_owner=e.source_type == "owner_entry") for e in awaiting],
        no_verified_record=sum(1 for r in rows if r.status.status == "no_verified_record"),
        unverified_only=sum(1 for r in rows if r.status.status == "unverified_record"),
        pets=rows,
        products=[ProductOptionOut(id=p.id, name=p.name, template_interval_days=p.template_interval_days,
                                   template_label=p.template_label) for p in products])


# ---- clinic record -----------------------------------------------------------------------------------------------

def record_clinic_vaccination(db: Session, ctx: OrgContext, data: ClinicVaccinationIn) -> UUID:
    """A vaccination given at the clinic, entered by an authorised vet: their own primary record, so it is stored as
    verified (no separate review; the database forbids reviewing one's own record). The vet's next due date wins;
    without one, the product's demo template (if any) applies. Reminders are rescheduled in this transaction."""
    ctx.require(Cap.VACCINATION_REVIEW)  # capability AND approved veterinary_review scope
    ctx.require_live_session(db)
    exists = db.execute(text("select 1 from app.animals where id = :a"), {"a": data.animal_id}).scalar()
    if exists is None:
        raise NotFound("Pet not found.", code="pet_not_found")
    real_today = datetime.now(ZoneInfo(ctx.timezone)).date()
    if data.administered_on > real_today:
        raise Unprocessable("The vaccination date cannot be in the future.",
                            fields=[FieldError(field="administered_on", code="date_in_future",
                                               message="Date is in the future.")])
    if data.next_due_on is not None and data.next_due_on <= data.administered_on:
        raise Unprocessable("The next due date must be after the vaccination date.",
                            fields=[FieldError(field="next_due_on", code="due_before_administration",
                                               message="Next due date is not after the vaccination date.")])
    vet_name = db.execute(text("select preferred_name from app.user_profiles where user_id = :u"),
                          {"u": ctx.user_id}).scalar()
    event_id = vaccinations.submit(db, ctx, VaccinationCreate(
        animal_id=data.animal_id, date_precision="day", administered_on=data.administered_on,
        product_id=data.product_id, lot_text=data.lot_text, administered_by_name=vet_name,
        source_type="clinic_record", source_reference="Recorded at the clinic"))
    event: Any = db.get(VaccinationEvent, event_id)
    event.state = "verified"
    event.verified_by = ctx.user_id
    event.verified_at = text("now()")
    db.flush()
    reminders.after_review(db, ctx.org_id, event, "verified", data.next_due_on)
    record_audit(db, ctx, "vaccination_event.recorded_at_clinic", "vaccination_event", event_id,
                 {"animal_id": str(data.animal_id), "next_due_source": event.next_review_source})
    return event_id
