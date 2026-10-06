"""Job execution: claim → run under the job's tenant context → record the outcome.

A job is claimed atomically (queued → processing, or a processing job whose lock expired). Duplicate deliveries
and already-finished jobs are no-ops. Handlers raise ``TerminalJobError`` for permanent failures (recorded with
a stable code) and any other exception for retryable ones (re-queued with backoff until ``max_attempts``).
"""

import os
import socket
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any
from uuid import UUID

from sqlalchemy import Connection, text

from pawguard_api.db import worker_engine
from pawguard_api.logging import get_logger

log = get_logger(__name__)
WORKER_ID = f"{socket.gethostname()}:{os.getpid()}"


class TerminalJobError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


class JobContext:
    def __init__(self, job_id: UUID, org_id: UUID, target_id: UUID, attempt: int) -> None:
        self.job_id, self.org_id, self.target_id, self.attempt = job_id, org_id, target_id, attempt

    @contextmanager
    def tx(self) -> Iterator[Connection]:
        """Transaction scoped to this job's organisation (RLS via app.set_worker_context)."""
        with worker_engine().begin() as c:
            c.execute(text("select app.set_worker_context(:j)"), {"j": self.job_id})
            yield c


def claim(job_id: UUID) -> JobContext | None:
    with worker_engine().begin() as c:
        row = c.execute(text("""
            update app.background_jobs
               set state = 'processing', attempts = attempts + 1, started_at = now(), locked_by = :w,
                   locked_until = now() + interval '10 minutes'
             where id = :id and attempts < max_attempts
               and (state = 'queued' or (state = 'processing' and locked_until < now()))
            returning org_id, target_id, attempts"""), {"id": job_id, "w": WORKER_ID}).one_or_none()
    if row is None:
        return None
    return JobContext(job_id, row.org_id, row.target_id, row.attempts)


def _finish(job_id: UUID, state: str, *, code: str | None = None, result: dict[str, Any] | None = None,
            retry_in: int | None = None) -> None:
    import json

    with worker_engine().begin() as c:
        c.execute(text("""update app.background_jobs set state = :s, last_error_code = :code,
                          result = coalesce(cast(:r as jsonb), result), finished_at = case when :s in
                          ('completed','failed','cancelled','needs_input') then now() end,
                          locked_by = null, locked_until = null where id = :id"""),
                  {"s": state, "code": code, "r": json.dumps(result) if result is not None else None, "id": job_id})
        if retry_in is not None:
            c.execute(text("""insert into app.outbox_events (org_id, event_type, aggregate_type, aggregate_id,
                              payload, available_at)
                              select org_id, 'job.queued', 'background_job', id,
                                     jsonb_build_object('job_type', job_type), now() + make_interval(secs => :d)
                              from app.background_jobs where id = :id"""),
                      {"id": job_id, "d": retry_in})


def run(job_id: str, handler: Callable[[JobContext], dict[str, Any]],
        on_terminal: Callable[[JobContext, str], None] | None = None) -> str:
    ctx = claim(UUID(job_id))
    if ctx is None:
        log.info("job_skipped", job_id=job_id)
        return "skipped"
    try:
        result = handler(ctx)
    except TerminalJobError as exc:
        if on_terminal:
            on_terminal(ctx, exc.code)
        _finish(ctx.job_id, "failed", code=exc.code)
        log.info("job_failed", job_id=job_id, code=exc.code)
        return "failed"
    except Exception as exc:
        with worker_engine().begin() as c:
            max_attempts = c.execute(text("select max_attempts from app.background_jobs where id = :id"),
                                     {"id": ctx.job_id}).scalar_one()
        if ctx.attempt >= max_attempts:
            if on_terminal:
                on_terminal(ctx, "retries_exhausted")
            _finish(ctx.job_id, "failed", code="retries_exhausted")
            log.warning("job_exhausted", job_id=job_id, error=type(exc).__name__)
            return "failed"
        _finish(ctx.job_id, "queued", code=type(exc).__name__, retry_in=min(300, 5 * 2 ** ctx.attempt))
        log.warning("job_retry", job_id=job_id, attempt=ctx.attempt, error=type(exc).__name__)
        return "retry"
    _finish(ctx.job_id, "completed", result=result)
    log.info("job_completed", job_id=job_id)
    return "completed"
