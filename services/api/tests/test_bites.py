"""'This pet bit someone' check: day counting, timeline, reports, privacy, urgent changes, share links, limits,
closing and the wording rules (never "safe", "rabies-free" or "no treatment needed")."""

import json
import re
import uuid
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import text
from test_petcare import _h, _pet

from pawguard_api.domain import bites
from pawguard_api.integrations import notify

FORBIDDEN = re.compile(r"\bsafe\b|rabies[- ]free|no treatment (is )?needed", re.I)


@pytest.fixture
def case(world, make_token, owner_engine, client, monkeypatch):
    """A demo clinic, an owner with a pet and a live card token, an approved vet; owner email confirmed."""
    org = world.org("Bite clinic", demo=True)
    users = {"owner_a": world.member(org, "resident"), "vet": world.member(org, "veterinary_reviewer")}
    world.approve(org, users["vet"])
    tokens = {k: make_token(u, session_id=world.session(u)) for k, u in users.items()}
    s = SimpleNamespace(org=org, users=users, tokens=tokens)
    pet = _pet(client, s)
    card = client.get(f"/api/v1/my/pets/{pet['id']}/card", headers=_h(tokens["owner_a"])).json()
    with owner_engine.begin() as c:
        c.execute(text("""insert into app.notification_preferences (user_id, email_enabled, email_address,
                          email_verified_at) values (:u, true, 'owner@example.org', now())
                          on conflict (user_id) do update set email_enabled = true, email_verified_at = now()"""),
                  {"u": users["owner_a"]})
    sent: list[tuple[str, notify.Message]] = []
    monkeypatch.setattr(notify, "send_email", lambda _s, to, msg: sent.append((to, msg)) or "<id>")
    return SimpleNamespace(**vars(s), pet=pet, card=card["token"], sent=sent)


def _report(client, case, ip=None, **extra):
    ip = ip or f"test-{uuid.uuid4()}"  # each report its own client unless a test sets one
    body = {"bite_date": str(date.today() - timedelta(days=1)), "bitten": "person", **extra}
    return client.post(f"/api/v1/public/cards/{case.card}/bites", json=body, headers={"x-pawguard-client-ip": ip})


def _token(created) -> str:
    return created.json()["tracking_path"].removeprefix("/bite/")


# ---- days and timeline (no database) -----------------------------------------------------------------------------

def test_day_counting_uses_the_clinics_local_date():
    # 00:00 IST on 1 Feb is still 31 Jan in UTC: a bite at 11:30 pm on 31 Jan is "day 1" on 1 Feb in India.
    now = datetime(2026, 1, 31, 18, 30, tzinfo=UTC)
    assert bites.local_today("Asia/Kolkata", now) == date(2026, 2, 1)
    assert bites.day_of(date(2026, 1, 31), bites.local_today("Asia/Kolkata", now)) == 1
    assert bites.day_of(date(2026, 1, 31), date(2026, 1, 31)) == 0  # the day of the bite itself
    obs = bites.observation(date(2026, 1, 31), 10, "active", "note", [], date(2026, 2, 11))
    assert obs["timeline"][0]["date"] == date(2026, 2, 1)
    assert obs["timeline"][-1]["date"] == date(2026, 2, 10) and obs["ended"]
    leap = bites.observation(date(2028, 2, 28), 10, "active", "note", [], date(2028, 3, 1))
    assert [t["date"] for t in leap["timeline"]] == [date(2028, 2, 29), date(2028, 3, 1)]
    year_end = bites.observation(date(2026, 12, 30), 10, "active", "note", [], date(2027, 1, 2))
    assert year_end["current_day"] == 3 and year_end["timeline"][-1]["date"] == date(2027, 1, 2)


def test_missed_days_are_no_update_never_normal():
    checks = [{"day": 1, "state": "normal", "source": "owner"}, {"day": 3, "state": "normal", "source": "owner"}]
    obs = bites.observation(date(2026, 10, 3), 10, "active", "note", checks, date(2026, 10, 7))
    assert [t["status"] for t in obs["timeline"]] == ["normal", "no_update", "normal", "awaiting"]
    assert obs["missed_days"] == 1 and not obs["urgent"]
    ended = bites.observation(date(2026, 9, 1), 10, "active", "note", checks, date(2026, 9, 20))
    assert ended["status"] == "completed_with_gaps"
    changed = bites.observation(date(2026, 10, 3), 10, "active", "note",
                                [*checks, {"day": 2, "state": "not_eating", "source": "vet"}], date(2026, 10, 7))
    assert changed["urgent"] and changed["timeline"][1] == {"day": 2, "date": date(2026, 10, 5), "status": "change",
                                                            "owner_state": None, "vet_state": "not_eating"}


