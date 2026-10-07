"""Notification settings, test messages and the staff delivery overview.

Channels are opt-in per person. Addresses are entered by the person themselves; in demo organisations messages go
only to the configured test recipients. Staff see delivery states and provider status, never addresses.
"""

import math
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from sqlalchemy import text

from pawguard_api.auth import Principal
from pawguard_api.capabilities import Cap
from pawguard_api.db import user_tx
from pawguard_api.deps import OrgContext
from pawguard_api.domain.common import record_audit
from pawguard_api.errors import ApiError, FieldError, Forbidden, Unprocessable
from pawguard_api.integrations import notify
from pawguard_api.settings import get_settings

Channel = Literal["email", "push", "whatsapp"]
TEST_LIMIT_PER_HOUR = 5
VERIFY_LIMIT_PER_HOUR = 3


def channel_available() -> dict[str, bool]:
    s = get_settings()
    return {"email": notify.email_configured(s),
            "push": notify.push_configured(s),
            "whatsapp": notify.whatsapp_configured(s), "call": notify.call_configured(s)}


def get_prefs(p: Principal) -> dict[str, Any]:
    with user_tx(p.user_id) as db:
        row = db.execute(text("select * from app.notification_preferences where user_id = :u"),
                         {"u": p.user_id}).one_or_none()
        demo = bool(db.execute(text("""select exists (select 1 from app.memberships m join app.organisations o
                                        on o.id = m.org_id where m.user_id = :u and m.status = 'active'
                                        and o.is_demo)"""), {"u": p.user_id}).scalar())
        push_devices = int(db.execute(text("""select count(*) from app.push_subscriptions where user_id = :u
                                               and revoked_at is null"""), {"u": p.user_id}).scalar() or 0)
    s = get_settings()
    return {
        "email_enabled": bool(row and row.email_enabled), "email_address": row.email_address if row else None,
        "email_verified": bool(row and row.email_verified_at),
        "email_pending": bool(row and row.email_address and not row.email_verified_at and row.email_verify_sent_at),
        "push_enabled": bool(row and row.push_enabled), "push_devices": push_devices,
        "whatsapp_enabled": bool(row and row.whatsapp_enabled), "whatsapp_number": row.whatsapp_number if row else None,
        "call_enabled": bool(row and row.call_enabled), "call_number": row.call_number if row else None,
        # Email override only: it decides whether confirmation applies (WhatsApp demo sends use their own check).
        "demo_recipients": demo and bool(s.demo_notify_email),
        "_demo_whatsapp": demo and bool(s.demo_notify_whatsapp),
        "available": channel_available(),
        "demo_email_set": bool(s.demo_notify_email), "demo_whatsapp_set": bool(s.demo_notify_whatsapp),
    }


def _queue_verification(db: Any, user_id: Any) -> bool:
    """Queue one confirmation email (max 3 an hour). Needs any active membership for the organisation id."""
    recent = db.execute(text("""select count(*) from app.notification_deliveries where user_id = :u
                                and kind = 'verify_email' and created_at > now() - interval '1 hour'"""),
                        {"u": user_id}).scalar()
    if (recent or 0) >= VERIFY_LIMIT_PER_HOUR:
        return False
    org = db.execute(text("""select m.org_id from app.memberships m where m.user_id = :u and m.status = 'active'
                             order by m.created_at limit 1"""), {"u": user_id}).scalar()
    if org is None:
        return False
    db.execute(text("select app.set_request_context(:u, :o)"), {"u": user_id, "o": org})
    db.execute(text("""insert into app.notification_deliveries (org_id, user_id, channel, kind, dedupe_key)
                       values (:o, :u, 'email', 'verify_email', :k)"""),
               {"o": org, "u": user_id, "k": f"verify:{uuid.uuid4()}"})
    return True


