"""Typed API errors with a single response shape.

Every error response is::

    {"error": {"code": "...", "message": "...", "request_id": "...", "fields": [...], "details": {...}}}

``code`` is stable and machine-readable; ``message`` is plain English for logs/devs; the web app maps codes
to localised copy.
"""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from pawguard_api.logging import get_logger

log = get_logger(__name__)


class FieldError(BaseModel):
    field: str
    code: str
    message: str


class ErrorBody(BaseModel):
    code: str
    message: str
    request_id: str | None = None
    fields: list[FieldError] = []
    details: dict[str, Any] = {}


class ErrorResponse(BaseModel):
    error: ErrorBody


class ApiError(Exception):
    status_code = 400
    code = "bad_request"

    def __init__(self, message: str | None = None, *, code: str | None = None,
                 fields: list[FieldError] | None = None, details: dict[str, Any] | None = None,
                 status_code: int | None = None) -> None:
        super().__init__(message or self.code)
        self.message = message or self.code.replace("_", " ")
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code
        self.fields = fields or []
        self.details = details or {}


class Unauthenticated(ApiError):
    status_code = 401
    code = "unauthenticated"


class Forbidden(ApiError):
    status_code = 403
    code = "forbidden"


class NotFound(ApiError):
    status_code = 404
    code = "not_found"


class Conflict(ApiError):
    status_code = 409
    code = "conflict"


class PreconditionRequired(ApiError):
    status_code = 428
    code = "precondition_required"


class Unprocessable(ApiError):
    status_code = 422
    code = "validation_error"


class ServiceUnavailable(ApiError):
    status_code = 503
    code = "service_unavailable"


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def _body(request: Request, code: str, message: str, fields: list[FieldError] | None = None,
          details: dict[str, Any] | None = None) -> dict[str, Any]:
    return ErrorResponse(error=ErrorBody(code=code, message=message, request_id=_request_id(request),
                                         fields=fields or [], details=details or {})).model_dump()


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code,
                            content=_body(request, exc.code, exc.message, exc.fields, exc.details))

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        fields = []
        for err in exc.errors():
            loc = [str(p) for p in err.get("loc", ()) if p not in ("body", "query", "path", "header")]
            fields.append(FieldError(field=".".join(loc) or "request", code=str(err.get("type", "invalid")),
                                     message=str(err.get("msg", "Invalid value"))))
        return JSONResponse(status_code=422, content=_body(request, "validation_error",
                                                           "Some fields need attention.", fields))

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
        return JSONResponse(status_code=exc.status_code, content=_body(request, code, str(exc.detail)))

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        # Log type and request id only; exception messages can contain record content.
        log.error("unhandled_exception", exc_type=type(exc).__name__, request_id=_request_id(request))
        return JSONResponse(status_code=500, content=_body(request, "internal_error",
                                                           "Something went wrong on our side."))
