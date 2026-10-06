"""Ask PawGuard: what is sent to the model, what comes back, and the guardrails around it."""

import time
from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from pawguard_api.domain import assistant
from pawguard_api.settings import get_settings


def _h(t, org=None):
    h = {"Authorization": f"Bearer {t}"}
    if org:
        h["X-PawGuard-Org"] = str(org)
    return h


class _Resp:
    def __init__(self, status, body):
        self.status_code, self._body = status, body

    def json(self):
        return self._body


@pytest.fixture
def owner(world, make_token, owner_engine, client, monkeypatch):
    org = world.org("Assistant clinic", demo=True)
    owner_id = world.member(org, "resident")
    vet = world.member(org, "veterinary_reviewer")
    world.approve(org, vet)
    staff = world.member(org, "field_volunteer")
    tok = {k: make_token(u, session_id=world.session(u)) for k, u in {"owner": owner_id, "vet": vet, "staff": staff}.items()}
    with owner_engine.begin() as c:
        product = c.execute(text("insert into app.vaccine_products (org_id, name) values (:o, 'Rabies (a)') returning id"),
                            {"o": org}).scalar_one()
    pet = client.post("/api/v1/my/pets", headers=_h(tok["owner"]),
                      json={"clinic_org_id": str(org), "name": "Coco", "species": "dog"}).json()
    client.post("/api/v1/clinic/vaccinations", headers=_h(tok["vet"], org),
                json={"animal_id": pet["id"], "product_id": str(product),
                      "administered_on": str(date.today() - timedelta(days=370)),
                      "next_due_on": str(date.today() - timedelta(days=5))})
    s = get_settings()
    for k, v in {"llm_provider": "gemini", "gemini_api_key": "AIza-test-key", "gemini_model": "gemini-test-flash"}.items():
        monkeypatch.setattr(s, k, v)
    assistant._recent.clear()
    return SimpleNamespace(org=org, tok=tok, settings=s)


def _fake_gemini(monkeypatch, replies, captured):
    import httpx

    def fake_post(url, json, headers, timeout):
        captured.append((url, json, headers))
        r = replies.pop(0)
        return r if isinstance(r, _Resp) else _Resp(200, {"candidates": [{"content": {"parts": [{"text": r}]},
                                                                           "finishReason": "STOP"}]})

    monkeypatch.setattr(httpx, "post", fake_post)


def test_redaction():
    assert assistant.redact("mail me at neha.k@example.com or +91 98765 43210") == \
        "mail me at [email removed] or [number removed]"
    assert assistant.redact("Coco is 3 years old") == "Coco is 3 years old"


def test_off_and_permissions(client, owner, monkeypatch):
    assert client.post("/api/v1/my/assistant", headers=_h(owner.tok["staff"]),
                       json={"messages": [{"role": "user", "text": "hi"}]}).status_code == 403  # owners only
    monkeypatch.setattr(owner.settings, "llm_provider", "off")
    assert client.get("/api/v1/my/assistant", headers=_h(owner.tok["owner"])).json() == \
        {"available": False, "provider": "off", "shares_with_google": False}
    r = client.post("/api/v1/my/assistant", headers=_h(owner.tok["owner"]), json={"messages": [{"role": "user", "text": "hi"}]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "assistant_unavailable"


def test_what_is_sent_and_how_the_reply_is_shaped(client, owner, monkeypatch):
    captured: list = []
    _fake_gemini(monkeypatch, ["Coco's rabies vaccine is overdue. Please book a visit with your clinic.\n"
                               "ACTIONS: mark_done, open_evil_link, add_calendar"], captured)
    r = client.post("/api/v1/my/assistant", headers=_h(owner.tok["owner"]),
                    json={"language": "en", "messages": [
                        {"role": "user", "text": "Is Coco ok? email me at owner@example.com, +91 98765 43210"}]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["actions"] == ["mark_done", "add_calendar"]  # unknown codes dropped
    assert "ACTIONS" not in body["reply"] and body["guarded"] is False
    url, sent, headers = captured[0]
    assert "key=" not in url and headers["x-goog-api-key"] == "AIza-test-key"  # key never in the URL
    system = sent["systemInstruction"]["parts"][0]["text"]
    assert "Coco (dog)" in system and "overdue" in system and "Never diagnose" in system
    user_text = sent["contents"][0]["parts"][0]["text"]
    assert "owner@example.com" not in user_text and "98765" not in user_text and "[email removed]" in user_text
    assert sent["generationConfig"]["temperature"] == 0.3


def test_dose_answers_are_replaced_and_bites_get_help(client, owner, monkeypatch):
    captured: list = []
    _fake_gemini(monkeypatch, ["Give 1 ml of vaccine yourself.\nACTIONS: none",
                               "Please wash the wound and see a doctor.\nACTIONS: none"], captured)
    r1 = client.post("/api/v1/my/assistant", headers=_h(owner.tok["owner"]),
                     json={"messages": [{"role": "user", "text": "How much vaccine should I give?"}]}).json()
    assert r1["guarded"] is True and "your vet decides" in r1["reply"] and "1 ml" not in r1["reply"]
    r2 = client.post("/api/v1/my/assistant", headers=_h(owner.tok["owner"]),
                     json={"messages": [{"role": "user", "text": "My son was bitten by a street dog"}]}).json()
    assert r2["actions"][0] == "bite_help"  # added even though the model said none


def test_busy_blocked_and_rate_limit(client, owner, monkeypatch):
    captured: list = []
    _fake_gemini(monkeypatch, [_Resp(429, {}), _Resp(200, {"promptFeedback": {"blockReason": "SAFETY"}})], captured)
    r = client.post("/api/v1/my/assistant", headers=_h(owner.tok["owner"]), json={"messages": [{"role": "user", "text": "hi"}]})
    assert r.status_code == 503 and r.json()["error"]["code"] == "assistant_busy"
    b = client.post("/api/v1/my/assistant", headers=_h(owner.tok["owner"]), json={"messages": [{"role": "user", "text": "x"}]})
    assert b.status_code == 200 and b.json()["guarded"] is True
    for q in assistant._recent.values():  # pretend this person already asked 20 questions this hour
        q.extend([time.monotonic()] * assistant.PER_HOUR)
    r = client.post("/api/v1/my/assistant", headers=_h(owner.tok["owner"]), json={"messages": [{"role": "user", "text": "hi"}]})
    assert r.status_code == 429


def test_ollama_path(client, owner, monkeypatch):
    import httpx

    monkeypatch.setattr(owner.settings, "llm_provider", "ollama")
    seen = {}

    def fake_post(url, json, timeout):
        seen["url"], seen["body"] = url, json
        return _Resp(200, {"message": {"content": "Hello from a local model.\nACTIONS: how_to"}})

    monkeypatch.setattr(httpx, "post", fake_post)
    r = client.post("/api/v1/my/assistant", headers=_h(owner.tok["owner"]),
                    json={"language": "ta", "messages": [{"role": "user", "text": "vanakkam"}]}).json()
    assert r == {"reply": "Hello from a local model.", "actions": ["how_to"], "guarded": False}
    assert seen["url"].endswith("/api/chat") and seen["body"]["messages"][0]["role"] == "system"
    assert "Tamil" in seen["body"]["messages"][0]["content"]
