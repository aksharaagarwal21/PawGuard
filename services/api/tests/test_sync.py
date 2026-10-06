"""Phase 8: replay of offline changes — accepted, duplicate, genuine conflict, and refusal under current permissions."""

import uuid
from datetime import date

from sqlalchemy import text
from test_prevention import _animal, org_setup  # noqa: F401 - reuse fixture/helpers


def _membership(owner_engine, org, user) -> str:
    with owner_engine.connect() as c:
        return str(c.execute(text("select id from app.memberships where org_id = :o and user_id = :u"),
                             {"o": org, "u": user}).scalar_one())


def _assigned_task(client, auth, s, owner_engine) -> dict:
    hc = auth(s["tokens"]["coordinator"], s["org"])
    r = client.post("/api/v1/tasks", headers=hc, json={
        "task_type": "vaccination_round", "title": "Round in Ward 1", "area_id": str(s["area"]),
        "assignee_membership_id": _membership(owner_engine, s["org"], s["users"]["volunteer"])})
    assert r.status_code == 201, r.text
    return r.json()


def _op(s, kind="task", **kw) -> dict:
    base = {"operation_id": str(uuid.uuid4()), "actor_user_id": str(s["users"]["volunteer"]), "org_id": str(s["org"]),
            "client_created_at": "2026-10-06T08:00:00Z"}
    if kind == "task":
        return {**base, "operation_type": "task.transition", **kw}
    return {**base, "operation_type": "observation.create", **kw}


def _send(client, auth, s, ops, who="volunteer"):
    return client.post("/api/v1/sync/operations", headers=auth(s["tokens"][who], s["org"]),
                       json={"device_id": "device-test-0001", "operations": ops})


def test_offline_changes_apply_once_and_duplicates_return_the_stored_outcome(client, auth, org_setup, owner_engine):  # noqa: F811
    s = org_setup()
    task = _assigned_task(client, auth, s, owner_engine)
    animal = _animal(client, auth, s)
    start = _op(s, target_id=task["id"], base_row_version=task["row_version"], task={"action": "start"})
    sighting = _op(s, "sighting", sighting={"animal_id": animal["id"], "observed_on": str(date.today()),
                                            "area_id": str(s["area"]), "notes": "Seen near the tea stall",
                                            "field_task_id": task["id"]})
    r = _send(client, auth, s, [start, sighting])
    assert r.status_code == 200, r.text
    res = {x["operation_id"]: x for x in r.json()["results"]}
    assert res[start["operation_id"]]["state"] == "accepted"
    assert res[start["operation_id"]]["server_row_version"] == task["row_version"] + 1
    assert res[sighting["operation_id"]]["state"] == "accepted"
    obs_id = res[sighting["operation_id"]]["target_id"]
    # Replaying the same operations (e.g. the device never saw the response) changes nothing
    again = {x["operation_id"]: x for x in _send(client, auth, s, [start, sighting]).json()["results"]}
    assert again[start["operation_id"]]["duplicate"] and again[start["operation_id"]]["state"] == "accepted"
    assert again[sighting["operation_id"]]["target_id"] == obs_id
    with owner_engine.connect() as c:
        assert c.execute(text("select count(*) from app.animal_observations where animal_id = :a"),
                         {"a": animal["id"]}).scalar_one() == 1
        assert c.execute(text("select state from app.field_tasks where id = :t"), {"t": task["id"]}).scalar_one() \
            == "in_progress"
        assert c.execute(text("select count(*) from app.sync_operations where org_id = :o"),
                         {"o": s["org"]}).scalar_one() == 2


def test_server_change_while_offline_is_a_conflict_not_an_overwrite(client, auth, org_setup, owner_engine):  # noqa: F811
    s = org_setup()
    task = _assigned_task(client, auth, s, owner_engine)
    # Coordinator cancels the task while the volunteer is offline
    hc = auth(s["tokens"]["coordinator"], s["org"])
    assert client.post(f"/api/v1/tasks/{task['id']}/transitions", headers=hc, json={
        "action": "cancel", "note": "Ward closed for festival", "row_version": task["row_version"]}).status_code == 200
    done = _op(s, target_id=task["id"], base_row_version=task["row_version"],
               task={"action": "complete", "note": "All dogs done"})
    out = _send(client, auth, s, [done]).json()["results"][0]
    assert out["state"] == "conflict" and out["result_code"] == "changed_on_server"
    assert out["server_state"] == "cancelled" and out["server_row_version"] == task["row_version"] + 1
    with owner_engine.connect() as c:
        assert c.execute(text("select state from app.field_tasks where id = :t"), {"t": task["id"]}).scalar_one() \
            == "cancelled"
    # The person decides to discard their change; that is recorded
    hv = auth(s["tokens"]["volunteer"], s["org"])
    assert client.post(f"/api/v1/sync/operations/{done['operation_id']}/resolve", headers=hv,
                       json={"resolution": "discarded"}).status_code == 204


def test_replay_uses_current_permissions_and_one_refusal_does_not_undo_others(client, auth, org_setup,  # noqa: F811
                                                                              owner_engine):
    s = org_setup()
    task = _assigned_task(client, auth, s, owner_engine)
    animal = _animal(client, auth, s)
    # While offline, the volunteer loses field-task permission (but may still record sightings)
    with owner_engine.begin() as c:
        c.execute(text("update app.memberships set capabilities = array_remove(capabilities, 'task.work') "
                       "where org_id = :o and user_id = :u"), {"o": s["org"], "u": s["users"]["volunteer"]})
    start = _op(s, target_id=task["id"], base_row_version=task["row_version"], task={"action": "start"})
    sighting = _op(s, "sighting", sighting={"animal_id": animal["id"], "observed_on": str(date.today())})
    other_user = _op(s, "sighting", sighting={"animal_id": animal["id"], "observed_on": str(date.today())})
    other_user["actor_user_id"] = str(s["users"]["coordinator"])
    wrong_org = _op(s, "sighting", sighting={"animal_id": animal["id"], "observed_on": str(date.today())})
    wrong_org["org_id"] = str(uuid.uuid4())
    res = {x["operation_id"]: x for x in _send(client, auth, s, [start, sighting, other_user, wrong_org])
           .json()["results"]}
    assert res[start["operation_id"]]["state"] == "rejected" and res[start["operation_id"]]["result_code"] == "missing_capability"
    assert res[sighting["operation_id"]]["state"] == "accepted"
    assert res[other_user["operation_id"]]["result_code"] == "actor_mismatch"
    assert res[wrong_org["operation_id"]]["result_code"] == "wrong_organisation"
    with owner_engine.connect() as c:
        assert c.execute(text("select state from app.field_tasks where id = :t"), {"t": task["id"]}).scalar_one() \
            == "assigned"
    # A suspended membership cannot replay anything at all
    with owner_engine.begin() as c:
        c.execute(text("update app.memberships set status = 'suspended' where org_id = :o and user_id = :u"),
                  {"o": s["org"], "u": s["users"]["volunteer"]})
    late = _op(s, "sighting", sighting={"animal_id": animal["id"], "observed_on": str(date.today())})
    assert _send(client, auth, s, [late]).status_code == 403
    with owner_engine.connect() as c:
        assert c.execute(text("select count(*) from app.sync_operations where operation_id = :o"),
                         {"o": late["operation_id"]}).scalar_one() == 0
