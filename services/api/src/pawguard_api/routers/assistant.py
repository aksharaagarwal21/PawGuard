"""Ask PawGuard: the pet-owner assistant (Gemini free tier or local Ollama; off unless configured)."""

from fastapi import APIRouter

from pawguard_api.deps import CurrentPrincipal
from pawguard_api.domain import assistant
from pawguard_api.notify_contracts import AssistantIn, AssistantOut, AssistantStatusOut

router = APIRouter(prefix="/api/v1/my/assistant", tags=["assistant"])


@router.get("", response_model=AssistantStatusOut, summary="Is the assistant available?")
def get_status(p: CurrentPrincipal) -> AssistantStatusOut:
    """Permission: any signed-in user."""
    return AssistantStatusOut(**assistant.status())


@router.post("", response_model=AssistantOut, summary="Ask the assistant")
def ask(body: AssistantIn, p: CurrentPrincipal) -> AssistantOut:
    """Permission: pet owners. Sends only pet facts (name, species, status, vaccine, dates, clinic) and the
    conversation with emails and phone numbers removed. Never gives treatment advice; actions come from a fixed
    list. 20 questions an hour per person."""
    return AssistantOut(**assistant.ask(p, [m.model_dump() for m in body.messages], body.language))
