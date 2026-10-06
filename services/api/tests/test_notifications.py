"""Outbound notifications: wording, opt-in settings, idempotent scanning, sending rules and staff overview."""

import uuid
from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from pawguard_api.integrations import notify
from pawguard_api.settings import get_settings


def _h(t, org=None):
    h = {"Authorization": f"Bearer {t}"}
    if org:
        h["X-PawGuard-Org"] = str(org)
    return h


@pytest.fixture
def setup(world, make_token, owner_engine, client, monkeypatch):
    # Scanning and sending are global (all organisations): start each test from a clean notification state.
    with owner_engine.begin() as c:
        c.execute(text("delete from app.notification_deliveries"))
        c.execute(text("delete from app.notification_preferences"))
        c.execute(text("delete from app.provider_status"))

    def build(demo: bool):
        org = world.org("Notify clinic", demo=demo)
        owner = world.member(org, "resident")
        other = world.member(org, "resident")
        vet = world.member(org, "veterinary_reviewer")
        world.approve(org, vet)
        tok = {k: make_token(u, session_id=world.session(u)) for k, u in
               {"owner": owner, "other": other, "vet": vet}.items()}
        with owner_engine.begin() as c:
            product = c.execute(text("insert into app.vaccine_products (org_id, name) values (:o, 'Rabies (t)') "
                                     "returning id"), {"o": org}).scalar_one()
        pet = client.post("/api/v1/my/pets", headers=_h(tok["owner"]),
                          json={"clinic_org_id": str(org), "name": "Coco", "species": "dog"}).json()
        r = client.post("/api/v1/clinic/vaccinations", headers=_h(tok["vet"], org),
                        json={"animal_id": pet["id"], "product_id": str(product),
                              "administered_on": str(date.today() - timedelta(days=300)),
                              "next_due_on": str(date.today() + timedelta(days=10))})
        assert r.status_code == 201, r.text
        return SimpleNamespace(org=org, owner=owner, other=other, vet=vet, tok=tok, pet=pet)

    s = get_settings()
    for k, v in {"smtp_user": "sender@example.com", "smtp_password": "app-password", "email_daily_cap": 100,
                 "demo_notify_email": "team-inbox@example.com"}.items():
        monkeypatch.setattr(s, k, v)
    sent: list[tuple[str, notify.Message]] = []

    def fake_send(_s, to, msg):
        sent.append((to, msg))
        return f"<id-{len(sent)}@test>"

    monkeypatch.setattr(notify, "send_email", fake_send)
    return SimpleNamespace(build=build, sent=sent, settings=s)


def _queue(owner_engine):
    with owner_engine.begin() as c:
        return c.execute(text("select app.queue_due_notifications()")).scalar()


def _deliveries(owner_engine, user):
    with owner_engine.begin() as c:
        return c.execute(text("select channel, kind, state, last_error from app.notification_deliveries "
                              "where user_id = :u order by created_at"), {"u": user}).all()


def test_compose_has_only_reminder_facts():
    s = get_settings()
    info = {"kind": "vaccination_reminder", "pet": "Coco", "vaccine": "Rabies", "clinic": "Lotus",
            "due_on": "2026-10-01", "today": "2026-10-07", "is_demo": True}
    m = notify.compose(info, s)
    assert m.subject == "Reminder: Coco's Rabies vaccination was due on 1 Oct 2026"
    assert "Please contact Lotus" in m.short and "/en/app/reminders" in m.text
    assert "Demo — fictional" in m.text and "your vet decides" in m.text
    m2 = notify.compose({**info, "due_on": "2026-10-17", "is_demo": False}, s)
    assert "is due on 17 Oct 2026" in m2.subject and "Demo" not in m2.text


