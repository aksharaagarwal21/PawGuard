"""Test configuration.

Tests run against a separate database (``PAWGUARD_TEST_DATABASE_NAME``, default ``pawguard_test``) on the local
PostgreSQL, created and migrated automatically. Requests use the real runtime role (``pawguard_api``, no
BYPASSRLS); fixtures are inserted with the owner role. Tokens are signed by a test-only EC key that the
verifier is configured to trust — Supabase Auth is not needed for API tests.
"""

import os
import time
import uuid
from collections.abc import Callable, Iterator
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from dotenv import dotenv_values
from jwt.algorithms import ECAlgorithm
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url

from pawguard_api.settings import find_env_file

# ---- point every connection at the test database before the app is imported --------------------------------
_env = {k: v for k, v in dotenv_values(find_env_file() or os.devnull).items() if v is not None}
for k, v in _env.items():
    os.environ.setdefault(k, v)
TEST_DB = os.environ.get("PAWGUARD_TEST_DATABASE_NAME", "pawguard_test")


def _with_db(url: str) -> str:
    return make_url(url).set(database=TEST_DB).render_as_string(hide_password=False)


os.environ["PAWGUARD_ENV"] = "test"
os.environ["PAWGUARD_DEMO_MODE"] = "false"
os.environ["PAWGUARD_DATABASE_URL"] = _with_db(os.environ["PAWGUARD_DATABASE_URL"])
os.environ["PAWGUARD_WORKER_DATABASE_URL"] = _with_db(os.environ["PAWGUARD_WORKER_DATABASE_URL"])
os.environ["PAWGUARD_MIGRATE_DATABASE_URL"] = _with_db(os.environ["PAWGUARD_MIGRATE_DATABASE_URL"])
os.environ["PAWGUARD_ENV_FILE"] = os.devnull  # settings must come only from the environment set above

from fastapi.testclient import TestClient  # noqa: E402

from pawguard_api.auth import JwksCache, TokenVerifier  # noqa: E402
from pawguard_api.capabilities import ROLE_TEMPLATES, Role  # noqa: E402
from pawguard_api.settings import get_settings  # noqa: E402

KID = "test-key-1"


def _sa(url: str) -> str:
    return url.replace("postgresql://", "postgresql+psycopg://", 1)


@pytest.fixture(scope="session", autouse=True)
def _test_database() -> None:
    from pawguard_api.cli import ensure_test_database

    ensure_test_database(TEST_DB, recreate=os.environ.get("PAWGUARD_TEST_RECREATE_DB") == "1")


@pytest.fixture(scope="session")
def owner_engine(_test_database: None) -> Iterator[Engine]:
    engine = create_engine(_sa(os.environ["PAWGUARD_MIGRATE_DATABASE_URL"]))
    with engine.begin() as c:
        tables = c.execute(text("select string_agg(format('app.%I', tablename), ', ') from pg_tables "
                                "where schemaname = 'app'")).scalar()
        if tables:
            c.execute(text(f"truncate {tables} cascade"))
        c.execute(text("truncate auth.sessions"))
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def ec_key() -> ec.EllipticCurvePrivateKey:
    return ec.generate_private_key(ec.SECP256R1())


@pytest.fixture(scope="session")
def jwks(ec_key: ec.EllipticCurvePrivateKey) -> dict[str, Any]:
    pub = ECAlgorithm.to_jwk(ec_key.public_key(), as_dict=True)
    pub.update({"kid": KID, "alg": "ES256", "use": "sig"})
    return {"keys": [pub]}


TokenFactory = Callable[..., str]


@pytest.fixture(scope="session")
def make_token(ec_key: ec.EllipticCurvePrivateKey) -> TokenFactory:
    settings = get_settings()

    def _make(user_id: uuid.UUID, *, session_id: uuid.UUID | None = None, headers: dict[str, Any] | None = None,
              key: Any = None, algorithm: str = "ES256", **claims: Any) -> str:
        now = int(time.time())
        payload = {"sub": str(user_id), "iss": settings.auth_issuer, "aud": "authenticated", "role": "authenticated",
                   "iat": now, "exp": now + 600, "aal": "aal1", "email": f"{user_id}@example.org",
                   "session_id": str(session_id or uuid.uuid4())}
        payload.update(claims)
        return jwt.encode(payload, key or ec_key, algorithm=algorithm, headers={"kid": KID, **(headers or {})})

    return _make


