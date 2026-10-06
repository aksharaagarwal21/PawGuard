"""``pawguard-worker`` command line.

  run        Start a Celery worker (solo pool on Windows, prefork elsewhere).
  dispatch   Run the transactional-outbox dispatcher loop.
"""

import sys

import typer

from pawguard_api.logging import configure_logging
from pawguard_api.settings import get_settings

app = typer.Typer(no_args_is_help=True, add_completion=False)


@app.command()
def run(concurrency: int = typer.Option(2, help="Worker processes (ignored on Windows: solo pool)")) -> None:
    from pawguard_worker.celery_app import app as celery_app

    configure_logging(get_settings().log_level)
    argv = ["worker", "--loglevel", "INFO", "-Q", "pawguard"]
    argv += ["--pool", "solo"] if sys.platform == "win32" else ["--concurrency", str(concurrency)]
    celery_app.worker_main(argv)


@app.command()
def dispatch(once: bool = typer.Option(False, help="Process one batch and exit")) -> None:
    from pawguard_worker.dispatcher import run_dispatcher

    configure_logging(get_settings().log_level)
    run_dispatcher(once=once)


if __name__ == "__main__":
    app()
