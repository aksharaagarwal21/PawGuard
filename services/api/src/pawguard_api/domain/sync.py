"""Replay of changes made offline on a trusted device.

Every operation is applied with the sender's permissions *at sync time* (a revoked or narrowed membership is
refused, never replayed with old rights), inside its own savepoint so one refusal does not undo the others, and is
recorded once in ``sync_operations``:

- ``accepted``  — applied through the normal domain command (same validation, audit and outbox);
- ``conflict``  — the record changed on the server since the device read it; nothing is applied and the server's
  current state is returned so the person can decide;
- ``rejected``  — not allowed or not valid any more (e.g. permission removed, animal archived, wrong account).

Re-sending an operation that was already received returns the stored outcome with ``duplicate = true``.
"""

from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from pawguard_api.contracts import ObservationCreate, SyncBatchIn, SyncOperationIn, SyncResultOut, TaskTransition
from pawguard_api.deps import OrgContext
from pawguard_api.domain.animals import create_observation
from pawguard_api.domain.tasks import transition_task
from pawguard_api.errors import ApiError, Conflict, NotFound
from pawguard_api.models import SyncOperation


def replay(db: Session, ctx: OrgContext, batch: SyncBatchIn) -> list[SyncResultOut]:
    return [_one(db, ctx, batch.device_id, op) for op in batch.operations]


def _record(db: Session, ctx: OrgContext, device_id: str, op: SyncOperationIn, res: SyncResultOut) -> SyncResultOut:
    db.add(SyncOperation(
        org_id=ctx.org_id, created_by=ctx.user_id, operation_id=op.operation_id, device_id=device_id,
        actor_user_id=ctx.user_id, operation_type=op.operation_type,
        target_type="task" if op.operation_type == "task.transition" else "observation",
        target_id=res.target_id, base_row_version=op.base_row_version, state=res.state, result_code=res.result_code,
        result_detail={k: v for k, v in {"server_state": res.server_state,
                                          "server_row_version": res.server_row_version}.items() if v is not None},
        client_created_at=op.client_created_at))
    db.flush()
    return res


def _one(db: Session, ctx: OrgContext, device_id: str, op: SyncOperationIn) -> SyncResultOut:
    prior = db.execute(select(SyncOperation).where(SyncOperation.operation_id == op.operation_id)).scalar()
    if prior is not None:
        detail = prior.result_detail or {}
        return SyncResultOut(operation_id=op.operation_id, state=prior.state, duplicate=True,
                             result_code=prior.result_code, target_id=prior.target_id,
                             server_state=detail.get("server_state"),
                             server_row_version=detail.get("server_row_version"))
    if op.actor_user_id != ctx.user_id:
        return _record(db, ctx, device_id, op, SyncResultOut(
            operation_id=op.operation_id, state="rejected", result_code="actor_mismatch",
            message="This change was made by a different account on this device."))
    if op.org_id != ctx.org_id:
        return _record(db, ctx, device_id, op, SyncResultOut(
            operation_id=op.operation_id, state="rejected", result_code="wrong_organisation",
            message="This change belongs to another organisation. Switch organisation to send it."))
    sp = db.begin_nested()
    try:
        if op.operation_type == "task.transition":
            assert op.task is not None and op.target_id is not None
            current = db.execute(text("select state, row_version from app.field_tasks where id = :id"),
                                 {"id": op.target_id}).one_or_none()
            if current is None:
                raise NotFound("Task not found.", code="task_not_found")
            if current.row_version != op.base_row_version:
                sp.rollback()
                return _record(db, ctx, device_id, op, SyncResultOut(
                    operation_id=op.operation_id, state="conflict", result_code="changed_on_server",
                    message="Someone changed this task after your device saved it.", target_id=op.target_id,
                    server_state=current.state, server_row_version=current.row_version))
            transition_task(db, ctx, op.target_id, TaskTransition(action=op.task.action, note=op.task.note,
                                                                  row_version=op.base_row_version))
            target: UUID = op.target_id
        else:
            s = op.sighting
            assert s is not None
            target = create_observation(db, ctx, ObservationCreate(
                animal_id=s.animal_id, observed_on=s.observed_on, time_precision="day", area_id=s.area_id,
                notes=s.notes, field_task_id=s.field_task_id, client_operation_id=op.operation_id))
        sp.commit()
    except ApiError as exc:
        sp.rollback()
        state = "conflict" if isinstance(exc, Conflict) else "rejected"
        return _record(db, ctx, device_id, op, SyncResultOut(
            operation_id=op.operation_id, state=state, result_code=exc.code, message=exc.message,
            target_id=op.target_id))
    except DBAPIError:
        sp.rollback()
        return _record(db, ctx, device_id, op, SyncResultOut(
            operation_id=op.operation_id, state="rejected", result_code="invalid_data",
            message="The change could not be stored.", target_id=op.target_id))
    row_version = None
    if op.operation_type == "task.transition":
        row_version = db.execute(text("select row_version from app.field_tasks where id = :id"),
                                 {"id": target}).scalar()
    return _record(db, ctx, device_id, op, SyncResultOut(operation_id=op.operation_id, state="accepted",
                                                         target_id=target, server_row_version=row_version))


def resolve(db: Session, ctx: OrgContext, operation_id: UUID, resolution: str) -> None:
    """The person decided what to do with a conflict or refusal (kept for the record)."""
    row = db.execute(select(SyncOperation).where(SyncOperation.operation_id == operation_id,
                                                 SyncOperation.actor_user_id == ctx.user_id)).scalar()
    if row is None:
        raise NotFound("Sync record not found.", code="sync_operation_not_found")
    if row.state == "accepted":
        raise Conflict("This change was applied; nothing to resolve.", code="already_applied")
    row.resolved_at = text("now()")
    row.resolved_by = ctx.user_id
    row.result_detail = {**(row.result_detail or {}), "resolution": resolution}
