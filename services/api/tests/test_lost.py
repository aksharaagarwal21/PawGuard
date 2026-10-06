"""Lost pets: owner reports, private finder conversations, privacy and limits."""

import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from pawguard_api.domain import lost as lost_domain
from pawguard_api.integrations import notify
from pawguard_api.settings import get_settings


def _h(t, org=None):
    h = {"Authorization": f"Bearer {t}"}
    if org:
        h["X-PawGuard-Org"] = str(org)
    return h


@pytest.fixture
def pet(world, make_token, client, owner_engine):
    org = world.org("Lost clinic", demo=True)
    a, b = world.member(org, "resident"), world.member(org, "resident")
    tok = {k: make_token(u, session_id=world.session(u)) for k, u in {"a": a, "b": b}.items()}
    p = client.post("/api/v1/my/pets", headers=_h(tok["a"]),
                    json={"clinic_org_id": str(org), "name": "Coco", "species": "dog"}).json()
    card = client.get(f"/api/v1/my/pets/{p['id']}/card", headers=_h(tok["a"])).json()
    with owner_engine.begin() as c:
        c.execute(text("insert into app.notification_preferences (user_id, push_enabled, email_enabled, email_address) "
                       "values (:u, true, true, 'owner-secret@example.com') on conflict (user_id) do update set "
                       "push_enabled = true, email_enabled = true, email_address = 'owner-secret@example.com', "
                       "email_verified_at = null"), {"u": a})
    lost_domain._public.clear()
    return SimpleNamespace(org=org, a=a, b=b, tok=tok, id=p["id"], token=card["token"])


def test_full_conversation_without_revealing_the_owner(client, pet, owner_engine):
    assert client.get(f"/api/v1/public/cards/{pet.token}/lost").json()["lost"] is False
    r = client.post(f"/api/v1/public/cards/{pet.token}/found", json={"message": "Is this your dog?"})
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_lost"  # only while reported lost
    assert client.post(f"/api/v1/my/pets/{pet.id}/lost", headers=_h(pet.tok["b"]), json={}).status_code == 404
    assert client.post(f"/api/v1/my/pets/{pet.id}/lost", headers=_h(pet.tok["a"]),
                       json={"last_seen_on": "2026-10-05", "area_text": "Near the park gate", "note": "Red collar"}
                       ).status_code == 204
    st = client.get(f"/api/v1/public/cards/{pet.token}/lost").json()
    assert st == {"lost": True, "last_seen_on": "2026-10-05", "area_text": "Near the park gate"}

    r = client.post(f"/api/v1/public/cards/{pet.token}/found",
                    json={"message": "I found a dog with this tag near the market.", "contact": "Call 98xxxxxx01"})
    assert r.status_code == 201
    conv = r.json()["conversation_token"]
    with owner_engine.begin() as c:  # only the hash of the finder's link is stored
        stored = c.execute(text("select finder_token_hash from app.lost_threads")).scalars().all()
    assert conv not in stored

    view = client.get("/api/v1/my/lost", headers=_h(pet.tok["a"])).json()
    assert view[0]["state"] == "open" and view[0]["pet_name"] == "Coco"
    thread = view[0]["threads"][0]
    assert thread["unread"] == 1 and thread["finder_contact"] == "Call 98xxxxxx01"
    assert thread["messages"][0]["body"].startswith("I found a dog")
    assert client.get("/api/v1/my/lost", headers=_h(pet.tok["b"])).json() == []  # another owner sees nothing

    assert client.post(f"/api/v1/my/lost/threads/{thread['id']}/reply", headers=_h(pet.tok["a"]),
                       json={"message": "Thank you! Can you keep her safe until 6 pm?"}).status_code == 204
    assert client.post(f"/api/v1/my/lost/threads/{thread['id']}/reply", headers=_h(pet.tok["b"]),
                       json={"message": "x"}).status_code == 404
    fv = client.get(f"/api/v1/public/found/{conv}")
    assert fv.status_code == 200
    body = fv.json()
    assert [m["sender"] for m in body["messages"]] == ["finder", "owner"] and body["pet_name"] == "Coco"
    assert "owner-secret@example.com" not in fv.text and str(pet.a) not in fv.text  # the owner stays private
    assert client.post(f"/api/v1/public/found/{conv}/messages", json={"message": "Yes, see you then."}).status_code == 204

    # The owner was told on their channels (push here; email isn't confirmed so it isn't used), without the text.
    with owner_engine.begin() as c:
        rows = c.execute(text("select channel, kind from app.notification_deliveries where user_id = :u"),
                         {"u": pet.a}).all()
    assert {(r.channel, r.kind) for r in rows} == {("push", "lost_message")}
    msg = notify.compose({"kind": "lost_message", "pet": "Coco", "is_demo": True}, get_settings())
    assert "Coco" in msg.short and "market" not in msg.text and "/en/app/lost" in msg.link

    # Found: conversations close.
    assert client.post(f"/api/v1/my/pets/{pet.id}/found", headers=_h(pet.tok["a"])).status_code == 204
    r = client.post(f"/api/v1/public/found/{conv}/messages", json={"message": "Hello?"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "report_closed"
    assert client.get(f"/api/v1/public/found/{conv}").json()["found"] is True
    assert client.get(f"/api/v1/public/cards/{pet.token}/lost").json()["lost"] is False


def test_limits_and_revoked_cards(client, pet, owner_engine):
    client.post(f"/api/v1/my/pets/{pet.id}/lost", headers=_h(pet.tok["a"]), json={})
    with owner_engine.begin() as c:
        report = c.execute(text("select id from app.lost_reports where animal_id = :a"), {"a": pet.id}).scalar()
        for _ in range(20):
            c.execute(text("insert into app.lost_threads (org_id, animal_id, report_id, finder_token_hash) "
                           "values (:o, :a, :r, :h)"),
                      {"o": pet.org, "a": pet.id, "r": report, "h": uuid.uuid4().hex + uuid.uuid4().hex})
    r = client.post(f"/api/v1/public/cards/{pet.token}/found", json={"message": "spam"})
    assert r.status_code == 429  # at most 20 new conversations per pet per day
    assert client.get("/api/v1/public/found/" + "x" * 43).status_code == 404
    client.delete(f"/api/v1/my/pets/{pet.id}/card", headers=_h(pet.tok["a"]))
    assert client.get(f"/api/v1/public/cards/{pet.token}/lost").status_code == 404
    assert client.post(f"/api/v1/public/cards/{pet.token}/found", json={"message": "hi"}).status_code == 404
