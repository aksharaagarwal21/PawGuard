"""Phase 8: surveys → campaign inputs → solved plan → approval → publication as team tasks; revised inputs."""

from datetime import date, timedelta

from sqlalchemy import text
from test_prevention import org_setup  # noqa: F401 - reuse fixture

SQUARE = "POLYGON(({w} {s}, {e} {s}, {e} {n}, {w} {n}, {w} {s}))"


def _areas(owner_engine, org, n=4):
    ids = []
    with owner_engine.begin() as c:
        for i in range(n):
            lat, lon = 13.05 + 0.01 * i, 80.25
            poly = SQUARE.format(w=lon - 0.004, e=lon + 0.004, s=lat - 0.004, n=lat + 0.004)
            ids.append(str(c.execute(text(
                "insert into app.areas (org_id, code, name, boundary) values (:o, :c, :n, "
                "extensions.st_multi(extensions.st_geomfromtext(:p, 4326))) returning id"),
                {"o": org, "c": f"P{i}", "n": f"Plan area {i}", "p": poly}).scalar_one()))
    return ids


def _run(owner_engine, plan_id):
    from pawguard_worker import jobs, plan_job

    with owner_engine.connect() as c:
        job = c.execute(text("select id from app.background_jobs where target_id = :p and job_type = 'plan.solve'"),
                        {"p": plan_id}).scalar_one()
    return jobs.run(str(job), plan_job.solve, on_terminal=plan_job.failed)


def test_plan_from_survey_to_published_team_tasks(client, auth, org_setup, owner_engine):  # noqa: F811
    s = org_setup()
    hc, hv = auth(s["tokens"]["coordinator"], s["org"]), auth(s["tokens"]["volunteer"], s["org"])
    areas = _areas(owner_engine, s["org"])
    # A volunteer's street count becomes the suggested estimate for that area
    sv = client.post("/api/v1/surveys", headers=hv, json={"area_id": areas[0], "observed_on": str(date.today()),
                                                         "dogs_counted": 18, "marked_count": 6})
    assert sv.status_code == 201, sv.text
    assert client.post("/api/v1/surveys", headers=hv, json={"area_id": areas[0], "observed_on": str(date.today()),
                                                           "dogs_counted": 3, "marked_count": 5}).status_code == 422
    teams = client.post("/api/v1/teams", headers=hc, json={"name": "Team North", "shift_start": "08:00",
                                                          "shift_end": "12:00", "doses_per_day": 50,
                                                          "start_area_id": areas[0]})
    assert teams.status_code == 201, teams.text
    team_id = teams.json()[0]["id"]
    with owner_engine.begin() as c:
        mid = c.execute(text("select id from app.memberships where org_id = :o and user_id = :u"),
                        {"o": s["org"], "u": s["users"]["volunteer"]}).scalar_one()
        c.execute(text("insert into app.team_members (org_id, team_id, membership_id) values (:o, :t, :m)"),
                  {"o": s["org"], "t": team_id, "m": mid})
    assert client.post("/api/v1/campaigns", headers=hv, json={"name": "x", "area_ids": areas}).status_code == 403
    camp = client.post("/api/v1/campaigns", headers=hc, json={"name": "October round", "area_ids": areas}).json()
    a0 = next(a for a in camp["areas"] if a["area_id"] == areas[0])
    assert a0["suggested_animals"] == 18 and a0["suggested_source"] == "survey" and a0["est_animals"] is None
    # Manual inputs: one area inaccessible, one with an explicit estimate
    a3 = next(a for a in camp["areas"] if a["area_id"] == areas[3])
    upd = client.put(f"/api/v1/campaigns/{camp['id']}/areas/{areas[3]}", headers=hc, json={
        "est_animals": 10, "accessible": False, "access_note": "Road closed", "row_version": a3["row_version"]})
    assert upd.status_code == 200, upd.text
    for a in camp["areas"]:
        if a["area_id"] in (areas[1], areas[2]):
            client.put(f"/api/v1/campaigns/{camp['id']}/areas/{a['area_id']}", headers=hc,
                       json={"est_animals": 12, "row_version": a["row_version"]})
    day = str(date.today() + timedelta(days=2))
    plan = client.post(f"/api/v1/campaigns/{camp['id']}/plans", headers=hc,
                       json={"plan_date": day, "teams": [{"team_id": team_id}]})
    assert plan.status_code == 201, plan.text
    assert plan.json()["state"] == "solving"
    assert _run(owner_engine, plan.json()["id"]) == "completed"
    p = client.get(f"/api/v1/plans/{plan.json()['id']}", headers=hc).json()
    assert p["state"] == "ready" and p["travel_basis"] == "straight_line_estimate"
    res = p["result"]
    planned = {st["area_id"] for r in res["routes"] for st in r["stops"]}
    assert areas[3] not in planned
    assert any(u["area_id"] == areas[3] and u["reasons"] == ["marked_not_accessible"] for u in res["unassigned"])
    assert res["baseline"]["totals"]["areas_total"] == 4 and any("straight-line" in n for n in res["notes"])
    assert p["inputs"]["areas"][0]["est_source"] in ("survey", "manual", "registry", "none")
    # Nothing is dispatched before approval
    assert client.post(f"/api/v1/plans/{p['id']}/publish", headers=hc,
                       json={"row_version": p["row_version"]}).status_code == 409
    ap = client.post(f"/api/v1/plans/{p['id']}/approve", headers=hc,
                     json={"row_version": p["row_version"], "note": "Checked with team lead"}).json()
    assert ap["state"] == "approved" and ap["approved_at"] and ap["approval_note"] == "Checked with team lead"
    pub = client.post(f"/api/v1/plans/{p['id']}/publish", headers=hc, json={"row_version": ap["row_version"]}).json()
    assert pub["state"] == "published" and pub["task_count"] == len(planned)
    # Team members see the published stops as their tasks and can work them
    mine = client.get("/api/v1/tasks?mine=true&state=assigned", headers=hv).json()["items"]
    plan_tasks = [t for t in mine if t["campaign_id"] == camp["id"]]
    assert len(plan_tasks) == len(planned) and all(t["planned_start"] for t in plan_tasks)
    t0 = plan_tasks[0]
    assert client.post(f"/api/v1/tasks/{t0['id']}/transitions", headers=hv,
                       json={"action": "start", "row_version": t0["row_version"]}).status_code == 200
    # Revised inputs → new version; publishing it supersedes the earlier version but leaves its tasks alone
    plan2 = client.post(f"/api/v1/campaigns/{camp['id']}/plans", headers=hc, json={
        "plan_date": day, "teams": [{"team_id": team_id, "doses": 12}], "excluded": [areas[1]]}).json()
    assert plan2["version"] == 2
    _run(owner_engine, plan2["id"])
    p2 = client.get(f"/api/v1/plans/{plan2['id']}", headers=hc).json()
    assert any(u["area_id"] == areas[1] and u["reasons"] == ["excluded_by_you"] for u in p2["result"]["unassigned"])
    ap2 = client.post(f"/api/v1/plans/{p2['id']}/approve", headers=hc, json={"row_version": p2["row_version"]}).json()
    client.post(f"/api/v1/plans/{p2['id']}/publish", headers=hc, json={"row_version": ap2["row_version"]})
    versions = {x["version"]: x["state"] for x in client.get(f"/api/v1/campaigns/{camp['id']}/plans", headers=hc).json()}
    assert versions == {1: "superseded", 2: "published"}
    still = client.get(f"/api/v1/tasks/{t0['id']}", headers=hc).json()
    assert still["state"] == "in_progress"
