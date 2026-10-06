"""Field tasks: unassigned → assigned → in_progress → completed, with blocked/cancelled branches.
Incomplete work always carries a reason. Assignees act on their own tasks; coordinators (task.manage) manage all."""

from typing import Any
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from pawguard_api.capabilities import Cap
from pawguard_api.contracts import AreaRef, TaskCreate, TaskOut, TaskTransition
from pawguard_api.deps import OrgContext
from pawguard_api.domain.animals import ensure_area, load_animal
from pawguard_api.domain.common import decode_cursor, emit, encode_cursor, expect_version, record_audit, require_reason
from pawguard_api.errors import Conflict, FieldError, Forbidden, NotFound, Unprocessable
from pawguard_api.models import FieldTask, Membership

# Teams the caller currently belongs to (team tasks count as "mine" for every current member).
_MY_TEAMS = ("select tm.team_id from app.team_members tm where tm.membership_id = :mid "
             "and (tm.valid_to is null or tm.valid_to >= current_date)")

# action → (allowed from states, resulting state, who: "assignee" | "manager" | "either")
TRANSITIONS: dict[str, tuple[set[str], str, str]] = {
    "assign": ({"unassigned", "assigned", "blocked"}, "assigned", "manager"),
    "start": ({"assigned", "blocked"}, "in_progress", "assignee"),
    "complete": ({"assigned", "in_progress"}, "completed", "assignee"),
    "block": ({"assigned", "in_progress"}, "blocked", "assignee"),
    "cancel": ({"unassigned", "assigned", "in_progress", "blocked"}, "cancelled", "manager"),
    "reopen": ({"completed", "cancelled"}, "assigned", "manager"),
}


def _member(db: Session, membership_id: UUID) -> Membership:
    m = db.execute(select(Membership).where(Membership.id == membership_id, Membership.status == "active")).scalar()
    if m is None:
        raise Unprocessable("Choose an active member of this organisation.",
                            fields=[FieldError(field="assignee_membership_id", code="invalid_reference",
                                               message="Not an active member.")])
    if "task.work" not in m.capabilities:
        raise Unprocessable("This member cannot be assigned field tasks.",
                            fields=[FieldError(field="assignee_membership_id", code="cannot_work_tasks",
                                               message="Member lacks field-task permission.")])
    return m


def create_task(db: Session, ctx: OrgContext, data: TaskCreate) -> UUID:
    ctx.require(Cap.TASK_MANAGE)
    ensure_area(db, data.area_id)
    if data.animal_id:
        load_animal(db, data.animal_id, usable=True)
    if data.assignee_membership_id:
        _member(db, data.assignee_membership_id)
    task = FieldTask(org_id=ctx.org_id, created_by=ctx.user_id,
                     state="assigned" if data.assignee_membership_id else "unassigned", **data.model_dump())
    db.add(task)
    db.flush()
    record_audit(db, ctx, "task.created", "task", task.id, {"type": data.task_type,
                                                             "assigned": bool(data.assignee_membership_id)})
    emit(db, ctx, "task.created", "task", task.id)
    return task.id


def transition_task(db: Session, ctx: OrgContext, task_id: UUID, data: TaskTransition) -> None:
    task = db.execute(select(FieldTask).where(FieldTask.id == task_id).with_for_update()).scalar()
    if task is None:
        raise NotFound("Task not found.", code="task_not_found")
    allowed_from, to_state, who = TRANSITIONS[data.action]
    is_assignee = task.assignee_membership_id == ctx.membership_id or (
        task.assignee_membership_id is None and task.team_id is not None
        and db.execute(text(f"select :t in ({_MY_TEAMS})"), {"t": task.team_id, "mid": ctx.membership_id}).scalar())
    if who == "manager" or not is_assignee:
        # Coordinators may act on any task (including on behalf of an assignee); others only on their own.
        if who == "assignee" and not ctx.can(Cap.TASK_MANAGE):
            raise Forbidden("Only the assigned person can update this task.", code="not_assignee")
        ctx.require(Cap.TASK_MANAGE)
    else:
        ctx.require(Cap.TASK_WORK)
    expect_version(task.row_version, data.row_version, "task")
    if task.state not in allowed_from:
        raise Conflict(f"A {task.state} task cannot be {data.action}ed.", code="invalid_transition",
                       details={"state": task.state})
    previous = task.state
    if data.action == "assign":
        if not data.assignee_membership_id:
            raise Unprocessable("Choose who to assign.", fields=[FieldError(field="assignee_membership_id",
                                                                            code="required", message="Required.")])
        _member(db, data.assignee_membership_id)
        task.assignee_membership_id = data.assignee_membership_id
    elif data.action == "block":
        task.blocked_reason = require_reason(data.note, "note")
    elif data.action == "cancel":
        task.cancelled_reason = require_reason(data.note, "note")
    elif data.action == "complete":
        task.outcome_note = data.note
        task.completed_at = text("now()")
    elif data.action == "reopen":
        task.completed_at = None
        task.cancelled_reason = None
        if task.assignee_membership_id is None:
            to_state = "unassigned"
    if to_state != "completed":
        task.completed_at = None
    task.state = to_state
    record_audit(db, ctx, f"task.{data.action}", "task", task.id, {"from": previous, "to": to_state},
                 reason=data.note if data.action in ("block", "cancel") else None)
    emit(db, ctx, "task.updated", "task", task.id)


