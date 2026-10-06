"""Prevention domain: authorisation boundaries, state machines and data integrity (as the runtime role)."""

import threading
import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import text


@pytest.fixture
def org_setup(world, make_token, owner_engine):
    """One organisation with a volunteer, an approved vet (live session), an unapproved vet, a coordinator and an
    admin, plus an area, a product and a lot."""

    def build():
        org = world.org()
        users = {
            "volunteer": world.member(org, "field_volunteer"),
            "vet": world.member(org, "veterinary_reviewer"),
            "vet2": world.member(org, "veterinary_reviewer"),
            "vet_unapproved": world.member(org, "veterinary_reviewer"),
            "coordinator": world.member(org, "programme_coordinator"),
            "admin": world.member(org, "org_admin"),
        }
        world.approve(org, users["vet"])
        world.approve(org, users["vet2"])
        tokens = {k: make_token(u, session_id=world.session(u)) for k, u in users.items()}
        with owner_engine.begin() as c:
            area = c.execute(text("insert into app.areas (org_id, code, name) values (:o, 'W1', 'Ward 1') "
                                  "returning id"), {"o": org}).scalar_one()
            product = c.execute(text("insert into app.vaccine_products (org_id, name) values (:o, 'Test vaccine') "
                                     "returning id"), {"o": org}).scalar_one()
            lot = c.execute(text("insert into app.vaccine_lots (org_id, product_id, lot_number, expiry_date) "
                                 "values (:o, :p, 'L-001', :e) returning id"),
                            {"o": org, "p": product, "e": date.today() + timedelta(days=100)}).scalar_one()
        return {"org": org, "users": users, "tokens": tokens, "area": area, "product": product, "lot": lot}

    return build