# ---- API ---------------------------------------------------------------------------------------------------------

def test_bite_mode_and_report_never_expose_the_owner(client, case, owner_engine):
    mode = client.get(f"/api/v1/public/cards/{case.card}/bite")
    assert mode.status_code == 200 and mode.json()["pet_name"] == "Coco"
    created = _report(client, case, contact_email="reporter@example.org", consent_updates=True)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["reference"].startswith("BR-") and body["duplicate"] is False and body["contact_saved"] is True
    view = client.get(f"/api/v1/public/bites/{_token(created)}")
    assert view.status_code == 200 and view.json()["purpose"] == "reporter"
    with owner_engine.begin() as c:
        owner_email = c.execute(text("select email_address from app.notification_preferences where user_id = :u"),
                                {"u": case.users["owner_a"]}).scalar()
        alerts = c.execute(text("select channel, kind from app.notification_deliveries where user_id = :u "
                                "and kind = 'bite_alert'"), {"u": case.users["owner_a"]}).all()
    for response in (mode, view):
        assert owner_email not in response.text and "owner_a" not in response.text
        assert "linked_user" not in response.text and "address" not in response.text
    assert alerts == [("email", "bite_alert")]  # owner told on their channel
    assert case.sent and "15 minutes" in case.sent[0][1].text and "/bite/" in case.sent[0][1].text  # tracking email


def test_reporter_contact_hidden_from_owner_unless_shared(client, case):
    _report(client, case, contact_email="hidden@example.org", consent_updates=True)
    _report(client, case, ip="10.0.0.2", contact_email="shared@example.org", consent_updates=True,
            consent_share_with_owner=True)
    cases = client.get("/api/v1/my/bites", headers=_h(case.tokens["owner_a"])).json()
    assert len(cases) == 1  # same pet and day: one observation
    contacts = [r["contact"] for r in cases[0]["reports"]]
    assert contacts == [None, "shared@example.org"]
    assert cases[0]["reports"][1]["possible_duplicate"] is True
    clinic = client.get("/api/v1/clinic/bites", headers=_h(case.tokens["vet"], case.org))
    assert "hidden@example.org" not in clinic.text and "shared@example.org" not in clinic.text


def test_a_change_alerts_reporter_doctor_link_and_clinic(client, case):
    created = _report(client, case, contact_email="reporter@example.org", consent_updates=True)
    token = _token(created)
    doctor = client.post(f"/api/v1/public/bites/{token}/doctor-links")
    assert doctor.status_code == 201
    doctor_token = doctor.json()["path"].removeprefix("/bite/")
    period = client.get("/api/v1/my/bites", headers=_h(case.tokens["owner_a"])).json()[0]["period_id"]
    case.sent.clear()
    r = client.post(f"/api/v1/my/bites/{period}/checkins", headers=_h(case.tokens["owner_a"]),
                    json={"state": "unusual_behaviour", "note": "Hiding under the bed"})
    assert r.status_code == 200, r.text
    assert r.json()["observation"]["urgent"] is True
    for t in (token, doctor_token):
        assert client.get(f"/api/v1/public/bites/{t}").json()["observation"]["urgent"] is True
    clinic = client.get("/api/v1/clinic/bites", headers=_h(case.tokens["vet"], case.org)).json()
    assert clinic[0]["observation"]["urgent"] is True
    assert len(case.sent) == 1 and "Tell your doctor right away" in case.sent[0][1].text
    assert "owner@example.org" not in case.sent[0][1].text
    # The vet records an examination; it is labelled as vet-recorded in the timeline.
    exam = client.post(f"/api/v1/clinic/bites/{period}/exams", headers=_h(case.tokens["vet"], case.org),
                       json={"state": "normal", "note": "Examined"})
    assert exam.status_code == 200
    day = exam.json()["observation"]["timeline"][-1]
    assert day["vet_state"] == "normal" and day["owner_state"] == "unusual_behaviour" and day["status"] == "change"


