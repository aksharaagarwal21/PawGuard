"""Campaigns, teams, surveys and day plans.

A plan is created from an immutable snapshot of the inputs (areas with their estimates and where each estimate came
from, teams with shifts and doses, travel assumptions, the person's pins and exclusions) and solved in the worker.
It is only a proposal: a coordinator approves it, then publishes it, which creates ordinary field tasks assigned to
teams. Re-planning creates a new version; earlier versions and their tasks are kept unchanged.
"""

import json
from datetime import date, datetime, time
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.orm import Session

from pawguard_api.capabilities import Cap
from pawguard_api.contracts import (
    CampaignAreaIn,
    CampaignAreaOut,
    CampaignIn,
    CampaignOut,
    PlanIn,
    PlanOut,
    SurveyIn,
    TeamIn,
    TeamOut,
)
from pawguard_api.deps import OrgContext
from pawguard_api.domain.animals import ensure_area
from pawguard_api.domain.common import emit, enqueue_job, expect_version, record_audit
from pawguard_api.errors import Conflict, NotFound, Unprocessable

ACTIVITY_TITLE = {"vaccination": "Vaccination round", "survey": "Street survey"}


def _t(v: time | None) -> str | None:
    return v.strftime("%H:%M") if v else None


# ---- surveys -----------------------------------------------------------------------------------------------------

def record_survey(db: Session, ctx: OrgContext, data: SurveyIn) -> UUID:
    ctx.require(Cap.SURVEY_WRITE)
    ensure_area(db, data.area_id)
    if data.client_operation_id:
        prior = db.execute(text("select id from app.survey_counts where client_operation_id = :c"),
                           {"c": data.client_operation_id}).scalar()
        if prior:
            return prior
    sid = db.execute(text("""
        insert into app.survey_counts (org_id, campaign_id, area_id, field_task_id, observed_on, dogs_counted,
          marked_count, puppies_count, method, notes, observer_user_id, client_operation_id)
        values (:o, :c, :a, :t, :d, :n, :m, :p, :method, :notes, :u, :op) returning id"""),
        {"o": ctx.org_id, "c": data.campaign_id, "a": data.area_id, "t": data.field_task_id, "d": data.observed_on,
         "n": data.dogs_counted, "m": data.marked_count, "p": data.puppies_count, "method": data.method,
         "notes": data.notes, "u": ctx.user_id, "op": data.client_operation_id}).scalar_one()
    record_audit(db, ctx, "survey.recorded", "survey", sid, {"area_id": str(data.area_id), "dogs": data.dogs_counted})
    return sid


# ---- teams -------------------------------------------------------------------------------------------------------

def _team_out(r: Any) -> TeamOut:
    return TeamOut(id=r.id, name=r.name, shift_start=_t(r.shift_start) or "08:00", shift_end=_t(r.shift_end) or "13:00",
                   doses_per_day=r.doses_per_day, start_area_id=r.start_area_id, member_count=r.member_count,
                   row_version=r.row_version)


def list_teams(db: Session, ctx: OrgContext) -> list[TeamOut]:
    if not ctx.can(Cap.CAMPAIGN_MANAGE):
        ctx.require(Cap.TASK_MANAGE)
    rows = db.execute(text("""select t.*, (select count(*) from app.team_members m where m.team_id = t.id
                                 and (m.valid_to is null or m.valid_to >= current_date)) as member_count
                              from app.teams t where t.active order by t.name""")).all()
    return [_team_out(r) for r in rows]


