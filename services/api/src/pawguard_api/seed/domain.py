"""Fictional Prevention data for the demo tenants (development/test only).

Deterministic (fixed RNG seed + uuid5 ids) so re-running inserts nothing new. Areas use synthetic square
boundaries labelled "Demo"; animals, people, products and lots are invented and flagged ``is_demo``. None of
this is evaluation data for any model.
"""

import json
import random
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from pawguard_api.seed.accounts import demo_id
from pawguard_api.seed.pets import seed_pets

NICKNAMES = ["Brownie", "Kutty", "Tiger", "Lakshmi", "Moti", "Raja", "Rani", "Jimmy", "Blacky", "Whitey", "Sheru",
             "Kaalu", "Lucky", "Shadow", "Mani", "Chotu", "Bholu", "Golu", "Sona", "Pinky", "Rocky", "Bruno",
             "Laddu", "Ginger"]
COATS = ["Brown, white chest blaze", "Black with tan eyebrows", "Fawn, black muzzle", "White with brown patches",
         "Brindle, medium coat", "Cream, short coat", "Black, white socks on front paws", "Reddish-brown, curled tail",
         "Grey-brown, thick coat", "Tan with dark saddle"]
MARKS = ["Left ear notched (sterilisation mark)", "Torn tip of right ear", "Short tail", "Scar on left flank",
         "Wears a red collar", "White star on forehead", "Limps slightly on rear left leg", None, None]
ORG_CENTRES = {"riverside": (13.050, 80.250), "hillview": (13.110, 80.180)}


def _rng(key: str) -> random.Random:
    return random.Random(f"pawguard-demo-{key}")  # noqa: S311 - deterministic fixtures, not security


def _ref(org: str, i: int) -> str:
    alphabet = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
    r = _rng(f"ref-{org}-{i}")
    s = "".join(r.choice(alphabet) for _ in range(8))
    return f"PG-{s[:4]}-{s[4:]}"


def _square(lat: float, lon: float, half: float) -> str:
    pts = [(lon - half, lat - half), (lon + half, lat - half), (lon + half, lat + half), (lon - half, lat + half),
           (lon - half, lat - half)]
    return "MULTIPOLYGON(((" + ", ".join(f"{x:.5f} {y:.5f}" for x, y in pts) + ")))"


def _ins(c: Connection, table: str, row: dict[str, Any], geo: dict[str, str] | None = None) -> None:
    """Insert one fixture row by fixed id; existing rows are left untouched (idempotent re-runs)."""
    cols = list(row) + list(geo or {})
    vals = [f":{k}" for k in row] + [v for v in (geo or {}).values()]
    params = {k: (json.dumps(v) if isinstance(v, dict) else v) for k, v in row.items()}
    c.execute(text(f"insert into app.{table} ({', '.join(cols)}) values ({', '.join(vals)}) "  # noqa: S608
                   "on conflict (id) do nothing"), params)


def _point(lat: float, lon: float) -> str:
    return f"extensions.st_setsrid(extensions.st_makepoint({lon:.6f}, {lat:.6f}), 4326)::extensions.geography"


def _approx(lat: float, lon: float) -> str:
    return (f"extensions.st_snaptogrid(extensions.st_setsrid(extensions.st_makepoint({lon:.6f}, {lat:.6f}), 4326),"
            f" 0.005)::extensions.geography")


