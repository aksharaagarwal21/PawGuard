"""Sample map data for Lotus Pet Clinic: three outreach areas, community dogs met at outreach camps (with a mix of
vaccination statuses), recent sightings, clinic visits by the registered pets, and open follow-up tasks.

Sample data (organisation flagged `is_demo`); deterministic ids, so re-running changes nothing. Community dogs are
`ownership_category = community`, so the clinic's registered-pet figures are unaffected.
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.engine import Connection

from pawguard_api.seed.accounts import demo_id

CLINIC_POINT = (13.0418, 80.2340)  # where pets are seen when they visit the clinic
AREAS = (  # code, name, centre (lat, lon), half-size (deg)
    ("TNG", "T. Nagar outreach area", (13.0405, 80.2337), 0.0075),
    ("MYL", "Mylapore outreach area", (13.0339, 80.2686), 0.0070),
    ("ADY", "Adyar outreach area", (13.0063, 80.2574), 0.0080),
)
# key, name, sex, coat, area, rabies given (days ago) or None, next due in (days), sightings [(dlat, dlon, days ago)]
DOGS = (
    ("raja", "Raja", "male", "Tan, white chest", "TNG", 200, 165, [(0.002, -0.003, 2), (0.003, -0.001, 9)]),
    ("kalu", "Kalu", "male", "Black, short coat", "TNG", 370, -5, [(-0.004, 0.002, 1)]),
    ("moti", "Moti", "female", "Cream, curled tail", "TNG", 355, 10, [(0.001, 0.004, 4), (-0.002, 0.005, 12)]),
    ("sheru", "Sheru", "male", "Brindle, torn left ear", "TNG", None, 0, [(-0.005, -0.004, 6)]),
    ("rani", "Rani", "female", "Brown with black muzzle", "MYL", 120, 245, [(0.003, 0.002, 3), (0.001, -0.003, 15)]),
    ("tiger", "Tiger", "male", "Striped brindle", "MYL", 380, -15, [(-0.003, 0.001, 2)]),
    ("bholu", "Bholu", "male", "White with brown patches", "MYL", 90, 275, [(0.004, -0.002, 8)]),
    ("chotu", "Chotu", "female", "Small, ginger", "MYL", None, 0, [(-0.001, 0.004, 5)]),
    ("lucky", "Lucky", "female", "Black and white", "ADY", 300, 65, [(0.002, 0.003, 1), (-0.003, -0.002, 10)]),
    ("brownie", "Brownie", "female", "Chocolate brown", "ADY", 359, 6, [(0.005, -0.004, 3)]),
    ("dosa", "Dosa", "male", "Fawn, black mask", "ADY", None, 0, [(-0.004, 0.005, 7)]),
    ("sona", "Sona", "female", "Golden, long coat", "ADY", 30, 335, [(0.0, 0.0, 2)]),
)
TASKS = (  # key, area, type, title, priority, due in days, state
    ("t1", "TNG", "vaccination_round", "Rabies booster round — T. Nagar (Kalu, Moti due)", "high", 3, "assigned"),
    ("t2", "MYL", "animal_followup", "Follow up Tiger — rabies vaccination overdue", "high", 1, "unassigned"),
    ("t3", "ADY", "animal_followup", "Check on Brownie — booster due next week", "normal", 6, "assigned"),
    ("t4", "ADY", "vaccination_round", "First vaccination for Dosa and new dogs in Adyar", "normal", 10, "unassigned"),
)


def _square(lat: float, lon: float, h: float) -> str:
    pts = [(lon - h, lat - h), (lon + h, lat - h), (lon + h, lat + h), (lon - h, lat + h), (lon - h, lat - h)]
    return "MULTIPOLYGON(((" + ", ".join(f"{x:.6f} {y:.6f}" for x, y in pts) + ")))"


def _ins(c: Connection, table: str, row: dict[str, Any], raw: dict[str, str] | None = None) -> None:
    cols = list(row) + list(raw or {})
    vals = [f":{k}" for k in row] + list((raw or {}).values())
    c.execute(text(f"insert into app.{table} ({', '.join(cols)}) values ({', '.join(vals)}) "  # noqa: S608
                   "on conflict (id) do nothing"), row)


def _point(lat: float, lon: float) -> dict[str, str]:
    p = f"extensions.st_setsrid(extensions.st_makepoint({lon:.6f}, {lat:.6f}), 4326)::extensions.geography"
    approx = (f"extensions.st_setsrid(extensions.st_makepoint({round(lon / 0.0045) * 0.0045:.6f}, "
              f"{round(lat / 0.0045) * 0.0045:.6f}), 4326)::extensions.geography")
    return {"location": p, "location_approx": approx}


def seed_clinic_map(c: Connection, users: dict[str, UUID]) -> dict[str, int]:
    org = demo_id("org", "lotus")
    vet = users["clinic_vet"]
    today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    now = datetime.now(UTC)
    rabies = c.execute(text("select id from app.vaccine_products where org_id = :o and name ilike '%rabies%' "
                            "order by created_at limit 1"), {"o": org}).scalar()
    counts = {"areas": 0, "community_dogs": 0, "sightings": 0, "tasks": 0}
    area_ids: dict[str, UUID] = {}
    for code, name, (lat, lon), h in AREAS:
        aid = demo_id("area", f"lotus:{code}")
        area_ids[code] = aid
        _ins(c, "areas", {"id": aid, "org_id": org, "code": f"LOTUS-{code}", "name": name, "kind": "locality",
                          "boundary_source": "Approximate outreach boundary drawn by the clinic",
                          "boundary_version": "1", "is_demo": True, "effective_from": today - timedelta(days=365)},
             {"boundary": f"extensions.st_geomfromtext('{_square(lat, lon, h)}', 4326)"})
        counts["areas"] += 1
    centres = {code: centre for code, _n, centre, _h in AREAS}
    for key, name, sex, coat, area, given_ago, due_in, sightings in DOGS:
        aid = demo_id("animal", f"lotus:community:{key}")
        _ins(c, "animals", {"id": aid, "org_id": org, "species": "dog", "nickname": name, "sex": sex,
                            "age_band": "adult", "coat_description": coat, "ownership_category": "community",
                            "home_area_id": area_ids[area], "profile_state": "active",
                            "source_type": "field_entry", "source_reference": "Registered at a clinic outreach camp",
                            "is_demo": True, "created_by": vet})
        counts["community_dogs"] += 1
        lat0, lon0 = centres[area]
        for n, (dlat, dlon, ago) in enumerate(sightings):
            seen = now - timedelta(days=ago, hours=n + 2)
            _ins(c, "animal_observations", {
                "id": demo_id("observation", f"lotus:{key}:{n}"), "org_id": org, "animal_id": aid,
                "reported_animal_reference": None, "observer_user_id": vet, "observed_at": seen,
                "time_precision": "exact", "location_accuracy_m": 15, "location_method": "gps",
                "area_id": area_ids[area], "notes": "Seen during outreach rounds", "source_type": "field_entry",
                "is_demo": True, "created_by": vet, "created_at": seen},
                _point(lat0 + dlat, lon0 + dlon))
            counts["sightings"] += 1
        if given_ago is not None and rabies:
            given = today - timedelta(days=given_ago)
            _ins(c, "animal_vaccination_events", {
                "id": demo_id("vaccination", f"lotus:community:{key}"), "org_id": org, "animal_id": aid,
                "original_animal_id": aid, "administered_on": given, "date_precision": "day", "product_id": rabies,
                "administered_by_name": "Dr Kiran", "source_type": "field_entry",
                "source_reference": "Outreach vaccination camp", "state": "verified",
                "next_review_on": given + timedelta(days=given_ago + due_in), "next_review_source": "vet",
                "submitted_by": vet, "submitted_at": now, "verified_by": vet, "verified_at": now, "is_demo": True,
                "created_by": vet})
    # Registered pets seen when they visited the clinic (the clinic's location, never an owner's home).
    for key in ("bruno", "misty", "coco"):
        aid = demo_id("animal", f"lotus:{key}")
        if c.execute(text("select 1 from app.animals where id = :a"), {"a": aid}).scalar():
            seen = now - timedelta(days=3)
            _ins(c, "animal_observations", {
                "id": demo_id("observation", f"lotus:visit:{key}"), "org_id": org, "animal_id": aid,
                "observer_user_id": vet, "observed_at": seen, "time_precision": "exact", "location_accuracy_m": 10,
                "location_method": "gps", "area_id": area_ids["TNG"], "notes": "Clinic visit",
                "source_type": "field_entry", "is_demo": True, "created_by": vet, "created_at": seen},
                _point(*CLINIC_POINT))
            counts["sightings"] += 1
    for key, area, ttype, title, priority, due, state in TASKS:
        _ins(c, "field_tasks", {"id": demo_id("task", f"lotus:{key}"), "org_id": org, "created_by": vet,
                                "task_type": ttype, "title": title, "area_id": area_ids[area],
                                "due_on": today + timedelta(days=due), "priority": priority, "state": state,
                                "assignee_membership_id": demo_id("membership", "clinic_vet:lotus")
                                if state == "assigned" else None,
                                "is_demo": True})
        counts["tasks"] += 1
    return counts