def create_team(db: Session, ctx: OrgContext, data: TeamIn) -> UUID:
    ctx.require(Cap.CAMPAIGN_MANAGE)
    if data.shift_end <= data.shift_start:
        raise Unprocessable("The shift must end after it starts.", code="invalid_shift")
    ensure_area(db, data.start_area_id)
    tid = db.execute(text("""insert into app.teams (org_id, name, shift_start, shift_end, doses_per_day, start_area_id,
                               created_by) values (:o, :n, :s, :e, :d, :a, :u) returning id"""),
                     {"o": ctx.org_id, "n": data.name, "s": data.shift_start, "e": data.shift_end,
                      "d": data.doses_per_day, "a": data.start_area_id, "u": ctx.user_id}).scalar_one()
    record_audit(db, ctx, "team.created", "team", tid, {"name": data.name})
    return tid


# ---- campaigns ---------------------------------------------------------------------------------------------------

def create_campaign(db: Session, ctx: OrgContext, data: CampaignIn) -> UUID:
    ctx.require(Cap.CAMPAIGN_MANAGE)
    if data.starts_on and data.ends_on and data.ends_on < data.starts_on:
        raise Unprocessable("The campaign must end after it starts.", code="invalid_dates")
    cid = db.execute(text("""insert into app.campaigns (org_id, name, activity, starts_on, ends_on, created_by,
                               coordinator_membership_id) values (:o, :n, :a, :s, :e, :u, :m) returning id"""),
                     {"o": ctx.org_id, "n": data.name, "a": data.activity, "s": data.starts_on, "e": data.ends_on,
                      "u": ctx.user_id, "m": ctx.membership_id}).scalar_one()
    for area_id in dict.fromkeys(data.area_ids):
        ensure_area(db, area_id)
        db.execute(text("insert into app.campaign_areas (org_id, campaign_id, area_id, created_by) "
                        "values (:o, :c, :a, :u)"), {"o": ctx.org_id, "c": cid, "a": area_id, "u": ctx.user_id})
    record_audit(db, ctx, "campaign.created", "campaign", cid, {"areas": len(data.area_ids)})
    return cid


def _suggestions(db: Session, area_ids: list[UUID]) -> dict[UUID, tuple[int, str]]:
    """Latest survey count, else the number of active registry records whose home area it is."""
    out: dict[UUID, tuple[int, str]] = {}
    if not area_ids:
        return out
    for r in db.execute(text("""select distinct on (area_id) area_id, dogs_counted from app.survey_counts
                                where area_id = any(cast(:a as uuid[])) order by area_id, observed_on desc,
                                created_at desc"""), {"a": area_ids}):
        out[r.area_id] = (r.dogs_counted, "survey")
    for r in db.execute(text("""select home_area_id, count(*) as n from app.animals
                                where home_area_id = any(cast(:a as uuid[]))
                                  and profile_state not in ('merged_alias','archived') group by home_area_id"""),
                        {"a": area_ids}):
        out.setdefault(r.home_area_id, (r.n, "registry"))
    return out


def get_campaign(db: Session, ctx: OrgContext, campaign_id: UUID) -> CampaignOut:
    if not ctx.can(Cap.CAMPAIGN_MANAGE):
        ctx.require(Cap.TASK_MANAGE)
    c = db.execute(text("select * from app.campaigns where id = :id"), {"id": campaign_id}).one_or_none()
    if c is None:
        raise NotFound("Campaign not found.", code="campaign_not_found")
    rows = db.execute(text("""select ca.*, a.code, a.name, a.boundary is not null as has_location
                              from app.campaign_areas ca join app.areas a on a.id = ca.area_id
                              where ca.campaign_id = :c order by a.code"""), {"c": campaign_id}).all()
    sugg = _suggestions(db, [r.area_id for r in rows])
    areas = [CampaignAreaOut(
        area_id=r.area_id, code=r.code, name=r.name, has_location=r.has_location, est_animals=r.est_animals,
        est_source=r.est_source, suggested_animals=sugg.get(r.area_id, (None, None))[0],
        suggested_source=sugg.get(r.area_id, (None, None))[1],
        service_minutes_per_animal=float(r.service_minutes_per_animal), access_start=_t(r.access_start),
        access_end=_t(r.access_end), accessible=r.accessible, access_note=r.access_note, priority=r.priority,
        row_version=r.row_version) for r in rows]
    return CampaignOut(id=c.id, name=c.name, activity=c.activity, state=c.state, starts_on=c.starts_on,
                       ends_on=c.ends_on, areas=areas, row_version=c.row_version)


