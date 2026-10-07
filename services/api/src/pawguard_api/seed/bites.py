"""Demo bite cases (fictional, labelled demo) for the 'This pet bit someone' walkthrough.

* Bruno: bitten 4 days ago → today is observation day 4; owner updates on days 1 and 3 (normal), day 2 missed
  ("No update"), today still waiting.
* Misty: bitten 3 days ago; day 1 normal, day 2 "unusual behaviour" (urgent banner for the reporter, doctor link and
  clinic).
Each case has a reporter link with a fixed DEMO token (documented in DEMO_GUIDE; fictional data only, refused outside
demo mode like the rest of the seed).
"""

from datetime import datetime, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.engine import Connection

from pawguard_api.domain.bites import token_hash
from pawguard_api.seed.accounts import demo_id

DEMO_REPORTER_TOKENS = {"bruno": "pawguard-demo-reporter-link-bruno-0001",
                        "misty": "pawguard-demo-reporter-link-misty-0002"}
CASES = (  # pet key, reference, days since bite, bitten, [(day, state)]
    ("bruno", "BR-DEMO-0001", 4, "person", [(1, "normal"), (3, "normal")]),
    ("misty", "BR-DEMO-0002", 3, "person", [(1, "normal"), (2, "unusual_behaviour")]),
)


def _ins(c: Connection, table: str, row: dict[str, Any]) -> None:
    cols, vals = ", ".join(row), ", ".join(f":{k}" for k in row)
    c.execute(text(f"insert into app.{table} ({cols}) values ({vals}) on conflict (id) do nothing"), row)  # noqa: S608


def seed_bites(c: Connection, users: dict[str, UUID]) -> dict[str, int]:
    org = demo_id("org", "lotus")
    today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    c.execute(text("update app.organisations set contact_email = coalesce(contact_email, :e) where id = :o"),
              {"o": org, "e": "clinic.lotus@example.org"})
    for key, reference, ago, bitten, checkins in CASES:
        animal = demo_id("animal", f"lotus:{key}")
        period, report = demo_id("observation", key), demo_id("bite_report", key)
        bite_date = today - timedelta(days=ago)
        if c.execute(text("select 1 from app.observation_periods where id = :p"), {"p": period}).scalar():
            continue  # already seeded (idempotent); dates are not moved
        _ins(c, "observation_periods", {"id": period, "org_id": org, "animal_id": animal, "bite_date": bite_date,
                                        "is_demo": True})
        _ins(c, "bite_reports", {"id": report, "org_id": org, "animal_id": animal, "period_id": period,
                                 "reference": reference, "bite_date": bite_date, "bite_time": "18:30",
                                 "bitten": bitten, "area": "Demo area (fictional)",
                                 "note": "Demo data — fictional report.", "status": "under_observation",
                                 "client_hash": "demo", "is_demo": True})
        for day, state in checkins:
            _ins(c, "observation_checkins", {"id": demo_id("checkin", f"{key}:{day}"), "org_id": org,
                                             "period_id": period, "day_number": day,
                                             "checkin_date": bite_date + timedelta(days=day), "state": state,
                                             "note": "Demo update", "source": "owner", "recorded_by": users["owner"]})
        _ins(c, "share_links", {"id": demo_id("share_link", key), "org_id": org, "report_id": report,
                                "purpose": "reporter", "token_hash": token_hash(DEMO_REPORTER_TOKENS[key]),
                                "expires_at": datetime.now(ZoneInfo("UTC")) + timedelta(days=60)})
    return {"bite_cases": len(CASES)}
