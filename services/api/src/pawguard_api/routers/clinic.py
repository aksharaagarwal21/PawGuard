"""Clinic staff: demo date control (and, later, the clinic vaccination dashboard)."""

from fastapi import APIRouter

from pawguard_api.deps import CurrentOrg
from pawguard_api.domain import clinic
from pawguard_api.pet_contracts import DemoClockIn, DemoClockOut

router = APIRouter(prefix="/api/v1/clinic", tags=["clinic"])


@router.get("/demo-clock", response_model=DemoClockOut, summary="Today's date for reminders (with any demo offset)")
def get_demo_clock(ctx: CurrentOrg) -> DemoClockOut:
    """Permission: clinic staff (``animal.read`` or ``vaccination.review``)."""
    with ctx.tx() as db:
        return clinic.demo_clock(db, ctx)


@router.put("/demo-clock", response_model=DemoClockOut, summary="Move the demo date (demo organisations only)")
def put_demo_clock(body: DemoClockIn, ctx: CurrentOrg) -> DemoClockOut:
    """Permission: clinic staff, in a demo organisation, with demo mode on. Changes only what "today" means for
    status and reminders in this organisation; stored dates are not changed. Audited."""
    with ctx.tx() as db:
        return clinic.set_demo_clock(db, ctx, body.offset_days)