def seed_org(c: Connection, org: str, users: dict[str, UUID], n_animals: int, volunteer: str, vet: str | None,
             coordinator: str | None) -> dict[str, int]:
    org_id = demo_id("org", org)
    r = _rng(org)
    today = datetime.now(UTC).date()
    lat0, lon0 = ORG_CENTRES[org]
    counts = {"areas": 0, "animals": 0, "observations": 0, "vaccination_events": 0, "tasks": 0}

    # Areas (synthetic squares, ~1.1 km)
    areas = []
    for code, name, dlat, dlon in [("A", "North", 0.012, 0.0), ("B", "Central", 0.0, 0.0),
                                   ("C", "South", -0.012, 0.004)]:
        aid = demo_id("area", f"{org}:{code}")
        alat, alon = lat0 + dlat, lon0 + dlon
        _ins(c, "areas", {"id": aid, "org_id": org_id, "code": f"W-{code}", "name": f"Ward {code} — {name}",
                          "kind": "ward", "boundary_source": "Approximate ward outline (sample data)",
                          "boundary_version": "v1", "is_demo": True, "effective_from": date(2026, 1, 1)},
             {"boundary": f"extensions.st_geomfromtext('{_square(alat, alon, 0.005)}', 4326)"})
        areas.append((aid, alat, alon))
        counts["areas"] += 1

    products = []
    for key, name in (("A", "Anti-rabies vaccine A"), ("B", "Anti-rabies vaccine B")):
        pid = demo_id("product", f"{org}:{key}")
        _ins(c, "vaccine_products", {"id": pid, "org_id": org_id, "name": name, "manufacturer": None,
                                     "species": ["dog", "cat"], "unit": "dose", "review_state": "unreviewed",
                                     "is_demo": True})
        lots = []
        for j, exp in enumerate((today + timedelta(days=200), today - timedelta(days=30))):
            lid = demo_id("lot", f"{org}:{key}:{j}")
            _ins(c, "vaccine_lots", {"id": lid, "org_id": org_id, "product_id": pid, "lot_number": f"ARV-{key}-{j + 1:03d}",
                                     "expiry_date": exp, "supplier": None, "is_demo": True})
            lots.append((lid, exp))
        products.append((pid, lots))

    vol_mid = demo_id("membership", f"{volunteer}:{org}")
    animals: list[tuple[UUID, int]] = []
    for i in range(n_animals):
        aid = demo_id("animal", f"{org}:{i}")
        area_id, alat, alon = areas[i % len(areas)]
        missing = i % 7 == 0  # some records with very little known
        state = "active" if i % 5 in (0, 1) else "reviewed" if i % 5 == 2 else "provisional"
        _ins(c, "animals", {
            "id": aid, "org_id": org_id, "reference_code": _ref(org, i), "species": "dog",
            "nickname": None if missing or i % 4 == 3 else NICKNAMES[i % len(NICKNAMES)],
            "sex": "unknown" if missing else r.choice(["female", "male"]),
            "sterilisation_status": "unknown" if missing else r.choice(["sterilised", "not_sterilised", "unknown"]),
            "age_band": "unknown" if missing else r.choice(["young", "adult", "adult", "senior", "puppy"]),
            "coat_description": None if missing else COATS[i % len(COATS)],
            "identifying_marks": None if missing else MARKS[i % len(MARKS)],
            "ownership_category": r.choice(["community", "community", "owned", "unknown"]),
            "profile_state": state, "home_area_id": area_id, "source_type": "field_entry", "is_demo": True,
            "created_by": users[volunteer]})
        counts["animals"] += 1
        animals.append((aid, i))
        # Sightings: recent for most, stale (> 6 months) for every sixth animal
        n_obs = 1 + (i % 3)
        last_seen = None
        for k in range(n_obs):
            days_ago = (200 + 30 * k) if i % 6 == 5 else (2 + 9 * k + i % 5)
            seen_on = today - timedelta(days=days_ago)
            olat, olon = alat + r.uniform(-0.004, 0.004), alon + r.uniform(-0.004, 0.004)
            oid = demo_id("observation", f"{org}:{i}:{k}")
            _ins(c, "animal_observations", {
                "id": oid, "org_id": org_id, "animal_id": aid, "observer_user_id": users[volunteer],
                "observed_on": seen_on, "time_precision": "day", "location_accuracy_m": round(r.uniform(5, 40), 1),
                "location_method": "gps", "area_id": area_id, "notes": None, "source_type": "field_entry",
                "is_demo": True, "created_by": users[volunteer]},
                {"location": _point(olat, olon), "location_approx": _approx(olat, olon)})
            counts["observations"] += 1
            last_seen = max(last_seen or seen_on, seen_on)
        c.execute(text("update app.animals set last_observed_at = :d where id = :a and last_observed_at is null"),
                  {"d": datetime.combine(last_seen, datetime.min.time(), UTC), "a": aid})

    def vacc(key: str, animal_idx: int, *, days_ago: int | None, precision: str, product: int | None, lot: int | None,
             state: str, submitter: str, reviewer: str | None = None, reason: str | None = None,
             note: str | None = None, lot_text: str | None = None) -> UUID:
        eid = demo_id("vaccination", f"{org}:{key}")
        aid = animals[animal_idx % len(animals)][0]
        administered = None if days_ago is None else today - timedelta(days=days_ago)
        if administered and precision == "month":
            administered = administered.replace(day=1)
        pid = products[product][0] if product is not None else None
        lid = products[product][1][lot][0] if (product is not None and lot is not None) else None
        row = {"id": eid, "org_id": org_id, "animal_id": aid, "original_animal_id": aid, "administered_on": administered,
               "date_precision": precision, "product_id": pid, "lot_id": lid, "lot_text": lot_text,
               "product_text": None if pid else "Rabies vaccine (product name not recorded)",
               "administered_by_name": "Dr Meera Rao", "source_type": "field_entry",
               "submitter_note": note, "state": "submitted" if state != "draft" else "draft",
               "submitted_by": users[submitter], "submitted_at": datetime.now(UTC) - timedelta(days=(days_ago or 3)),
               "is_demo": True, "created_by": users[submitter]}
        _ins(c, "animal_vaccination_events", row)
        counts["vaccination_events"] += 1
        if reviewer and state in ("verified", "rejected", "needs_correction"):
            exists = c.execute(text("select 1 from app.vaccination_reviews where event_id = :e"), {"e": eid}).first()
            if not exists:
                c.execute(text("""insert into app.vaccination_reviews (org_id, event_id, reviewer_user_id, outcome,
                                  reason, event_row_version, evidence_snapshot, is_demo)
                                  values (:o, :e, :r, :out, :reason, 1, '{}'::jsonb, true)"""),
                          {"o": org_id, "e": eid, "r": users[reviewer], "out": state, "reason": reason})
                c.execute(text("""update app.animal_vaccination_events set state = :s,
                                  verified_by = case when :s = 'verified' then cast(:r as uuid) end,
                                  verified_at = case when :s = 'verified' then now() - interval '1 day' end
                                  where id = :e"""), {"s": state, "r": users[reviewer], "e": eid})
        return eid

    if vet:
        for n, idx in enumerate(range(0, n_animals, 3)):  # a third of animals have a verified record
            vacc(f"verified-{idx}", idx, days_ago=40 + n * 7, precision="day" if n % 4 else "month", product=n % 2,
                 lot=0, state="verified", submitter=volunteer, reviewer=vet)
        vacc("pending-1", 1, days_ago=2, precision="day", product=0, lot=0, state="submitted", submitter=volunteer,
             note="Given during the morning round.")
        vacc("pending-2", 4, days_ago=1, precision="day", product=None, lot=None, state="submitted",
             submitter=volunteer, lot_text="UNREADABLE-7", note="Lot label smudged.")
        fix = vacc("needs-fix", 7, days_ago=5, precision="day", product=1, lot=0, state="needs_correction",
                   submitter=volunteer, reviewer=vet, reason="The certificate photo shows a different date. "
                   "Please check the date and re-attach a clear photo.")
        vacc("rejected", 10, days_ago=9, precision="day", product=0, lot=1, state="rejected", submitter=volunteer,
             reviewer=vet, reason="Evidence refers to a different animal (collar and markings do not match).")
        # Conflicting evidence: two submissions two days apart for the same animal
        c1 = vacc("conflict-a", 13, days_ago=12, precision="day", product=0, lot=0, state="submitted",
                  submitter=volunteer)
        c2 = vacc("conflict-b", 13, days_ago=10, precision="day", product=1, lot=0, state="submitted",
                  submitter=coordinator or volunteer)
        for eid in (c1, c2):
            c.execute(text("update app.animal_vaccination_events set has_conflict = true where id = :e"), {"e": eid})
            _ins(c, "data_quality_issues", {"id": demo_id("dq", f"{org}:{eid}"), "org_id": org_id,
                                            "resource_type": "vaccination_event", "resource_id": eid,
                                            "rule": "possible_duplicate_vaccination", "severity": "warning",
                                            "explanation": "2 records for this animal within 3 days.", "is_demo": True})
        _ins(c, "field_tasks", {"id": demo_id("task", f"{org}:fix"), "org_id": org_id, "task_type": "evidence_correction",
                                "title": f"Correct vaccination record for {_ref(org, 7)}",
                                "instructions": "The certificate photo shows a different date. Please check the date "
                                                "and re-attach a clear photo.", "animal_id": animals[7 % len(animals)][0],
                                "assignee_membership_id": vol_mid, "state": "assigned", "source_event_type":
                                "vaccination_event", "source_event_id": fix, "is_demo": True,
                                "created_by": users[vet]})
        counts["tasks"] += 1

    # Field tasks for the volunteer and an unassigned pool for the coordinator
    plan = [("round-a", "vaccination_round", "Vaccination round — Ward A", 0, None, "assigned", 0),
            ("round-b", "vaccination_round", "Vaccination round — Ward B", 1, None, "in_progress", 1),
            ("follow-2", "animal_followup", "Check on limping dog", 2, 6, "assigned", 2),
            ("survey-c", "survey", "Street survey — Ward C", 2, None, "unassigned", 4),
            ("follow-blocked", "animal_followup", "Re-sight dog last seen near the market", 0, 5, "blocked", -1)]
    for key, ttype, title, area_i, animal_i, state, due in plan:
        _ins(c, "field_tasks", {
            "id": demo_id("task", f"{org}:{key}"), "org_id": org_id, "task_type": ttype, "title": title,
            "instructions": "Follow your programme's field protocol.", "area_id": areas[area_i][0],
            "animal_id": animals[animal_i][0] if animal_i is not None else None,
            "assignee_membership_id": None if state == "unassigned" else vol_mid, "state": state,
            "due_on": today + timedelta(days=due), "priority": "high" if key == "follow-2" else "normal",
            "priority_rationale": "Reported limp; check welfare and refer if needed." if key == "follow-2" else None,
            "blocked_reason": "Gate locked; caregiver not available until next week." if state == "blocked" else None,
            "is_demo": True, "created_by": users[coordinator] if coordinator else users[volunteer]})
        counts["tasks"] += 1

    # Probable duplicate profile (same dog registered twice) with a pending merge proposal
    dup_id = demo_id("animal", f"{org}:dup")
    src_i = 3
    _ins(c, "animals", {"id": dup_id, "org_id": org_id, "reference_code": _ref(org, 999), "species": "dog",
                        "nickname": None, "sex": "unknown", "age_band": "adult",
                        "coat_description": COATS[src_i % len(COATS)], "identifying_marks": MARKS[src_i % len(MARKS)],
                        "ownership_category": "community", "profile_state": "provisional",
                        "home_area_id": areas[src_i % 3][0], "is_demo": True, "created_by": users[volunteer]})
    if coordinator:
        _ins(c, "animal_merge_operations", {
            "id": demo_id("merge", f"{org}:dup"), "org_id": org_id, "source_animal_id": dup_id,
            "target_animal_id": animals[src_i][0], "state": "proposed",
            "reason": "Same coat and marks, registered twice on different days.", "proposed_by": users[volunteer],
            "is_demo": True, "created_by": users[volunteer]})

    if coordinator:
        _seed_planning(c, org, org_id, areas, lat0, lon0, users, vol_mid, coordinator)

    # A sync operation that conflicted with a newer server edit
    _ins(c, "sync_operations", {
        "id": demo_id("sync", f"{org}:conflict"), "org_id": org_id, "operation_id": demo_id("op", f"{org}:conflict"),
        "device_id": "demo-device-0001", "actor_user_id": users[volunteer], "operation_type": "animal.update",
        "target_type": "animal", "target_id": animals[2][0], "base_row_version": 1, "state": "conflict",
        "result_code": "stale_row_version",
        "result_detail": {"fields": ["nickname", "identifying_marks"], "server_row_version": 2},
        "client_created_at": datetime.now(UTC) - timedelta(hours=5), "is_demo": True})
    return counts


