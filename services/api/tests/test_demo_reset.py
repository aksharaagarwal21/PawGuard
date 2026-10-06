"""Phase 9: the demo reset removes demo-organisation data only and never touches real organisations."""

from sqlalchemy import text

from pawguard_api.seed.reset import KEEP, reset_demo_rows, tenant_tables


def _animal(client, auth, token, org, name):
    r = client.post("/api/v1/animals", headers=auth(token, org), json={"species": "dog", "nickname": name})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_reset_deletes_demo_rows_only_and_keeps_people(client, auth, world, make_token, owner_engine):
    real = world.org()
    demo = world.org(demo=True)
    real_user, demo_user = world.member(real, "field_volunteer"), world.member(demo, "field_volunteer")
    real_animal = _animal(client, auth, make_token(real_user), real, "Real dog")
    _animal(client, auth, make_token(demo_user), demo, "Demo dog")
    with owner_engine.connect() as c:
        real_audit = c.execute(text("select count(*) from app.audit_events where org_id = :o"), {"o": real}).scalar_one()
    with owner_engine.begin() as c:
        summary = reset_demo_rows(c)
    assert summary["deleted"].get("animals", 0) >= 1
    assert not KEEP & set(summary["deleted"])
    with owner_engine.connect() as c:
        assert c.execute(text("select count(*) from app.animals where org_id = :o"), {"o": demo}).scalar_one() == 0
        assert c.execute(text("select count(*) from app.memberships where org_id = :o"), {"o": demo}).scalar_one() == 1
        assert c.execute(text("select nickname from app.animals where id = :a"), {"a": real_animal}).scalar_one() \
            == "Real dog"
        assert c.execute(text("select count(*) from app.audit_events where org_id = :o"),
                         {"o": real}).scalar_one() == real_audit
        assert c.execute(text("select count(*) from app.audit_events where action = 'demo.reset'")).scalar_one() >= 1
        # Guards are back on after the reset: audit rows still cannot be deleted
        assert c.execute(text("show session_replication_role")).scalar_one() == "origin"
    assert "memberships" not in tenant_tables(owner_engine.connect())
