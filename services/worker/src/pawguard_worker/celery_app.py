"""Celery application. Tasks are at-least-once and idempotent; durable job state lives in PostgreSQL, not in
Celery result storage (no result backend is configured)."""

from celery import Celery

from pawguard_api.settings import get_settings

settings = get_settings()

app = Celery("pawguard", broker=settings.redis_url, include=["pawguard_worker.tasks"])
app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    task_default_queue="pawguard",
    task_acks_late=True,  # a task is re-delivered if the worker dies mid-run
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_soft_time_limit=120,
    task_time_limit=180,
    broker_connection_retry_on_startup=True,
    task_ignore_result=True,
    worker_hijack_root_logger=False,
)
