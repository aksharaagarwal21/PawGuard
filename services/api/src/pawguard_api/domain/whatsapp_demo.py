"""Twilio WhatsApp demo tools: clinic staff in the demo organisation send the trial template to the one configured
demo recipient, either now or scheduled 2 minutes ahead (sent by the dispatcher and worker, so the browser can be
closed). No pet records, vaccinations or due dates are touched; the scheduled reminder is for a fictional pet."""

from typing import Any, Literal

from sqlalchemy import text

from pawguard_api.capabilities import Cap
from pawguard_api.deps import OrgContext
from pawguard_api.domain.common import record_audit
from pawguard_api.errors import ApiError, Forbidden
from pawguard_api.integrations import notify
from pawguard_api.settings import get_settings

SENDS_PER_HOUR = 5
SCHEDULE_MINUTES = 2
# One of the fixed sample texts Twilio's trial templates use (the exact text appears after the first send).
TEMPLATE_SAMPLE = "Reminder: Appt Tue Oct 29, 3:00 PM. Reply C to confirm or R to reschedule. Test message from Twilio."
# Twilio / WhatsApp error codes seen with trial senders, in plain words.
ERROR_HELP = {
    "63015": "The recipient hasn't joined the Twilio trial sender (send the join code from that phone first).",
    "63016": "Outside the 24-hour window: only an approved template can be sent.",
    "63003": "Twilio couldn't reach this number on WhatsApp.",
    "63024": "The recipient number isn't a valid WhatsApp user.",
    "63018": "Twilio's WhatsApp rate limit was reached; try again later.",
    "63049": "WhatsApp chose not to deliver this template message.",
    "21608": "Trial accounts can only send to numbers verified in the Twilio console.",
    "21610": "The recipient opted out (replied STOP).",
    "30008": "Unknown delivery error reported by WhatsApp.",
}


def _check(db: Any, ctx: OrgContext) -> None:
    if not (ctx.can(Cap.ANIMAL_READ) or ctx.can(Cap.VACCINATION_REVIEW)):
        raise Forbidden("Clinic staff only.", code="staff_only")
    is_demo = db.execute(text("select is_demo from app.organisations where id = :o"), {"o": ctx.org_id}).scalar()
    if not (is_demo and get_settings().demo_mode):
        raise Forbidden("Only available in the demo organisation.", code="not_demo")


def missing_settings() -> list[str]:
    s = get_settings()
    checks = {"PAWGUARD_WHATSAPP_PROVIDER=twilio": s.whatsapp_provider == "twilio",
              "PAWGUARD_TWILIO_ACCOUNT_SID": bool(s.twilio_account_sid),
              "PAWGUARD_TWILIO_AUTH_TOKEN": bool(s.twilio_auth_token),
              "PAWGUARD_TWILIO_WHATSAPP_FROM": bool(s.twilio_whatsapp_from),
              "PAWGUARD_TWILIO_CONTENT_SID": bool(s.twilio_content_sid),
              "PAWGUARD_DEMO_NOTIFY_WHATSAPP": bool(s.demo_notify_whatsapp)}
    return [name for name, ok in checks.items() if not ok]


def _explain(r: Any) -> str | None:
    if r.provider_error_code and r.provider_error_code in ERROR_HELP:
        return f"{ERROR_HELP[r.provider_error_code]} (Twilio error {r.provider_error_code})"
    return r.last_error


