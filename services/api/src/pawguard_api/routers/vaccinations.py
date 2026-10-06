from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Header, Query
from fastapi.responses import JSONResponse

from pawguard_api.capabilities import Cap
from pawguard_api.contracts import ReviewCreate, VaccinationAmend, VaccinationCreate, VaccinationOut, VaccinationPage
from pawguard_api.deps import CurrentOrg
from pawguard_api.domain import idempotency, vaccinations

router = APIRouter(prefix="/api/v1", tags=["vaccinations"])
IdemKey = Annotated[str | None, Header(alias="Idempotency-Key")]

StateFilter = Literal["draft", "submitted", "verified", "rejected", "needs_correction", "superseded"]


@router.get("/vaccination-events", response_model=VaccinationPage, summary="List vaccination records")
def list_events(ctx: CurrentOrg, animal_id: UUID | None = None,
                state: Annotated[list[StateFilter] | None, Query()] = None, submitted_by_me: bool = False,
                cursor: Annotated[str | None, Query(max_length=300)] = None,
                limit: Annotated[int, Query(ge=1, le=100)] = 25) -> VaccinationPage:
    """Permission: ``animal.read``."""
    with ctx.tx() as db:
        items, nxt = vaccinations.list_events(db, ctx, animal_id=animal_id, states=state,
                                              submitted_by_me=submitted_by_me, cursor=cursor, limit=limit)
    return VaccinationPage(items=items, next_cursor=nxt)


@router.get("/vaccination-review-queue", response_model=VaccinationPage, summary="Records awaiting review")
def review_queue(ctx: CurrentOrg, cursor: Annotated[str | None, Query(max_length=300)] = None,
                 limit: Annotated[int, Query(ge=1, le=100)] = 25) -> VaccinationPage:
    """Permission: ``vaccination.review`` with an approved ``veterinary_review`` professional authority. Oldest
    first; the reviewer's own submissions are excluded."""
    ctx.require(Cap.VACCINATION_REVIEW)
    with ctx.tx() as db:
        items, nxt = vaccinations.list_events(db, ctx, animal_id=None, states=None, submitted_by_me=False,
                                              cursor=cursor, limit=limit, review_queue=True)
    return VaccinationPage(items=items, next_cursor=nxt)


@router.post("/vaccination-events", status_code=201, response_model=VaccinationOut,
             summary="Submit vaccination evidence for review")
def submit(body: VaccinationCreate, ctx: CurrentOrg, idempotency_key: IdemKey = None) -> JSONResponse:
    """Permission: ``vaccination.submit``. The record is created as ``submitted`` (or ``draft``) — never
    ``verified``. A state cannot be supplied. Supports ``Idempotency-Key`` and ``client_operation_id`` so a
    retried or replayed submission never creates a second administration."""
    route = "POST /vaccination-events"
    with ctx.tx() as db:
        replay = idempotency.claim(db, ctx, route, idempotency_key, body.model_dump(mode="json"))
        if replay:
            return JSONResponse(replay.body, status_code=replay.status_code)
        event_id = vaccinations.submit(db, ctx, body)
        db.flush()
        payload = vaccinations.get_event(db, ctx, event_id).model_dump(mode="json")
        idempotency.store(db, ctx, route, idempotency_key, 201, payload, "vaccination_event", event_id)
    return JSONResponse(payload, status_code=201)


@router.get("/vaccination-events/{event_id}", response_model=VaccinationOut, summary="Vaccination record detail")
def get_event(event_id: UUID, ctx: CurrentOrg) -> VaccinationOut:
    """Permission: ``animal.read``. Includes evidence (short-lived links for approved files) and review history."""
    with ctx.tx() as db:
        return vaccinations.get_event(db, ctx, event_id)


@router.post("/vaccination-events/{event_id}/reviews", response_model=VaccinationOut,
             summary="Verify, reject or request correction")
def review(event_id: UUID, body: ReviewCreate, ctx: CurrentOrg) -> VaccinationOut:
    """Permission: ``vaccination.review`` + approved ``veterinary_review`` authority + a live session. The reviewer
    cannot be the submitter. Requires the event's ``row_version``; concurrent reviews return 409. Rejection and
    correction requests need a reason; a correction request assigns a follow-up task to the submitter."""
    with ctx.tx() as db:
        vaccinations.review(db, ctx, event_id, body)
        db.flush()
        return vaccinations.get_event(db, ctx, event_id)


@router.post("/vaccination-events/{event_id}/amendments", status_code=201, response_model=VaccinationOut,
             summary="Submit a corrected record")
def amend(event_id: UUID, body: VaccinationAmend, ctx: CurrentOrg) -> JSONResponse:
    """Permission: ``vaccination.submit`` (original submitter) or ``task.manage``. Only for records marked
    ``needs_correction`` or drafts. Creates a new record that supersedes the old one; nothing is deleted."""
    with ctx.tx() as db:
        new_id = vaccinations.amend(db, ctx, event_id, body)
        db.flush()
        payload = vaccinations.get_event(db, ctx, new_id).model_dump(mode="json")
    return JSONResponse(payload, status_code=201)
