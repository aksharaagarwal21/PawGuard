"""Organisation selection is a selector, not proof: membership is checked server-side on every request."""

import uuid

import pytest


def test_requires_org_header(auth, client, make_token, world):
    user = world.member(world.org(), "org_admin")
    r = client.get("/api/v1/system/providers", headers=auth(make_token(user)))
    assert r.status_code == 403 and r.json()["error"]["code"] == "organisation_required"


def test_member_with_capability_is_allowed(auth, client, make_token, world):
    org = world.org()
    admin = world.member(org, "org_admin")
    r = client.get("/api/v1/system/providers", headers=auth(make_token(admin), org))
    assert r.status_code == 200, r.text
    keys = {c["key"]: c["status"] for c in r.json()["capabilities"]}
    assert keys["identity_matching"] == "unavailable"  # never claims a model that does not exist


def test_other_organisation_is_refused(auth, client, make_token, world):
    mine, theirs = world.org(), world.org()
    admin = world.member(mine, "org_admin")
    r = client.get("/api/v1/system/providers", headers=auth(make_token(admin), theirs))
    assert r.status_code == 403 and r.json()["error"]["code"] == "not_a_member"


def test_nonexistent_org_looks_the_same_as_foreign_org(auth, client, make_token, world):
    admin = world.member(world.org(), "org_admin")
    r = client.get("/api/v1/system/providers", headers=auth(make_token(admin), uuid.uuid4()))
    assert r.status_code == 403 and r.json()["error"]["code"] == "not_a_member"


@pytest.mark.parametrize("status,valid_until", [("revoked", "null"), ("suspended", "null"),
                                                 ("active", "now() - interval '1 hour'")])
def test_inactive_memberships_are_refused(auth, client, make_token, world, status, valid_until):
    org = world.org()
    user = world.member(org, "org_admin", status=status, valid_until_sql=valid_until)
    r = client.get("/api/v1/system/providers", headers=auth(make_token(user), org))
    assert r.status_code == 403
    me = client.get("/api/v1/me", headers=auth(make_token(user))).json()
    assert me["memberships"] == []


def test_revocation_takes_effect_on_next_request(auth, client, make_token, world, owner_engine):
    from sqlalchemy import text

    org = world.org()
    user = world.member(org, "org_admin")
    token = make_token(user)
    assert client.get("/api/v1/system/providers", headers=auth(token, org)).status_code == 200
    with owner_engine.begin() as c:
        c.execute(text("update app.memberships set status = 'revoked', revoked_at = now() where user_id = :u"),
                  {"u": user})
    # Same, still-unexpired token: access ends immediately because membership is read on every request.
    assert client.get("/api/v1/system/providers", headers=auth(token, org)).status_code == 403


def test_inactive_organisation_is_hidden_from_me(auth, client, make_token, world):
    org = world.org(state="suspended")
    user = world.member(org)
    assert client.get("/api/v1/me", headers=auth(make_token(user))).json()["memberships"] == []


def test_profile_update_uses_row_version(auth, client, make_token, world):
    user = world.member(world.org())
    token = make_token(user)
    me = client.get("/api/v1/me", headers=auth(token)).json()
    ok = client.patch("/api/v1/me", headers=auth(token),
                      json={"preferred_name": "Asha", "row_version": me["profile_row_version"]})
    assert ok.status_code == 200 and ok.json()["preferred_name"] == "Asha"
    stale = client.patch("/api/v1/me", headers=auth(token),
                         json={"preferred_name": "Other", "row_version": me["profile_row_version"]})
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "stale_row_version"
    bad = client.patch("/api/v1/me", headers=auth(token), json={"locale": "fr", "row_version": 1})
    assert bad.status_code == 422 and bad.json()["error"]["fields"][0]["field"] == "locale"