def list_campaigns(db: Session, ctx: OrgContext) -> list[CampaignOut]:
    if not ctx.can(Cap.CAMPAIGN_MANAGE):
        ctx.require(Cap.TASK_MANAGE)
    rows = db.execute(text("select * from app.campaigns order by coalesce(starts_on, created_at::date) desc")).all()
    return [CampaignOut(id=c.id, name=c.name, activity=c.activity, state=c.state, starts_on=c.starts_on,
                        ends_on=c.ends_on, row_version=c.row_version) for c in rows]


def update_campaign_area(db: Session, ctx: OrgContext, campaign_id: UUID, area_id: UUID, data: CampaignAreaIn) -> None:
    ctx.require(Cap.CAMPAIGN_MANAGE)
    row = db.execute(text("select id, row_version from app.campaign_areas where campaign_id = :c and area_id = :a "
                          "for update"), {"c": campaign_id, "a": area_id}).one_or_none()
    if row is None:
        raise NotFound("That area is not part of this campaign.", code="campaign_area_not_found")
    expect_version(row.row_version, data.row_version, "campaign area")
    if data.access_start and data.access_end and data.access_end <= data.access_start:
        raise Unprocessable("The access window must end after it starts.", code="invalid_window")
    db.execute(text("""update app.campaign_areas set est_animals = :n, est_source = case when :n is null then null
                         else 'manual' end, service_minutes_per_animal = :s, access_start = :as_, access_end = :ae,
                         accessible = :acc, access_note = :note, priority = :p where id = :id"""),
               {"n": data.est_animals, "s": data.service_minutes_per_animal, "as_": data.access_start,
                "ae": data.access_end, "acc": data.accessible, "note": data.access_note, "p": data.priority,
                "id": row.id})
    record_audit(db, ctx, "campaign.area_updated", "campaign", campaign_id, {"area_id": str(area_id)})


# ---- plans -------------------------------------------------------------------------------------------------------