def test_settings_are_opt_in_and_validated(client, setup):
    w = setup.build(demo=False)
    d = client.get("/api/v1/my/notification-settings", headers=_h(w.tok["owner"])).json()
    assert (d["email_enabled"], d["push_enabled"], d["whatsapp_enabled"]) == (False, False, False)
    assert d["available"]["email"] is True and d["demo_recipients"] is False
    r = client.put("/api/v1/my/notification-settings", headers=_h(w.tok["owner"]), json={"email_enabled": True})
    assert r.status_code == 422  # a real organisation needs the person's own address
    assert client.put("/api/v1/my/notification-settings", headers=_h(w.tok["owner"]),
                      json={"email_enabled": True, "email_address": "not-an-email"}).status_code == 422
    assert client.put("/api/v1/my/notification-settings", headers=_h(w.tok["owner"]),
                      json={"whatsapp_enabled": True, "whatsapp_number": "98765"}).status_code == 422
    ok = client.put("/api/v1/my/notification-settings", headers=_h(w.tok["owner"]),
                    json={"email_enabled": True, "email_address": "owner@example.com"})
    assert ok.status_code == 200 and ok.json()["email_enabled"] is True
    # Settings are private: another person sees only their own (defaults).
    other = client.get("/api/v1/my/notification-settings", headers=_h(w.tok["other"])).json()
    assert other["email_enabled"] is False and other["email_address"] is None


def test_scan_is_idempotent_and_sends_to_own_address(client, setup, owner_engine):
    from pawguard_worker import notify as worker_notify

    w = setup.build(demo=False)
    assert _queue(owner_engine) == 0  # nothing enabled yet
    client.put("/api/v1/my/notification-settings", headers=_h(w.tok["owner"]),
               json={"email_enabled": True, "email_address": "owner@example.com"})
    assert _queue(owner_engine) == 1
    assert _queue(owner_engine) == 0  # same reminder, same channel: never twice
    counts = worker_notify.drain()
    assert counts.get("sent") == 1
    to, msg = setup.sent[-1]
    assert to == "owner@example.com" and msg.subject.startswith("Reminder: Coco's Rabies (t) vaccination is due on")
    assert [(r.channel, r.kind, r.state) for r in _deliveries(owner_engine, w.owner)] == \
        [("email", "vaccination_reminder", "sent")]
    with owner_engine.begin() as c:
        assert c.execute(text("select state from app.provider_status where provider = 'email'")).scalar() == "ok"


def test_demo_sends_only_to_test_recipient_and_respects_cap(client, setup, owner_engine, monkeypatch):
    from pawguard_worker import notify as worker_notify

    w = setup.build(demo=True)
    client.put("/api/v1/my/notification-settings", headers=_h(w.tok["owner"]),
               json={"email_enabled": True, "email_address": "someone-real@example.com"})
    monkeypatch.setattr(setup.settings, "email_daily_cap", 0)
    _queue(owner_engine)
    assert worker_notify.drain().get("deferred") == 1  # cap reached: held, not dropped
    with owner_engine.begin() as c:
        assert c.execute(text("select state from app.provider_status where provider = 'email'")).scalar() == "cap_reached"
        c.execute(text("update app.notification_deliveries set available_at = now() where user_id = :u"),
                  {"u": w.owner})
    monkeypatch.setattr(setup.settings, "email_daily_cap", 100)
    assert worker_notify.drain().get("sent") == 1
    assert setup.sent[-1][0] == "team-inbox@example.com"  # never the address on file in a demo organisation


