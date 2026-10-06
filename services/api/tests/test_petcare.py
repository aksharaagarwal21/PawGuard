"""Pet vaccination tracking and reminders: status rules, reminder scheduling and owner/clinic permissions."""

import uuid
from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from pawguard_api.domain.reminders import (
    Record,
    current_reminder,
    ics_event,
    pet_status,
    reminder_plan,
    schedule_reminders,
)

TODAY = date(2026, 10, 7)


# ---- status rules (pure) -------------------------------------------------------------------------------------

def _v(due_in: int | None, given_ago: int = 300, vaccine: str = "Rabies", state: str = "verified") -> Record:
    due = TODAY + timedelta(days=due_in) if due_in is not None else None
    return Record(state, vaccine, TODAY - timedelta(days=given_ago), due, "vet" if due else None)


@pytest.mark.parametrize(("due_in", "expected"), [
    (15, "up_to_date"), (14, "due_soon"), (1, "due_soon"), (0, "due_soon"), (-1, "overdue"), (-90, "overdue"),
])
def test_status_boundaries(due_in, expected):
    s = pet_status([_v(due_in)], TODAY)
    assert s.status == expected and s.days_until_due == due_in


def test_no_records_is_no_verified_record_never_overdue():
    assert pet_status([], TODAY).status == "no_verified_record"
    assert pet_status([_v(-30, state="rejected"), _v(-30, state="superseded")], TODAY).status == "no_verified_record"


def test_unverified_only_is_its_own_state():
    s = pet_status([_v(-30, state="submitted")], TODAY)
    assert s.status == "unverified_record" and s.next_due_on is None


def test_verified_without_due_date_is_up_to_date_without_a_date():
    s = pet_status([_v(None)], TODAY)
    assert s.status == "up_to_date" and s.next_due_on is None


def test_latest_verified_record_per_vaccine_decides():
    old, new = _v(-5, given_ago=370), _v(360, given_ago=5)
    assert pet_status([old, new], TODAY).status == "up_to_date"
    # An unverified newer record does not clear an overdue verified one.
    assert pet_status([old, _v(360, given_ago=5, state="submitted")], TODAY).status == "overdue"
    # The earliest due date across vaccines wins.
    s = pet_status([_v(200, vaccine="Rabies"), _v(3, vaccine="DHPPi")], TODAY)
    assert (s.status, s.vaccine) == ("due_soon", "DHPPi")


def test_reminder_plan_and_visible_kind():
    due = date(2026, 11, 1)
    plan = dict(reminder_plan(due))
    assert plan == {"due_in_14": date(2026, 10, 18), "due_in_7": date(2026, 10, 25), "due_in_1": date(2026, 10, 31),
                    "overdue": date(2026, 11, 2)}
    rows = [SimpleNamespace(state="pending", show_on=d, snoozed_until=None, kind=k) for k, d in plan.items()]
    assert current_reminder(rows, date(2026, 10, 17)) is None
    assert current_reminder(rows, date(2026, 10, 26)).kind == "due_in_7"
    assert current_reminder(rows, date(2026, 11, 1)).kind == "due_in_1"
    assert current_reminder(rows, date(2026, 11, 2)).kind == "overdue"
    snoozed = [SimpleNamespace(**{**vars(r), "snoozed_until": date(2026, 10, 28)}) for r in rows]
    assert current_reminder(snoozed, date(2026, 10, 26)) is None
    assert current_reminder(snoozed, date(2026, 10, 28)).kind == "due_in_7"


def test_ics_is_date_only_crlf_and_folded():
    body = ics_event("abc", "Coco", "Rabies vaccine (demo product)", date(2026, 10, 1),
                     "Demo — Lotus Pet Clinic (fictional) with a very long name for folding")
    lines = body.split("\r\n")
    assert body.endswith("\r\n") and "\n" not in body.replace("\r\n", "")
    assert "DTSTART;VALUE=DATE:20261001" in lines and "DTEND;VALUE=DATE:20261002" in lines
    assert all(len(line.encode()) <= 75 for line in lines)
    assert lines[0] == "BEGIN:VCALENDAR" and "END:VEVENT" in lines


