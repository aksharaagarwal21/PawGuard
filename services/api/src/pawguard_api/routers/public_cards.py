"""Public vaccination card behind a pet's QR code. No sign-in; the random token is the only key."""

from fastapi import APIRouter, Response

from pawguard_api.domain import petcards
from pawguard_api.pet_contracts import PublicCardOut

router = APIRouter(prefix="/api/v1/public", tags=["public"])


@router.get("/cards/{token}", response_model=PublicCardOut, summary="Public vaccination card")
def get_card(token: str, response: Response) -> PublicCardOut:
    """Permission: public. Unknown and revoked tokens both return 404. Shows the pet's name, species, photo, clinic
    name and verified vaccinations only — nothing about the owner or any location."""
    response.headers["cache-control"] = "no-store"
    response.headers["x-robots-tag"] = "noindex"
    return petcards.public_card(token)
