"""'This pet bit someone' instant check.

First aid always comes first on every page (web). This module handles what follows: the bite report from the pet's
public card, the observation period (10 days for dogs and cats — WHO, 2018, pending clinical review), daily check-ins
by the owner (and examinations recorded by the vet), the reporter's private tracking link and doctor links.

Safety rules (tested): nothing here says or implies that treatment can be skipped, and a day without an update is shown
as "No update" — never assumed normal. Privacy: owners never see the reporter's contact unless the reporter chose to
share it; reporters and doctors never see anything about the owner.
"""

import hashlib
import secrets
from datetime import date, datetime, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import text

from pawguard_api.auth import Principal
from pawguard_api.capabilities import Cap
from pawguard_api.db import public_tx
from pawguard_api.deps import OrgContext
from pawguard_api.domain import petcare
from pawguard_api.domain.common import record_audit
from pawguard_api.errors import ApiError, Conflict, Forbidden, NotFound
from pawguard_api.integrations import cose, notify
from pawguard_api.logging import get_logger
from pawguard_api.settings import get_settings

log = get_logger(__name__)
REF_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
STATE_WORDS = {"normal": "normal", "not_eating": "not eating", "unusual_behaviour": "unusual behaviour",
               "missing": "missing", "died": "died", "other": "other change"}


# ---- days and timeline ---------------------------------------------------------------------------------------------

def local_today(tz: str, now: datetime | None = None, offset_days: int = 0) -> date:
    """Today's date where the clinic is (date only), plus the demo-clock offset."""
    moment = now or datetime.now(ZoneInfo("UTC"))
    return moment.astimezone(ZoneInfo(tz)).date() + timedelta(days=offset_days)


def day_of(bite_date: date, today: date) -> int:
    """0 = the day of the bite; observation day N is bite_date + N days (a bite at 11:30 pm still counts as that
    day, and month or year boundaries need no special handling with date arithmetic)."""
    return (today - bite_date).days


def observation(bite_date: date, length_days: int, status: str, policy_note: str, checkins: list[dict[str, Any]],
                today: date) -> dict[str, Any]:
    current = day_of(bite_date, today)
    by_day: dict[int, dict[str, str]] = {}
    for c in checkins:
        by_day.setdefault(int(c["day"]), {})[str(c["source"])] = str(c["state"])
    timeline, missed, urgent = [], 0, False
    for d in range(1, min(current, length_days) + 1):
        owner, vet = by_day.get(d, {}).get("owner"), by_day.get(d, {}).get("vet")
        states = [s for s in (owner, vet) if s]
        if any(s != "normal" for s in states):
            day_status, urgent = "change", True
        elif states:
            day_status = "normal"
        elif d == current:
            day_status = "awaiting"  # today, no update yet
        else:
            day_status, missed = "no_update", missed + 1
        timeline.append({"day": d, "date": bite_date + timedelta(days=d), "status": day_status,
                         "owner_state": owner, "vet_state": vet})
    ended = current > length_days
    if ended and status == "active":  # the closing job may not have run yet; show the same outcome it will record
        status = "change_reported" if urgent else ("completed_with_gaps" if missed else "completed")
    return {"bite_date": bite_date, "length_days": length_days, "status": status, "policy_note": policy_note,
            "current_day": current, "ended": ended, "timeline": timeline, "urgent": urgent, "missed_days": missed}


# ---- tokens ------------------------------------------------------------------------------------------------------

def _token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _reference() -> str:
    pick = lambda n: "".join(secrets.choice(REF_ALPHABET) for _ in range(n))  # noqa: E731
    return f"BR-{pick(4)}-{pick(4)}"


def client_hash(ip: str | None) -> str:
    return hashlib.sha256(f"pawguard-bite:{ip or 'unknown'}".encode()).hexdigest()


# ---- public (no account) -----------------------------------------------------------------------------------------

def bite_pet(card_token: str) -> dict[str, Any]:
    if not (32 <= len(card_token) <= 100):
        raise NotFound("Card not found.", code="card_not_found")
    with public_tx() as db:
        data = db.execute(text("select app.public_bite_pet(:t)"), {"t": card_token}).scalar()
    if not data:
        raise NotFound("Card not found.", code="card_not_found")
    return dict(data)


