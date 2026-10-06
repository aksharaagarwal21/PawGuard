"""Pet vaccination status and reminder rules.

- The app never decides treatment. A next due date comes from the vet (``next_review_source = 'vet'``) or from a
  product's *demo* schedule template (``'demo_template'``, shown as "Demo template — confirm with your vet").
- States stay distinct: verified by a vet, entered by the owner (unverified), no verified record. "No verified
  record" is never shown as unvaccinated or overdue.
- Dates are calendar dates in the organisation's timezone (Asia/Kolkata for the demo clinics). A demo organisation
  may add a day offset (``demo_clock``) that moves "today" for status and reminders only; stored dates never change.
- Reminders are in-app only. Email/SMS texts are previews; nothing is sent.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

from pawguard_api.pet_contracts import PetStatusOut

DUE_SOON_DAYS = 14
REMINDER_OFFSETS = (("due_in_14", -14), ("due_in_7", -7), ("due_in_1", -1), ("overdue", 1))


@dataclass(frozen=True)
class Record:
    state: str
    vaccine: str
    administered_on: date | None
    next_due_on: date | None = None
    next_due_source: str | None = None


def latest_verified(records: Iterable[Any]) -> dict[str, Any]:
    """Most recent verified record per vaccine (later administration wins)."""
    latest: dict[str, Any] = {}
    for r in sorted((r for r in records if r.state == "verified"), key=lambda r: r.administered_on or date.min):
        latest[r.vaccine] = r
    return latest


def pet_status(records: Iterable[Record], today: date) -> PetStatusOut:
    """One status per pet.
    - no records (ignoring rejected, superseded and drafts) → no_verified_record
    - records exist but none verified → unverified_record
    - otherwise the earliest next due date among each vaccine's latest verified record decides:
      before today → overdue; today to 14 days ahead → due_soon; later, or no due date → up_to_date."""
    live = [r for r in records if r.state not in ("rejected", "superseded", "draft")]
    if not live:
        return PetStatusOut(status="no_verified_record")
    latest = latest_verified(live)
    if not latest:
        return PetStatusOut(status="unverified_record")
    dues = [r for r in latest.values() if r.next_due_on is not None]
    if not dues:
        return PetStatusOut(status="up_to_date")
    r = min(dues, key=lambda r: r.next_due_on)
    days = (r.next_due_on - today).days
    status = "overdue" if days < 0 else "due_soon" if days <= DUE_SOON_DAYS else "up_to_date"
    return PetStatusOut(status=status, next_due_on=r.next_due_on, next_due_source=r.next_due_source,
                        vaccine=r.vaccine, days_until_due=days)


def reminder_plan(due_on: date) -> list[tuple[str, date]]:
    """Reminder kinds and the day each appears: 14, 7 and 1 day before the due date, and the day after it."""
    return [(kind, due_on + timedelta(days=off)) for kind, off in REMINDER_OFFSETS]


def current_reminder(rows: Iterable[Any], today: date) -> Any | None:
    """Of the pending reminders for one due date, the one to show today (the latest that has appeared), unless the
    owner snoozed it."""
    visible = [r for r in rows if r.state == "pending" and r.show_on <= today
               and (r.snoozed_until is None or r.snoozed_until <= today)]
    return max(visible, key=lambda r: r.show_on) if visible else None


def _ics_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(line: str) -> str:
    """RFC 5545 line folding: at most 75 octets per line; continuation lines start with a space."""
    out: list[str] = []
    cur = b""
    for ch in line:
        b = ch.encode("utf-8")
        if len(cur) + len(b) > (75 if not out else 74):
            out.append(cur.decode("utf-8"))
            cur = b""
        cur += b
    out.append(cur.decode("utf-8"))
    return "\r\n ".join(out)


def ics_event(uid: str, pet: str, vaccine: str, due_on: date, clinic: str, now: datetime | None = None) -> str:
    """RFC 5545 calendar with one all-day event on the due date (VALUE=DATE: no timezone conversion)."""
    stamp = (now or datetime.now(UTC)).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//PawGuard 360//Pet vaccination reminders//EN",
        "CALSCALE:GREGORIAN", "METHOD:PUBLISH", "BEGIN:VEVENT", f"UID:{uid}@pawguard360.demo", f"DTSTAMP:{stamp}",
        f"DTSTART;VALUE=DATE:{due_on:%Y%m%d}", f"DTEND;VALUE=DATE:{due_on + timedelta(days=1):%Y%m%d}",
        f"SUMMARY:{_ics_escape(f'Vaccination due: {pet} ({vaccine})')}",
        "DESCRIPTION:" + _ics_escape(f"Reminder from PawGuard 360 (demo) for {clinic}. "
                                     "Please confirm the date with your vet."),
        "TRANSP:TRANSPARENT", "END:VEVENT", "END:VCALENDAR",
    ]
    return "\r\n".join(_fold(x) for x in lines) + "\r\n"


def preview_texts(pet: str, vaccine: str, due_on: date, clinic: str, today: date) -> dict[str, str]:
    """What an email or SMS would say. Nothing is sent. Minimal detail: pet name, vaccine and date."""
    when = f"{due_on.day} {due_on:%b %Y}"
    verb = "was due on" if due_on < today else "is due on"
    return {
        "email_subject": f"Reminder: {pet}'s {vaccine} vaccination {verb} {when}",
        "email_body": (f"Hello,\n\nThis is a reminder from {clinic}: {pet}'s {vaccine} vaccination {verb} {when}.\n"
                       "Please contact your vet to book a visit.\n\n— PawGuard 360 (demo)"),
        "sms": f"PawGuard: {pet}'s {vaccine} vaccination {verb} {when}. Please contact {clinic}.",
    }


def org_today(db: Session | Connection, org_id: UUID, tz: str) -> tuple[date, int]:
    """Calendar 'today' in the organisation's timezone plus its demo offset (demo organisations only)."""
    offset = db.execute(text("select offset_days from app.demo_clock where org_id = :o"), {"o": org_id}).scalar() or 0
    return datetime.now(ZoneInfo(tz)).date() + timedelta(days=int(offset)), int(offset)


