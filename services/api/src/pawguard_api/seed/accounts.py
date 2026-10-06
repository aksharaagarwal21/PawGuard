"""Demo organisations and accounts (development/test ONLY).

Everything here is fictional and flagged ``is_demo``. Organisation names start with "Demo —". Emails use the
reserved example.org domain. The shared password is a published development credential and must never be
used anywhere real; ``seed-demo`` refuses to run in staging/production or without demo mode.
"""

from dataclasses import dataclass
from uuid import UUID, uuid5

NAMESPACE = UUID("6f2b3c1e-7a1d-4c55-9a51-2b7c8f1d0e42")
DEMO_PASSWORD = "PawGuard-demo-2026"


def demo_id(kind: str, key: str) -> UUID:
    return uuid5(NAMESPACE, f"{kind}:{key}")


@dataclass(frozen=True)
class DemoOrg:
    key: str
    name: str
    org_type: str
    region_code: str


@dataclass(frozen=True)
class DemoAccount:
    key: str
    email: str
    preferred_name: str
    description: str
    memberships: tuple[tuple[str, str], ...]  # (org key, role)
    vet_approval_in: tuple[str, ...] = ()  # org keys where a veterinary_review approval is granted
    locale: str = "en"


ORGS = (
    DemoOrg("riverside", "Demo — Riverside Animal Welfare Trust", "animal_welfare_ngo", "IN-TN"),
    DemoOrg("hillview", "Demo — Hillview Municipal Programme", "municipal_programme", "IN-TN"),
    DemoOrg("lotus", "Demo — Lotus Pet Clinic (fictional)", "veterinary_service", "IN-TN"),
    DemoOrg("banyan", "Demo — Banyan Veterinary Centre (fictional)", "veterinary_service", "IN-TN"),
)

ACCOUNTS = (
    DemoAccount("admin", "admin.kavya@example.org", "Kavya", "Organisation administrator (Riverside)",
                (("riverside", "org_admin"),)),
    DemoAccount("volunteer", "volunteer.priya@example.org", "Priya", "Field volunteer (Riverside)",
                (("riverside", "field_volunteer"),), locale="ta"),
    DemoAccount("vet", "vet.arun@example.org", "Dr Arun", "Veterinary reviewer (Riverside)",
                (("riverside", "veterinary_reviewer"),), vet_approval_in=("riverside",)),
    DemoAccount("coordinator", "coordinator.meena@example.org", "Meena",
                "Programme coordinator (Riverside); field volunteer (Hillview)",
                (("riverside", "programme_coordinator"), ("hillview", "field_volunteer"))),
    DemoAccount("vet_pending", "vet.joseph@example.org", "Dr Joseph",
                "Veterinary reviewer role but professional approval NOT granted (Riverside)",
                (("riverside", "veterinary_reviewer"),)),
    DemoAccount("hill_volunteer", "volunteer.ravi@example.org", "Ravi", "Field volunteer (Hillview)",
                (("hillview", "field_volunteer"),), locale="hi"),
    DemoAccount("hill_vet", "vet.sana@example.org", "Dr Sana", "Veterinary reviewer (Hillview)",
                (("hillview", "veterinary_reviewer"),), vet_approval_in=("hillview",)),
    DemoAccount("hill_admin", "admin.farhan@example.org", "Farhan", "Organisation administrator (Hillview)",
                (("hillview", "org_admin"),)),
    # Pet vaccination reminders (fictional clinics)
    DemoAccount("owner", "owner.neha@example.org", "Neha", "Pet owner — 3 demo pets at Lotus Pet Clinic",
                (("lotus", "resident"),)),
    DemoAccount("clinic_vet", "vet.kiran@example.org", "Dr Kiran", "Clinic vet (Lotus Pet Clinic)",
                (("lotus", "veterinary_reviewer"),), vet_approval_in=("lotus",)),
    DemoAccount("lotus_admin", "clinic.asha@example.org", "Asha", "Clinic manager (Lotus Pet Clinic)",
                (("lotus", "org_admin"),)),
    DemoAccount("banyan_admin", "clinic.vikram@example.org", "Vikram", "Clinic manager (Banyan Veterinary Centre)",
                (("banyan", "org_admin"),)),
)