def test_share_links_expire_and_can_be_revoked(client, case, owner_engine):
    token = _token(_report(client, case))
    doctor_token = client.post(f"/api/v1/public/bites/{token}/doctor-links").json()["path"].removeprefix("/bite/")
    view = client.get(f"/api/v1/public/bites/{doctor_token}").json()
    assert view["purpose"] == "doctor" and view["doctor_links"] is None
    assert len(client.get(f"/api/v1/public/bites/{token}").json()["doctor_links"]) == 1
    assert client.post(f"/api/v1/public/bites/{token}/doctor-links/revoke").json() == {"revoked": 1}
    revoked = client.get(f"/api/v1/public/bites/{doctor_token}")
    assert revoked.status_code == 404 and "Coco" not in revoked.text
    with owner_engine.begin() as c:
        c.execute(text("update app.share_links set expires_at = now() - interval '1 minute' where purpose = 'reporter'"))
        views = c.execute(text("select count(*) from app.share_link_access")).scalar()
    assert client.get(f"/api/v1/public/bites/{token}").status_code == 404
    assert views >= 3  # every view is logged


def test_rate_limits_dates_and_duplicates(client, case):
    assert _report(client, case, bite_date=str(date.today() + timedelta(days=1))).status_code == 422
    assert _report(client, case, bite_date=str(date.today() - timedelta(days=31))).status_code == 422
    first = _report(client, case, ip="10.9.9.9")
    second = _report(client, case, ip="10.9.9.9")
    assert first.status_code == 201 and second.json()["duplicate"] is True
    assert _report(client, case, ip="10.9.9.9").status_code == 201
    limited = _report(client, case, ip="10.9.9.9")
    assert limited.status_code == 429 and "get medical care first" in limited.json()["error"]["message"]
    assert _report(client, case, ip="10.1.1.1").status_code == 201
    assert _report(client, case, ip="10.1.1.2").status_code == 201
    assert _report(client, case, ip="10.1.1.3").status_code == 429  # 5 per pet per day


def test_dispute_keeps_observation_and_closing_never_says_safe(client, case, owner_engine):
    _report(client, case)
    period = client.get("/api/v1/my/bites", headers=_h(case.tokens["owner_a"])).json()[0]["period_id"]
    d = client.post(f"/api/v1/my/bites/{period}/dispute", headers=_h(case.tokens["owner_a"]),
                    json={"reason": "My dog was at home with me all evening."})
    assert d.status_code == 200 and d.json()["disputed"] is True and d.json()["today_needed"] is True
    assert client.post(f"/api/v1/my/bites/{period}/checkins", headers=_h(case.tokens["owner_a"]),
                       json={"state": "normal"}).status_code == 200
    with owner_engine.begin() as c:  # move the bite 12 days back: the period has ended, with missed days
        c.execute(text("update app.observation_periods set bite_date = bite_date - 11 where id = :p"), {"p": period})
        closed = bites.close_and_notify(c)
        status = c.execute(text("select status from app.observation_periods where id = :p"), {"p": period}).scalar()
        notices = c.execute(text("select count(*) from app.notification_deliveries where kind = 'bite_closed'")).scalar()
    assert closed >= 1 and status == "completed_with_gaps" and notices >= 1


def test_wording_never_suggests_skipping_care(client, case):
    created = _report(client, case, contact_email="reporter@example.org", consent_updates=True)
    texts = [client.get(f"/api/v1/public/bites/{_token(created)}").text,
             client.get(f"/api/v1/public/cards/{case.card}/bite").text,
             *bites.CLOSING.values(), *bites.tracking_email("BR-AAAA-BBBB", "https://x", "Coco", date.today()),
             *bites.urgent_email("Coco", 2, "not_eating"), *(m.text for _, m in case.sent)]
    for info_kind in ("bite_alert", "bite_closed"):
        msg = notify.compose({"kind": info_kind, "pet": "Coco", "pet_sex": "female", "bite_date": "2026-10-01",
                              "observation_days": 10, "observation_status": "completed", "is_demo": True},
                             _settings())
        texts += [msg.subject, msg.text, msg.short]
    for t in texts:
        assert not FORBIDDEN.search(t), t[:200]
    en = json.dumps(_messages()["bite"])
    assert not FORBIDDEN.search(en)


def _settings():
    from pawguard_api.settings import get_settings

    return get_settings()


def _messages() -> dict:
    from pathlib import Path

    return json.loads((Path(__file__).resolve().parents[3] / "apps/web/messages/en.json").read_text(encoding="utf-8"))
