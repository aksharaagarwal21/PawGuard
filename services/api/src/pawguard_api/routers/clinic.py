"""Clinic staff: pet vaccination dashboard, clinic vaccination records and the demo date control."""

from fastapi import APIRouter

from pawguard_api.deps import CurrentOrg
from pawguard_api.domain import clinic
from pawguard_api.pet_contracts import ClinicDashboardOut, ClinicVaccinationIn, DemoClockIn, DemoClockOut

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


@router.get("/dashboard", response_model=ClinicDashboardOut, summary="Clinic pet vaccination dashboard")
def get_dashboard(ctx: CurrentOrg) -> ClinicDashboardOut:
    """Permission: ``animal.read``. This clinic's registered pets only: due this week, overdue, awaiting
    verification. Counts describe pets registered in this app, not population coverage."""
    with ctx.tx() as db:
        return clinic.dashboard(db, ctx)


@router.post("/vaccinations", status_code=201, response_model=ClinicDashboardOut,
             summary="Record a vaccination given at the clinic (vet)")
def record_vaccination(body: ClinicVaccinationIn, ctx: CurrentOrg) -> ClinicDashboardOut:
    """Permission: ``vaccination.review`` with an approved ``veterinary_review`` authority and a live session.
    Stored as verified (the vet's own record) with the vet's next due date, or the demo template if none."""
    with ctx.tx() as db:
        clinic.record_clinic_vaccination(db, ctx, body)
        db.flush()
        return clinic.dashboard(db, ctx)
