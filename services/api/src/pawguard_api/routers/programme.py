"""Programme views: map layers, per-area registry measures and scoped exports.

Every number here is a *registry* measure (records in this organisation's PawGuard registry). None of them is
population vaccination coverage, which needs a survey with an explicit denominator (Phase 8).
"""

import csv
import io
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import text

from pawguard_api.capabilities import Cap
from pawguard_api.contracts import Out
from pawguard_api.deps import CurrentOrg
from pawguard_api.domain.common import record_audit

router = APIRouter(prefix="/api/v1", tags=["programme"])

REGISTRY_NOTE = ("Registry measures count records in this organisation's PawGuard registry. They are not population "
                 "vaccination coverage: animals never registered are not counted.")


class AreaSummary(Out):
    area_id: UUID | None
    area_code: str | None
    area_name: str
    registered_animals: int
    animals_with_verified_record: int
    animals_with_pending_evidence_only: int
    sightings_last_30_days: int
    open_tasks: int
    submitted_awaiting_review: int


class ProgrammeSummary(Out):
    generated_at: datetime
    data_mode: str  # "demo" if any counted record is a demo fixture, else "live"
    note: str
    areas: list[AreaSummary]
    totals: AreaSummary


@router.get("/programme/summary", response_model=ProgrammeSummary, summary="Registry measures by area")
def summary(ctx: CurrentOrg) -> ProgrammeSummary:
    """Permission: ``animal.read``. Counts are registry measures, not coverage (see ``note``)."""
    ctx.require(Cap.ANIMAL_READ)
    with ctx.tx() as db:
        rows = db.execute(text("""
            with a as (
              select an.id, an.home_area_id,
                     exists (select 1 from app.animal_vaccination_events e where e.animal_id = an.id
                             and e.state = 'verified') as verified,
                     exists (select 1 from app.animal_vaccination_events e where e.animal_id = an.id
                             and e.state = 'submitted') as pending
              from app.animals an where an.profile_state not in ('merged_alias','archived'))
            select ar.id as area_id, ar.code as area_code, coalesce(ar.name, 'No area recorded') as area_name,
                   count(a.id) as registered_animals,
                   count(a.id) filter (where a.verified) as animals_with_verified_record,
                   count(a.id) filter (where not a.verified and a.pending) as animals_with_pending_evidence_only,
                   (select count(*) from app.animal_observations o where o.area_id is not distinct from ar.id
                      and o.created_at >= now() - interval '30 days') as sightings_last_30_days,
                   (select count(*) from app.field_tasks t where t.area_id is not distinct from ar.id
                      and t.state in ('unassigned','assigned','in_progress','blocked')) as open_tasks,
                   (select count(*) from app.animal_vaccination_events e join app.animals x on x.id = e.animal_id
                      where e.state = 'submitted' and x.home_area_id is not distinct from ar.id)
                      as submitted_awaiting_review
            from app.areas ar full outer join a on a.home_area_id = ar.id
            group by ar.id, ar.code, ar.name order by ar.name nulls last""")).all()
        demo = db.execute(text("select coalesce(bool_or(is_demo), false) from app.animals")).scalar()
    areas = [AreaSummary(**r._mapping) for r in rows]
    tot = {k: sum(getattr(a, k) for a in areas) for k in AreaSummary.model_fields
           if k not in ("area_id", "area_code", "area_name")}
    return ProgrammeSummary(generated_at=datetime.now(UTC), data_mode="demo" if demo else "live", note=REGISTRY_NOTE,
                            areas=areas, totals=AreaSummary(area_id=None, area_code=None, area_name="All areas", **tot))


def _status(last_verified: Any, next_due: Any) -> str:
    """Vaccination status for map colouring (same 14-day rule as the pet status)."""
    from datetime import date, timedelta

    if last_verified is None:
        return "no_verified_record"
    if next_due is None:
        return "verified"
    today = date.today()
    return "overdue" if next_due < today else "due_soon" if next_due <= today + timedelta(days=14) else "up_to_date"