# ---- API: owners, vets and reminders ---------------------------------------------------------------------------

@pytest.fixture
def clinic(world, make_token, owner_engine):
    org = world.org("Test clinic", demo=True)
    users = {"owner_a": world.member(org, "resident"), "owner_b": world.member(org, "resident"),
             "vet": world.member(org, "veterinary_reviewer"), "staff": world.member(org, "field_volunteer")}
    world.approve(org, users["vet"])
    tokens = {k: make_token(u, session_id=world.session(u)) for k, u in users.items()}
    with owner_engine.begin() as c:
        product = c.execute(text("""insert into app.vaccine_products (org_id, name, species, template_interval_days,
                                    template_label) values (:o, 'Rabies (test)', '{dog,cat}', 365, 'Demo template')
                                    returning id"""), {"o": org}).scalar_one()
    return SimpleNamespace(org=org, users=users, tokens=tokens, product=product)


def _media(owner_engine, org, uploader, purpose="vaccination_evidence"):
    with owner_engine.begin() as c:
        return c.execute(text("""insert into app.media_assets (org_id, bucket, object_key, purpose, declared_mime,
                                 declared_bytes, state, uploader_user_id)
                                 values (:o, 'media', :k, :p, 'image/jpeg', 1000, 'approved', :u) returning id"""),
                         {"o": org, "k": f"test/{uuid.uuid4()}", "p": purpose, "u": uploader}).scalar_one()


def _h(t, org=None):
    h = {"Authorization": f"Bearer {t}"}
    if org:
        h["X-PawGuard-Org"] = str(org)
    return h


def _pet(client, s, who="owner_a", **extra):
    r = client.post("/api/v1/my/pets", headers=_h(s.tokens[who]),
                    json={"clinic_org_id": str(s.org), "name": "Coco", "species": "dog", **extra})
    assert r.status_code == 201, r.text
    return r.json()


def _owner_record(client, s, owner_engine, pet, who="owner_a", days_ago=3):
    cert = _media(owner_engine, s.org, s.users[who])
    return client.post(f"/api/v1/my/pets/{pet['id']}/vaccinations", headers=_h(s.tokens[who]),
                       json={"product_id": str(s.product), "administered_on": str(date.today() - timedelta(days=days_ago)),
                             "certificate_media_ids": [str(cert)]})


def _verify(client, s, event_id, **extra):
    ev = client.get(f"/api/v1/vaccination-events/{event_id}", headers=_h(s.tokens["vet"], s.org)).json()
    return client.post(f"/api/v1/vaccination-events/{event_id}/reviews", headers=_h(s.tokens["vet"], s.org),
                       json={"outcome": "verified", "row_version": ev["row_version"], **extra})


def test_owner_sees_only_own_pets(client, clinic):
    pet = _pet(client, clinic)
    assert pet["status"]["status"] == "no_verified_record"
    assert [p["id"] for p in client.get("/api/v1/my/pets", headers=_h(clinic.tokens["owner_a"])).json()] == [pet["id"]]
    assert client.get("/api/v1/my/pets", headers=_h(clinic.tokens["owner_b"])).json() == []
    r = client.get(f"/api/v1/my/pets/{pet['id']}", headers=_h(clinic.tokens["owner_b"]))
    assert r.status_code == 404 and r.json()["error"]["code"] == "pet_not_found"
    # Owners have no registry-wide access in the clinic.
    assert client.get("/api/v1/animals", headers=_h(clinic.tokens["owner_a"], clinic.org)).status_code == 403
    assert client.get(f"/api/v1/animals/{pet['id']}", headers=_h(clinic.tokens["owner_a"], clinic.org)).status_code == 403


def test_owner_cannot_register_with_a_clinic_they_do_not_belong_to(client, clinic, world):
    other = world.org("Other clinic")
    r = client.post("/api/v1/my/pets", headers=_h(clinic.tokens["owner_a"]),
                    json={"clinic_org_id": str(other), "name": "X", "species": "cat"})
    assert r.status_code == 403