def create_report(card_token: str, body: dict[str, Any], ip: str | None) -> dict[str, Any]:
    """Create the report (and observation period). Returns the private tracking token once; only its hash is stored.
    The reporter's email is stored only with consent to updates, sealed with the master key."""
    s = get_settings()
    if not (32 <= len(card_token) <= 100):
        raise NotFound("Card not found.", code="card_not_found")
    reference, token = _reference(), _token()
    email = body.get("contact_email") if body.get("consent_updates") else None
    sealed = None
    if email:
        try:
            sealed = cose.seal(email.encode("utf-8"), reference, s)
        except cose.SigningUnavailable:
            sealed = None  # the report still works; no update emails
    with public_tx() as db:
        out = db.execute(text("""select app.public_create_bite_report(:t, :ref, :d, :tm, :b, :area, :note, :c, :ck,
                                 :cu, :cs, :client, :h)"""),
                         {"t": card_token, "ref": reference, "d": body["bite_date"], "tm": body.get("bite_time"),
                          "b": body["bitten"], "area": (body.get("area") or "").strip(),
                          "note": (body.get("note") or "").strip(), "c": sealed, "ck": "email" if sealed else None,
                          "cu": bool(sealed), "cs": bool(body.get("consent_share_with_owner")) and bool(sealed),
                          "client": client_hash(ip), "h": token_hash(token)}).scalar()
    err = (out or {}).get("error")
    if err == "not_found":
        raise NotFound("Card not found.", code="card_not_found")
    if err == "bad_date":
        raise ApiError("The date must be today or within the last 30 days.", code="bad_date", status_code=422)
    if err == "rate_limited":
        raise ApiError("Too many reports were sent just now. If someone was bitten, get medical care first; you can "
                       "report later.", code="rate_limited", status_code=429)
    return {"reference": reference, "token": token, "duplicate": bool(out["duplicate"]), "contact": email if sealed
            else None, "period_id": out["period_id"]}


def _rabies(data: Any) -> dict[str, Any] | None:
    return dict(data) if data else None


def share_view(token: str) -> dict[str, Any]:
    if not (32 <= len(token) <= 100):
        raise NotFound("Link not found.", code="link_not_found")
    with public_tx() as db:
        v = db.execute(text("select app.share_view(:h)"), {"h": token_hash(token)}).scalar()
    if not v:
        raise NotFound("This link has expired or was turned off.", code="link_not_found")
    today = local_today(v["timezone"])
    period = v["period"]
    obs = observation(date.fromisoformat(period["bite_date"]), int(period["length_days"]), period["status"],
                      period["policy_note"], v["checkins"], today)
    return {"purpose": v["purpose"], "reference": v["reference"], "bite_date": v["bite_date"],
            "bite_time": v["bite_time"], "bitten": v["bitten"], "pet_name": v["pet_name"], "species": v["species"],
            "clinic_name": v["clinic_name"], "clinic_email": v["clinic_email"], "clinic_phone": v["clinic_phone"],
            "is_demo": v["is_demo"], "expires_at": v["expires_at"], "observation": obs,
            "rabies": _rabies(v["rabies"]), "doctor_links": v.get("doctor_links")}


def new_doctor_link(reporter_token: str) -> dict[str, Any]:
    token = _token()
    with public_tx() as db:
        ok = db.execute(text("select app.share_create_doctor_link(:r, :d)"),
                        {"r": token_hash(reporter_token), "d": token_hash(token)}).scalar()
    if not ok:
        raise ApiError("A doctor link could not be made (the link expired, or 5 doctor links are already active).",
                       code="doctor_link_refused", status_code=409)
    return {"path": f"/bite/{token}", "expires_at": datetime.now(ZoneInfo("UTC")) + timedelta(days=30)}


def revoke_doctor_links(reporter_token: str) -> int:
    with public_tx() as db:
        return int(db.execute(text("select app.share_revoke_doctor_links(:r)"),
                              {"r": token_hash(reporter_token)}).scalar() or 0)


