"""Demo-mode helpers. Every endpoint returns 404 unless demo mode is enabled (never in production)."""

from fastapi import APIRouter

from pawguard_api.contracts import Out
from pawguard_api.errors import NotFound
from pawguard_api.seed.accounts import ACCOUNTS
from pawguard_api.settings import get_settings

router = APIRouter(prefix="/api/v1/demo", tags=["demo"])


class DemoAccountOut(Out):
    email: str
    name: str
    description: str


@router.get("/accounts", response_model=list[DemoAccountOut], summary="Fictional demo accounts (demo mode only)")
def demo_accounts() -> list[DemoAccountOut]:
    """Permission: public, but only exists when ``PAWGUARD_DEMO_MODE=true`` outside production. Lists the fictional
    seed accounts (no passwords) for the development sign-in shortcuts."""
    if not get_settings().demo_mode:
        raise NotFound()
    return [DemoAccountOut(email=a.email, name=a.preferred_name, description=a.description) for a in ACCOUNTS]