def test_owner_record_is_unverified_and_owner_cannot_verify(client, clinic, owner_engine):
    pet = _pet(client, clinic)
    r = _owner_record(client, clinic, owner_engine, pet)
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["status"]["status"] == "unverified_record" and d["awaiting_verification"] == 1
    entry = d["timeline"][0]
    assert entry["verification"] == "entered_by_owner_unverified"
    ev = client.get(f"/api/v1/vaccination-events/{entry['event_id']}", headers=_h(clinic.tokens["vet"], clinic.org))
    assert ev.json()["source_type"] == "owner_entry" and ev.json()["state"] == "submitted"
    # The owner cannot verify (no review capability), nor read the staff record.
    rv = client.post(f"/api/v1/vaccination-events/{entry['event_id']}/reviews",
                     headers=_h(clinic.tokens["owner_a"], clinic.org), json={"outcome": "verified", "row_version": 1})
    assert rv.status_code == 403
    # Another owner's certificate cannot be attached.
    foreign = _media(owner_engine, clinic.org, clinic.users["owner_b"])
    bad = client.post(f"/api/v1/my/pets/{pet['id']}/vaccinations", headers=_h(clinic.tokens["owner_a"]),
                      json={"product_id": str(clinic.product), "administered_on": str(date.today()),
                            "certificate_media_ids": [str(foreign)]})
    assert bad.status_code == 422
    # Owner B cannot add a record to owner A's pet.
    assert _owner_record(client, clinic, owner_engine, pet, who="owner_b").status_code == 404


def test_vet_due_date_creates_reminders_and_rescheduling_replaces_them(client, clinic, owner_engine):
    pet = _pet(client, clinic)
    event_id = _owner_record(client, clinic, owner_engine, pet).json()["timeline"][0]["event_id"]
    due = date.today() + timedelta(days=10)
    assert _verify(client, clinic, event_id, next_due_on=str(due)).status_code == 200
    d = client.get(f"/api/v1/my/pets/{pet['id']}", headers=_h(clinic.tokens["owner_a"])).json()
    assert d["status"]["status"] == "due_soon" and d["status"]["next_due_source"] == "vet"
    assert d["timeline"][0]["verification"] == "verified_by_vet"
    rem = client.get("/api/v1/my/reminders", headers=_h(clinic.tokens["owner_a"])).json()
    assert [(r["kind"], r["due_on"]) for r in rem] == [("due_in_14", str(due))]
    assert "Preview" not in rem[0]["preview"]["sms"] and "Coco" in rem[0]["preview"]["sms"]
    assert client.get("/api/v1/my/reminders", headers=_h(clinic.tokens["owner_b"])).json() == []

    with owner_engine.begin() as c:
        assert c.execute(text("select count(*) from app.vaccination_reminders where animal_id = :a "
                              "and state = 'pending'"), {"a": pet["id"]}).scalar() == 4
        assert schedule_reminders(c, clinic.org, pet["id"]) == {"created": 0, "cancelled": 0}  # idempotent
        new_due = due + timedelta(days=30)
        c.execute(text("update app.animal_vaccination_events set next_review_on = :d where id = :e"),
                  {"d": new_due, "e": event_id})
        assert schedule_reminders(c, clinic.org, pet["id"]) == {"created": 4, "cancelled": 4}
        live = c.execute(text("select distinct due_on from app.vaccination_reminders where animal_id = :a "
                              "and state = 'pending'"), {"a": pet["id"]}).scalars().all()
        assert live == [new_due]


def test_template_fills_due_date_only_when_vet_gives_none(client, clinic, owner_engine):
    pet = _pet(client, clinic)
    r = _owner_record(client, clinic, owner_engine, pet, days_ago=5)
    entry = r.json()["timeline"][0]
    assert _verify(client, clinic, entry["event_id"]).status_code == 200
    d = client.get(f"/api/v1/my/pets/{pet['id']}", headers=_h(clinic.tokens["owner_a"])).json()
    given = date.fromisoformat(entry["administered_on"])
    assert d["timeline"][0]["next_due_on"] == str(given + timedelta(days=365))
    assert d["timeline"][0]["next_due_source"] == "demo_template"
    bad = _owner_record(client, clinic, owner_engine, pet, days_ago=2).json()["timeline"][0]["event_id"]
    r = _verify(client, clinic, bad, next_due_on=str(date.today() - timedelta(days=10)))
    assert r.status_code == 422


