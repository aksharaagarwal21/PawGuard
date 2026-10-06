"""Campaign day planning job (``plan.solve``): reads the plan's input snapshot, solves, stores the proposal."""

import json
from typing import Any

from sqlalchemy import text

from pawguard_worker import planning
from pawguard_worker.jobs import JobContext


def solve(ctx: JobContext) -> dict[str, Any]:
    with ctx.tx() as c:
        p = c.execute(text("select id, state, inputs from app.campaign_plans where id = :id"),
                      {"id": ctx.target_id}).one_or_none()
    if p is None or p.state != "solving":
        return {"skipped": "not waiting for a solution"}
    result = planning.plan(p.inputs)
    with ctx.tx() as c:
        c.execute(text("""update app.campaign_plans set state = 'ready', result = cast(:r as jsonb),
                            solver_version = :v where id = :id and state = 'solving'"""),
                  {"r": json.dumps(result), "v": f"{result['solver']} / {planning.SOLVER_VERSION}",
                   "id": ctx.target_id})
    return {"solver": result["solver"], "areas_planned": result["totals"]["areas_planned"]}


def failed(ctx: JobContext, code: str) -> None:
    with ctx.tx() as c:
        c.execute(text("update app.campaign_plans set state = 'failed', failure_code = :c "
                       "where id = :id and state = 'solving'"), {"c": code, "id": ctx.target_id})