# ---- reporter emails (only with consent; never the owner's details) -------------------------------------------------

def _reporter_emails(db: Any, period_id: Any) -> list[tuple[str, str]]:
    s = get_settings()
    out = []
    for r in db.execute(text("select * from app.bite_update_contacts(:p)"), {"p": period_id}):
        try:
            out.append((r.reference, cose.unseal_bytes(bytes(r.contact_sealed), r.reference, s).decode("utf-8")))
        except Exception as exc:  # unreadable or no master key: skip that contact
            log.warning("bite_contact_unreadable", error=type(exc).__name__)
    return out


def send_reporter_emails(contacts: list[tuple[str, str]], subject: str, body: str) -> int:
    s = get_settings()
    sent = 0
    for reference, email in contacts:
        try:
            notify.send_email(s, email, notify.Message(f"{subject} ({reference})", body, body[:150], ""))
            sent += 1
        except notify.ProviderError as err:
            log.warning("bite_reporter_email_failed", code=err.code)
    return sent


def tracking_email(reference: str, link: str, pet: str, bite_date: date) -> tuple[str, str]:
    return (f"Your PawGuard bite report {reference}",
            "If you have not done so yet: wash the wound with soap and running water for 15 minutes and see a doctor "
            "today, whatever the pet's vaccination status. Your doctor decides your treatment.\n\n"
            f"You reported a bite by {pet} on {bite_date:%d %b %Y}. Follow the pet's observation here (keep this link "
            f"private; it is the only way to open your report):\n{link}\n\n— PawGuard 360")


# ---- owner -------------------------------------------------------------------------------------------------------

_CASES = f"""
select op.*, coalesce(a.nickname, a.reference_code) as pet_name, a.sex, o.name as clinic_name,
       o.contact_email as clinic_email, o.contact_phone as clinic_phone, o.timezone,
       coalesce(dc.offset_days, 0) as offset_days
  from app.observation_periods op
  join app.animals a on a.id = op.animal_id
  join app.organisations o on o.id = op.org_id
  left join app.demo_clock dc on dc.org_id = op.org_id
  join app.animal_caregivers c on c.animal_id = op.animal_id and {petcare.LIVE_OWNER}
"""  # noqa: S608 - fixed SQL; LIVE_OWNER is a constant that uses bound parameters


def _checkins(db: Any, period_id: Any) -> list[dict[str, Any]]:
    return [{"day": r.day_number, "state": r.state, "source": r.source} for r in db.execute(text(
        "select day_number, state, source from app.observation_checkins where period_id = :p"), {"p": period_id})]


def _owner_case(db: Any, row: Any) -> dict[str, Any]:
    s = get_settings()
    today = local_today(row.timezone, offset_days=row.offset_days)
    obs = observation(row.bite_date, row.length_days, row.status, row.policy_note, _checkins(db, row.id), today)
    reports = []
    for r in db.execute(text("""select reference, bite_time, bitten, area, status, duplicate_of, contact_sealed,
                                       consent_share_with_owner from app.bite_reports where period_id = :p
                                order by created_at"""), {"p": row.id}):
        contact = None
        if r.consent_share_with_owner and r.contact_sealed:
            try:
                contact = cose.unseal_bytes(bytes(r.contact_sealed), r.reference, s).decode("utf-8")
            except Exception:
                contact = None
        reports.append({"reference": r.reference, "bite_time": r.bite_time, "bitten": r.bitten, "area": r.area,
                        "status": r.status, "possible_duplicate": r.duplicate_of is not None, "contact": contact})
    today_needed = not obs["ended"] and obs["current_day"] >= 1 and not any(
        t["day"] == obs["current_day"] and t["owner_state"] for t in obs["timeline"])
    return {"period_id": row.id, "animal_id": row.animal_id, "pet_name": row.pet_name,
            "clinic_name": row.clinic_name, "clinic_email": row.clinic_email, "clinic_phone": row.clinic_phone,
            "observation": obs, "reports": reports, "disputed": any(r["status"] == "disputed" for r in reports),
            "today_needed": today_needed}


