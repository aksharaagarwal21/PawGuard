"""Row-level security checked with the real runtime role (pawguard_api), never the owner."""

import os
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import QueuePool


@pytest.fixture
def api_engine(owner_engine):
    url = os.environ["PAWGUARD_DATABASE_URL"].replace("postgresql://", "postgresql+psycopg://", 1)
    # One pooled connection, so consecutive transactions are guaranteed to reuse the same session.
    engine = create_engine(url, poolclass=QueuePool, pool_size=1, max_overflow=0)
    yield engine
    engine.dispose()


def _ctx(c, user, org):
    c.execute(text("select app.set_request_context(:u, :o)"), {"u": user, "o": org})


def test_runtime_role_is_not_privileged(api_engine):
    with api_engine.connect() as c:
        row = c.execute(text("select rolsuper, rolbypassrls from pg_roles where rolname = current_user")).one()
    assert row == (False, False)


def test_no_context_sees_nothing(api_engine, world):
    world.member(world.org())
    with api_engine.begin() as c:
        assert c.execute(text("select count(*) from app.organisations")).scalar() == 0
        assert c.execute(text("select count(*) from app.memberships")).scalar() == 0
        assert c.execute(text("select count(*) from app.audit_events")).scalar() == 0


def test_tenant_isolation_for_memberships(api_engine, world):
    a, b = world.org(), world.org()
    ua = world.member(a, "org_admin")
    world.member(b, "org_admin")
    with api_engine.begin() as c:
        _ctx(c, ua, a)
        orgs = {r[0] for r in c.execute(text("select distinct org_id from app.memberships"))}
    assert orgs == {a}


def test_org_context_without_membership_is_void(api_engine, world):
    a, b = world.org(), world.org()
    ua = world.member(a)
    with api_engine.begin() as c:
        _ctx(c, ua, b)  # claims org B but is not a member there
        assert c.execute(text("select app.current_org_id()")).scalar() is None
        assert c.execute(text("select count(*) from app.memberships where org_id = :b"), {"b": b}).scalar() == 0


def test_context_does_not_leak_across_pooled_transactions(api_engine, world):
    a = world.org()
    ua = world.member(a, "org_admin")
    with api_engine.connect() as c, c.begin():
        pid1 = c.execute(text("select pg_backend_pid()")).scalar()
        _ctx(c, ua, a)
        assert c.execute(text("select app.current_org_id()")).scalar() == a
    with api_engine.connect() as c:  # same physical connection from the pool
        with c.begin():
            assert c.execute(text("select pg_backend_pid()")).scalar() == pid1
            assert c.execute(text("select current_setting('pawguard.user_id', true)")).scalar() in ("", None)
            assert c.execute(text("select app.current_org_id()")).scalar() is None
            assert c.execute(text("select count(*) from app.memberships")).scalar() == 0


def test_cannot_grant_self_capabilities_without_member_manage(api_engine, world):
    a = world.org()
    volunteer = world.member(a, "field_volunteer")
    with api_engine.begin() as c:
        _ctx(c, volunteer, a)
        updated = c.execute(text("update app.memberships set capabilities = array['vaccination.review'] "
                                 "where user_id = :u"), {"u": volunteer}).rowcount
    assert updated == 0


def test_professional_approval_cannot_be_self_granted(api_engine, world):
    from sqlalchemy.exc import DBAPIError

    a = world.org()
    admin = world.member(a, "org_admin")
    with api_engine.connect() as c, pytest.raises(DBAPIError), c.begin():
        _ctx(c, admin, a)
        mid = c.execute(text("select id from app.memberships where user_id = :u"), {"u": admin}).scalar()
        c.execute(text("""insert into app.professional_approvals (org_id, membership_id, user_id, scope,
                              evidence_reference, reviewer_user_id, review_state)
                              values (:o, :m, :u, 'veterinary_review', 'x', :u, 'approved')"""),
                  {"o": a, "m": mid, "u": admin})


def test_audit_events_are_append_only(api_engine, owner_engine, world):
    from sqlalchemy.exc import DBAPIError

    a = world.org()
    admin = world.member(a, "org_admin")
    with api_engine.begin() as c:
        _ctx(c, admin, a)
        c.execute(text("insert into app.audit_events (org_id, actor_user_id, actor_kind, action) "
                       "values (:o, :u, 'user', 'test.event')"), {"o": a, "u": admin})
    with owner_engine.connect() as c, pytest.raises(DBAPIError):  # even the owner cannot rewrite history
        with c.begin():
            c.execute(text("update app.audit_events set action = 'test.changed' where org_id = :o"), {"o": a})


def test_session_liveness_function(api_engine, world):
    user = uuid.uuid4()
    live, ended = world.session(user), world.session(user, active=False)
    with api_engine.begin() as c:
        assert c.execute(text("select app.session_is_active(:s, :u)"), {"s": live, "u": user}).scalar() is True
        assert c.execute(text("select app.session_is_active(:s, :u)"), {"s": ended, "u": user}).scalar() is False
        assert c.execute(text("select app.session_is_active(:s, :u)"),
                         {"s": live, "u": uuid.uuid4()}).scalar() is False
