"""Clinic staff views for pet vaccinations, and the demo date control.

Clinic staff see only pets of their own clinic (tenant isolation). The demo clock moves "today" for status and
reminders in a *demo* organisation only, when demo mode is on; stored dates are never changed.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.orm import Session

from pawguard_api.capabilities import Cap
from pawguard_api.deps import OrgContext
from pawguard_api.domain import reminders
from pawguard_api.domain.common import record_audit
from pawguard_api.errors import Forbidden
from pawguard_api.pet_contracts import DemoClockOut
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