def _animal(client, auth, s, who="volunteer", **extra):
    body = {"species": "dog", "nickname": "Brownie", "coat_description": "Brown, white blaze", "home_area_id":
            str(s["area"]), **extra}
    r = client.post("/api/v1/animals", headers=auth(s["tokens"][who], s["org"]), json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _vacc(client, auth, s, animal_id, who="volunteer", **extra):
    body = {"animal_id": animal_id, "date_precision": "day", "administered_on": str(date.today() - timedelta(days=1)),
            "product_id": str(s["product"]), "lot_id": str(s["lot"]), "administered_by_name": "Dr Test", **extra}
    return client.post("/api/v1/vaccination-events", headers=auth(s["tokens"][who], s["org"]), json=body)


# ---- registry ------------------------------------------------------------------------------------------------

def test_new_animals_are_provisional_with_no_verified_record(client, auth, org_setup):
    s = org_setup()
    a = _animal(client, auth, s)
    assert a["profile_state"] == "provisional"
    assert a["vaccination"]["status"] == "no_verified_record"
    assert a["reference_code"].startswith("PG-") and len(a["reference_code"]) == 12
    assert "location" not in a and "caregiver" not in str(a)


def test_unknown_is_explicit_not_missing(client, auth, org_setup):
    s = org_setup()
    a = _animal(client, auth, s, nickname=None)
    assert (a["sex"], a["age_band"], a["sterilisation_status"]) == ("unknown", "unknown", "unknown")


def test_extra_fields_cannot_be_injected(client, auth, org_setup):
    s = org_setup()
    r = client.post("/api/v1/animals", headers=auth(s["tokens"]["volunteer"], s["org"]),
                    json={"species": "dog", "profile_state": "active"})
    assert r.status_code == 422


def test_idempotent_creation(client, auth, org_setup, owner_engine):
    s = org_setup()
    h = {**auth(s["tokens"]["volunteer"], s["org"]), "Idempotency-Key": "key-" + uuid.uuid4().hex}
    body = {"species": "dog", "nickname": "Once"}
    r1 = client.post("/api/v1/animals", headers=h, json=body)
    r2 = client.post("/api/v1/animals", headers=h, json=body)
    assert r1.status_code == r2.status_code == 201 and r1.json()["id"] == r2.json()["id"]
    with owner_engine.connect() as c:
        assert c.execute(text("select count(*) from app.animals where org_id = :o and nickname = 'Once'"),
                         {"o": s["org"]}).scalar() == 1
    r3 = client.post("/api/v1/animals", headers=h, json={"species": "dog", "nickname": "Different"})
    assert r3.status_code == 422 and r3.json()["error"]["code"] == "idempotency_key_reused"


def test_search_pagination_and_counts_stay_in_tenant(client, auth, org_setup):
    a, b = org_setup(), org_setup()
    for i in range(3):
        _animal(client, auth, a, nickname=f"Alpha{i}")
    _animal(client, auth, b, nickname="AlphaB")
    r = client.get("/api/v1/animals?q=alpha&limit=2", headers=auth(a["tokens"]["volunteer"], a["org"])).json()
    assert r["total_matching"] == 3 and len(r["items"]) == 2 and r["next_cursor"]
    r2 = client.get(f"/api/v1/animals?q=alpha&limit=2&cursor={r['next_cursor']}",
                    headers=auth(a["tokens"]["volunteer"], a["org"])).json()
    names = {x["nickname"] for x in r["items"] + r2["items"]}
    assert names == {"Alpha0", "Alpha1", "Alpha2"}


def test_cross_tenant_access_is_indistinguishable_from_absence(client, auth, org_setup):
    a, b = org_setup(), org_setup()
    animal = _animal(client, auth, a)
    event = _vacc(client, auth, a, animal["id"]).json()
    hb = auth(b["tokens"]["vet"], b["org"])
    assert client.get(f"/api/v1/animals/{animal['id']}", headers=hb).status_code == 404
    assert client.get(f"/api/v1/vaccination-events/{event['id']}", headers=hb).status_code == 404
    assert _vacc(client, auth, b, animal["id"], who="volunteer").status_code == 404
    r = client.post(f"/api/v1/vaccination-events/{event['id']}/reviews", headers=hb,
                    json={"outcome": "verified", "row_version": event["row_version"]})
    assert r.status_code == 404
    assert client.get(f"/api/v1/animals/{animal['id']}/observations", headers=hb).status_code == 404
    # A member of B pretending to be in A's organisation is refused before any query.
    r = client.get(f"/api/v1/animals/{animal['id']}", headers=auth(b["tokens"]["vet"], a["org"]))
    assert r.status_code == 403
    # Cross-tenant references in writes are rejected too.
    r = client.post("/api/v1/animals", headers=auth(b["tokens"]["volunteer"], b["org"]),
                    json={"species": "dog", "home_area_id": str(a["area"])})
    assert r.status_code == 422


def test_location_precision_depends_on_capability(client, auth, org_setup):
    s = org_setup()
    a = _animal(client, auth, s, first_observation={
        "observed_on": str(date.today()), "time_precision": "day",
        "location": {"lat": 13.08271, "lon": 80.27068, "accuracy_m": 8, "method": "gps"}})
    vol = client.get(f"/api/v1/animals/{a['id']}/observations", headers=auth(s["tokens"]["volunteer"], s["org"])).json()
    coord = client.get(f"/api/v1/animals/{a['id']}/observations",
                       headers=auth(s["tokens"]["coordinator"], s["org"])).json()
    assert coord[0]["location"] == {"lat": 13.08271, "lon": 80.27068, "accuracy_m": 8.0, "precision": "exact"}
    v = vol[0]["location"]
    assert v["precision"] == "approximate" and v["accuracy_m"] is None
    assert abs(v["lat"] - 13.08271) <= 0.005 and abs(v["lon"] - 80.27068) <= 0.005  # lat/lon not swapped
    assert (v["lat"], v["lon"]) != (13.08271, 80.27068)


# ---- vaccination ledger ----------------------------------------------------------------------------------------

def test_full_review_cycle_with_correction(client, auth, org_setup, owner_engine):
    s = org_setup()
    animal = _animal(client, auth, s)
    r = _vacc(client, auth, s, animal["id"])
    assert r.status_code == 201
    event = r.json()
    assert event["state"] == "submitted"
    hv = auth(s["tokens"]["vet"], s["org"])

    # Reason required to request a correction
    r = client.post(f"/api/v1/vaccination-events/{event['id']}/reviews", headers=hv,
                    json={"outcome": "needs_correction", "row_version": event["row_version"]})
    assert r.status_code == 422
    r = client.post(f"/api/v1/vaccination-events/{event['id']}/reviews", headers=hv,
                    json={"outcome": "needs_correction", "reason": "Date unclear on certificate",
                          "row_version": event["row_version"]})
    assert r.status_code == 200 and r.json()["state"] == "needs_correction"

    # The submitter now has a correction task
    tasks = client.get("/api/v1/tasks", headers=auth(s["tokens"]["volunteer"], s["org"])).json()["items"]
    fix = [t for t in tasks if t["task_type"] == "evidence_correction"]
    assert len(fix) == 1 and fix[0]["source_event_id"] == event["id"]

    # Amend: new record supersedes the old one; the old one is kept
    old = client.get(f"/api/v1/vaccination-events/{event['id']}", headers=hv).json()
    r = client.post(f"/api/v1/vaccination-events/{event['id']}/amendments",
                    headers=auth(s["tokens"]["volunteer"], s["org"]),
                    json={"animal_id": animal["id"], "date_precision": "day",
                          "administered_on": str(date.today() - timedelta(days=2)), "product_id": str(s["product"]),
                          "lot_id": str(s["lot"]), "row_version": old["row_version"]})
    assert r.status_code == 201, r.text
    new = r.json()
    assert new["state"] == "submitted" and new["supersedes_event_id"] == event["id"]
    old = client.get(f"/api/v1/vaccination-events/{event['id']}", headers=hv).json()
    assert old["state"] == "superseded" and old["superseded_by_event_id"] == new["id"]
    tasks = client.get("/api/v1/tasks?state=completed", headers=auth(s["tokens"]["volunteer"], s["org"])).json()
    assert any(t["source_event_id"] == event["id"] for t in tasks["items"])

    # Stale version → 409; then verify
    r = client.post(f"/api/v1/vaccination-events/{new['id']}/reviews", headers=hv,
                    json={"outcome": "verified", "row_version": new["row_version"] - 1})
    assert r.status_code == 409 and r.json()["error"]["code"] == "stale_row_version"
    r = client.post(f"/api/v1/vaccination-events/{new['id']}/reviews", headers=hv,
                    json={"outcome": "verified", "row_version": new["row_version"]})
    assert r.status_code == 200 and r.json()["state"] == "verified" and len(r.json()["reviews"]) == 1

    summary = client.get(f"/api/v1/animals/{animal['id']}", headers=hv).json()["vaccination"]
    assert summary["status"] == "verified_record"
    assert summary["last_verified_on"] == str(date.today() - timedelta(days=2))
    with owner_engine.connect() as c:
        actions = set(c.execute(text("select action from app.audit_events where org_id = :o"), {"o": s["org"]}).scalars())
    assert {"vaccination_event.submitted", "vaccination_event.needs_correction", "vaccination_event.superseded",
            "vaccination_event.verified"} <= actions


def test_only_approved_live_reviewers_who_did_not_submit_can_review(client, auth, org_setup, world, make_token):
    s = org_setup()
    animal = _animal(client, auth, s)
    ev = _vacc(client, auth, s, animal["id"]).json()
    url = f"/api/v1/vaccination-events/{ev['id']}/reviews"
    body = {"outcome": "verified", "row_version": ev["row_version"]}
    # Field volunteer: no capability
    r = client.post(url, headers=auth(s["tokens"]["volunteer"], s["org"]), json=body)
    assert r.status_code == 403 and r.json()["error"]["code"] == "missing_capability"
    # Veterinary role without an approved professional authority
    r = client.post(url, headers=auth(s["tokens"]["vet_unapproved"], s["org"]), json=body)
    assert r.status_code == 403 and r.json()["error"]["code"] == "missing_professional_approval"
    # Approved vet, but the Auth session was signed out server-side (token still unexpired)
    ended = make_token(s["users"]["vet"], session_id=world.session(s["users"]["vet"], active=False))
    r = client.post(url, headers=auth(ended, s["org"]), json=body)
    assert r.status_code == 401 and r.json()["error"]["code"] == "session_revoked"
    # Administrator: manages people, not clinical/veterinary verification
    r = client.post(url, headers=auth(s["tokens"]["admin"], s["org"]), json=body)
    assert r.status_code == 403
    # A vet cannot review their own submission
    own = _vacc(client, auth, s, animal["id"], who="vet", administered_on=str(date.today() - timedelta(days=30))).json()
    r = client.post(f"/api/v1/vaccination-events/{own['id']}/reviews", headers=auth(s["tokens"]["vet"], s["org"]),
                    json={"outcome": "verified", "row_version": own["row_version"]})
    assert r.status_code == 403 and r.json()["error"]["code"] == "cannot_review_own_submission"
    queue = client.get("/api/v1/vaccination-review-queue", headers=auth(s["tokens"]["vet"], s["org"])).json()
    assert own["id"] not in {e["id"] for e in queue["items"]} and ev["id"] in {e["id"] for e in queue["items"]}


def test_database_refuses_self_review_even_if_code_is_bypassed(client, auth, org_setup, api_engine_for_tests):
    s = org_setup()
    animal = _animal(client, auth, s)
    ev = _vacc(client, auth, s, animal["id"], who="vet").json()
    from sqlalchemy.exc import DBAPIError

    with api_engine_for_tests.connect() as c, pytest.raises(DBAPIError, match="cannot review their own"):
        with c.begin():
            c.execute(text("select app.set_request_context(:u, :o)"), {"u": s["users"]["vet"], "o": s["org"]})
            c.execute(text("""insert into app.vaccination_reviews (org_id, event_id, reviewer_user_id, outcome,
                              event_row_version, evidence_snapshot) values (:o, :e, :u, 'verified', 1, '{}')"""),
                      {"o": s["org"], "e": ev["id"], "u": s["users"]["vet"]})


def test_state_cannot_be_forged_through_the_api(client, auth, org_setup):
    s = org_setup()
    animal = _animal(client, auth, s)
    r = _vacc(client, auth, s, animal["id"], state="verified")
    assert r.status_code == 422
    r = _vacc(client, auth, s, animal["id"], verified_by=str(s["users"]["vet"]))
    assert r.status_code == 422


def test_future_dates_and_inconsistent_precision_are_rejected(client, auth, org_setup):
    s = org_setup()
    animal = _animal(client, auth, s)
    r = _vacc(client, auth, s, animal["id"], administered_on=str(date.today() + timedelta(days=10)))
    assert r.status_code == 422 and r.json()["error"]["code"] in ("date_in_future", "validation_error")
    r = _vacc(client, auth, s, animal["id"], date_precision="unknown")
    assert r.status_code == 422  # a date was given with 'unknown' precision
    r = _vacc(client, auth, s, animal["id"], date_precision="unknown", administered_on=None)
    assert r.status_code == 201 and r.json()["administered_on"] is None
    r = _vacc(client, auth, s, animal["id"], date_precision="month", administered_on="2026-03-17")
    assert r.status_code == 201 and r.json()["administered_on"] == "2026-03-01"


def test_simultaneous_reviews_produce_exactly_one_decision(client, auth, org_setup, owner_engine):
    s = org_setup()
    animal = _animal(client, auth, s)
    ev = _vacc(client, auth, s, animal["id"]).json()
    results: list[int] = []

    def go(who: str) -> None:
        r = client.post(f"/api/v1/vaccination-events/{ev['id']}/reviews", headers=auth(s["tokens"][who], s["org"]),
                        json={"outcome": "verified", "row_version": ev["row_version"]})
        results.append(r.status_code)

    threads = [threading.Thread(target=go, args=(w,)) for w in ("vet", "vet2")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(results) == [200, 409]
    with owner_engine.connect() as c:
        assert c.execute(text("select count(*) from app.vaccination_reviews where event_id = :e"),
                         {"e": ev["id"]}).scalar() == 1


def test_replayed_submission_never_duplicates_an_administration(client, auth, org_setup, owner_engine):
    s = org_setup()
    animal = _animal(client, auth, s)
    op = str(uuid.uuid4())
    r1 = _vacc(client, auth, s, animal["id"], client_operation_id=op)
    r2 = _vacc(client, auth, s, animal["id"], client_operation_id=op)
    assert r1.json()["id"] == r2.json()["id"]
    with owner_engine.connect() as c:
        assert c.execute(text("select count(*) from app.animal_vaccination_events where animal_id = :a"),
                         {"a": animal["id"]}).scalar() == 1


def test_conflicting_evidence_is_flagged_not_resolved(client, auth, org_setup):
    s = org_setup()
    animal = _animal(client, auth, s)
    _vacc(client, auth, s, animal["id"])
    second = _vacc(client, auth, s, animal["id"], administered_on=str(date.today() - timedelta(days=2))).json()
    assert second["has_conflict"] is True and "possible_duplicate_vaccination" in second["conflicts"]
    events = client.get(f"/api/v1/vaccination-events?animal_id={animal['id']}",
                        headers=auth(s["tokens"]["vet"], s["org"])).json()["items"]
    assert {e["state"] for e in events} == {"submitted"}  # both kept for a reviewer


def test_revoked_member_loses_access_on_next_request(client, auth, org_setup):
    s = org_setup()
    animal = _animal(client, auth, s)
    ha = auth(s["tokens"]["admin"], s["org"])
    members = {m["user_id"]: m for m in client.get("/api/v1/members", headers=ha).json()}
    vol = members[str(s["users"]["volunteer"])]
    assert _vacc(client, auth, s, animal["id"]).status_code == 201
    r = client.post(f"/api/v1/members/{vol['membership_id']}/revoke", headers=ha,
                    json={"reason": "Left the programme", "row_version": 1})
    assert r.status_code == 204, r.text
    # Same unexpired token: refused, because membership is read on every request.
    r = _vacc(client, auth, s, animal["id"])
    assert r.status_code == 403 and r.json()["error"]["code"] == "not_a_member"
    r = client.post(f"/api/v1/members/{vol['membership_id']}/revoke", headers=ha,
                    json={"reason": "again", "row_version": 2})
    assert r.status_code == 409


def test_professional_authority_revocation_blocks_review(client, auth, org_setup, owner_engine):
    s = org_setup()
    animal = _animal(client, auth, s)
    ev = _vacc(client, auth, s, animal["id"]).json()
    with owner_engine.connect() as c:
        approval = c.execute(text("select id from app.professional_approvals where user_id = :u"),
                             {"u": s["users"]["vet"]}).scalar_one()
    r = client.post(f"/api/v1/professional-approvals/{approval}/revoke", headers=auth(s["tokens"]["admin"], s["org"]),
                    json={"reason": "Registration lapsed"})
    assert r.status_code == 204
    r = client.post(f"/api/v1/vaccination-events/{ev['id']}/reviews", headers=auth(s["tokens"]["vet"], s["org"]),
                    json={"outcome": "verified", "row_version": ev["row_version"]})
    assert r.status_code == 403 and r.json()["error"]["code"] == "missing_professional_approval"


def test_admin_cannot_self_grant_professional_authority(client, auth, org_setup):
    s = org_setup()
    ha = auth(s["tokens"]["admin"], s["org"])
    me = {m["user_id"]: m for m in client.get("/api/v1/members", headers=ha).json()}[str(s["users"]["admin"])]
    r = client.post("/api/v1/professional-approvals", headers=ha,
                    json={"membership_id": me["membership_id"], "scope": "veterinary_review",
                          "evidence_reference": "self"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "self_approval"


# ---- merges ----------------------------------------------------------------------------------------------------

def test_merge_requires_second_person_and_is_reversible(client, auth, org_setup, owner_engine):
    s = org_setup()
    src = _animal(client, auth, s, nickname="Dup", first_observation={"observed_on": str(date.today()),
                                                                       "time_precision": "day"})
    dst = _animal(client, auth, s, nickname="Original")
    ev = _vacc(client, auth, s, src["id"]).json()
    hv, hp = auth(s["tokens"]["vet"], s["org"]), auth(s["tokens"]["volunteer"], s["org"])
    pv = client.post("/api/v1/animal-merges/preview", headers=hp,
                     json={"source_animal_id": src["id"], "target_animal_id": dst["id"], "reason": "same dog"}).json()
    assert pv["moves"]["observations"] == 1 and pv["moves"]["vaccination_events"] == 1
    m = client.post("/api/v1/animal-merges", headers=hp,
                    json={"source_animal_id": src["id"], "target_animal_id": dst["id"], "reason": "same dog"}).json()
    assert m["state"] == "proposed"
    # Volunteer lacks animal.merge; the proposer cannot approve their own proposal either
    assert client.post(f"/api/v1/animal-merges/{m['id']}/approve", headers=hp, json={"reason": "looks right"}).status_code == 403
    r = client.post(f"/api/v1/animal-merges/{m['id']}/approve", headers=hv, json={"reason": "Confirmed by marks"})
    assert r.status_code == 200 and r.json()["state"] == "executed"
    alias = client.get(f"/api/v1/animals/{src['id']}", headers=hv).json()
    assert alias["profile_state"] == "merged_alias" and alias["merged_into_reference"] == dst["reference_code"]
    moved = client.get(f"/api/v1/vaccination-events/{ev['id']}", headers=hv).json()
    assert moved["animal_id"] == dst["id"] and moved["original_animal_id"] == src["id"]  # provenance kept
    r = _vacc(client, auth, s, src["id"])
    assert r.status_code == 409 and r.json()["error"]["details"]["merged_into_reference"] == dst["reference_code"]
    # Reverse restores exactly what moved
    r = client.post(f"/api/v1/animal-merges/{m['id']}/reverse", headers=hv, json={"reason": "Different dogs after all"})
    assert r.status_code == 200 and r.json()["state"] == "reversed"
    back = client.get(f"/api/v1/vaccination-events/{ev['id']}", headers=hv).json()
    assert back["animal_id"] == src["id"]
    assert client.get(f"/api/v1/animals/{src['id']}", headers=hv).json()["profile_state"] == "provisional"
    assert len(client.get(f"/api/v1/animals/{src['id']}/observations", headers=hv).json()) == 1


# ---- tasks -----------------------------------------------------------------------------------------------------

def test_task_state_machine_and_ownership(client, auth, org_setup):
    s = org_setup()
    hc, hp = auth(s["tokens"]["coordinator"], s["org"]), auth(s["tokens"]["volunteer"], s["org"])
    members = {m["user_id"]: m for m in client.get("/api/v1/members", headers=hc).json()}
    vol_mid = members[str(s["users"]["volunteer"])]["membership_id"]
    assert client.post("/api/v1/tasks", headers=hp, json={"task_type": "other", "title": "x"}).status_code == 403
    t = client.post("/api/v1/tasks", headers=hc, json={"task_type": "vaccination_round", "title": "Ward 1 round",
                                                      "area_id": str(s["area"]),
                                                      "assignee_membership_id": vol_mid}).json()
    assert t["state"] == "assigned"
    r = client.post(f"/api/v1/tasks/{t['id']}/transitions", headers=hp,
                    json={"action": "block", "row_version": t["row_version"]})
    assert r.status_code == 422  # a reason is required
    r = client.post(f"/api/v1/tasks/{t['id']}/transitions", headers=hp,
                    json={"action": "start", "row_version": t["row_version"]})
    assert r.status_code == 200 and r.json()["state"] == "in_progress"
    t2 = r.json()
    r = client.post(f"/api/v1/tasks/{t['id']}/transitions", headers=hp,
                    json={"action": "cancel", "note": "no", "row_version": t2["row_version"]})
    assert r.status_code == 403  # only managers cancel
    r = client.post(f"/api/v1/tasks/{t['id']}/transitions", headers=hp,
                    json={"action": "complete", "note": "12 dogs seen", "row_version": t2["row_version"]})
    assert r.status_code == 200 and r.json()["state"] == "completed" and r.json()["completed_at"]
    # Another volunteer cannot touch it
    other = s["tokens"]["vet"]
    r = client.post(f"/api/v1/tasks/{t['id']}/transitions", headers=auth(other, s["org"]),
                    json={"action": "start", "row_version": r.json()["row_version"]})
    assert r.status_code == 403


def test_audit_log_requires_capability(client, auth, org_setup):
    s = org_setup()
    _animal(client, auth, s)
    assert client.get("/api/v1/audit", headers=auth(s["tokens"]["volunteer"], s["org"])).status_code == 403
    entries = client.get("/api/v1/audit", headers=auth(s["tokens"]["admin"], s["org"])).json()
    assert any(e["action"] == "animal.created" for e in entries)
    assert all("Brownie" not in str(e["change_summary"]) for e in entries)  # no record content in audit


def test_records_in_a_demo_organisation_are_always_flagged_demo(client, auth, world, make_token):
    org = world.org(demo=True)
    vol = world.member(org, "field_volunteer")
    r = client.post("/api/v1/animals", headers=auth(make_token(vol), org), json={"species": "dog"})
    assert r.status_code == 201 and r.json()["is_demo"] is True
