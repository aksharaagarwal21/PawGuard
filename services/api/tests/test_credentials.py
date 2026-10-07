"""Signed vaccination certificates (ADR 0010/0011): issuing, revoking, signed lists, keys, interop and leak checks.

Every test uses throwaway keys created in a temporary folder — never the machine's real master or root key.
"""

import base64
import logging
import zlib
from datetime import date, timedelta

import base45
import cbor2
import pytest
from sqlalchemy import text
from test_petcare import _h, _owner_record, _pet, _verify

from pawguard_api.domain import credentials
from pawguard_api.integrations import cose
from pawguard_api.settings import get_settings


@pytest.fixture
def clinic(world, make_token, owner_engine):
    """A demo clinic with two owners, an approved vet and a rabies product (same shape as test_petcare's fixture)."""
    from types import SimpleNamespace

    org = world.org("Signing clinic", demo=True)
    users = {"owner_a": world.member(org, "resident"), "vet": world.member(org, "veterinary_reviewer")}
    world.approve(org, users["vet"])
    tokens = {k: make_token(u, session_id=world.session(u)) for k, u in users.items()}
    with owner_engine.begin() as conn:
        product = conn.execute(text("""insert into app.vaccine_products (org_id, name, species, template_interval_days,
                                       template_label) values (:o, 'Rabies (test)', '{dog,cat}', 365, 'Demo template')
                                       returning id"""), {"o": org}).scalar_one()
    return SimpleNamespace(org=org, users=users, tokens=tokens, product=product)


@pytest.fixture
def keys(tmp_path, monkeypatch):
    s = get_settings()
    master = base64.b64encode(b"\x07" * 32).decode()
    root_pub = cose.write_root_key(tmp_path / "root.pem", "test-passphrase")
    for k, v in {"signing_master_key": master, "signing_master_key_file": None, "root_key_file": str(tmp_path / "root.pem"),
                 "root_key_passphrase": "test-passphrase", "root_key_passphrase_file": None}.items():
        monkeypatch.setattr(s, k, v)
    credentials._lists.clear()  # signed-list cache is per process
    yield base64.b64decode(root_pub)
    credentials._lists.clear()


def _cred(owner_engine, event_id, state="active"):
    with owner_engine.begin() as c:
        return c.execute(text("""select c.*, k.public_key from app.vaccination_credentials c
                                 join app.clinic_signing_keys k on k.kid = c.kid
                                 where c.event_id = :e and c.state = :s"""), {"e": event_id, "s": state}).first()


def _verified_event(client, clinic, owner_engine, **extra):
    pet = _pet(client, clinic)
    event_id = _owner_event(client, clinic, owner_engine, pet)
    r = _verify(client, clinic, event_id, next_due_on=str(date.today() + timedelta(days=300)), **extra)
    assert r.status_code == 200, r.text
    return pet, event_id


def _owner_event(client, clinic, owner_engine, pet):
    r = _owner_record(client, clinic, owner_engine, pet)
    assert r.status_code == 201, r.text
    return r.json()["timeline"][0]["event_id"]


def test_verification_issues_a_minimal_signed_certificate(client, clinic, owner_engine, keys):
    pet = _pet(client, clinic)
    entry = {"event_id": _owner_event(client, clinic, owner_engine, pet)}
    # Owner-entered and not yet verified: no certificate, and the API refuses to issue one.
    assert _cred(owner_engine, entry["event_id"]) is None
    refused = client.post(f"/api/v1/vaccination-events/{entry['event_id']}/certificate",
                          headers=_h(clinic.tokens["vet"], clinic.org))
    assert refused.status_code == 409 and refused.json()["error"]["code"] == "not_verified"
    owner_try = client.post(f"/api/v1/vaccination-events/{entry['event_id']}/certificate",
                            headers=_h(clinic.tokens["owner_a"], clinic.org))
    assert owner_try.status_code == 403
    assert _verify(client, clinic, entry["event_id"], next_due_on=str(date.today() + timedelta(days=300))).status_code == 200
    row = _cred(owner_engine, entry["event_id"])  # issued in the vet's verification transaction
    assert row is not None and row.qr_text.startswith("PG1:")
    msg = cose.parse_sign1(cose.from_qr_text(row.qr_text))
    assert cose.verify_sign1(msg, bytes(row.public_key))
    p = msg.payload
    assert set(p) == {1, 2, 3, 4, 5, 6, 7}
    assert p[3][2] == "Coco" and p[4][1] == "Rabies (test)" and p[4][5] == "vet" and len(p[4][3]) == 10
    def texts(v):  # only the text values: random id bytes can print as "@" and made this test flaky
        if isinstance(v, dict):
            return [t for k, x in v.items() for t in [str(k), *texts(x)]]
        return [v] if isinstance(v, str) else []

    flat = " ".join(texts(p)).lower()
    for forbidden in ("@", "owner", "phone", "address", "lat", "lon"):
        assert forbidden not in flat, forbidden
    # The owner's view lists it with a QR; no certificate for unverified records.
    mine = client.get(f"/api/v1/my/pets/{pet['id']}/certificates", headers=_h(clinic.tokens["owner_a"])).json()
    assert mine["featured_event_id"] == entry["event_id"] and mine["items"][0]["qr_svg"].startswith("<svg")