_TASK_SELECT = """
select t.*, ar.code as area_code, ar.name as area_name, an.reference_code as animal_reference,
       up.preferred_name as assignee_name, tt.name as team_name,
       coalesce(t.assignee_membership_id = :mid, false)
         or (t.assignee_membership_id is null and t.team_id in (""" + _MY_TEAMS + """)) as assigned_to_me
from app.field_tasks t
left join app.teams tt on tt.id = t.team_id
left join app.areas ar on ar.id = t.area_id
left join app.animals an on an.id = t.animal_id
left join app.memberships m on m.id = t.assignee_membership_id
left join app.user_profiles up on up.user_id = m.user_id
"""


def _task_out(r: Any) -> TaskOut:
    return TaskOut(
        id=r.id, task_type=r.task_type, title=r.title, instructions=r.instructions, state=r.state, priority=r.priority,
        priority_rationale=r.priority_rationale,
        area=AreaRef(id=r.area_id, code=r.area_code, name=r.area_name) if r.area_id else None,
        animal_id=r.animal_id, animal_reference=r.animal_reference, assignee_membership_id=r.assignee_membership_id,
        assignee_name=r.assignee_name, team_id=r.team_id, team_name=r.team_name,
        assigned_to_me=bool(r.assigned_to_me), campaign_id=r.campaign_id, due_on=r.due_on,
        planned_start=r.planned_start,
        planned_end=r.planned_end, outcome_note=r.outcome_note, blocked_reason=r.blocked_reason,
        cancelled_reason=r.cancelled_reason, completed_at=r.completed_at, source_event_type=r.source_event_type,
        source_event_id=r.source_event_id, is_demo=r.is_demo, created_at=r.created_at, row_version=r.row_version)


def get_task(db: Session, ctx: OrgContext, task_id: UUID) -> TaskOut:
    if not (ctx.can(Cap.TASK_WORK) or ctx.can(Cap.TASK_MANAGE)):
        ctx.require(Cap.TASK_WORK)
    row = db.execute(text(_TASK_SELECT + " where t.id = :id"),
                     {"id": task_id, "mid": ctx.membership_id}).one_or_none()
    if row is None:
        raise NotFound("Task not found.", code="task_not_found")
    return _task_out(row)


def list_tasks(db: Session, ctx: OrgContext, *, mine: bool, states: list[str] | None, animal_id: UUID | None,
               area_id: UUID | None, cursor: str | None, limit: int) -> tuple[list[TaskOut], str | None]:
    if not ctx.can(Cap.TASK_MANAGE):
        ctx.require(Cap.TASK_WORK)
        mine = True if animal_id is None else mine  # field workers see their own list; animal views show context
    where, params = ["true"], {"mid": ctx.membership_id}
    if mine:
        where.append("(t.assignee_membership_id = :mid or (t.assignee_membership_id is null and t.team_id in ("
                     + _MY_TEAMS + ")))")
    if states:
        where.append("t.state = any(:states)")
        params["states"] = states
    if animal_id:
        where.append("t.animal_id = :a")
        params["a"] = animal_id
    if area_id:
        where.append("t.area_id = :ar")
        params["ar"] = area_id
    c = decode_cursor(cursor, 3)
    order_key = "coalesce(t.due_on, date '9999-12-31')"
    if c:
        where.append(f"({order_key}, t.created_at, t.id) > "
                     "(cast(:c0 as date), cast(:c1 as timestamptz), cast(:c2 as uuid))")
        params.update(c0=c[0], c1=c[1], c2=c[2])
    rows = db.execute(text(_TASK_SELECT + " where " + " and ".join(where) +
                           f" order by {order_key}, t.created_at, t.id limit :lim"), {**params, "lim": limit + 1}).all()
    more = len(rows) > limit
    rows = rows[:limit]
    nxt = None
    if more and rows:
        last = rows[-1]
        nxt = encode_cursor((last.due_on.isoformat() if last.due_on else "9999-12-31"), last.created_at, last.id)
    return [_task_out(r) for r in rows], nxt
