"""Campaign day planning: which team visits which areas, in what order, within shifts, access windows and doses.

Two solvers over the same inputs:
- ``greedy`` — a transparent baseline: each team repeatedly takes the highest-priority, nearest area it can still
  finish in time and with enough doses;
- ``ortools`` — OR-Tools vehicle routing with time windows, dose capacity, pinned areas and droppable areas
  (dropping costs more for higher-priority and larger areas, so coverage is maximised before travel is minimised).

Every solution is re-checked by an independent validator before it is shown. Travel times are an estimate
(straight-line distance × detour factor ÷ speed) unless a real travel-time matrix is supplied, and the result says
which. A plan is a proposal: nothing is dispatched until a person approves and publishes it.
"""

import math
import time
from dataclasses import dataclass, field
from typing import Any

SOLVER_VERSION = "planner-1"


def hhmm(minutes: int | float) -> str:
    m = round(minutes)
    return f"{m // 60:02d}:{m % 60:02d}"


def to_min(v: str | None) -> int | None:
    if not v:
        return None
    h, m = v.split(":")[:2]
    return int(h) * 60 + int(m)


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h))


@dataclass
class Team:
    team_id: str
    name: str
    start_min: int
    end_min: int
    doses: int
    start: tuple[float, float]


@dataclass
class Area:
    area_id: str
    name: str
    loc: tuple[float, float] | None
    animals: int
    service: int  # minutes on site
    open_min: int | None
    close_min: int | None
    accessible: bool
    priority: int  # 1 high … 3 low
    demand: int  # doses needed (0 for surveys)
    pinned_team: str | None = None
    excluded: bool = False


@dataclass
class Problem:
    teams: list[Team]
    areas: list[Area]
    speed_kmh: float
    detour: float
    notes: list[str] = field(default_factory=list)

    def travel(self, a: tuple[float, float], b: tuple[float, float]) -> int:
        return math.ceil(haversine_km(a, b) * self.detour / self.speed_kmh * 60)


def build(inputs: dict[str, Any]) -> Problem:
    travel = inputs.get("travel") or {}
    vaccination = inputs.get("activity", "vaccination") != "survey"
    pins = (inputs.get("overrides") or {}).get("pinned") or {}
    excluded = set((inputs.get("overrides") or {}).get("excluded") or [])
    teams = [Team(t["team_id"], t["name"], to_min(t["shift_start"]) or 0, to_min(t["shift_end"]) or 0,
                  int(t.get("doses") or 0), (float(t["start"]["lat"]), float(t["start"]["lon"])))
             for t in inputs["teams"]]
    areas = []
    for a in inputs["areas"]:
        animals = int(a.get("est_animals") or 0)
        areas.append(Area(
            a["area_id"], a["name"], (float(a["lat"]), float(a["lon"])) if a.get("lat") is not None else None,
            animals, max(1, math.ceil(animals * float(a.get("service_minutes_per_animal") or 4))),
            to_min(a.get("access_start")), to_min(a.get("access_end")), bool(a.get("accessible", True)),
            int(a.get("priority") or 2), animals if vaccination else 0, pins.get(a["area_id"]),
            a["area_id"] in excluded))
    basis = travel.get("basis", "straight_line_estimate")
    p = Problem(teams, areas, float(travel.get("speed_kmh") or 15), float(travel.get("detour_factor") or 1.3))
    if basis == "straight_line_estimate":
        p.notes.append(f"Travel times are straight-line distance × {p.detour:g} at {p.speed_kmh:g} km/h — an "
                       "estimate, not a road route.")
    return p


# ---- feasibility of single areas (reasons shown to people) ------------------------------------------------------

def static_reasons(p: Problem, a: Area) -> list[str]:
    if a.excluded:
        return ["excluded_by_you"]
    if not a.accessible:
        return ["marked_not_accessible"]
    if a.loc is None:
        return ["no_location"]
    if a.animals <= 0:
        return ["no_animals_estimated"]
    teams = [t for t in p.teams if a.pinned_team in (None, t.team_id)]
    if not teams:
        return ["pinned_team_not_in_plan"]
    reasons = []
    if all(a.service > t.end_min - t.start_min for t in teams):
        reasons.append("longer_than_any_shift")
    if a.demand and all(a.demand > t.doses for t in teams):
        reasons.append("needs_more_doses_than_any_team")
    lo, hi = a.open_min or 0, a.close_min or 24 * 60
    if all(max(lo, t.start_min + p.travel(t.start, a.loc)) + a.service > min(hi, t.end_min) for t in teams):
        reasons.append("cannot_fit_in_access_window_and_shift")
    return reasons