def test_unconfigured_provider_and_stale_reminders_are_skipped(client, setup, owner_engine, monkeypatch):
    from pawguard_worker import notify as worker_notify

    w = setup.build(demo=False)
    client.put("/api/v1/my/notification-settings", headers=_h(w.tok["owner"]),
               json={"email_enabled": True, "email_address": "owner@example.com"})
    _queue(owner_engine)
    with owner_engine.begin() as c:  # the owner marked it done before the worker ran
        c.execute(text("update app.vaccination_reminders set state = 'done' where animal_id = :a"), {"a": w.pet["id"]})
    assert worker_notify.drain().get("skipped") == 1
    assert _deliveries(owner_engine, w.owner)[-1].last_error == "reminder no longer pending"

    monkeypatch.setattr(setup.settings, "smtp_password", None)
    r = client.post("/api/v1/my/notification-settings/test", headers=_h(w.tok["owner"], w.org), json={"channel": "email"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "channel_unavailable"


def test_test_messages_are_rate_limited(client, setup, owner_engine):
    from pawguard_worker import notify as worker_notify

    w = setup.build(demo=False)
    client.put("/api/v1/my/notification-settings", headers=_h(w.tok["owner"]),
               json={"email_enabled": False, "email_address": "owner@example.com"})
    for _ in range(5):
        assert client.post("/api/v1/my/notification-settings/test", headers=_h(w.tok["owner"], w.org),
                           json={"channel": "email"}).status_code == 202
    r = client.post("/api/v1/my/notification-settings/test", headers=_h(w.tok["owner"], w.org), json={"channel": "email"})
    assert r.status_code == 429
    assert worker_notify.drain().get("sent") == 5
    assert setup.sent[-1][1].subject == "PawGuard test message"


def test_staff_overview_has_states_not_addresses(client, setup, owner_engine):
    from pawguard_worker import notify as worker_notify

    w = setup.build(demo=False)
    client.put("/api/v1/my/notification-settings", headers=_h(w.tok["owner"]),
               json={"email_enabled": True, "email_address": "owner-private@example.com"})
    _queue(owner_engine)
    worker_notify.drain()
    assert client.get("/api/v1/clinic/notifications", headers=_h(w.tok["owner"], w.org)).status_code == 403
    r = client.get("/api/v1/clinic/notifications", headers=_h(w.tok["vet"], w.org))
    assert r.status_code == 200 and "owner-private@example.com" not in r.text
    body = r.json()
    assert body["deliveries"][0]["state"] == "sent" and body["deliveries"][0]["pet_name"] == "Coco"
    assert {p["provider"] for p in body["providers"]} == {"email", "push", "whatsapp"}
    # Demo-only scan trigger.
    assert client.post("/api/v1/clinic/notifications/run", headers=_h(w.tok["vet"], w.org)).status_code == 403
    assert uuid.UUID(body["deliveries"][0]["id"])


# ---- Web Push ----------------------------------------------------------------------------------------------------

def test_vapid_keys_and_endpoint_allow_list():
    import base64

    pub, priv = notify.generate_vapid_keys()
    pad = lambda s: s + "=" * (-len(s) % 4)  # noqa: E731
    assert len(base64.urlsafe_b64decode(pad(pub))) == 65 and len(base64.urlsafe_b64decode(pad(priv))) == 32
    assert notify.push_endpoint_allowed("https://fcm.googleapis.com/fcm/send/abc")
    assert notify.push_endpoint_allowed("https://web.push.apple.com/QGx")
    assert notify.push_endpoint_allowed("https://wns2-pn1p.notify.windows.com/w/?token=x")
    assert not notify.push_endpoint_allowed("https://evil.example.com/fcm.googleapis.com")
    assert not notify.push_endpoint_allowed("https://fcm.googleapis.com.evil.com/x")
    assert not notify.push_endpoint_allowed("http://fcm.googleapis.com/x")


def test_push_subscribe_send_and_revoke_gone_devices(client, setup, owner_engine, monkeypatch):
    import pywebpush

    from pawguard_worker import notify as worker_notify

    pub, priv = notify.generate_vapid_keys()
    for k, v in {"vapid_public_key": pub, "vapid_private_key": priv, "vapid_contact": "mailto:t@example.com"}.items():
        monkeypatch.setattr(setup.settings, k, v)
    w = setup.build(demo=False)
    assert client.get("/api/v1/push/public-key").json()["public_key"] == pub
    keys = {"p256dh": "B" * 87, "auth": "A" * 22}
    bad = client.post("/api/v1/my/push-subscriptions", headers=_h(w.tok["owner"]),
                      json={"endpoint": "https://attacker.example.com/x", "keys": keys})
    assert bad.status_code == 422
    for ep in ("https://fcm.googleapis.com/fcm/send/one", "https://fcm.googleapis.com/fcm/send/gone"):
        assert client.post("/api/v1/my/push-subscriptions", headers=_h(w.tok["owner"]),
                           json={"endpoint": ep, "keys": keys}).status_code == 204
    assert client.get("/api/v1/my/notification-settings", headers=_h(w.tok["owner"])).json()["push_devices"] == 2

    calls = []

    def fake_webpush(sub, data, **kw):
        calls.append((sub["endpoint"], data, kw["vapid_claims"]))
        if sub["endpoint"].endswith("gone"):
            raise pywebpush.WebPushException("gone", response=SimpleNamespace(status_code=410, text=""))
        return SimpleNamespace(status_code=201)

    monkeypatch.setattr(pywebpush, "webpush", fake_webpush)
    assert _queue(owner_engine) == 1  # push enabled by subscribing
    assert worker_notify.drain().get("sent") == 1
    assert {c[0] for c in calls} == {"https://fcm.googleapis.com/fcm/send/one", "https://fcm.googleapis.com/fcm/send/gone"}
    assert "Coco" in calls[0][1] and calls[0][2] == {"sub": "mailto:t@example.com"}
    with owner_engine.begin() as c:
        live = c.execute(text("select endpoint from app.push_subscriptions where user_id = :u and revoked_at is null"),
                         {"u": w.owner}).scalars().all()
    assert live == ["https://fcm.googleapis.com/fcm/send/one"]  # the gone device was revoked
    assert client.post("/api/v1/my/push-subscriptions/remove", headers=_h(w.tok["owner"]),
                       json={"endpoint": "https://fcm.googleapis.com/fcm/send/one"}).status_code == 204
    d = client.get("/api/v1/my/notification-settings", headers=_h(w.tok["owner"])).json()
    assert d["push_devices"] == 0 and d["push_enabled"] is False


# ---- WhatsApp ----------------------------------------------------------------------------------------------------

class _Resp:
    def __init__(self, status, body):
        self.status_code, self._body = status, body

    def json(self):
        return self._body


def _wa(monkeypatch, setup, responses, captured):
    import httpx

    for k, v in {"whatsapp_token": "test-token", "whatsapp_phone_number_id": "1234567890",
                 "demo_notify_whatsapp": "+919800000001", "whatsapp_app_secret": "app-secret",
                 "whatsapp_verify_token": "verify-me"}.items():
        monkeypatch.setattr(setup.settings, k, v)

    def fake_post(url, json, headers, timeout):
        captured.append((url, json, headers))
        return responses.pop(0)

    monkeypatch.setattr(httpx, "post", fake_post)


def test_whatsapp_text_template_and_token_expiry(client, setup, owner_engine, monkeypatch):
    from pawguard_worker import notify as worker_notify

    captured: list = []
    responses = [_Resp(200, {"messages": [{"id": "wamid.ONE"}]}),
                 _Resp(400, {"error": {"code": 190, "message": "Error validating access token"}})]
    _wa(monkeypatch, setup, responses, captured)
    w = setup.build(demo=True)
    client.put("/api/v1/my/notification-settings", headers=_h(w.tok["owner"]), json={"whatsapp_enabled": True})
    _queue(owner_engine)
    assert worker_notify.drain().get("sent") == 1
    url, body, headers = captured[-1]
    assert url == f"https://graph.facebook.com/{setup.settings.whatsapp_api_version}/1234567890/messages"
    assert body["to"] == "919800000001" and body["type"] == "text"  # demo: only the test number
    assert "Coco" in body["text"]["body"] and headers["Authorization"] == "Bearer test-token"
    # A test message with an expired token: provider shows "token expired", the delivery fails clearly.
    assert client.post("/api/v1/my/notification-settings/test", headers=_h(w.tok["owner"], w.org),
                       json={"channel": "whatsapp"}).status_code == 202
    assert worker_notify.drain().get("failed") == 1
    over = client.get("/api/v1/clinic/notifications", headers=_h(w.tok["vet"], w.org)).json()
    wa = next(p for p in over["providers"] if p["provider"] == "whatsapp")
    assert wa["state"] == "token_expired" and "renew" in wa["detail"]
    assert over["whatsapp_webhook_url"].endswith("/api/v1/webhooks/whatsapp")

    # With an approved template configured, reminders use it (works outside the 24-hour window).
    monkeypatch.setattr(setup.settings, "whatsapp_template", "pet_vaccination_reminder")
    msg = notify.compose({"kind": "vaccination_reminder", "pet": "Coco", "vaccine": "Rabies", "clinic": "Lotus",
                          "due_on": "2026-10-17", "today": "2026-10-07", "is_demo": True}, setup.settings)
    responses.append(_Resp(200, {"messages": [{"id": "wamid.TWO"}]}))
    notify.send_whatsapp(setup.settings, "+919800000001", msg,
                         {"kind": "vaccination_reminder", "pet": "Coco", "vaccine": "Rabies", "clinic": "Lotus",
                          "due_on": "2026-10-17"})
    tpl = captured[-1][1]["template"]
    assert tpl["name"] == "pet_vaccination_reminder"
    assert [p["text"] for p in tpl["components"][0]["parameters"]] == ["Lotus", "Coco", "Rabies", "17 Oct 2026"]


def test_whatsapp_outside_window_and_rate_limit_codes(setup, monkeypatch):
    captured: list = []
    responses = [_Resp(400, {"error": {"code": 131047}}), _Resp(400, {"error": {"code": 130429}})]
    _wa(monkeypatch, setup, responses, captured)
    msg = notify.Message("s", "t", "short", "link")
    with pytest.raises(notify.ProviderError) as e1:
        notify.send_whatsapp(setup.settings, "+919800000001", msg, {"kind": "test"})
    assert e1.value.code == "outside_window" and e1.value.retry_in is None and "reply 'hi'" in e1.value.detail
    with pytest.raises(notify.ProviderError) as e2:
        notify.send_whatsapp(setup.settings, "+919800000001", msg, {"kind": "test"})
    assert e2.value.code == "rate_limited" and e2.value.retry_in == 600


def test_whatsapp_webhook_verification_and_signature(client, setup, owner_engine, monkeypatch):
    import hashlib
    import hmac
    import json as _json

    from pawguard_worker import notify as worker_notify

    captured: list = []
    _wa(monkeypatch, setup, [_Resp(200, {"messages": [{"id": "wamid.SENT1"}]})], captured)
    ok = client.get("/api/v1/webhooks/whatsapp",
                    params={"hub.mode": "subscribe", "hub.verify_token": "verify-me", "hub.challenge": "12345"})
    assert ok.status_code == 200 and ok.text == "12345"
    assert client.get("/api/v1/webhooks/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "wrong",
                                                            "hub.challenge": "1"}).status_code == 403
    w = setup.build(demo=True)
    client.put("/api/v1/my/notification-settings", headers=_h(w.tok["owner"]), json={"whatsapp_enabled": True})
    _queue(owner_engine)
    worker_notify.drain()
    body = _json.dumps({"entry": [{"changes": [{"value": {"statuses": [{
        "id": "wamid.SENT1", "status": "failed", "errors": [{"code": 131026, "title": "Message undeliverable"}]}]}}]}]})
    raw = body.encode()
    bad = client.post("/api/v1/webhooks/whatsapp", content=raw, headers={"X-Hub-Signature-256": "sha256=deadbeef"})
    assert bad.status_code == 403
    sig = "sha256=" + hmac.new(b"app-secret", raw, hashlib.sha256).hexdigest()
    assert client.post("/api/v1/webhooks/whatsapp", content=raw, headers={"X-Hub-Signature-256": sig}).status_code == 200
    rows = _deliveries(owner_engine, w.owner)
    assert rows[-1].state == "failed" and rows[-1].last_error == "WhatsApp 131026: Message undeliverable"