_EVENTS = """
select e.id, e.animal_id, e.state, e.source_type, e.administered_on, e.next_review_on, e.next_review_source,
       e.administered_by_name, e.submitted_at, e.product_id, coalesce(p.name, e.product_text, 'Vaccine') as vaccine,
       (select count(*) from app.vaccination_evidence v where v.event_id = e.id) as certificates,
       (select r.reason from app.vaccination_reviews r where r.event_id = e.id order by r.created_at desc limit 1)
         as review_reason
from app.animal_vaccination_events e left join app.vaccine_products p on p.id = e.product_id
where e.animal_id = any(cast(:ids as uuid[]))
order by e.administered_on desc nulls last, e.created_at desc
"""


def events_by_animal(db: Session | Connection, animal_ids: list[UUID]) -> dict[UUID, list[Any]]:
    animal_ids = [UUID(str(i)) for i in animal_ids]
    out: dict[UUID, list[Any]] = {i: [] for i in animal_ids}
    if animal_ids:
        for r in db.execute(text(_EVENTS), {"ids": [str(i) for i in animal_ids]}):
            out[r.animal_id].append(r)
    return out


def status_for(rows: list[Any], today: date) -> PetStatusOut:
    return pet_status([Record(r.state, r.vaccine, r.administered_on, r.next_review_on, r.next_review_source)
                       for r in rows], today)


def schedule_reminders(db: Session | Connection, org_id: UUID, animal_id: UUID) -> dict[str, int]:
    """Make one pet's pending reminders match its current verified due dates. Idempotent. Call it in the same
    transaction as any change to verified records or due dates; reminders for an old due date are cancelled."""
    owner = db.execute(text("""select linked_user_id from app.animal_caregivers where animal_id = :a
                               and relationship = 'owner' and linked_user_id is not null
                               and (valid_to is null or valid_to > current_date) order by created_at limit 1"""),
                       {"a": animal_id}).scalar()
    wanted: dict[tuple[str, date, str], tuple[date, UUID]] = {}
    if owner is not None:
        for vaccine, r in latest_verified(events_by_animal(db, [animal_id])[UUID(str(animal_id))]).items():
            if r.next_review_on is not None:
                for kind, show_on in reminder_plan(r.next_review_on):
                    wanted[(vaccine, r.next_review_on, kind)] = (show_on, r.id)
    existing = db.execute(text("""select id, vaccine_name, due_on, kind, state from app.vaccination_reminders
                                  where animal_id = :a and state <> 'cancelled'"""), {"a": animal_id}).all()
    have = {(e.vaccine_name, e.due_on, e.kind) for e in existing}
    cancelled = created = 0
    for e in existing:
        if e.state == "pending" and (e.vaccine_name, e.due_on, e.kind) not in wanted:
            db.execute(text("update app.vaccination_reminders set state = 'cancelled' where id = :id"), {"id": e.id})
            cancelled += 1
    for (vaccine, due, kind), (show_on, event_id) in wanted.items():
        if (vaccine, due, kind) in have:
            continue
        created += db.execute(text("""
            insert into app.vaccination_reminders (org_id, animal_id, owner_user_id, source_event_id, vaccine_name,
              due_on, kind, show_on)
            values (:o, :a, :u, :e, :v, :d, :k, :s) on conflict do nothing"""),
            {"o": org_id, "a": animal_id, "u": owner, "e": event_id, "v": vaccine, "d": due, "k": kind,
             "s": show_on}).rowcount
    return {"created": created, "cancelled": cancelled}


def after_review(db: Session, org_id: UUID, event: Any, outcome: str, vet_due: date | None) -> None:
    """Hook for vaccination review, in the review's transaction.
    Verified: the vet's due date wins; otherwise the product's demo template (if any) fills it in.
    Rejected or correction requested: reminders the owner marked done with this record come back."""
    if outcome == "verified":
        if vet_due is not None:
            event.next_review_on, event.next_review_source = vet_due, "vet"
        elif event.next_review_on is None and event.administered_on is not None and event.product_id is not None:
            interval = db.execute(text("select template_interval_days from app.vaccine_products where id = :p"),
                                  {"p": event.product_id}).scalar()
            if interval:
                event.next_review_on = event.administered_on + timedelta(days=int(interval))
                event.next_review_source = "demo_template"
        db.flush()
    else:
        db.execute(text("""update app.vaccination_reminders set state = 'pending', done_event_id = null
                           where done_event_id = :e and state = 'done'"""), {"e": event.id})
    schedule_reminders(db, org_id, event.animal_id)