def update_prefs(p: Principal, data: dict[str, Any]) -> dict[str, Any]:
    if data.get("email_enabled") and not data.get("email_address") and not get_prefs(p)["demo_recipients"]:
        raise Unprocessable("Add the email address for reminders.",
                            fields=[FieldError(field="email_address", code="required",
                                               message="Enter an email address.")])
    if data.get("whatsapp_enabled") and not data.get("whatsapp_number") and not get_prefs(p)["_demo_whatsapp"]:
        raise Unprocessable("Add the WhatsApp number for reminders.",
                            fields=[FieldError(field="whatsapp_number", code="required",
                                               message="Enter the number with country code, e.g. +91…")])
    new_email = (data.get("email_address") or "").strip().lower() or None
    with user_tx(p.user_id) as db:
        old = db.execute(text("select email_address, email_verified_at from app.notification_preferences "
                              "where user_id = :u"), {"u": p.user_id}).one_or_none()
        changed = (old.email_address if old else None) != new_email
        db.execute(text("""
            insert into app.notification_preferences (user_id, email_enabled, email_address, push_enabled,
              whatsapp_enabled, whatsapp_number, call_enabled, call_number, updated_at)
            values (:u, :ee, :ea, :pe, :we, :wn, :ce, :cn, now())
            on conflict (user_id) do update set email_enabled = excluded.email_enabled,
              email_address = excluded.email_address, push_enabled = excluded.push_enabled,
              whatsapp_enabled = excluded.whatsapp_enabled, whatsapp_number = excluded.whatsapp_number,
              call_enabled = excluded.call_enabled, call_number = excluded.call_number, updated_at = now()"""),
            {"u": p.user_id, "ee": data["email_enabled"], "ea": new_email,
             "pe": data["push_enabled"], "we": data["whatsapp_enabled"], "wn": data.get("whatsapp_number") or None,
             "ce": data.get("call_enabled", False), "cn": data.get("call_number") or None})
        if changed:  # a new address must be confirmed again
            db.execute(text("""update app.notification_preferences set email_verified_at = null,
                               email_verify_hash = null, email_verify_sent_at = null where user_id = :u"""),
                       {"u": p.user_id})
        verified = bool(old and old.email_verified_at and not changed)
        s = get_settings()
        if (data["email_enabled"] and new_email and not verified and channel_available()["email"]
                and not s.demo_notify_email and (changed or not (old and old.email_verified_at))):
            _queue_verification(db, p.user_id)
    return get_prefs(p)


def resend_verification(p: Principal) -> None:
    if not channel_available()["email"]:
        raise ApiError("Email isn't set up on this server yet.", code="channel_unavailable", status_code=409)
    with user_tx(p.user_id) as db:
        row = db.execute(text("select email_address, email_verified_at from app.notification_preferences "
                              "where user_id = :u"), {"u": p.user_id}).one_or_none()
        if not row or not row.email_address:
            raise Unprocessable("Add your email address first.", code="no_email")
        if row.email_verified_at:
            return
        if not _queue_verification(db, p.user_id):
            raise ApiError("Several confirmation emails were sent already. Try again in an hour.",
                           code="rate_limited", status_code=429)


def confirm_email(token: str) -> bool:
    from pawguard_api.db import public_tx

    if not (20 <= len(token) <= 100):
        return False
    with public_tx() as db:
        return bool(db.execute(text("select app.confirm_email(:t)"), {"t": token}).scalar())


def send_test(db: Any, ctx: OrgContext, channel: Channel) -> None:
    """Queue a test message to yourself on one channel (sent within about 15 seconds by the worker)."""
    if not channel_available()[channel]:
        raise ApiError("This channel is not set up on the server yet.", code="channel_unavailable", status_code=409)
    if channel == "email" and not get_settings().demo_notify_email:
        ok = db.execute(text("select email_verified_at is not null from app.notification_preferences "
                             "where user_id = :u"), {"u": ctx.user_id}).scalar()
        if not ok:
            raise ApiError("Confirm your email address first — open the link we sent you.",
                           code="email_not_confirmed", status_code=409)
    if channel == "call":  # a call goes to the person's own number (WhatsApp tests go to the team's test number)
        prefs = db.execute(text("select call_enabled, call_number from app.notification_preferences "
                                "where user_id = :u"), {"u": ctx.user_id}).first()
        if not (prefs and prefs.call_enabled and prefs.call_number):
            raise ApiError("Turn this on and save your phone number first.", code="number_missing", status_code=409)
    # Per channel (testing email must not use up the phone-call tests); tests we skipped ourselves don't count.
    recent = db.execute(text("""select count(*) as n, min(created_at) as first from app.notification_deliveries
                                where user_id = :u and kind = 'test' and channel = :c and state <> 'skipped'
                                  and created_at > now() - interval '1 hour'"""),
                        {"u": ctx.user_id, "c": channel}).one()
    if recent.n >= TEST_LIMIT_PER_HOUR:
        wait = max(1, math.ceil((recent.first + timedelta(hours=1) - datetime.now(UTC)).total_seconds() / 60))
        raise ApiError(f"You've sent several tests on this channel. Try again in {wait} minutes.",
                       code="rate_limited", status_code=429, details={"retry_in_minutes": wait})
    db.execute(text("""insert into app.notification_deliveries (org_id, user_id, channel, kind, dedupe_key)
                       values (:o, :u, :c, 'test', :k)"""),
               {"o": ctx.org_id, "u": ctx.user_id, "c": channel, "k": f"test:{uuid.uuid4()}"})
    record_audit(db, ctx, "notification.test_queued", "user", ctx.user_id, {"channel": channel})


