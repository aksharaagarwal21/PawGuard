from typing import Literal
from uuid import UUID

from fastapi import APIRouter

from pawguard_api.contracts import StrictModel, SyncBatchIn, SyncBatchOut
from pawguard_api.deps import CurrentOrg
from pawguard_api.domain import sync

router = APIRouter(prefix="/api/v1/sync", tags=["sync"])


class SyncResolveIn(StrictModel):
    resolution: Literal["discarded", "superseded"]


@router.post("/operations", response_model=SyncBatchOut, summary="Send changes made offline")
def send(body: SyncBatchIn, ctx: CurrentOrg) -> SyncBatchOut:
    """Each operation is replayed with the sender's *current* permissions and reported as accepted, conflict or
    rejected; already-received operations return their stored outcome (``duplicate``). Operations must belong to
    the signed-in account and the selected organisation."""
    with ctx.tx() as db:
        return SyncBatchOut(results=sync.replay(db, ctx, body))


@router.post("/operations/{operation_id}/resolve", status_code=204, summary="Record how a conflict was handled")
def resolve(operation_id: UUID, body: SyncResolveIn, ctx: CurrentOrg) -> None:
    """Only for your own operations that were not applied."""
    with ctx.tx() as db:
        sync.resolve(db, ctx, operation_id, body.resolution)