# ---- validation (independent of either solver) ------------------------------------------------------------------

def simulate(p: Problem, team: Team, stops: list[Area]) -> dict[str, Any] | None:
    """Times for a route; None if it breaks the shift, an access window or the dose limit."""
    now, pos, doses, travel_total, out = team.start_min, team.start, team.doses, 0, []
    for a in stops:
        assert a.loc is not None
        tr = p.travel(pos, a.loc)
        arrive = now + tr
        start = max(arrive, a.open_min or 0)
        finish = start + a.service
        if finish > team.end_min or (a.close_min is not None and finish > a.close_min) or a.demand > doses:
            return None
        doses -= a.demand
        travel_total += tr
        out.append({"area_id": a.area_id, "name": a.name, "travel_minutes": tr, "arrive": hhmm(arrive),
                    "start": hhmm(start), "finish": hhmm(finish), "animals": a.animals, "doses": a.demand,
                    "priority": a.priority})
        now, pos = finish, a.loc
    return {"team_id": team.team_id, "name": team.name, "stops": out, "travel_minutes": travel_total,
            "service_minutes": sum(a.service for a in stops), "doses_used": team.doses - doses,
            "doses_available": team.doses, "ends_at": hhmm(now),
            "shift": f"{hhmm(team.start_min)}–{hhmm(team.end_min)}"}


# ---- solvers ----------------------------------------------------------------------------------------------------

def greedy(p: Problem) -> dict[str, list[Area]]:
    open_areas = [a for a in p.areas if not static_reasons(p, a)]
    routes: dict[str, list[Area]] = {t.team_id: [] for t in p.teams}
    for t in p.teams:
        while True:
            best, best_key = None, None
            for a in open_areas:
                if a.pinned_team not in (None, t.team_id):
                    continue
                if simulate(p, t, [*routes[t.team_id], a]) is None:
                    continue
                pos = routes[t.team_id][-1].loc if routes[t.team_id] else t.start
                key = (a.priority, p.travel(pos, a.loc))  # type: ignore[arg-type]
                if best_key is None or key < best_key:
                    best, best_key = a, key
            if best is None:
                break
            routes[t.team_id].append(best)
            open_areas.remove(best)
    return routes


def ortools_solve(p: Problem, time_limit_s: int = 5) -> dict[str, list[Area]] | None:
    from ortools.constraint_solver import pywrapcp, routing_enums_pb2

    candidates = [a for a in p.areas if not static_reasons(p, a)]
    if not p.teams or not candidates:
        return {t.team_id: [] for t in p.teams}
    nt = len(p.teams)
    # nodes: [team starts 0..nt-1] [team ends nt..2nt-1] [areas 2nt..]
    locs: list[tuple[float, float] | None] = [t.start for t in p.teams] + [None] * nt + [a.loc for a in candidates]
    service = [0] * (2 * nt) + [a.service for a in candidates]
    demand = [0] * (2 * nt) + [a.demand for a in candidates]
    n = len(locs)
    manager = pywrapcp.RoutingIndexManager(n, nt, list(range(nt)), list(range(nt, 2 * nt)))
    routing = pywrapcp.RoutingModel(manager)

    def travel(i: int, j: int) -> int:
        if locs[i] is None or locs[j] is None:
            return 0  # open routes: no return trip
        return p.travel(locs[i], locs[j])  # type: ignore[arg-type]

    def time_cb(fi: int, ti: int) -> int:
        i, j = manager.IndexToNode(fi), manager.IndexToNode(ti)
        return service[i] + travel(i, j)

    def cost_cb(fi: int, ti: int) -> int:
        return travel(manager.IndexToNode(fi), manager.IndexToNode(ti))

    t_idx = routing.RegisterTransitCallback(time_cb)
    routing.SetArcCostEvaluatorOfAllVehicles(routing.RegisterTransitCallback(cost_cb))
    routing.AddDimension(t_idx, 24 * 60, 24 * 60, False, "Time")
    tdim = routing.GetDimensionOrDie("Time")
    d_idx = routing.RegisterUnaryTransitCallback(lambda fi: demand[manager.IndexToNode(fi)])
    routing.AddDimensionWithVehicleCapacity(d_idx, 0, [t.doses for t in p.teams], True, "Doses")
    for v, t in enumerate(p.teams):
        tdim.CumulVar(routing.Start(v)).SetRange(t.start_min, t.start_min)
        tdim.CumulVar(routing.End(v)).SetRange(t.start_min, t.end_min)
    team_index = {t.team_id: v for v, t in enumerate(p.teams)}
    for k, a in enumerate(candidates):
        idx = manager.NodeToIndex(2 * nt + k)
        lo = a.open_min or 0
        hi = (a.close_min - a.service) if a.close_min is not None else 24 * 60
        tdim.CumulVar(idx).SetRange(lo, max(lo, hi))
        if a.pinned_team is not None:
            routing.VehicleVar(idx).SetValues([-1, team_index[a.pinned_team]])
        penalty = (4 - a.priority) * 1000 * (a.animals + 1)
        routing.AddDisjunction([idx], penalty)
    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    params.time_limit.seconds = time_limit_s
    sol = routing.SolveWithParameters(params)
    if sol is None:
        return None
    routes: dict[str, list[Area]] = {}
    for v, t in enumerate(p.teams):
        stops, idx = [], routing.Start(v)
        while not routing.IsEnd(idx):
            node = manager.IndexToNode(idx)
            if node >= 2 * nt:
                stops.append(candidates[node - 2 * nt])
            idx = sol.Value(routing.NextVar(idx))
        routes[t.team_id] = stops
    return routes