def overview(db: Any, ctx: OrgContext) -> dict[str, Any]:
    """Provider status and the clinic's recent deliveries (states only, never addresses)."""
    if not (ctx.can(Cap.ANIMAL_READ) or ctx.can(Cap.VACCINATION_REVIEW)):
        raise Forbidden("Clinic staff only.", code="staff_only")
    status = {r.provider: r for r in db.execute(text("select * from app.provider_status"))}
    available = channel_available()
    providers = []
    for name in ("email", "push", "whatsapp", "call"):
        r = status.get(name)
        providers.append({"provider": name, "configured": available[name],
                          "state": (r.state if r else ("ok" if available[name] else "not_configured")),
                          "detail": r.detail if r else None, "updated_at": r.updated_at if r else None})
    rows = db.execute(text("""
        select d.id, d.channel, d.kind, d.state, d.created_at, d.sent_at, d.last_error, d.reply,
               coalesce(a.nickname, a.reference_code) as pet_name
        from app.notification_deliveries d
        left join app.vaccination_reminders r on r.id = d.reminder_id
        left join app.animals a on a.id = r.animal_id
        order by d.created_at desc limit 30""")).all()
    s = get_settings()
    webhook = f"{s.public_app_url}/api/v1/webhooks/whatsapp" if available["whatsapp"] else None
    return {"providers": providers, "deliveries": [dict(r._mapping) for r in rows], "whatsapp_webhook_url": webhook}


def run_now(db: Any, ctx: OrgContext) -> int:
    """Demo tool: queue reminders that are due today (normally done every 10 minutes by the dispatcher)."""
    if not (ctx.can(Cap.ANIMAL_READ) or ctx.can(Cap.VACCINATION_REVIEW)):
        raise Forbidden("Clinic staff only.", code="staff_only")
    is_demo = db.execute(text("select is_demo from app.organisations where id = :o"), {"o": ctx.org_id}).scalar()
    if not (is_demo and get_settings().demo_mode):
        raise Forbidden("Only available in demo organisations.", code="not_demo")
    n = int(db.execute(text("select app.queue_due_notifications(:c)"),
                       {"c": not get_settings().demo_notify_email}).scalar() or 0)
    record_audit(db, ctx, "notification.scan_requested", "organisation", ctx.org_id, {"queued": n})
    return n


# ---- Web Push subscriptions (own only) ---------------------------------------------------------------------------

def add_push_subscription(p: Principal, endpoint: str, p256dh: str, auth: str, user_agent: str | None) -> None:
    if not notify.push_endpoint_allowed(endpoint):
        raise Unprocessable("This browser's push service isn't supported.",
                            fields=[FieldError(field="endpoint", code="push_service_not_allowed",
                                               message="Unknown push service.")])
    with user_tx(p.user_id) as db:
        db.execute(text("""
            insert into app.push_subscriptions (user_id, endpoint, p256dh, auth, user_agent)
            values (:u, :e, :k, :a, :ua)
            on conflict (endpoint) do update set p256dh = excluded.p256dh, auth = excluded.auth,
              user_agent = excluded.user_agent, revoked_at = null
            where app.push_subscriptions.user_id = :u"""),
            {"u": p.user_id, "e": endpoint, "k": p256dh, "a": auth, "ua": (user_agent or "")[:300] or None})
        db.execute(text("""insert into app.notification_preferences (user_id, push_enabled) values (:u, true)
                           on conflict (user_id) do update set push_enabled = true, updated_at = now()"""),
                   {"u": p.user_id})


def remove_push_subscription(p: Principal, endpoint: str) -> None:
    with user_tx(p.user_id) as db:
        db.execute(text("update app.push_subscriptions set revoked_at = now() where endpoint = :e and user_id = :u"),
                   {"e": endpoint, "u": p.user_id})
        left = db.execute(text("""select count(*) from app.push_subscriptions where user_id = :u
                                   and revoked_at is null"""), {"u": p.user_id}).scalar()
        if not left:
            db.execute(text("update app.notification_preferences set push_enabled = false where user_id = :u"),
                       {"u": p.user_id})


# ---- WhatsApp webhook --------------------------------------------------------------------------------------------

def whatsapp_receipts(db: Any, payload: dict[str, Any]) -> int:
    """Record delivery receipts (failed → the delivery shows 'Failed' with Meta's reason). Incoming messages are
    only counted: they open the 24-hour window on Meta's side; PawGuard stores no message content."""
    updated = 0
    for entry in payload.get("entry", []) if isinstance(payload, dict) else []:
        for change in entry.get("changes", []) or []:
            value = change.get("value", {}) or {}
            for st in value.get("statuses", []) or []:
                mid, status = str(st.get("id", ""))[:200], str(st.get("status", ""))[:20]
                if not mid:
                    continue
                errs = st.get("errors") or []
                reason = (f"WhatsApp {errs[0].get('code')}: {str(errs[0].get('title', ''))[:120]}"
                          if errs and isinstance(errs[0], dict) else None)
                updated += int(db.execute(text("select app.record_whatsapp_status(:m, :s, :e)"),
                                          {"m": mid, "s": status, "e": reason}).scalar() or 0)
    return updated