def test_clinic_record_is_signed_and_correction_replaces_the_certificate(client, clinic, owner_engine, keys):
    pet = _pet(client, clinic)
    r = client.post("/api/v1/clinic/vaccinations", headers=_h(clinic.tokens["vet"], clinic.org),
                    json={"animal_id": pet["id"], "product_id": str(clinic.product),
                          "administered_on": str(date.today() - timedelta(days=2))})
    assert r.status_code == 201, r.text
    with owner_engine.begin() as c:
        event = c.execute(text("select id, row_version from app.animal_vaccination_events where animal_id = :a"),
                          {"a": pet["id"]}).one()
    old = _cred(owner_engine, event.id)
    assert old is not None
    rl_before = client.get("/api/v1/public/revocations").json()
    fixed = client.post(f"/api/v1/vaccination-events/{event.id}/correction", headers=_h(clinic.tokens["vet"], clinic.org),
                        json={"row_version": event.row_version, "reason": "Wrong date entered",
                              "administered_on": str(date.today() - timedelta(days=3))})
    assert fixed.status_code == 201, fixed.text
    new_id = fixed.json()["credential_id"]
    with owner_engine.begin() as c:
        revoked = c.execute(text("select state, replaced_by, revoke_reason from app.vaccination_credentials "
                                 "where id = :i"), {"i": old.id}).one()
        superseded = c.execute(text("select state from app.animal_vaccination_events where id = :e"),
                               {"e": event.id}).scalar()
    assert revoked.state == "revoked" and str(revoked.replaced_by) == new_id and superseded == "superseded"
    rl_after = client.get("/api/v1/public/revocations").json()
    assert rl_after["version"] > rl_before["version"]
    ids = cose.parse_sign1(base64.b64decode(rl_after["cose"])).payload[3]
    assert old.id.bytes in ids


def test_lists_are_signed_by_the_root_and_keys_rotate_and_revoke(client, clinic, owner_engine, keys):
    _, event_id = _verified_event(client, clinic, owner_engine)
    first = _cred(owner_engine, event_id)
    doc = client.get("/api/v1/public/trust-list").json()
    msg = cose.parse_sign1(base64.b64decode(doc["cose"]))
    assert doc["format"] == "PG-TL1" and cose.verify_sign1(msg, keys)
    assert not cose.verify_sign1(msg, cose.new_key()[1])  # another root key does not verify it
    entry = next(e for e in msg.payload[3] if e[1] == bytes.fromhex(first.kid))
    assert entry[4] == bytes(first.public_key) and entry[7] == "active"
    # Rotate: the old key is retired (still listed with an end date); new certificates use the new key.
    with owner_engine.begin() as c:
        c.execute(text("select app.set_request_context(null, :o)"), {"o": clinic.org})
        new_kid = credentials.rotate_key(c, credentials.Actor(clinic.org, None))
    reissued = client.post(f"/api/v1/vaccination-events/{event_id}/certificate", headers=_h(clinic.tokens["vet"], clinic.org))
    assert reissued.status_code == 201
    assert _cred(owner_engine, event_id).kid == new_kid
    keys_now = {e[1].hex(): e for e in cose.parse_sign1(base64.b64decode(
        client.get("/api/v1/public/trust-list").json()["cose"])).payload[3]}
    assert keys_now[first.kid][7] == "retired" and 6 in keys_now[first.kid] and keys_now[new_kid][7] == "active"
    # Revoke a (compromised) key: listed as revoked.
    with owner_engine.begin() as c:
        assert credentials.revoke_key(c, credentials.Actor(clinic.org, None), new_kid, "test: key leaked")
    keys_after = {e[1].hex(): e for e in cose.parse_sign1(base64.b64decode(
        client.get("/api/v1/public/trust-list").json()["cose"])).payload[3]}
    assert keys_after[new_kid][7] == "revoked"
    with owner_engine.begin() as c:
        actions = set(c.execute(text("select action from app.audit_events where org_id = :o and action like "
                                     "'signing_key.%'"), {"o": clinic.org}).scalars())
    assert {"signing_key.created", "signing_key.rotated", "signing_key.revoked"} <= actions