# ---- assembling a result ----------------------------------------------------------------------------------------

def summarise(p: Problem, routes: dict[str, list[Area]]) -> dict[str, Any]:
    teams = {t.team_id: t for t in p.teams}
    out_routes, planned = [], set()
    for tid, stops in routes.items():
        sim = simulate(p, teams[tid], stops)
        if sim is None:
            raise ValueError(f"solver returned an infeasible route for team {tid}")
        out_routes.append(sim)
        planned.update(a.area_id for a in stops)
    unassigned = []
    for a in p.areas:
        if a.area_id in planned:
            continue
        reasons = static_reasons(p, a) or ["not_enough_time_or_doses_left"]
        unassigned.append({"area_id": a.area_id, "name": a.name, "animals": a.animals, "priority": a.priority,
                           "reasons": reasons})
    area_by = {a.area_id: a for a in p.areas}
    return {"routes": out_routes, "unassigned": unassigned,
            "totals": {"areas_total": len(p.areas), "areas_planned": len(planned),
                       "animals_total": sum(a.animals for a in p.areas),
                       "animals_planned": sum(area_by[i].animals for i in planned),
                       "high_priority_unplanned": sum(1 for u in unassigned if u["priority"] == 1),
                       "travel_minutes": sum(r["travel_minutes"] for r in out_routes)}}


def plan(inputs: dict[str, Any], time_limit_s: int = 5) -> dict[str, Any]:
    p = build(inputs)
    t0 = time.perf_counter()
    base = summarise(p, greedy(p))
    greedy_ms = (time.perf_counter() - t0) * 1000
    t1 = time.perf_counter()
    try:
        opt_routes = ortools_solve(p, time_limit_s)
        chosen = summarise(p, opt_routes) if opt_routes is not None else None
    except ValueError:
        chosen = None
    solve_ms = (time.perf_counter() - t1) * 1000
    notes = list(p.notes)
    solver = "ortools"
    if chosen is None:
        chosen, solver = base, "greedy"
        notes.append("The optimiser found no valid solution, so the simpler plan is shown.")
    elif (chosen["totals"]["animals_planned"], -chosen["totals"]["travel_minutes"]) < \
            (base["totals"]["animals_planned"], -base["totals"]["travel_minutes"]):
        chosen, solver = base, "greedy"
        notes.append("The simpler plan covered more animals (or the same with less travel), so it is shown.")
    return {**chosen, "solver": solver, "solver_version": SOLVER_VERSION, "notes": notes,
            "baseline": {"totals": base["totals"]}, "timing_ms": {"greedy": round(greedy_ms, 1),
                                                                 "ortools": round(solve_ms, 1)}}
