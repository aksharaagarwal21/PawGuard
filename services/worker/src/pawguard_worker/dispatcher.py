"""Transactional-outbox dispatcher.

Claims pending outbox rows with ``FOR UPDATE SKIP LOCKED`` (several dispatchers may run), publishes Celery tasks
for queued jobs, and marks rows dispatched. Delivery is at-least-once: if the commit fails after publishing,
the job is published again and the task's claim step makes the duplicate a no-op.
"""

import time
from typing import Any

from sqlalchemy import text

from pawguard_api.db import worker_engine
from pawguard_api.logging import get_logger

log = get_logger(__name__)

# job_type → Celery task name
JOB_TASKS: dict[str, str] = {
    "media.validate": "pawguard.media.validate",
    "media.analyse": "pawguard.media.analyse",
    "identity.enrol": "pawguard.identity.enrol",
    "identity.search": "pawguard.identity.search",
    "plan.solve": "pawguard.plan.solve",
}
MAX_DISPATCH_ATTEMPTS = 10


def _publish(row: Any) -> None:
    if row.event_type == "job.queued":
        task = JOB_TASKS.get(row.payload.get("job_type", ""))
        if task is None:
            raise LookupError(f"no task registered for job type {row.payload.get('job_type')}")
        from pawguard_worker.celery_app import app

        app.send_task(task, args=[str(row.aggregate_id)])
    # Other domain events currently have no asynchronous consumers; they are kept for audit/integration.


def dispatch_batch(batch: int = 50) -> int:
    with worker_engine().begin() as c:
        rows = c.execute(text("""
            select id, event_type, aggregate_id, payload, attempts from app.outbox_events
            where state = 'pending' and available_at <= now()
            order by available_at limit :n for update skip locked"""), {"n": batch}).all()
        for row in rows:
            try:
                _publish(row)
                c.execute(text("update app.outbox_events set state = 'dispatched', dispatched_at = now(), "
                               "attempts = attempts + 1 where id = :id"), {"id": row.id})
            except Exception as exc:
                attempts = row.attempts + 1
                c.execute(text("""update app.outbox_events set attempts = :a, last_error = :e,
                                  state = case when :a >= :max then 'failed' else 'pending' end,
                                  available_at = now() + make_interval(secs => least(300, power(2, :a)))
                                  where id = :id"""),
                          {"a": attempts, "e": type(exc).__name__ + ": " + str(exc)[:200], "max": MAX_DISPATCH_ATTEMPTS,
                           "id": row.id})
                log.warning("outbox_dispatch_failed", outbox_id=str(row.id), error=type(exc).__name__)
    return len(rows)


SCAN_EVERY = 600  # seconds between scans for reminders that are due today
SEND_CHECK_EVERY = 15  # seconds between checks for queued notifications


class NotificationTicker:
    """Periodic notification work inside the dispatcher loop: queue due reminders, then publish a send task when
    anything is ready. Failures are logged and retried on the next tick; they never stop job dispatch."""

    def __init__(self) -> None:
        self.next_scan = 0.0
        self.next_check = 0.0

    def tick(self, now: float) -> None:
        from pawguard_worker import notify

        try:
            if now >= self.next_scan:
                self.next_scan = now + SCAN_EVERY
                queued = notify.queue_due()
                if queued:
                    log.info("notifications_queued", count=queued)
            if now >= self.next_check:
                self.next_check = now + SEND_CHECK_EVERY
                if notify.has_ready():
                    from pawguard_worker.celery_app import app

                    app.send_task("pawguard.notify.drain")
        except Exception as exc:
            log.warning("notification_tick_failed", error=type(exc).__name__)


def run_dispatcher(once: bool = False, poll_seconds: float = 1.0) -> None:
    log.info("dispatcher_started")
    ticker = NotificationTicker()
    while True:
        ticker.tick(time.monotonic())
        try:
            n = dispatch_batch()
        except Exception as exc:
            log.error("dispatcher_error", error=type(exc).__name__)
            n = 0
            time.sleep(5)
        if once:
            return
        if n == 0:
            time.sleep(poll_seconds)
