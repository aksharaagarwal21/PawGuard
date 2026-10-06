"""Lost pets: owner reports, and private finder ↔ owner conversations started from the pet's QR card.

Owners act through their clinic membership (row security). Finders need no account: they get a private conversation
link (random token; only its hash is stored). The owner's identity and contact details are never sent to finders.
Public writes go through security-definer functions with per-pet and per-conversation limits, plus a global cap here
(the API sees every public request through the web gateway, so per-address limits wouldn't mean anything).
"""

import hashlib
import secrets
import time
from collections import deque
from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from pawguard_api.auth import Principal
from pawguard_api.db import public_tx
from pawguard_api.domain import petcare
from pawguard_api.domain.common import record_audit
from pawguard_api.errors import ApiError, NotFound, Unprocessable

GLOBAL_PUBLIC_PER_HOUR = 300
_MARK_READ = """update app.lost_messages set read_by_owner_at = now()
                where thread_id = :t and sender = 'finder' and read_by_owner_at is null"""
_public: deque[float] = deque()


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _public_limit() -> None:
    now = time.monotonic()
    while _public and now - _public[0] > 3600:
        _public.popleft()
    if len(_public) >= GLOBAL_PUBLIC_PER_HOUR:
        raise ApiError("Too many messages right now — try again later.", code="rate_limited", status_code=429)
    _public.append(now)


def _clean(body: str) -> str:
    body = body.replace("\r", "").strip()
    if not body:
        raise Unprocessable("Write a message.", code="empty_message")
    return body[:500]


# ---- owner -------------------------------------------------------------------------------------------------------

def report_lost(p: Principal, animal_id: UUID, last_seen_on: date | None, area: str | None, note: str | None) -> None:
    ctx = petcare.owned_context(p, animal_id)
    with ctx.tx() as db:
        db.execute(text("""
            insert into app.lost_reports (org_id, animal_id, owner_user_id, last_seen_on, area_text, note)
            values (:o, :a, :u, :d, :ar, :n)
            on conflict (animal_id) where state = 'open' do update set last_seen_on = excluded.last_seen_on,
              area_text = excluded.area_text, note = excluded.note"""),
            {"o": ctx.org_id, "a": animal_id, "u": ctx.user_id, "d": last_seen_on, "ar": (area or None),
             "n": (note or None)})
        record_audit(db, ctx, "pet.reported_lost", "animal", animal_id, {})


def mark_found(p: Principal, animal_id: UUID) -> None:
    ctx = petcare.owned_context(p, animal_id)
    with ctx.tx() as db:
        db.execute(text("""update app.lost_reports set state = 'found', closed_at = now()
                           where animal_id = :a and state = 'open'"""), {"a": animal_id})
        record_audit(db, ctx, "pet.marked_found", "animal", animal_id, {})


def owner_view(p: Principal) -> list[dict[str, Any]]:
    """Every lost report on the owner's pets (open first), with conversations and messages."""
    out: list[dict[str, Any]] = []
    for ctx in petcare.owner_contexts(p):
        with ctx.tx() as db:
            reports = db.execute(text("""
                select r.*, coalesce(a.nickname, a.reference_code) as pet_name from app.lost_reports r
                join app.animals a on a.id = r.animal_id
                join app.animal_caregivers c on c.animal_id = a.id and c.relationship = 'owner'
                     and c.linked_user_id = :u and (c.valid_to is null or c.valid_to > current_date)
                order by (r.state = 'open') desc, r.created_at desc limit 20"""), {"u": ctx.user_id}).all()
            for r in reports:
                threads = []
                for t in db.execute(text("select * from app.lost_threads where report_id = :r "
                                         "order by last_message_at desc"), {"r": r.id}):
                    msgs = db.execute(text("""select sender, body, created_at, read_by_owner_at from app.lost_messages
                                              where thread_id = :t order by created_at"""), {"t": t.id}).all()
                    threads.append({"id": t.id, "finder_contact": t.finder_contact, "created_at": t.created_at,
                                    "unread": sum(1 for m in msgs if m.sender == "finder" and not m.read_by_owner_at),
                                    "messages": [{"sender": m.sender, "body": m.body, "created_at": m.created_at}
                                                 for m in msgs]})
                out.append({"report_id": r.id, "pet_id": r.animal_id, "pet_name": r.pet_name, "state": r.state,
                            "last_seen_on": r.last_seen_on, "area_text": r.area_text, "note": r.note,
                            "created_at": r.created_at, "threads": threads})
    return out


