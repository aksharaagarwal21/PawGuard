"""Pet owners ("My pets"): only pets linked to the signed-in owner, across the clinics they belong to."""

from uuid import UUID

from fastapi import APIRouter, Request, Response

from pawguard_api.deps import CurrentPrincipal
from pawguard_api.domain import petcare
from pawguard_api.pet_contracts import (
    ClinicOut,
    OwnerVaccinationIn,
    PetCardOut,
    PetCreate,
    PetDetailOut,
    ProductOptionOut,
    ReminderOut,
    SnoozeIn,
)

router = APIRouter(prefix="/api/v1/my", tags=["pets"])


def _rid(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


@router.get("/pets", response_model=list[PetCardOut], summary="My pets with vaccination status")
def list_pets(p: CurrentPrincipal, request: Request) -> list[PetCardOut]:
    """Permission: ``pet.own`` in at least one clinic. Only pets linked to the caller as owner."""
    return petcare.list_pets(p, _rid(request))


@router.post("/pets", status_code=201, response_model=PetDetailOut, summary="Register my pet with a clinic")
def create_pet(body: PetCreate, p: CurrentPrincipal, request: Request) -> PetDetailOut:
    """Permission: ``pet.own`` in the chosen clinic. The pet is linked to the caller as owner."""
    pet_id = petcare.create_pet(p, body, _rid(request))
    return petcare.pet_detail(p, pet_id, _rid(request))


@router.get("/pets/{pet_id}", response_model=PetDetailOut, summary="My pet: status, timeline and reminders")
def get_pet(pet_id: UUID, p: CurrentPrincipal, request: Request) -> PetDetailOut:
    """Permission: the caller owns this pet; otherwise 404."""
    return petcare.pet_detail(p, pet_id, _rid(request))


@router.get("/pets/{pet_id}/vaccine-options", response_model=list[ProductOptionOut],
            summary="Vaccines my pet's clinic records")
def vaccine_options(pet_id: UUID, p: CurrentPrincipal, request: Request) -> list[ProductOptionOut]:
    """Permission: the caller owns this pet."""
    return petcare.products(p, pet_id, _rid(request))


@router.post("/pets/{pet_id}/vaccinations", status_code=201, response_model=PetDetailOut,
             summary="Add a past vaccination with a certificate (unverified until a vet reviews it)")
def add_vaccination(pet_id: UUID, body: OwnerVaccinationIn, p: CurrentPrincipal, request: Request) -> PetDetailOut:
    """Permission: the caller owns this pet. Creates an unverified owner-entered record that goes to the clinic's
    vet workbench. It never counts as verified until a vet verifies it."""
    petcare.submit_owner_record(p, pet_id, body, _rid(request))
    return petcare.pet_detail(p, pet_id, _rid(request))


@router.get("/clinics", response_model=list[ClinicOut], summary="Clinics I am registered with")
def my_clinics(p: CurrentPrincipal, request: Request) -> list[ClinicOut]:
    """Permission: any signed-in user (empty unless they hold ``pet.own`` somewhere)."""
    return petcare.clinics(p, _rid(request))


@router.get("/reminders", response_model=list[ReminderOut], summary="My vaccination reminders due today")
def reminders(p: CurrentPrincipal, request: Request) -> list[ReminderOut]:
    """Permission: owner. In-app reminders only; ``preview`` shows what an email/SMS would say (nothing is sent)."""
    return petcare.my_reminders(p, _rid(request))


@router.post("/reminders/{reminder_id}/snooze", status_code=204, summary="Snooze a reminder for 1 or 3 days")
def snooze(reminder_id: UUID, body: SnoozeIn, p: CurrentPrincipal, request: Request) -> Response:
    """Permission: the reminder's owner."""
    petcare.snooze(p, reminder_id, body.days, _rid(request))
    return Response(status_code=204)


@router.post("/reminders/{reminder_id}/done", status_code=201, response_model=PetDetailOut,
             summary="Mark a reminder done with a certificate")
def done(reminder_id: UUID, body: OwnerVaccinationIn, p: CurrentPrincipal, request: Request) -> PetDetailOut:
    """Permission: the reminder's owner. Records an unverified owner entry (with certificate) for the vet to review
    and stops the reminders for that due date. If the vet rejects it, the reminders come back."""
    pet_id = petcare.mark_done(p, reminder_id, body, _rid(request))
    return petcare.pet_detail(p, pet_id, _rid(request))


@router.get("/reminders/{reminder_id}/calendar.ics", summary="Calendar file for the due date",
            response_class=Response, responses={200: {"content": {"text/calendar": {}}}})
def calendar(reminder_id: UUID, p: CurrentPrincipal, request: Request) -> Response:
    """Permission: the reminder's owner. An all-day event on the due date (date only, no time zone shift)."""
    body, filename = petcare.reminder_ics(p, reminder_id, _rid(request))
    return Response(body, media_type="text/calendar; charset=utf-8",
                    headers={"content-disposition": f'attachment; filename="{filename}"'})