def _seed_planning(c: Connection, org: str, org_id: str, areas: list, lat0: float, lon0: float,
                   users: dict[str, UUID], vol_mid: str, coordinator: str) -> None:
    """Extra synthetic wards, two teams, street counts and a draft campaign for the day planner."""
    today = datetime.now(UTC).date()
    extra = [("D", "East", 0.004, 0.014), ("E", "West", 0.002, -0.013), ("F", "Market", -0.006, -0.008)]
    all_areas = list(areas)
    for code, name, dlat, dlon in extra:
        aid = demo_id("area", f"{org}:{code}")
        alat, alon = lat0 + dlat, lon0 + dlon
        _ins(c, "areas", {"id": aid, "org_id": org_id, "code": f"W-{code}", "name": f"Ward {code} — {name}",
                          "kind": "ward", "boundary_source": "Approximate ward outline (sample data)",
                          "boundary_version": "v1", "is_demo": True, "effective_from": date(2026, 1, 1)},
             {"boundary": f"extensions.st_geomfromtext('{_square(alat, alon, 0.004)}', 4326)"})
        all_areas.append((aid, alat, alon))
    coord_mid = demo_id("membership", f"{coordinator}:{org}")
    for key, name, start_i, start, end, doses in (("1", "Team 1", 0, "08:00", "12:30", 60),
                                                  ("2", "Team 2", 1, "09:00", "13:00", 45)):
        _ins(c, "teams", {"id": demo_id("team", f"{org}:{key}"), "org_id": org_id, "name": name,
                          "shift_start": start, "shift_end": end, "doses_per_day": doses,
                          "start_area_id": all_areas[start_i][0], "is_demo": True, "created_by": users[coordinator]})
    _ins(c, "team_members", {"id": demo_id("team_member", f"{org}:1:vol"), "org_id": org_id,
                             "team_id": demo_id("team", f"{org}:1"), "membership_id": vol_mid, "is_demo": True})
    for i, n, days in ((2, 22, 3), (3, 25, 2)):
        _ins(c, "survey_counts", {"id": demo_id("survey", f"{org}:{i}"), "org_id": org_id,
                                  "area_id": all_areas[i][0], "observed_on": today - timedelta(days=days),
                                  "dogs_counted": n, "marked_count": n // 3, "puppies_count": 2,
                                  "method": "street_count", "notes": "Sample count.",
                                  "observer_user_id": users[coordinator], "is_demo": True})
    camp = demo_id("campaign", f"{org}:october")
    _ins(c, "campaigns", {"id": camp, "org_id": org_id, "name": "October vaccination round",
                          "purpose": "Sample campaign for trying the day planner.", "activity": "vaccination",
                          "starts_on": today + timedelta(days=2), "ends_on": today + timedelta(days=9),
                          "coordinator_membership_id": coord_mid, "state": "draft", "is_demo": True,
                          "created_by": users[coordinator]})
    inputs = [(None, None, 2, None, None, None), (30, "manual", 2, None, None, None), (None, None, 2, None, None, None),
              (25, "manual", 1, None, None, None), (40, "manual", 2, None, None, None),
              (20, "manual", 1, "06:30", "09:30", "Market lanes: only before shops open.")]
    for (aid, _lat, _lon), (n, src, prio, a_start, a_end, note) in zip(all_areas, inputs, strict=True):
        _ins(c, "campaign_areas", {"id": demo_id("campaign_area", f"{org}:{aid}"), "org_id": org_id,
                                   "campaign_id": camp, "area_id": aid, "est_animals": n, "est_source": src,
                                   "service_minutes_per_animal": 4, "access_start": a_start, "access_end": a_end,
                                   "access_note": note, "priority": prio, "is_demo": True,
                                   "created_by": users[coordinator]})


def seed_domain(c: Connection, users: dict[str, UUID]) -> dict[str, object]:
    out: dict[str, object] = {}
    out["riverside"] = seed_org(c, "riverside", users, n_animals=36, volunteer="volunteer", vet="vet",
                                coordinator="coordinator")
    out["hillview"] = seed_org(c, "hillview", users, n_animals=12, volunteer="hill_volunteer", vet="hill_vet",
                               coordinator=None)
    out["pet_clinics"] = seed_pets(c, users)
    from pawguard_api.seed.bites import seed_bites

    out["bite_cases"] = seed_bites(c, users)
    from pawguard_api.seed.clinic_map import seed_clinic_map

    out["clinic_map"] = seed_clinic_map(c, users)
    return out
