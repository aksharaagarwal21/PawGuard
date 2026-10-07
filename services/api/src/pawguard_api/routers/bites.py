"""'This pet bit someone': public bite mode and reports, private reporter/doctor links, owner check-ins, clinic view."""

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Request, Response

from pawguard_api.bite_contracts import (
    BitePetOut,
    BiteReportCreatedOut,
    BiteReportIn,
    CheckinIn,
    ClinicBiteCaseOut,
    DisputeIn,
    NewDoctorLinkOut,
    OwnerCaseOut,
    RevokedOut,
    ShareViewOut,
)
from pawguard_api.deps import CurrentOrg, CurrentPrincipal
from pawguard_api.domain import bites
from pawguard_api.settings import get_settings

router = APIRouter(prefix="/api/v1", tags=["bite check"])


def _private(response: Response) -> None:
    response.headers["cache-control"] = "no-store"
    response.headers["x-robots-tag"] = "noindex"
    response.headers["referrer-policy"] = "no-referrer"


def _rid(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def _send(tasks: BackgroundTasks, emails: bites.Emails | None) -> None:
    if emails:
        contacts, subject, body = emails
        tasks.add_task(bites.send_reporter_emails, contacts, subject, body)


# ---- public ------------------------------------------------------------------------------------------------------

@router.get("/public/cards/{token}/bite", response_model=BitePetOut, summary="Bite mode: the pet's vaccination proof")
def bite_pet(token: str, response: Response) -> BitePetOut:
    """Permission: public (the card's random token). Pet name, species, clinic contact and the latest verified rabies
    record with its signed certificate — nothing about the owner or any location."""
    _private(response)
    return BitePetOut(**bites.bite_pet(token))


@router.post("/public/cards/{token}/bites", status_code=201, response_model=BiteReportCreatedOut,
             summary="Report a bite (no account)")
def report_bite(token: str, body: BiteReportIn, request: Request, response: Response,
                tasks: BackgroundTasks) -> BiteReportCreatedOut:
    """Permission: public. Starts the 10-day observation (or joins it if the same bite was already reported) and
    returns a private tracking link once. Limits: 3 per client per hour, 5 per pet per day. The email is kept only
    with consent, sealed, and never shown to the owner unless the reporter chose to share it."""
    _private(response)
    ip = request.headers.get("x-pawguard-client-ip") or (request.client.host if request.client else None)
    out = bites.create_report(token, body.model_dump(), ip)
    path = f"/bite/{out['token']}"
    if out["contact"]:
        pet = bites.bite_pet(token)["pet_name"]
        subject, text_ = bites.tracking_email(out["reference"], f"{get_settings().public_app_url}/en{path}", pet,
                                              body.bite_date)
        tasks.add_task(bites.send_reporter_emails, [(out["reference"], out["contact"])], subject, text_)
    return BiteReportCreatedOut(reference=out["reference"], tracking_path=path, duplicate=out["duplicate"],
                                contact_saved=bool(out["contact"]))


@router.get("/public/bites/{token}", response_model=ShareViewOut, summary="Private bite report page (reporter/doctor)")
def share_view(token: str, response: Response) -> ShareViewOut:
    """Permission: the private link's token. Expired or turned-off links return 404. Every view is logged."""
    _private(response)
    return ShareViewOut(**bites.share_view(token))


@router.post("/public/bites/{token}/doctor-links", status_code=201, response_model=NewDoctorLinkOut,
             summary="Make a read-only link for a doctor (30 days)")
def doctor_link(token: str, response: Response) -> NewDoctorLinkOut:
    """Permission: the reporter's private link. At most 5 active doctor links; each expires after 30 days."""
    _private(response)
    return NewDoctorLinkOut(**bites.new_doctor_link(token))


@router.post("/public/bites/{token}/doctor-links/revoke", response_model=RevokedOut,
             summary="Turn off all doctor links")
def revoke_doctor_links(token: str, response: Response) -> RevokedOut:
    """Permission: the reporter's private link. Turned-off links stop working at once."""
    _private(response)
    return RevokedOut(revoked=bites.revoke_doctor_links(token))


# ---- owner -------------------------------------------------------------------------------------------------------

@router.get("/my/bites", response_model=list[OwnerCaseOut], summary="Bite reports about my pets")
def my_bites(p: CurrentPrincipal, request: Request) -> list[OwnerCaseOut]:
    """Permission: pet owner (own pets only). Reporters' contact details appear only if they chose to share them."""
    return [OwnerCaseOut(**c) for c in bites.my_cases(p, _rid(request))]


@router.get("/my/bites/{period_id}", response_model=OwnerCaseOut, summary="One bite report and its daily updates")
def my_bite(period_id: UUID, p: CurrentPrincipal, request: Request) -> OwnerCaseOut:
    """Permission: pet owner (own pets only)."""
    return OwnerCaseOut(**bites.my_case(p, period_id, _rid(request)))


@router.post("/my/bites/{period_id}/checkins", response_model=OwnerCaseOut, summary="Today's update on my pet")
def checkin(period_id: UUID, body: CheckinIn, p: CurrentPrincipal, request: Request,
            tasks: BackgroundTasks) -> OwnerCaseOut:
    """Permission: pet owner. One update per day (changing it the same day replaces it). Anything other than
    "normal" is flagged at once for the reporter, the doctor link and the clinic."""
    case, emails = bites.checkin(p, period_id, body.state, body.note, _rid(request))
    _send(tasks, emails)
    return OwnerCaseOut(**case)


@router.post("/my/bites/{period_id}/dispute", response_model=OwnerCaseOut, summary="Dispute a bite report")
def dispute(period_id: UUID, body: DisputeIn, p: CurrentPrincipal, request: Request) -> OwnerCaseOut:
    """Permission: pet owner. The clinic sees the dispute; daily updates are still needed."""
    return OwnerCaseOut(**bites.dispute(p, period_id, body.reason, _rid(request)))


# ---- clinic ------------------------------------------------------------------------------------------------------

@router.get("/clinic/bites", response_model=list[ClinicBiteCaseOut], summary="Bite reports for this clinic's pets")
def clinic_bites(ctx: CurrentOrg) -> list[ClinicBiteCaseOut]:
    """Permission: clinic staff. Changes reported, missed days and disputes first. No reporter contact details."""
    with ctx.tx() as db:
        return [ClinicBiteCaseOut(**c) for c in bites.clinic_cases(db, ctx)]


@router.post("/clinic/bites/{period_id}/exams", response_model=ClinicBiteCaseOut,
             summary="Record a vet examination during observation")
def vet_exam(period_id: UUID, body: CheckinIn, ctx: CurrentOrg, tasks: BackgroundTasks) -> ClinicBiteCaseOut:
    """Permission: approved veterinary reviewer. Shown as "Vet-recorded" for today's observation day."""
    with ctx.tx() as db:
        case, emails = bites.vet_exam(db, ctx, period_id, body.state, body.note)
    _send(tasks, emails)
    return ClinicBiteCaseOut(**case)

