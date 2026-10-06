from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from pawguard_api.contracts import TaskCreate, TaskOut, TaskPage, TaskState, TaskTransition
from pawguard_api.deps import CurrentOrg
from pawguard_api.domain import tasks

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])


@router.get("", response_model=TaskPage, summary="List field tasks")
def list_tasks(ctx: CurrentOrg, mine: bool = True, state: Annotated[list[TaskState] | None, Query()] = None,
               animal_id: UUID | None = None, area_id: UUID | None = None,
               cursor: Annotated[str | None, Query(max_length=300)] = None,
               limit: Annotated[int, Query(ge=1, le=100)] = 25) -> TaskPage:
    """Permission: ``task.work`` (own tasks) or ``task.manage`` (all tasks in the organisation)."""
    with ctx.tx() as db:
        items, nxt = tasks.list_tasks(db, ctx, mine=mine, states=state, animal_id=animal_id, area_id=area_id,
                                      cursor=cursor, limit=limit)
    return TaskPage(items=items, next_cursor=nxt)


@router.post("", status_code=201, response_model=TaskOut, summary="Create a task")
def create(body: TaskCreate, ctx: CurrentOrg) -> JSONResponse:
    """Permission: ``task.manage``. Assignees must be active members with ``task.work``."""
    with ctx.tx() as db:
        task_id = tasks.create_task(db, ctx, body)
        db.flush()
        payload = tasks.get_task(db, ctx, task_id).model_dump(mode="json")
    return JSONResponse(payload, status_code=201)


@router.get("/{task_id}", response_model=TaskOut, summary="Task detail")
def get(task_id: UUID, ctx: CurrentOrg) -> TaskOut:
    """Permission: ``task.work`` or ``task.manage``."""
    with ctx.tx() as db:
        return tasks.get_task(db, ctx, task_id)


@router.post("/{task_id}/transitions", response_model=TaskOut, summary="Start, complete, block, assign or cancel")
def transition(task_id: UUID, body: TaskTransition, ctx: CurrentOrg) -> TaskOut:
    """Permission: the assignee (``task.work``) may start, complete or block their task; ``task.manage`` may do
    anything including assign, cancel and reopen. Blocking and cancelling need a reason. Requires ``row_version``."""
    with ctx.tx() as db:
        tasks.transition_task(db, ctx, task_id, body)
        db.flush()
        return tasks.get_task(db, ctx, task_id)