def my_cases(p: Principal, request_id: str | None = None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for ctx in petcare.owner_contexts(p, request_id):
        with ctx.tx() as db:
            rows = db.execute(text(_CASES + " order by op.bite_date desc"), {"u": ctx.user_id}).all()
            out.extend(_owner_case(db, r) for r in rows)
    return out


def _owned_period(p: Principal, period_id: UUID, request_id: str | None) -> tuple[OrgContext, Any]:
    for ctx in petcare.owner_contexts(p, request_id):
        with ctx.tx() as db:
            row = db.execute(text(_CASES + " where op.id = :p"), {"u": ctx.user_id, "p": period_id}).first()
            if row:
                return ctx, row
    raise NotFound("Bite report not found.", code="bite_case_not_found")


def my_case(p: Principal, period_id: UUID, request_id: str | None = None) -> dict[str, Any]:
    ctx, _ = _owned_period(p, period_id, request_id)
    with ctx.tx() as db:
        row = db.execute(text(_CASES + " where op.id = :p"), {"u": ctx.user_id, "p": period_id}).one()
        return _owner_case(db, row)


def _record_checkin(db: Any, ctx: OrgContext, row: Any, state: str, note: str | None, source: str) -> int:
    today = local_today(row.timezone, offset_days=row.offset_days)
    day = day_of(row.bite_date, today)
    if day < 1 or day > row.length_days:
        raise Conflict(f"Daily updates are for days 1 to {row.length_days} after the bite.", code="not_in_period",
                       details={"day": day})
    db.execute(text("""insert into app.observation_checkins (org_id, period_id, day_number, checkin_date, state, note,
                                                            source, recorded_by)
                       values (:o, :p, :d, :dt, :s, :n, :src, :u)
                       on conflict (period_id, day_number, source) do update
                         set state = excluded.state, note = excluded.note, recorded_by = excluded.recorded_by,
                             updated_at = now()"""),
               {"o": row.org_id, "p": row.id, "d": day, "dt": today, "s": state, "n": (note or "").strip() or None,
                "src": source, "u": ctx.user_id})
    record_audit(db, ctx, f"bite.checkin_{source}", "observation_period", row.id, {"day": day, "state": state})
    return day


Emails = tuple[list[tuple[str, str]], str, str]  # (reporter contacts, subject, body) — sent after the commit


def checkin(p: Principal, period_id: UUID, state: str, note: str | None, request_id: str | None = None
            ) -> tuple[dict[str, Any], Emails | None]:
    """Owner's daily update. A change (anything but normal) also returns the reporters to tell right away."""
    ctx, _ = _owned_period(p, period_id, request_id)
    with ctx.tx() as db:
        row = db.execute(text(_CASES + " where op.id = :p"), {"u": ctx.user_id, "p": period_id}).one()
        day = _record_checkin(db, ctx, row, state, note, "owner")
        contacts = _reporter_emails(db, row.id) if state != "normal" else []
        case = _owner_case(db, row)
    return case, ((contacts, *urgent_email(row.pet_name, day, state)) if contacts else None)


def urgent_email(pet: str, day: int, state: str) -> tuple[str, str]:
    return ("Important: the owner reported a change",
            f"The owner of {pet} reported a change on observation day {day}: {STATE_WORDS.get(state, state)}.\n\n"
            "Tell your doctor right away. Open the private link we sent you earlier to see the details.\n\n"
            "— PawGuard 360")


def dispute(p: Principal, period_id: UUID, reason: str, request_id: str | None = None) -> dict[str, Any]:
    """The owner disputes the report. Observation continues (a dispute never stops the daily updates); the clinic sees
    the flag."""
    ctx, _ = _owned_period(p, period_id, request_id)
    with ctx.tx() as db:
        db.execute(text("""update app.bite_reports set status = 'disputed', dispute_reason = :r, disputed_at = now()
                           where period_id = :p and status <> 'withdrawn'"""), {"p": period_id, "r": reason.strip()})
        record_audit(db, ctx, "bite.disputed", "observation_period", period_id, {}, reason=reason.strip())
        row = db.execute(text(_CASES + " where op.id = :p"), {"u": ctx.user_id, "p": period_id}).one()
        return _owner_case(db, row)


# ---- clinic ------------------------------------------------------------------------------------------------------

_CLINIC = """
select op.*, coalesce(a.nickname, a.reference_code) as pet_name, o.timezone, coalesce(dc.offset_days, 0) as offset_days,
       (select count(*) from app.bite_reports r where r.period_id = op.id) as reports,
       exists (select 1 from app.bite_reports r where r.period_id = op.id and r.duplicate_of is not null)
         as possible_duplicate,
       exists (select 1 from app.bite_reports r where r.period_id = op.id and r.status = 'disputed') as disputed,
       (select max(c.checkin_date) from app.observation_checkins c where c.period_id = op.id) as last_update
  from app.observation_periods op
  join app.animals a on a.id = op.animal_id
  join app.organisations o on o.id = op.org_id
  left join app.demo_clock dc on dc.org_id = op.org_id
"""


def _staff(ctx: OrgContext) -> None:
    if not (ctx.can(Cap.ANIMAL_READ) or ctx.can(Cap.VACCINATION_REVIEW)):
        raise Forbidden("Clinic staff only.", code="staff_only")


def _clinic_case(db: Any, row: Any) -> dict[str, Any]:
    today = local_today(row.timezone, offset_days=row.offset_days)
    return {"period_id": row.id, "pet_name": row.pet_name,
            "observation": observation(row.bite_date, row.length_days, row.status, row.policy_note,
                                       _checkins(db, row.id), today),
            "reports": row.reports, "possible_duplicate": row.possible_duplicate, "disputed": row.disputed,
            "last_update": row.last_update}


def clinic_cases(db: Any, ctx: OrgContext) -> list[dict[str, Any]]:
    """Open cases and those closed in the last 14 days, most urgent first (change reported, missed days, disputes)."""
    _staff(ctx)
    rows = db.execute(text(_CLINIC + " where op.status = 'active' or op.closed_at > now() - interval '14 days'"
                                      " order by op.bite_date desc limit 50")).all()
    cases = [_clinic_case(db, r) for r in rows]
    return sorted(cases, key=lambda c: (not c["observation"]["urgent"], c["observation"]["missed_days"] == 0,
                                        not c["disputed"]))


def vet_exam(db: Any, ctx: OrgContext, period_id: UUID, state: str, note: str | None
             ) -> tuple[dict[str, Any], Emails | None]:
    """An examination recorded by the clinic's vet (shown as "Vet-recorded")."""
    ctx.require(Cap.VACCINATION_REVIEW)
    row = db.execute(text(_CLINIC + " where op.id = :p"), {"p": period_id}).first()
    if row is None:
        raise NotFound("Bite report not found.", code="bite_case_not_found")
    day = _record_checkin(db, ctx, row, state, note, "vet")
    contacts = _reporter_emails(db, row.id) if state != "normal" else []
    case = _clinic_case(db, db.execute(text(_CLINIC + " where op.id = :p"), {"p": period_id}).one())
    return case, ((contacts, *urgent_email(row.pet_name, day, state)) if contacts else None)


# ---- closing (dispatcher) ----------------------------------------------------------------------------------------

CLOSING = {
    "completed": "The observation period was completed — the owner reported no changes.",
    "completed_with_gaps": "The observation period ended with days without an update. The clinic has been asked to "
                           "follow up.",
    "change_reported": "A change was reported during the observation period. The clinic has been asked to follow up.",
}


def close_and_notify(conn: Any) -> int:
    """End periods whose last day has passed; tell owners (their channels) and consenting reporters (email)."""
    closed = conn.execute(text("select * from app.close_due_observations()")).all()
    for row in closed:
        conn.execute(text("select app.queue_bite_notice(:p, 'bite_closed')"), {"p": row.period_id})
        contacts = _reporter_emails(conn, row.period_id)
        if contacts:
            send_reporter_emails(contacts, "Observation period ended",
                                 CLOSING[row.status] + "\n\nThis does not change anything your doctor advised. Keep "
                                 "following your doctor's advice.\n\n— PawGuard 360")
    return len(closed)
