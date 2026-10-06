"""Token verification: only correctly signed, unexpired, user-session tokens for this issuer/audience pass."""

import time
import uuid

from cryptography.hazmat.primitives.asymmetric import ec


def test_valid_token_returns_profile_and_creates_it(auth, client, make_token, world):
    org = world.org("Alpha")
    user = world.member(org, "field_volunteer")
    r = client.get("/api/v1/me", headers=auth(make_token(user)))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user_id"] == str(user)
    assert [m["org_name"] for m in body["memberships"]] == ["Alpha"]
    assert "vaccination.review" not in body["memberships"][0]["capabilities"]
    assert r.headers["cache-control"] == "no-store"
    assert r.headers["x-request-id"]


def test_missing_and_malformed_tokens_are_rejected(client):
    assert client.get("/api/v1/me").json()["error"]["code"] == "unauthenticated"
    r = client.get("/api/v1/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_token"


def test_expired_token(auth, client, make_token):
    now = int(time.time())
    r = client.get("/api/v1/me", headers=auth(make_token(uuid.uuid4(), iat=now - 7200, exp=now - 3600)))
    assert r.status_code == 401 and r.json()["error"]["code"] == "token_expired"


def test_wrong_issuer_audience_role(auth, client, make_token):
    for claims in ({"iss": "https://attacker.example/auth/v1"}, {"aud": "anon"}, {"role": "service_role"},
                   {"role": "anon"}):
        r = client.get("/api/v1/me", headers=auth(make_token(uuid.uuid4(), **claims)))
        assert r.status_code == 401, claims


def test_token_signed_by_another_key_is_rejected(auth, client, make_token):
    other = ec.generate_private_key(ec.SECP256R1())
    r = client.get("/api/v1/me", headers=auth(make_token(uuid.uuid4(), key=other)))
    assert r.status_code == 401


def test_symmetric_hs256_token_is_rejected(auth, client, make_token):
    token = make_token(uuid.uuid4(), key="super-secret-jwt-token-with-at-least-32-characters-long",
                       algorithm="HS256")
    assert client.get("/api/v1/me", headers=auth(token)).status_code == 401


def test_unknown_key_id_is_rejected(auth, client, make_token):
    r = client.get("/api/v1/me", headers=auth(make_token(uuid.uuid4(), headers={"kid": "rotated-away"})))
    assert r.status_code == 401


def test_capabilities_in_token_are_ignored(auth, client, make_token, world):
    org = world.org()
    user = world.member(org, "field_volunteer")
    token = make_token(user, app_metadata={"capabilities": ["system.view", "vaccination.review"]},
                       user_role="org_admin")
    r = client.get("/api/v1/system/providers", headers=auth(token, org))
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "missing_capability"
