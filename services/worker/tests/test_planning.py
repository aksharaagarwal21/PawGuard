"""Planner behaviour on small synthetic inputs: feasibility, reasons for unplanned areas, overrides, baseline."""

from pawguard_worker import planning

BASE = (13.05, 80.25)


def _inputs(**over):
    areas = [
        {"area_id": f"a{i}", "name": f"Area {i}", "lat": BASE[0] + 0.01 * i, "lon": BASE[1], "est_animals": 20,
         "service_minutes_per_animal": 3, "priority": 2} for i in range(1, 6)
    ]
    data = {
        "plan_date": "2026-10-08", "activity": "vaccination",
        "travel": {"basis": "straight_line_estimate", "speed_kmh": 15, "detour_factor": 1.3},
        "teams": [{"team_id": "t1", "name": "Team 1", "shift_start": "08:00", "shift_end": "12:00", "doses": 60,
                   "start": {"lat": BASE[0], "lon": BASE[1]}},
                  {"team_id": "t2", "name": "Team 2", "shift_start": "08:00", "shift_end": "12:00", "doses": 60,
                   "start": {"lat": BASE[0], "lon": BASE[1]}}],
        "areas": areas, "overrides": {"pinned": {}, "excluded": []},
    }
    data.update(over)
    return data


def _check(result, inputs):
    teams = {t["team_id"]: t for t in inputs["teams"]}
    seen = set()
    for r in result["routes"]:
        t = teams[r["team_id"]]
        assert r["doses_used"] <= t["doses"]
        assert r["ends_at"] <= t["shift_end"]
        for s in r["stops"]:
            assert s["area_id"] not in seen
            seen.add(s["area_id"])
    assert seen.isdisjoint({u["area_id"] for u in result["unassigned"]})
    assert len(seen) + len(result["unassigned"]) == len(inputs["areas"])


def test_feasible_plan_respects_shifts_doses_and_explains_the_rest():
    inp = _inputs()
    res = planning.plan(inp, time_limit_s=2)
    _check(res, inp)
    # 5 areas × 20 doses > 2 teams × 60 doses: at most 6 areas' worth of doses, so all 5 can fit by doses (100 ≤ 120)
    # but each area takes 60 min on site; 2 teams × 4 h → at most 6 areas by time. Expect all planned.
    assert res["totals"]["areas_planned"] == 5
    assert any("straight-line" in n for n in res["notes"])
    assert res["baseline"]["totals"]["areas_total"] == 5


def test_reasons_for_unplanned_areas_are_specific():
    inp = _inputs()
    inp["areas"].append({"area_id": "big", "name": "Huge", "lat": BASE[0], "lon": BASE[1] + 0.01, "est_animals": 200,
                         "service_minutes_per_animal": 3})
    inp["areas"].append({"area_id": "closed", "name": "Closed", "lat": BASE[0], "lon": BASE[1], "est_animals": 5,
                         "accessible": False})
    inp["areas"].append({"area_id": "late", "name": "Evening only", "lat": BASE[0], "lon": BASE[1], "est_animals": 5,
                         "access_start": "17:00", "access_end": "19:00"})
    inp["areas"].append({"area_id": "nowhere", "name": "No map", "lat": None, "lon": None, "est_animals": 5})
    inp["overrides"]["excluded"] = ["a5"]
    res = planning.plan(inp, time_limit_s=2)
    _check(res, inp)
    reasons = {u["area_id"]: u["reasons"] for u in res["unassigned"]}
    assert "longer_than_any_shift" in reasons["big"] and "needs_more_doses_than_any_team" in reasons["big"]
    assert reasons["closed"] == ["marked_not_accessible"]
    assert reasons["late"] == ["cannot_fit_in_access_window_and_shift"]
    assert reasons["nowhere"] == ["no_location"]
    assert reasons["a5"] == ["excluded_by_you"]


def test_pinned_area_goes_to_its_team_and_overload_is_reported():
    inp = _inputs()
    inp["overrides"]["pinned"] = {"a5": "t2", "a4": "t2"}
    res = planning.plan(inp, time_limit_s=2)
    _check(res, inp)
    t2 = next(r for r in res["routes"] if r["team_id"] == "t2")
    assert {"a4", "a5"} <= {s["area_id"] for s in t2["stops"]}
    # Not enough doses for everything: 1 team × 30 doses for 5 areas of 20
    small = _inputs(teams=[{"team_id": "t1", "name": "Team 1", "shift_start": "08:00", "shift_end": "12:00",
                            "doses": 30, "start": {"lat": BASE[0], "lon": BASE[1]}}])
    res2 = planning.plan(small, time_limit_s=2)
    _check(res2, small)
    assert res2["totals"]["areas_planned"] == 1
    assert all(u["reasons"] == ["not_enough_time_or_doses_left"] for u in res2["unassigned"])


def test_optimiser_is_never_worse_than_the_baseline_shown():
    inp = _inputs()
    inp["areas"][0]["priority"] = 1
    res = planning.plan(inp, time_limit_s=2)
    assert (res["totals"]["animals_planned"], -res["totals"]["travel_minutes"]) >= \
        (res["baseline"]["totals"]["animals_planned"], -res["baseline"]["totals"]["travel_minutes"])