@router.get("/map/layers", summary="Map layers (GeoJSON)")
def layers(ctx: CurrentOrg, days: Annotated[int, Query(ge=1, le=365)] = 90) -> dict[str, Any]:
    """Permission: ``animal.read``. Sighting points are exact only with ``animal.location.exact`` and otherwise
    snapped to a ~500 m grid. At most 2,000 sightings (most recent) are returned; ``truncated`` says if more exist."""
    ctx.require(Cap.ANIMAL_READ)
    exact = ctx.can(Cap.ANIMAL_LOCATION_EXACT)
    col = "o.location" if exact else "o.location_approx"
    with ctx.tx() as db:
        area_rows = db.execute(text("""
            select id, code, name, st_asgeojson(boundary, 6)::json as geom from app.areas
            where boundary is not null and (effective_to is null or effective_to > current_date)""")).all()
        sightings = db.execute(text(f"""
            select o.id, o.animal_id, a.reference_code, coalesce(o.observed_at::date, o.observed_on) as day,
                   st_asgeojson({col}::geometry, 6)::json as geom, a.nickname, a.species, a.ownership_category,
                   v.administered_on as last_verified, v.next_review_on as next_due
            from app.animal_observations o left join app.animals a on a.id = o.animal_id
            left join lateral (select e.administered_on, e.next_review_on from app.animal_vaccination_events e
                               where e.animal_id = a.id and e.state = 'verified'
                               order by e.administered_on desc nulls last limit 1) v on true
            where {col} is not null and o.created_at >= now() - make_interval(days => :d)
            order by o.created_at desc limit 2001"""), {"d": days}).all()  # noqa: S608
        tasks = db.execute(text("""
            select t.id, t.title, t.state, t.task_type, st_asgeojson(st_centroid(ar.boundary), 6)::json as geom
            from app.field_tasks t join app.areas ar on ar.id = t.area_id
            where t.state in ('unassigned','assigned','in_progress','blocked') and ar.boundary is not null""")).all()
    truncated = len(sightings) > 2000
    return {
        "precision": "exact" if exact else "approximate",
        "truncated": truncated,
        "areas": {"type": "FeatureCollection", "features": [
            {"type": "Feature", "id": str(r.id), "geometry": r.geom,
             "properties": {"code": r.code, "name": r.name}} for r in area_rows]},
        "sightings": {"type": "FeatureCollection", "features": [
            {"type": "Feature", "id": str(r.id), "geometry": r.geom,
             "properties": {"animal_id": str(r.animal_id) if r.animal_id else None, "reference": r.reference_code,
                            "day": r.day.isoformat() if r.day else None, "name": r.nickname, "species": r.species,
                            "ownership": r.ownership_category, "status": _status(r.last_verified, r.next_due),
                            "last_verified": r.last_verified.isoformat() if r.last_verified else None,
                            "next_due": r.next_due.isoformat() if r.next_due else None}}
            for r in sightings[:2000]]},
        "tasks": {"type": "FeatureCollection", "features": [
            {"type": "Feature", "id": str(r.id), "geometry": r.geom,
             "properties": {"title": r.title, "state": r.state, "task_type": r.task_type}} for r in tasks]},
    }


EXPORT_COLUMNS = ["reference_code", "species", "nickname", "sex", "sterilisation_status", "age_band",
                  "ownership_category", "profile_state", "home_area_code", "last_observed_on",
                  "last_verified_vaccination_on", "last_verified_vaccination_precision", "pending_review_count",
                  "is_demo"]


@router.get("/exports/animals.csv", summary="Registry export (CSV)")
def export_animals(ctx: CurrentOrg) -> StreamingResponse:
    """Permission: ``report.aggregate``. Only this organisation's records; never caregiver contacts, coordinates or
    free-text notes. The first line declares the data mode (demo/live). Every export is audited."""
    ctx.require(Cap.REPORT_AGGREGATE)
    with ctx.tx() as db:
        rows = db.execute(text("""
            select a.reference_code, a.species, a.nickname, a.sex, a.sterilisation_status, a.age_band,
                   a.ownership_category, a.profile_state, ar.code as home_area_code,
                   a.last_observed_at::date as last_observed_on,
                   lv.administered_on as last_verified_vaccination_on,
                   lv.date_precision as last_verified_vaccination_precision,
                   (select count(*) from app.animal_vaccination_events e where e.animal_id = a.id
                    and e.state = 'submitted') as pending_review_count, a.is_demo
            from app.animals a left join app.areas ar on ar.id = a.home_area_id
            left join lateral (select administered_on, date_precision from app.animal_vaccination_events e
                               where e.animal_id = a.id and e.state = 'verified'
                               order by administered_on desc nulls last limit 1) lv on true
            where a.profile_state not in ('merged_alias')
            order by a.reference_code""")).all()
        record_audit(db, ctx, "export.animals_csv", "organisation", ctx.org_id, {"rows": len(rows)})
    mode = "demo" if any(r.is_demo for r in rows) else "live"
    buf = io.StringIO()
    buf.write(f"# data_mode: {mode}; generated_at: {datetime.now(UTC).isoformat()}; registry export, not coverage\n")
    w = csv.writer(buf)
    w.writerow(EXPORT_COLUMNS)
    for r in rows:
        w.writerow(["" if getattr(r, c) is None else getattr(r, c) for c in EXPORT_COLUMNS])
    filename = f"pawguard-animals-{datetime.now(UTC).date()}.csv"
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": f'attachment; filename="{filename}"'})
