"""Map PostgreSQL constraint and permission errors to structured API errors (never leaking SQL or values)."""

from psycopg import errors as pg_errors
from sqlalchemy.exc import DBAPIError

from pawguard_api.errors import ApiError, Conflict, FieldError, Forbidden, Unprocessable
from pawguard_api.logging import get_logger

log = get_logger(__name__)

_CONSTRAINT_ERRORS: dict[str, tuple[type[ApiError], str, str | None, str]] = {
    # constraint name → (error class, code, field, message)
    "vacc_not_future": (Unprocessable, "date_in_future", "administered_on",
                        "The administration date cannot be in the future."),
    "review_not_self": (Forbidden, "cannot_review_own_submission", None,
                        "You cannot review a vaccination record you submitted."),
}


def map_db_error(exc: DBAPIError) -> ApiError:
    """Translate constraint violations into structured API errors (never leak SQL or values)."""
    orig = exc.orig
    name = getattr(getattr(orig, "diag", None), "constraint_name", None) or ""
    if name in _CONSTRAINT_ERRORS:
        cls, code, field, message = _CONSTRAINT_ERRORS[name]
        return cls(message, code=code, fields=[FieldError(field=field, code=code, message=message)] if field else [])
    if isinstance(orig, pg_errors.UniqueViolation):
        return Conflict("This record already exists.", code="duplicate", details={"constraint": name})
    if isinstance(orig, pg_errors.ForeignKeyViolation):
        return Unprocessable("A referenced record does not exist in this organisation.", code="invalid_reference",
                             details={"constraint": name})
    if isinstance(orig, pg_errors.CheckViolation):
        return Unprocessable("The record breaks a data rule.", code="constraint_violation",
                             details={"constraint": name})
    if isinstance(orig, pg_errors.InsufficientPrivilege):
        # Privilege/RLS messages name the object but contain no row values.
        log.warning("db_permission_denied", detail=getattr(getattr(orig, "diag", None), "message_primary", None))
        return Forbidden("You don't have permission to do this.", code="forbidden")
    if isinstance(orig, pg_errors.LockNotAvailable | pg_errors.SerializationFailure | pg_errors.DeadlockDetected):
        return Conflict("Someone else is changing this record. Try again.", code="concurrent_update")
    # Unexpected: log the error class and SQLSTATE only (messages can contain record values).
    log.error("unmapped_db_error", error=type(orig).__name__, sqlstate=getattr(orig, "sqlstate", None),
              constraint=name or None, table=getattr(getattr(orig, "diag", None), "table_name", None),
              column=getattr(getattr(orig, "diag", None), "column_name", None))
    return ApiError("The database rejected the change.", code="database_error", status_code=500)