def create_plan(db: Session, ctx: OrgContext, campaign_id: UUID, data: PlanIn) -> UUID:
    ctx.require(Cap.CAMPAIGN_MANAGE)
    campaign = get_campaign(db, ctx, campaign_id)
    if not campaign.areas:
        raise Unprocessable("Add areas to the campaign before planning.", code="no_areas")
    team_rows = {r.id: r for r in db.execute(text("""
        select t.*, extensions.st_y(extensions.st_centroid(a.boundary)) as lat,
               extensions.st_x(extensions.st_centroid(a.boundary)) as lon, a.name as start_name
        from app.teams t left join app.areas a on a.id = t.start_area_id
        where t.id = any(cast(:ids as uuid[])) and t.active"""), {"ids": [t.team_id for t in data.teams]})}
    teams = []
    for t in data.teams:
        r = team_rows.get(t.team_id)
        if r is None:
            raise Unprocessable("Choose active teams of this organisation.", code="unknown_team")
        if r.lat is None:
            raise Unprocessable(f"Team {r.name} needs a starting area with a map location.", code="team_without_start")
        start, end = t.shift_start or _t(r.shift_start), t.shift_end or _t(r.shift_end)
        if end <= start:  # type: ignore[operator]
            raise Unprocessable("A shift must end after it starts.", code="invalid_shift")
        teams.append({"team_id": str(r.id), "name": r.name, "shift_start": start, "shift_end": end,
                      "doses": t.doses if t.doses is not None else r.doses_per_day,
                      "start": {"lat": r.lat, "lon": r.lon, "label": r.start_name}})
    team_ids = {t["team_id"] for t in teams}
    area_ids = {str(a.area_id) for a in campaign.areas}
    for area, team in data.pinned.items():
        if str(area) not in area_ids or str(team) not in team_ids:
            raise Unprocessable("A pinned area or team is not part of this plan.", code="invalid_pin")
    locs = {r.id: r for r in db.execute(text("""
        select id, extensions.st_y(extensions.st_centroid(boundary)) as lat,
               extensions.st_x(extensions.st_centroid(boundary)) as lon
        from app.areas where id = any(cast(:ids as uuid[]))"""), {"ids": [a.area_id for a in campaign.areas]})}
    areas = []
    for a in campaign.areas:
        manual = a.est_animals is not None
        n, src = (a.est_animals, a.est_source) if manual else (a.suggested_animals, a.suggested_source)
        loc = locs.get(a.area_id)
        areas.append({"area_id": str(a.area_id), "name": a.name, "lat": loc.lat if loc else None,
                      "lon": loc.lon if loc else None, "est_animals": n or 0, "est_source": src or "none",
                      "service_minutes_per_animal": a.service_minutes_per_animal, "access_start": a.access_start,
                      "access_end": a.access_end, "accessible": a.accessible, "priority": a.priority})
    inputs = {"plan_date": data.plan_date.isoformat(), "activity": campaign.activity,
              "travel": {"basis": "straight_line_estimate", "speed_kmh": data.speed_kmh,
                         "detour_factor": data.detour_factor},
              "teams": teams, "areas": areas,
              "overrides": {"pinned": {str(k): str(v) for k, v in data.pinned.items()},
                            "excluded": [str(x) for x in data.excluded]}}
    version = db.execute(text("select coalesce(max(version), 0) + 1 from app.campaign_plans where campaign_id = :c"),
                         {"c": campaign_id}).scalar_one()
    pid = db.execute(text("""insert into app.campaign_plans (org_id, campaign_id, version, plan_date, inputs,
                               created_by) values (:o, :c, :v, :d, cast(:i as jsonb), :u) returning id"""),
                     {"o": ctx.org_id, "c": campaign_id, "v": version, "d": data.plan_date, "i": json.dumps(inputs),
                      "u": ctx.user_id}).scalar_one()
    enqueue_job(db, ctx, "plan.solve", "campaign_plan", pid, max_attempts=2)
    record_audit(db, ctx, "plan.requested", "campaign_plan", pid, {"version": version, "teams": len(teams),
                                                                  "areas": len(areas)})
    return pid


def get_plan(db: Session, ctx: OrgContext, plan_id: UUID) -> PlanOut:
    if not ctx.can(Cap.CAMPAIGN_MANAGE):
        ctx.require(Cap.TASK_MANAGE)
    p = db.execute(text("""select p.*, up.preferred_name as approver from app.campaign_plans p
                           left join app.user_profiles up on up.user_id = p.approved_by where p.id = :id"""),
                   {"id": plan_id}).one_or_none()
    if p is None:
        raise NotFound("Plan not found.", code="plan_not_found")
    return PlanOut(id=p.id, campaign_id=p.campaign_id, version=p.version, plan_date=p.plan_date, state=p.state,
                   travel_basis=p.travel_basis, inputs=p.inputs, result=p.result, failure_code=p.failure_code,
                   created_at=p.created_at, approved_by_name=p.approver, approved_at=p.approved_at,
                   approval_note=p.approval_note, published_at=p.published_at, task_count=len(p.task_ids or []),
                   row_version=p.row_version)


def list_plans(db: Session, ctx: OrgContext, campaign_id: UUID) -> list[PlanOut]:
    ids = db.execute(text("select id from app.campaign_plans where campaign_id = :c order by version desc"),
                     {"c": campaign_id}).scalars().all()
    return [get_plan(db, ctx, i) for i in ids]


