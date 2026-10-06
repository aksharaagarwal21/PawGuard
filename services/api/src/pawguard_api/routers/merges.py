from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from sqlalchemy import text

from pawguard_api.capabilities import Cap
from pawguard_api.contracts import MergeDecision, MergeOut, MergePreview, MergePropose
from pawguard_api.deps import CurrentOrg
from pawguard_api.domain import merges

router = APIRouter(prefix="/api/v1/animal-merges", tags=["merges"])


@router.get("", response_model=list[MergeOut], summary="List merge proposals")
def list_merges(ctx: CurrentOrg, state: Literal["proposed", "executed", "reversed", "rejected"] | None = None,
                limit: Annotated[int, Query(ge=1, le=100)] = 50) -> list[MergeOut]:
    """Permission: ``animal.read``. Newest first."""
    ctx.require(Cap.ANIMAL_READ)
    with ctx.tx() as db:
        ids = db.execute(text("select id from app.animal_merge_operations "
                              "where (cast(:s as text) is null or state = :s) order by created_at desc limit :n"),
                         {"s": state, "n": limit}).scalars().all()
        return [merges.merge_out(db, i) for i in ids]


@router.post("/preview", response_model=MergePreview, summary="Preview merging two profiles")
def preview(body: MergePropose, ctx: CurrentOrg) -> MergePreview:
    """Permission: ``animal.read``. Read-only: shows both profiles, how many linked records would move and any
    conflicting details."""
    with ctx.tx() as db:
        return merges.preview(db, ctx, body.source_animal_id, body.target_animal_id)


@router.post("", status_code=201, response_model=MergeOut, summary="Propose a merge")
def propose(body: MergePropose, ctx: CurrentOrg) -> JSONResponse:
    """Permission: ``animal.write`` or ``animal.merge``. Nothing changes until a different person approves."""
    with ctx.tx() as db:
        merge_id = merges.propose(db, ctx, body)
        db.flush()
        payload = merges.merge_out(db, merge_id).model_dump(mode="json")
    return JSONResponse(payload, status_code=201)


@router.get("/{merge_id}", response_model=MergeOut, summary="Merge detail")
def get(merge_id: UUID, ctx: CurrentOrg) -> MergeOut:
    """Permission: ``animal.read``."""
    ctx.require(Cap.ANIMAL_READ)
    with ctx.tx() as db:
        return merges.merge_out(db, merge_id)


@router.post("/{merge_id}/approve", response_model=MergeOut, summary="Approve and execute a merge")
def approve(merge_id: UUID, body: MergeDecision, ctx: CurrentOrg) -> MergeOut:
    """Permission: ``animal.merge`` + live session; must not be the proposer. Records every moved link."""
    with ctx.tx() as db:
        merges.execute(db, ctx, merge_id, body.reason)
        db.flush()
        return merges.merge_out(db, merge_id)


@router.post("/{merge_id}/reject", response_model=MergeOut, summary="Reject a proposed merge")
def reject(merge_id: UUID, body: MergeDecision, ctx: CurrentOrg) -> MergeOut:
    """Permission: ``animal.merge``."""
    with ctx.tx() as db:
        merges.reject(db, ctx, merge_id, body.reason)
        db.flush()
        return merges.merge_out(db, merge_id)


@router.post("/{merge_id}/reverse", response_model=MergeOut, summary="Reverse an executed merge")
def reverse(merge_id: UUID, body: MergeDecision, ctx: CurrentOrg) -> MergeOut:
    """Permission: ``animal.merge`` + live session. Moves back exactly the links recorded at execution."""
    with ctx.tx() as db:
        merges.reverse(db, ctx, merge_id, body.reason)
        db.flush()
        return merges.merge_out(db, merge_id)