def test_independent_cose_library_verifies_our_certificates(client, clinic, owner_engine, keys):
    from pycose.keys import OKPKey
    from pycose.keys.curves import Ed25519
    from pycose.messages import Sign1Message

    _, event_id = _verified_event(client, clinic, owner_engine)
    row = _cred(owner_engine, event_id)
    # pycose 1.1.0 predates cbor2 6 (which returns tuples), so hand it the decoded COSE_Sign1 array directly.
    protected, unprotected, payload, signature = cbor2.loads(cose.from_qr_text(row.qr_text)).value
    msg = Sign1Message.from_cose_obj([protected, dict(unprotected), payload, signature], True)
    msg.key = OKPKey(crv=Ed25519, x=bytes(row.public_key))
    assert msg.verify_signature()


def test_any_changed_byte_fails_and_bad_codes_are_rejected(client, clinic, owner_engine, keys):
    _, event_id = _verified_event(client, clinic, owner_engine)
    row = _cred(owner_engine, event_id)
    raw = cose.from_qr_text(row.qr_text)
    msg = cose.parse_sign1(raw)
    start = raw.find(msg.body)
    for i in range(len(msg.body)):
        b = bytearray(raw)
        b[start + i] ^= 0x01
        try:
            changed = cose.parse_sign1(bytes(b))
        except cose.InvalidCertificate:
            continue
        assert not cose.verify_sign1(changed, bytes(row.public_key)), i
    bomb = "PG1:" + base45.b45encode(zlib.compress(b"\x00" * 100_000)).decode()
    for bad in ("", "hello", "https://example.org/card/x", "PG1:", "PG1:%%%", "PG1:" + "A" * 2100, bomb,
                "HC1:" + row.qr_text[4:]):
        with pytest.raises(cose.InvalidCertificate):
            cose.parse_sign1(cose.from_qr_text(bad))
    not_cose = "PG1:" + base45.b45encode(zlib.compress(cbor2.dumps({"a": 1}))).decode()
    with pytest.raises(cose.InvalidCertificate):
        cose.parse_sign1(cose.from_qr_text(not_cose))


def test_private_keys_never_appear_in_responses_or_logs(client, clinic, owner_engine, keys, caplog):
    caplog.set_level(logging.DEBUG)
    pet, event_id = _verified_event(client, clinic, owner_engine)
    bodies = [client.get(path, headers=headers).text for path, headers in (
        ("/api/v1/public/trust-list", {}), ("/api/v1/public/revocations", {}),
        (f"/api/v1/my/pets/{pet['id']}/certificates", _h(clinic.tokens["owner_a"])),
        (f"/api/v1/public/credentials/{_cred(owner_engine, event_id).id}/photo", {}))]
    bodies.append(client.post(f"/api/v1/vaccination-events/{event_id}/certificate",
                              headers=_h(clinic.tokens["vet"], clinic.org)).text)
    with owner_engine.begin() as c:
        sealed = c.execute(text("select kid, private_key_sealed from app.clinic_signing_keys where org_id = :o"),
                           {"o": clinic.org}).all()
    s = get_settings()
    secrets_ = []
    for row in sealed:
        from cryptography.hazmat.primitives import serialization

        raw = cose.unseal(bytes(row.private_key_sealed), row.kid, s).private_bytes(
            serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
        secrets_ += [raw.hex(), base64.b64encode(raw).decode(), base64.urlsafe_b64encode(raw).decode().rstrip("="),
                     bytes(row.private_key_sealed).hex()]
    from cryptography.hazmat.primitives import serialization

    root_raw = cose.root_key(s).private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                                              serialization.NoEncryption())
    secrets_ += [root_raw.hex(), base64.b64encode(root_raw).decode(), base64.b64encode(b"\x07" * 32).decode()]
    haystack = "\n".join(bodies) + "\n" + caplog.text
    for secret in secrets_:
        assert secret not in haystack