def _lock_plan(db: Session, plan_id: UUID, row_version: int) -> Any:
    p = db.execute(text("select * from app.campaign_plans where id = :id for update"), {"id": plan_id}).one_or_none()
    if p is None:
        raise NotFound("Plan not found.", code="plan_not_found")
    expect_version(p.row_version, row_version, "plan")
    return p


def approve_plan(db: Session, ctx: OrgContext, plan_id: UUID, row_version: int, note: str | None) -> None:
    ctx.require(Cap.CAMPAIGN_MANAGE)
    p = _lock_plan(db, plan_id, row_version)
    if p.state != "ready":
        raise Conflict("Only a finished plan can be approved.", code="invalid_state", details={"state": p.state})
    db.execute(text("""update app.campaign_plans set state = 'approved', approved_by = :u, approved_at = now(),
                         approval_note = :n where id = :id"""), {"u": ctx.user_id, "n": note, "id": plan_id})
    record_audit(db, ctx, "plan.approved", "campaign_plan", plan_id, {"version": p.version}, reason=note)


def publish_plan(db: Session, ctx: OrgContext, plan_id: UUID, row_version: int) -> int:
    """Create one field task per planned stop, assigned to the team, with planned times. Earlier published
    versions for the same campaign and date are marked superseded; their tasks are left for people to review."""
    ctx.require(Cap.CAMPAIGN_MANAGE)
    ctx.require(Cap.TASK_MANAGE)
    p = _lock_plan(db, plan_id, row_version)
    if p.state != "approved":
        raise Conflict("Approve the plan before publishing it.", code="invalid_state", details={"state": p.state})
    tz = ZoneInfo(ctx.timezone)
    day: date = p.plan_date
    activity = p.inputs.get("activity", "vaccination")
    task_ids: list[UUID] = []
    for route in p.result.get("routes", []):
        for n, stop in enumerate(route["stops"], start=1):
            start = datetime.combine(day, time.fromisoformat(stop["start"]), tz)
            finish = datetime.combine(day, time.fromisoformat(stop["finish"]), tz)
            instructions = (f"Planned stop {n} for {route['name']} on {day.isoformat()}: "
                            f"arrive about {stop['arrive']}, about {stop['animals']} animals"
                            + (f", {stop['doses']} doses" if activity == "vaccination" else "")
                            + ". Times use a travel estimate, not a road route.")
            tid = db.execute(text("""
                insert into app.field_tasks (org_id, campaign_id, task_type, title, instructions, area_id, team_id,
                  planned_start, planned_end, due_on, priority, state, source_event_type, source_event_id, created_by)
                values (:o, :c, :type, :title, :ins, :a, :team, :ps, :pe, :d, :prio, 'assigned', 'campaign_plan',
                  :pid, :u) returning id"""),
                {"o": ctx.org_id, "c": p.campaign_id, "type": "survey" if activity == "survey" else "vaccination_round",
                 "title": f"{ACTIVITY_TITLE.get(activity, 'Field work')} — {stop['name']}", "ins": instructions,
                 "a": stop["area_id"], "team": route["team_id"], "ps": start, "pe": finish, "d": day,
                 "prio": {1: "high", 2: "normal", 3: "low"}.get(stop.get("priority", 2), "normal"),
                 "pid": plan_id, "u": ctx.user_id}).scalar_one()
            task_ids.append(tid)
            emit(db, ctx, "task.created", "task", tid)
    db.execute(text("""update app.campaign_plans set state = 'superseded' where campaign_id = :c and plan_date = :d
                         and state = 'published' and id <> :id"""), {"c": p.campaign_id, "d": day, "id": plan_id})
    db.execute(text("""update app.campaign_plans set state = 'published', published_by = :u, published_at = now(),
                         task_ids = cast(:t as uuid[]) where id = :id"""),
               {"u": ctx.user_id, "t": [str(t) for t in task_ids], "id": plan_id})
    record_audit(db, ctx, "plan.published", "campaign_plan", plan_id, {"tasks": len(task_ids), "version": p.version})
    return len(task_ids)
