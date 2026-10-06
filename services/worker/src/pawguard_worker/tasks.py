"""Celery tasks. Each receives only a job id; state is loaded from PostgreSQL and duplicate deliveries are no-ops."""

from pawguard_worker import analysis, identity, jobs, media, notify, plan_job
from pawguard_worker.celery_app import app


@app.task(name="pawguard.ping")
def ping() -> str:
    """Liveness probe for the broker → worker path."""
    return "pong"


@app.task(name="pawguard.media.validate")
def validate_media(job_id: str) -> str:
    return jobs.run(job_id, media.validate, on_terminal=media.reject)


@app.task(name="pawguard.media.analyse")
def analyse_media(job_id: str) -> str:
    """Advisory quality + detection. Failure leaves the photo usable (manual path)."""
    return jobs.run(job_id, analysis.analyse)


@app.task(name="pawguard.identity.enrol")
def enrol_identity(job_id: str) -> str:
    """Add a linked, chosen-subject photo to the gallery of each maintained identity model."""
    return jobs.run(job_id, identity.enrol)


@app.task(name="pawguard.identity.search")
def search_identity(job_id: str) -> str:
    """Candidate search. Failure leaves manual search and registration fully available."""
    return jobs.run(job_id, identity.search, on_terminal=identity.search_failed)


@app.task(name="pawguard.plan.solve")
def solve_plan(job_id: str) -> str:
    """Campaign day plan. A proposal only; people approve and publish."""
    return jobs.run(job_id, plan_job.solve, on_terminal=plan_job.failed)


@app.task(name="pawguard.notify.drain")
def drain_notifications() -> dict[str, int]:
    """Send one batch of queued notifications (email, push, WhatsApp)."""
    return notify.drain()