def _owned_thread(p: Principal, thread_id: UUID) -> tuple[Any, Any]:
    for ctx in petcare.owner_contexts(p):
        with ctx.tx() as db:
            t = db.execute(text("""select t.id, t.animal_id, r.state from app.lost_threads t
                                   join app.lost_reports r on r.id = t.report_id where t.id = :t"""),
                           {"t": thread_id}).one_or_none()
            if t is not None and petcare.owns(db, ctx.user_id, t.animal_id):
                return ctx, t
    raise NotFound("Conversation not found.", code="thread_not_found")


def owner_reply(p: Principal, thread_id: UUID, body: str) -> None:
    ctx, t = _owned_thread(p, thread_id)
    if t.state != "open":
        raise ApiError("This pet is no longer reported lost.", code="report_closed", status_code=409)
    with ctx.tx() as db:
        db.execute(text("insert into app.lost_messages (org_id, thread_id, sender, body) values (:o, :t, 'owner', :b)"),
                   {"o": ctx.org_id, "t": thread_id, "b": _clean(body)})
        db.execute(text("update app.lost_threads set last_message_at = now() where id = :t"), {"t": thread_id})
        db.execute(text(_MARK_READ), {"t": thread_id})


def mark_read(p: Principal, thread_id: UUID) -> None:
    ctx, _ = _owned_thread(p, thread_id)
    with ctx.tx() as db:
        db.execute(text(_MARK_READ), {"t": thread_id})


# ---- public (finder) ---------------------------------------------------------------------------------------------

def lost_status(card_token: str) -> dict[str, Any]:
    with public_tx() as db:
        row = db.execute(text("select * from app.public_lost_status(:t)"), {"t": card_token}).one_or_none()
    if row is None:
        raise NotFound("Card not found.", code="card_not_found")
    return {"lost": bool(row.lost), "last_seen_on": row.last_seen_on, "area_text": row.area_text}


def start(card_token: str, body: str, contact: str | None) -> str:
    _public_limit()
    token = secrets.token_urlsafe(32)
    try:
        with public_tx() as db:
            thread = db.execute(text("select app.finder_start_thread(:c, :h, :b, :ct)"),
                                {"c": card_token, "h": _hash(token), "b": _clean(body),
                                 "ct": (contact or "").strip()[:120]}).scalar()
    except DBAPIError as exc:
        raise ApiError("Many people have written about this pet today — try again tomorrow.", code="rate_limited",
                       status_code=429) from exc
    if thread is None:
        raise NotFound("This pet isn't reported lost.", code="not_lost")
    return token


def thread(token: str) -> dict[str, Any]:
    if not (20 <= len(token) <= 100):
        raise NotFound("Conversation not found.", code="thread_not_found")
    with public_tx() as db:
        data = db.execute(text("select app.finder_thread(:h)"), {"h": _hash(token)}).scalar()
    if not data:
        raise NotFound("Conversation not found.", code="thread_not_found")
    return dict(data)


def post(token: str, body: str) -> None:
    _public_limit()
    try:
        with public_tx() as db:
            ok = db.execute(text("select app.finder_post(:h, :b)"), {"h": _hash(token), "b": _clean(body)}).scalar()
    except DBAPIError as exc:
        raise ApiError("Too many messages today — try again tomorrow.", code="rate_limited", status_code=429) from exc
    if not ok:
        raise ApiError("This conversation is closed — the pet is no longer reported lost.", code="report_closed",
                       status_code=409)
