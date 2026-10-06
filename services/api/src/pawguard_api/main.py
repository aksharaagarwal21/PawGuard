"""FastAPI application factory."""

import re
import time
import uuid

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.routing import APIRoute

from pawguard_api.errors import ErrorResponse, install_error_handlers
from pawguard_api.logging import configure_logging, get_logger
from pawguard_api.routers import (
    animals,
    campaigns,
    clinic,
    demo,
    health,
    identity,
    imports,
    me,
    media,
    merges,
    notifications,
    pets,
    programme,
    public_cards,
    reference,
    sync,
    system,
    tasks,
    vaccinations,
)
from pawguard_api.settings import get_settings

_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
log = get_logger("pawguard.access")


def _operation_id(route: APIRoute) -> str:
    return f"{route.tags[0]}_{route.name}" if route.tags else route.name


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    app = FastAPI(
        title="PawGuard 360 API",
        version="0.1.0",
        description=("Business-rule boundary for PawGuard 360. Every endpoint documents its permission "
                     "requirement. Organisation-scoped endpoints require the `X-PawGuard-Org` header; membership "
                     "is verified server-side on every request."),
        generate_unique_id_function=_operation_id,
        responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None,
    )
    install_error_handlers(app)

    @app.middleware("http")
    async def request_context(request: Request, call_next):  # type: ignore[no-untyped-def]
        incoming = request.headers.get("x-request-id", "")
        request_id = incoming if _REQUEST_ID_RE.match(incoming) else uuid.uuid4().hex
        request.state.request_id = request_id
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)
        start = time.perf_counter()
        response: Response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        # Path only — the query string can contain search terms about animals or people.
        log.info("request", method=request.method, path=request.url.path, status=response.status_code,
                 ms=round((time.perf_counter() - start) * 1000, 1),
                 user_id=getattr(request.state, "user_id", None), org_id=getattr(request.state, "org_id", None))
        return response

    app.include_router(health.router)
    app.include_router(me.router)
    app.include_router(system.router)
    app.include_router(demo.router)
    for r in (animals, vaccinations, media, tasks, merges, reference, programme, imports, identity, sync, campaigns,
              pets, clinic, public_cards, notifications):
        app.include_router(r.router)
    return app


app = create_app()
