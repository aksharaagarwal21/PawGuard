"""Database engines and tenant-scoped transactions.

Request handlers never get a bare connection: they open a transaction through :func:`user_tx` or
:func:`tenant_tx`, which first calls ``app.set_request_context`` (transaction-local ``set_config``). When the
transaction ends the context is gone, so a pooled connection cannot carry one caller's identity into the
next request.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache
from uuid import UUID

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from pawguard_api.settings import get_settings


def _engine(url: str, pool_size: int) -> Engine:
    # psycopg 3 driver; `postgresql://` URLs are normalised to `postgresql+psycopg://`.
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url.removeprefix("postgresql://")
    return create_engine(url, pool_size=pool_size, max_overflow=pool_size, pool_pre_ping=True,
                         pool_recycle=1800, connect_args={"application_name": "pawguard"},
                         hide_parameters=True)  # errors never echo SQL parameters (addresses, sealed keys) into logs


@lru_cache
def api_engine() -> Engine:
    s = get_settings()
    return _engine(s.database_url, s.db_pool_size)


@lru_cache
def worker_engine() -> Engine:
    s = get_settings()
    if not s.worker_database_url:
        raise RuntimeError("PAWGUARD_WORKER_DATABASE_URL is not configured")
    return _engine(s.worker_database_url, 4)


@lru_cache
def _api_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=api_engine(), expire_on_commit=False, autoflush=False)


def new_session() -> Session:
    return _api_sessionmaker()()


@contextmanager
def user_tx(user_id: UUID, org_id: UUID | None = None, session: Session | None = None) -> Iterator[Session]:
    """Open a transaction with the caller's identity (and optionally organisation) as RLS context."""
    own = session is None
    db = session or new_session()
    try:
        with db.begin():
            db.execute(text("select app.set_request_context(:u, :o)"), {"u": user_id, "o": org_id})
            yield db
    finally:
        if own:
            db.close()


def tenant_tx(user_id: UUID, org_id: UUID, session: Session | None = None):  # type: ignore[no-untyped-def]
    return user_tx(user_id, org_id, session)


@contextmanager
def public_tx(session: Session | None = None) -> Iterator[Session]:
    """Transaction with no identity: RLS returns only rows explicitly published for anonymous reading."""
    own = session is None
    db = session or new_session()
    try:
        with db.begin():
            yield db
    finally:
        if own:
            db.close()
