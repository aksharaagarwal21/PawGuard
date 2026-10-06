from uuid import UUID

from fastapi import APIRouter

from pawguard_api.contracts import (
    IdentityDecisionIn,
    IdentityFeedbackOut,
    IdentitySearchIn,
    IdentitySearchOut,
    IdentityStatusOut,
)
from pawguard_api.deps import CurrentOrg
from pawguard_api.domain import identity

router = APIRouter(prefix="/api/v1/identity", tags=["identity"])


@router.get("/status", response_model=IdentityStatusOut, summary="Is photo-based candidate search available?")
def get_status(ctx: CurrentOrg) -> IdentityStatusOut:
    """Permission: ``identity.search``. ``unavailable`` with a reason when no validated model exists; demo
    organisations may see ``research_preview`` (never offered for real records)."""
    with ctx.tx() as db:
        return identity.status(db, ctx)


@router.post("/searches", status_code=201, response_model=IdentitySearchOut, summary="Look for possible matches")
def create_search(body: IdentitySearchIn, ctx: CurrentOrg) -> IdentitySearchOut:
    """Permission: ``identity.search``. Queues a search of this organisation's gallery for an approved photo
    (optionally a chosen subject box). Returns ``pending``, or ``unavailable`` immediately."""
    with ctx.tx() as db:
        sid = identity.create_search(db, ctx, body.media_id, body.box)
        db.flush()
        return identity.get_search(db, ctx, sid)


@router.get("/searches/{search_id}", response_model=IdentitySearchOut, summary="Search result")
def get_search(search_id: UUID, ctx: CurrentOrg) -> IdentitySearchOut:
    """Permission: ``identity.search``. Candidates carry a rank and supporting photos — never a percentage."""
    with ctx.tx() as db:
        return identity.get_search(db, ctx, search_id)


@router.post("/searches/{search_id}/decision", response_model=IdentitySearchOut, summary="Record your decision")
def decide(search_id: UUID, body: IdentityDecisionIn, ctx: CurrentOrg) -> IdentitySearchOut:
    """Permission: ``identity.decide``. Same animal (choose it), new animal, or not sure. Recording a decision does
    not link anything by itself; the sighting or registration is created as a separate, explicit step."""
    with ctx.tx() as db:
        identity.decide(db, ctx, search_id, body.decision, body.animal_id, body.reason)
        db.flush()
        return identity.get_search(db, ctx, search_id)


@router.get("/feedback", response_model=IdentityFeedbackOut, summary="How people used the suggestions")
def get_feedback(ctx: CurrentOrg) -> IdentityFeedbackOut:
    """Permission: ``identity.search``. Counts of decisions relative to the suggestions (correction feedback)."""
    with ctx.tx() as db:
        return identity.feedback(db, ctx)
