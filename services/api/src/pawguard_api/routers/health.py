"""Liveness/readiness. Readiness reports component status without exposing configuration values."""

import time

import httpx
import redis
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from pawguard_api.db import api_engine
from pawguard_api.deps import get_verifier
from pawguard_api.settings import get_settings

router = APIRouter(tags=["health"])


@router.get("/health/live", summary="Process is running")
def live() -> dict[str, str]:
    return {"status": "ok"}


def check_components() -> dict[str, dict[str, object]]:
    settings = get_settings()
    out: dict[str, dict[str, object]] = {}

    t = time.perf_counter()
    try:
        with api_engine().connect() as c:
            c.execute(text("select 1"))
            rev = c.execute(text("select app.schema_version()")).scalar()
        out["database"] = {"ok": True, "migration": rev, "ms": round((time.perf_counter() - t) * 1000, 1)}
    except Exception as exc:
        out["database"] = {"ok": False, "error": type(exc).__name__}

    out["auth_keys"] = {"ok": get_verifier().jwks.is_reachable()}

    try:
        r = httpx.get(f"{settings.supabase_url.rstrip('/')}/storage/v1/status", timeout=3.0)
        out["storage"] = {"ok": r.status_code < 500}
    except httpx.HTTPError as exc:
        out["storage"] = {"ok": False, "error": type(exc).__name__}

    try:
        redis.Redis.from_url(settings.redis_url, socket_connect_timeout=2).ping()
        out["job_broker"] = {"ok": True}
    except Exception as exc:
        out["job_broker"] = {"ok": False, "error": type(exc).__name__}
    return out


@router.get("/health/ready", summary="Dependencies reachable")
def ready() -> JSONResponse:
    comps = check_components()
    # The broker is not required to serve requests (outbox buffers work), so it does not gate readiness.
    critical = all(comps[k]["ok"] for k in ("database", "auth_keys"))
    return JSONResponse(status_code=200 if critical else 503,
                        content={"status": "ready" if critical else "not_ready", "components": comps})