def test_snooze_done_rejection_and_calendar(client, clinic, owner_engine):
    pet = _pet(client, clinic)
    first = _owner_record(client, clinic, owner_engine, pet, days_ago=300).json()["timeline"][0]["event_id"]
    _verify(client, clinic, first, next_due_on=str(date.today() - timedelta(days=2)))  # overdue
    rem = client.get("/api/v1/my/reminders", headers=_h(clinic.tokens["owner_a"])).json()
    assert [r["kind"] for r in rem] == ["overdue"]
    rid = rem[0]["id"]

    ics = client.get(f"/api/v1/my/reminders/{rid}/calendar.ics", headers=_h(clinic.tokens["owner_a"]))
    assert ics.status_code == 200 and ics.headers["content-type"].startswith("text/calendar")
    assert f"DTSTART;VALUE=DATE:{(date.today() - timedelta(days=2)):%Y%m%d}" in ics.text
    assert client.get(f"/api/v1/my/reminders/{rid}/calendar.ics",
                      headers=_h(clinic.tokens["owner_b"])).status_code == 404

    assert client.post(f"/api/v1/my/reminders/{rid}/snooze", headers=_h(clinic.tokens["owner_a"]),
                       json={"days": 3}).status_code == 204
    assert client.get("/api/v1/my/reminders", headers=_h(clinic.tokens["owner_a"])).json() == []
    assert client.post(f"/api/v1/my/reminders/{rid}/snooze", headers=_h(clinic.tokens["owner_a"]),
                       json={"days": 2}).status_code == 422

    with owner_engine.begin() as c:
        c.execute(text("update app.vaccination_reminders set snoozed_until = null where animal_id = :a"),
                  {"a": pet["id"]})
    cert = _media(owner_engine, clinic.org, clinic.users["owner_a"])
    done = client.post(f"/api/v1/my/reminders/{rid}/done", headers=_h(clinic.tokens["owner_a"]),
                       json={"product_id": str(clinic.product), "administered_on": str(date.today()),
                             "certificate_media_ids": [str(cert)]})
    assert done.status_code == 201, done.text
    assert done.json()["status"]["status"] == "overdue"  # unverified record does not clear it
    assert done.json()["awaiting_verification"] == 1
    assert client.get("/api/v1/my/reminders", headers=_h(clinic.tokens["owner_a"])).json() == []
    # The vet asks for a correction: the reminder comes back.
    new_event = next(t for t in done.json()["timeline"] if t["verification"] == "entered_by_owner_unverified")
    ev = client.get(f"/api/v1/vaccination-events/{new_event['event_id']}", headers=_h(clinic.tokens["vet"], clinic.org))
    r = client.post(f"/api/v1/vaccination-events/{new_event['event_id']}/reviews",
                    headers=_h(clinic.tokens["vet"], clinic.org),
                    json={"outcome": "needs_correction", "reason": "Certificate unreadable",
                          "row_version": ev.json()["row_version"]})
    assert r.status_code == 200, r.text
    assert [x["kind"] for x in client.get("/api/v1/my/reminders", headers=_h(clinic.tokens["owner_a"])).json()] \
        == ["overdue"]


