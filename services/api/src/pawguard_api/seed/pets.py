"""Fictional pet-clinic data for the vaccination-reminder demo (development/test only).

Two fictional clinics, one pet owner with three pets (one up to date, one due soon, one overdue) and one clinic vet.
Dates are relative to today so the three statuses hold whenever the demo is reset. Products carry a *demo* schedule
template ("Standard schedule — confirm with your vet"); every seeded due date is entered as the vet's own date.
The owner-uploaded certificate awaiting verification is created through the API by ``scripts/demo_prepare.py``.
"""

from datetime import UTC, date, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.engine import Connection

from pawguard_api.domain.reminders import schedule_reminders
from pawguard_api.seed.accounts import demo_id

TEMPLATE_LABEL = "Standard schedule — confirm with your vet"
PRODUCTS = {  # key: (name, species, demo template interval in days)
    "rabies": ("Rabies vaccine", ["dog", "cat"], 365),
    "dhppi": ("DHPPi combination", ["dog"], 365),
    "tricat": ("Feline tricat combination", ["cat"], 365),
}
PETS = (  # key, name, species, sex, age in years, [(product, given days ago, next due in days)]
    ("bruno", "Bruno", "dog", "male", 3, [("rabies", 120, 245), ("dhppi", 120, 245)]),
    ("misty", "Misty", "cat", "female", 2, [("tricat", 355, 10)]),
    ("coco", "Coco", "dog", "female", 5, [("rabies", 370, -5)]),
)


def _ins(c: Connection, table: str, row: dict[str, object]) -> None:
    cols = ", ".join(row)
    vals = ", ".join(f":{k}" for k in row)
    c.execute(text(f"insert into app.{table} ({cols}) values ({vals}) on conflict (id) do nothing"), row)  # noqa: S608


def seed_pets(c: Connection, users: dict[str, UUID]) -> dict[str, int]:
    org = "lotus"
    org_id = demo_id("org", org)
    today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    owner, vet = users["owner"], users["clinic_vet"]
    counts = {"pets": 0, "vaccination_events": 0}
    for clinic in ("lotus", "banyan"):
        for key, (name, species, interval) in PRODUCTS.items():
            _ins(c, "vaccine_products", {
                "id": demo_id("product", f"{clinic}:{key}"), "org_id": demo_id("org", clinic), "name": name,
                "manufacturer": None, "species": species, "form": "injection",
                "review_state": "reviewed", "template_interval_days": interval, "template_label": TEMPLATE_LABEL,
                "is_demo": True, "created_by": users[f"{clinic}_admin"]})
    for key, name, species, sex, years, shots in PETS:
        aid = demo_id("animal", f"{org}:{key}")
        _ins(c, "animals", {
            "id": aid, "org_id": org_id, "species": species, "nickname": name, "sex": sex, "age_band": "adult",
            "date_of_birth": date(today.year - years, 6, 15), "ownership_category": "owned",
            "profile_state": "active", "source_type": "field_entry", "source_reference": "Registered by the pet owner",
            "is_demo": True, "created_by": owner})
        _ins(c, "animal_caregivers", {
            "id": demo_id("caregiver", f"{org}:{key}"), "org_id": org_id, "animal_id": aid, "relationship": "owner",
            "linked_user_id": owner, "is_demo": True, "created_by": owner})
        counts["pets"] += 1
        for product, given_ago, due_in in shots:
            eid = demo_id("vaccination", f"{org}:{key}:{product}")
            given = today - timedelta(days=given_ago)
            at = datetime.combine(given, datetime.min.time(), UTC) + timedelta(hours=6)
            _ins(c, "animal_vaccination_events", {
                "id": eid, "org_id": org_id, "animal_id": aid, "original_animal_id": aid, "administered_on": given,
                "date_precision": "day", "product_id": demo_id("product", f"{org}:{product}"),
                "administered_by_name": "Dr Kiran", "source_type": "clinic_record",
                "source_reference": "Recorded at the clinic", "state": "verified",
                "next_review_on": today + timedelta(days=due_in), "next_review_source": "vet",
                "submitted_by": vet, "submitted_at": at, "verified_by": vet, "verified_at": at, "is_demo": True,
                "created_by": vet})
            counts["vaccination_events"] += 1
        schedule_reminders(c, org_id, aid)
    return counts
