"""Lost pets: owner reports and private finder <-> owner conversations (finders need no account)."""

from uuid import UUID

from fastapi import APIRouter, Response

from pawguard_api.deps import CurrentPrincipal
from pawguard_api.domain import lost
from pawguard_api.notify_contracts import (
    FinderStartIn,
    FinderStartOut,
    FinderThreadOut,
    LostReportIn,
    LostReportOut,
    LostStatusOut,
    MessageIn,
)

router = APIRouter(prefix="/api/v1", tags=["lost pets"])


@router.post("/my/pets/{pet_id}/lost", status_code=204, summary="Report my pet lost")
def report_lost(pet_id: UUID, body: LostReportIn, p: CurrentPrincipal) -> Response:
    """Permission: the pet's owner. The public QR card then shows "lost" and lets a finder write privately."""
    lost.report_lost(p, pet_id, body.last_seen_on, body.area_text, body.note)
    return Response(status_code=204)


@router.post("/my/pets/{pet_id}/found", status_code=204, summary="Mark my pet found")
def mark_found(pet_id: UUID, p: CurrentPrincipal) -> Response:
    """Permission: the pet's owner. Closes the conversations."""
    lost.mark_found(p, pet_id)
    return Response(status_code=204)


@router.get("/my/lost", response_model=list[LostReportOut], summary="My lost reports and finder messages")
def my_lost(p: CurrentPrincipal) -> list[LostReportOut]:
    """Permission: owner. Only conversations about the caller's own pets."""
    return [LostReportOut(**r) for r in lost.owner_view(p)]


@router.post("/my/lost/threads/{thread_id}/reply", status_code=204, summary="Reply to a finder")
def reply(thread_id: UUID, body: MessageIn, p: CurrentPrincipal) -> Response:
    """Permission: the pet's owner. Shown to the finder as "Owner" - no name or contact details."""
    lost.owner_reply(p, thread_id, body.message)
    return Response(status_code=204)


@router.post("/my/lost/threads/{thread_id}/read", status_code=204, summary="Mark a conversation read")
def read(thread_id: UUID, p: CurrentPrincipal) -> Response:
    """Permission: the pet's owner."""
    lost.mark_read(p, thread_id)
    return Response(status_code=204)


@router.get("/public/cards/{token}/lost", response_model=LostStatusOut, summary="Is this pet reported lost?")
def lost_status(token: str, response: Response) -> LostStatusOut:
    """Permission: public (QR card)."""
    response.headers["cache-control"] = "no-store"
    return LostStatusOut(**lost.lost_status(token))


@router.post("/public/cards/{token}/found", response_model=FinderStartOut, status_code=201,
             summary="I found this pet: write privately to the owner")
def finder_start(token: str, body: FinderStartIn) -> FinderStartOut:
    """Permission: public, only while the pet is reported lost. Returns the finder's private conversation link token
    (keep it to read replies). Limits: 20 conversations per pet per day, 500 characters per message."""
    return FinderStartOut(conversation_token=lost.start(token, body.message, body.contact))


@router.get("/public/found/{token}", response_model=FinderThreadOut, summary="The finder's private conversation")
def finder_thread(token: str, response: Response) -> FinderThreadOut:
    """Permission: whoever holds the conversation link. Shows the pet's name and the messages, never the owner."""
    response.headers["cache-control"] = "no-store"
    response.headers["x-robots-tag"] = "noindex"
    return FinderThreadOut(**lost.thread(token))


@router.post("/public/found/{token}/messages", status_code=204, summary="Finder writes again")
def finder_post(token: str, body: MessageIn) -> Response:
    """Permission: whoever holds the conversation link; only while the pet is reported lost (30 a day)."""
    lost.post(token, body.message)
    return Response(status_code=204)