def test_demo_clock_is_staff_only_demo_only_and_moves_reminders(client, clinic, owner_engine, world, make_token,
                                                                monkeypatch):
    from pawguard_api.settings import get_settings

    pet = _pet(client, clinic)
    event_id = _owner_record(client, clinic, owner_engine, pet).json()["timeline"][0]["event_id"]
    _verify(client, clinic, event_id, next_due_on=str(date.today() + timedelta(days=10)))
    kinds = lambda: [r["kind"] for r in client.get("/api/v1/my/reminders",  # noqa: E731
                                                   headers=_h(clinic.tokens["owner_a"])).json()]
    assert kinds() == ["due_in_14"]
    put = lambda who, org, d: client.put("/api/v1/clinic/demo-clock", headers=_h(clinic.tokens[who], org),  # noqa: E731
                                         json={"offset_days": d})
    assert put("staff", clinic.org, 5).status_code == 403  # demo mode is off
    monkeypatch.setattr(get_settings(), "demo_mode", True)
    assert put("owner_a", clinic.org, 5).status_code == 403  # owners are not staff
    r = put("staff", clinic.org, 5)
    assert r.status_code == 200 and r.json()["offset_days"] == 5
    assert kinds() == ["due_in_7"]
    assert put("staff", clinic.org, 11).status_code == 200
    assert kinds() == ["overdue"]
    d = client.get(f"/api/v1/my/pets/{pet['id']}", headers=_h(clinic.tokens["owner_a"])).json()
    assert d["status"]["status"] == "overdue" and d["demo_offset_days"] == 11
    # A real (non-demo) organisation cannot move its date.
    real = world.org("Real clinic")
    staff = world.member(real, "field_volunteer")
    tok = make_token(staff, session_id=world.session(staff))
    assert client.put("/api/v1/clinic/demo-clock", headers=_h(tok, real), json={"offset_days": 3}).status_code == 403


def test_card_token_public_view_regenerate_revoke_and_pdf(client, clinic, owner_engine):
    pet = _pet(client, clinic, name="Misty", species="cat")
    first = _owner_record(client, clinic, owner_engine, pet).json()["timeline"][0]["event_id"]
    _verify(client, clinic, first, next_due_on=str(date.today() + timedelta(days=200)))
    _owner_record(client, clinic, owner_engine, pet, days_ago=1)  # unverified: must not appear publicly
    owner = _h(clinic.tokens["owner_a"])
    card = client.get(f"/api/v1/my/pets/{pet['id']}/card", headers=owner, params={"base_url": "https://pets.example"})
    assert card.status_code == 200, card.text
    token = card.json()["token"]
    assert len(token) >= 32 and card.json()["qr_svg"].lstrip().startswith("<svg")
    assert client.get(f"/api/v1/my/pets/{pet['id']}/card", headers=owner).json()["token"] == token  # stable
    assert client.get(f"/api/v1/my/pets/{pet['id']}/card", headers=_h(clinic.tokens["owner_b"])).status_code == 404
    assert client.get(f"/api/v1/my/pets/{pet['id']}/card", headers=owner,
                      params={"base_url": "javascript:alert(1)"}).status_code == 422

    pub = client.get(f"/api/v1/public/cards/{token}")
    assert pub.status_code == 200 and pub.headers["cache-control"] == "no-store"
    body = pub.json()
    assert set(body) == {"pet_name", "species", "photo_url", "clinic_name", "status", "vaccinations", "is_demo",
                         "disclaimer"}
    assert body["pet_name"] == "Misty" and body["status"]["status"] == "up_to_date"
    assert len(body["vaccinations"]) == 1  # verified only
    assert body["disclaimer"] == "This card shows recorded vaccinations. It is not a health guarantee."
    assert str(clinic.users["owner_a"]) not in pub.text

    pdf = client.get(f"/api/v1/my/pets/{pet['id']}/card.pdf", headers=owner)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF") and pdf.headers["content-type"] == "application/pdf"

    new = client.post(f"/api/v1/my/pets/{pet['id']}/card/regenerate", headers=owner).json()["token"]
    assert new != token
    assert client.get(f"/api/v1/public/cards/{token}").status_code == 404  # old QR stops working
    assert client.get(f"/api/v1/public/cards/{new}").status_code == 200
    assert client.delete(f"/api/v1/my/pets/{pet['id']}/card", headers=owner).status_code == 204
    revoked = client.get(f"/api/v1/public/cards/{new}")
    assert revoked.status_code == 404 and revoked.json()["error"]["code"] == "card_not_found"
    assert client.get("/api/v1/public/cards/" + "x" * 40).status_code == 404