@pytest.fixture(scope="session")
def app(jwks: dict[str, Any], owner_engine: Engine):  # type: ignore[no-untyped-def]
    from pawguard_api.deps import get_verifier
    from pawguard_api.main import create_app

    application = create_app()
    verifier = TokenVerifier(get_settings(), JwksCache("http://unused.invalid", static_jwks=jwks))
    application.dependency_overrides[get_verifier] = lambda: verifier
    return application


@pytest.fixture
def client(app) -> TestClient:  # type: ignore[no-untyped-def]
    return TestClient(app)


class World:
    """Fixture builder using the owner connection (bypasses RLS — test setup only)."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def org(self, name: str | None = None, *, state: str = "active", demo: bool = False) -> uuid.UUID:
        with self.engine.begin() as c:
            return c.execute(text("insert into app.organisations (name, org_type, activation_state, is_demo) "
                                  "values (:n, 'animal_welfare_ngo', :s, :d) returning id"),
                             {"n": name or f"Org {uuid.uuid4().hex[:8]}", "s": state, "d": demo}).scalar_one()

    def member(self, org_id: uuid.UUID, role: str = "field_volunteer", *, user_id: uuid.UUID | None = None,
               status: str = "active", capabilities: list[str] | None = None,
               valid_until_sql: str = "null") -> uuid.UUID:
        user_id = user_id or uuid.uuid4()
        caps = capabilities if capabilities is not None else sorted(c.value for c in ROLE_TEMPLATES[Role(role)])
        with self.engine.begin() as c:
            c.execute(text("insert into app.user_profiles (user_id) values (:u) on conflict do nothing"),
                      {"u": user_id})
            c.execute(text(f"""
                insert into app.memberships (org_id, user_id, role, capabilities, status, valid_from, valid_until,
                                             revoked_at)
                values (:o, :u, :r, :caps, :s, now() - interval '1 day', {valid_until_sql},
                        case when :s = 'revoked' then now() end)"""),
                      {"o": org_id, "u": user_id, "r": role, "caps": caps, "s": status})
        return user_id

    def approve(self, org_id: uuid.UUID, user_id: uuid.UUID, scope: str = "veterinary_review") -> None:
        reviewer = self.member(org_id, "org_admin")
        with self.engine.begin() as c:
            mid = c.execute(text("select id from app.memberships where org_id = :o and user_id = :u"),
                            {"o": org_id, "u": user_id}).scalar_one()
            c.execute(text("""insert into app.professional_approvals (org_id, membership_id, user_id, scope,
                              evidence_reference, reviewer_user_id, review_state, decided_at)
                              values (:o, :m, :u, :s, 'test evidence', :r, 'approved', now())"""),
                      {"o": org_id, "m": mid, "u": user_id, "s": scope, "r": reviewer})

    def session(self, user_id: uuid.UUID, *, active: bool = True) -> uuid.UUID:
        sid = uuid.uuid4()
        with self.engine.begin() as c:
            c.execute(text("insert into auth.sessions (id, user_id, not_after) values (:id, :u, "
                           + ("null" if active else "now() - interval '1 minute'") + ")"), {"id": sid, "u": user_id})
        return sid


@pytest.fixture(scope="session")
def api_engine_for_tests(owner_engine: Engine) -> Iterator[Engine]:
    """Direct connections as the runtime API role (pawguard_api) for database-level checks."""
    engine = create_engine(_sa(os.environ["PAWGUARD_DATABASE_URL"]))
    yield engine
    engine.dispose()


@pytest.fixture
def world(owner_engine: Engine) -> World:
    return World(owner_engine)


def _auth(token: str, org_id: uuid.UUID | None = None) -> dict[str, str]:
    h = {"Authorization": f"Bearer {token}"}
    if org_id:
        h["X-PawGuard-Org"] = str(org_id)
    return h


@pytest.fixture
def auth() -> Callable[..., dict[str, str]]:
    """``auth(token, org_id=None)`` → request headers."""
    return _auth