def status(db: Any, ctx: OrgContext) -> dict[str, Any]:
    """Configuration state (never credentials), the masked recipient, the template preview and the history."""
    _check(db, ctx)
    s = get_settings()
    rows = db.execute(text("""
        select id, kind, state, available_at, created_at, sent_at, attempts, provider_message_id, provider_status,
               provider_status_at, provider_error_code, last_error, recipient_masked, provider_body
          from app.notification_deliveries
         where org_id = :o and channel = 'whatsapp' and kind in ('test','demo_reminder')
         order by created_at desc limit 20"""), {"o": ctx.org_id}).all()
    return {
        "ready": not missing_settings(),
        "missing": missing_settings(),
        "recipient_masked": notify.mask_number(s.demo_notify_whatsapp),
        "callback_url": (f"{s.public_app_url}/api/v1/webhooks/twilio/status"
                         if s.public_app_url.startswith("https://") else None),
        "template_body": next((r.provider_body for r in rows if r.provider_body), None),
        "template_sample": TEMPLATE_SAMPLE,
        "sends_left_this_hour": max(0, SENDS_PER_HOUR - _sent_last_hour(db, ctx)),
        "history": [{"id": r.id, "kind": r.kind, "state": r.state, "scheduled_for": r.available_at,
                     "created_at": r.created_at, "sent_at": r.sent_at, "attempts": r.attempts,
                     "message_sid": r.provider_message_id, "provider_status": r.provider_status,
                     "provider_status_at": r.provider_status_at, "error_code": r.provider_error_code,
                     "explanation": _explain(r) if r.state in ("failed", "skipped", "deferred") else None,
                     "recipient_masked": r.recipient_masked} for r in rows],
    }


def _sent_last_hour(db: Any, ctx: OrgContext) -> int:
    return int(db.execute(text("""
        select count(*) from app.notification_deliveries
         where org_id = :o and channel = 'whatsapp' and kind in ('test','demo_reminder')
           and created_at > now() - interval '1 hour'"""), {"o": ctx.org_id}).scalar() or 0)


def queue(db: Any, ctx: OrgContext, kind: Literal["test", "demo_reminder"]) -> dict[str, Any]:
    """Queue one demo send. Double clicks and parallel requests are refused while another one is still waiting."""
    _check(db, ctx)
    missing = missing_settings()
    if missing:
        raise ApiError(f"Twilio WhatsApp isn't fully set up on the server ({', '.join(missing)}).",
                       code="channel_unavailable", status_code=409)
    db.execute(text("select pg_advisory_xact_lock(hashtext(:k))"), {"k": f"whatsapp-demo:{ctx.org_id}"})
    waiting = db.execute(text("""
        select count(*) from app.notification_deliveries
         where org_id = :o and channel = 'whatsapp' and kind = :k and state in ('queued','sending','deferred')"""),
                         {"o": ctx.org_id, "k": kind}).scalar()
    if waiting:
        raise ApiError("One is already waiting to be sent — see the history below.", code="already_queued",
                       status_code=409)
    if _sent_last_hour(db, ctx) >= SENDS_PER_HOUR:
        raise ApiError("The demo allows 5 WhatsApp sends an hour. Try again later.", code="rate_limited",
                       status_code=429)
    minutes = SCHEDULE_MINUTES if kind == "demo_reminder" else 0
    row = db.execute(text("""
        insert into app.notification_deliveries (org_id, user_id, channel, kind, dedupe_key, available_at, is_demo)
        values (:o, :u, 'whatsapp', :k, 'whatsapp-demo:' || extensions.gen_random_uuid()::text,
                now() + make_interval(mins => :m), true)
        returning id, available_at"""), {"o": ctx.org_id, "u": ctx.user_id, "k": kind, "m": minutes}).one()
    record_audit(db, ctx, "notification.whatsapp_demo_queued", "organisation", ctx.org_id,
                 {"kind": kind, "minutes_ahead": minutes})
    return {"id": row.id, "scheduled_for": row.available_at}


def cancel(db: Any, ctx: OrgContext, delivery_id: str) -> None:
    _check(db, ctx)
    if not db.execute(text("select app.cancel_demo_delivery(:i)"), {"i": delivery_id}).scalar():
        raise ApiError("It can't be cancelled any more (already sent or not found).", code="not_cancellable",
                       status_code=409)
    record_audit(db, ctx, "notification.whatsapp_demo_cancelled", "organisation", ctx.org_id, {})
