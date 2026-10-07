"""Send queued notifications (email now; push and WhatsApp plug into `SENDERS`).

Rows are claimed through `app.claim_notification_deliveries` (SKIP LOCKED) and finished through
`app.finish_notification_delivery`; the worker never reads the tables directly. Demo organisations send only to the
configured test recipients (never to the fictional demo addresses). Email respects a rolling 24-hour cap.
"""

import json
from collections.abc import Callable
from typing import Any

from sqlalchemy import text

from pawguard_api.db import worker_engine
from pawguard_api.integrations import notify
from pawguard_api.logging import get_logger
from pawguard_api.settings import Settings, get_settings

log = get_logger(__name__)
MAX_ATTEMPTS = 5
# Errors about one recipient (not the provider as a whole).
RECIPIENT_CODES = {"no_recipient", "not_confirmed", "outside_window", "recipient_refused", "push_failed",
                   "not_verified_number", "timeout_unknown"}


def _sql(sql: str, **params: Any) -> Any:
    with worker_engine().begin() as c:
        return c.execute(text(sql), params)


def queue_due() -> int:
    needs_confirmation = not get_settings().demo_notify_email
    with worker_engine().begin() as c:
        return int(c.execute(text("select app.queue_due_notifications(:c)"), {"c": needs_confirmation}).scalar() or 0)


def close_bite_observations() -> int:
    """End observation periods whose last day has passed and send the closing notices (owner channels via the queue,
    consenting reporters by email)."""
    from pawguard_api.domain import bites

    with worker_engine().begin() as c:
        return bites.close_and_notify(c)


def has_ready() -> bool:
    """Read-only check used by the dispatcher before publishing a drain task."""
    with worker_engine().begin() as c:
        return bool(c.execute(text("select app.notifications_ready()")).scalar())


def _finish(row_id: str, state: str, *, error: str | None = None, provider_id: str | None = None,
            retry_in: int | None = None) -> None:
    _sql("select app.finish_notification_delivery(:i, :s, :e, :p, :r)", i=row_id, s=state, e=error, p=provider_id,
         r=retry_in)


def _status(provider: str, state: str, detail: str = "") -> None:
    _sql("select app.set_provider_status(:p, :s, :d)", p=provider, s=state, d=detail)


def _override(info: dict[str, Any], s: Settings) -> str | None:
    """Optional team test recipient for demo organisations (empty = use each person's own address)."""
    if not info["is_demo"]:
        return None
    return (s.demo_notify_email if info["channel"] == "email" else
            s.demo_notify_whatsapp if info["channel"] == "whatsapp" else None) or None


def _recipient(info: dict[str, Any], s: Settings) -> str | None:
    if info["channel"] == "email":
        return _override(info, s) or info.get("email_address")
    if info["channel"] == "whatsapp":
        return _override(info, s) or info.get("whatsapp_number")
    return None


def _send_email(info: dict[str, Any], msg: notify.Message, s: Settings) -> str:
    to = _recipient(info, s)
    if not to:
        raise notify.ProviderError("no_recipient", detail="No email address")
    if info["kind"] == "verify_email":
        if _override(info, s):
            raise notify.ProviderError("no_recipient", detail="Demo uses the team inbox; no confirmation needed")
        token = _sql("select app.issue_email_verification(:u)", u=str(info["user_id"])).scalar()
        if not token:
            raise notify.ProviderError("no_recipient", detail="No email address to confirm")
        msg = notify.compose_verification(str(token), s)
    elif not _override(info, s) and not info.get("email_verified"):
        raise notify.ProviderError("not_confirmed", detail="Email address not confirmed yet")
    sent = int(_sql("select app.notifications_sent_last_day('email')").scalar() or 0)
    if sent >= s.email_daily_cap:
        raise notify.ProviderError("cap_reached", retry_in=3600, status="cap_reached",
                                   detail=f"Daily cap of {s.email_daily_cap} emails reached — waiting")
    return notify.send_email(s, to, msg)


def _send_push(info: dict[str, Any], msg: notify.Message, s: Settings) -> str:
    return notify.send_push(
        s, list(info.get("push") or []), msg,
        on_gone=lambda ep: _sql("select app.revoke_push_endpoint(:e)", e=ep),
        on_ok=lambda ep: _sql("select app.mark_push_success(:e)", e=ep))


def _send_whatsapp(info: dict[str, Any], msg: notify.Message, s: Settings) -> str:
    if s.whatsapp_provider == "twilio":
        return _send_whatsapp_twilio(info, s)
    to = _recipient(info, s)
    if not to:
        raise notify.ProviderError("no_recipient",
                                   detail="No WhatsApp number (demo: set PAWGUARD_DEMO_NOTIFY_WHATSAPP)")
    return notify.send_whatsapp(s, to, msg, info)


# The trial template is fixed sample text, so only demo sends use it (never real vaccination reminders).
TWILIO_TRIAL_KINDS = {"test", "demo_reminder"}


def _send_whatsapp_twilio(info: dict[str, Any], s: Settings) -> str:
    """Twilio trial: only the demo organisation, only the configured demo recipient, never sent twice."""
    row_id = str(info["id"])
    if not info.get("org_is_demo"):
        raise notify.ProviderError("no_recipient", detail="Twilio WhatsApp trial is for the demo organisation only")
    if info["kind"] not in TWILIO_TRIAL_KINDS:
        raise notify.ProviderError("no_recipient", detail="Twilio trial template is generic; used for demo sends only")
    to = s.demo_notify_whatsapp
    if not to:
        raise notify.ProviderError("no_recipient", detail="PAWGUARD_DEMO_NOTIFY_WHATSAPP is not set")
    if info.get("provider_message_id"):  # accepted earlier; the worker stopped before recording it
        return str(info["provider_message_id"])
    if info.get("send_started"):  # an earlier request's outcome is unknown: never resend blindly
        raise notify.ProviderError("timeout_unknown", detail="An earlier attempt may have been sent; not resending. "
                                                             "Check the Twilio message log.")
    _sql("select app.set_delivery_provider(:i, 'twilio', :r)", i=row_id, r=notify.mask_number(to))
    callback = (f"{s.public_app_url}/api/v1/webhooks/twilio/status" if s.public_app_url.startswith("https://")
                else None)
    try:
        result = notify.send_whatsapp_twilio(s, to, callback)
    except notify.ProviderError as err:
        if err.code != "timeout_unknown":  # definitely not sent: a later retry is safe
            _sql("select app.clear_delivery_send(:i)", i=row_id)
        raise
    _sql("select app.set_provider_result(:i, :sid, :st, :b)", i=row_id, sid=result.sid,
         st=result.status if result.status in notify.TWILIO_STATUSES else "queued", b=result.body)
    return result.sid


def poll_twilio_status(limit: int = 10) -> int:
    """Fallback when status callbacks can't reach us: ask Twilio about recent, unfinished messages (bounded)."""
    s = get_settings()
    if s.whatsapp_provider != "twilio" or not notify.twilio_whatsapp_configured(s):
        return 0
    with worker_engine().begin() as c:
        rows = c.execute(text("select * from app.twilio_status_to_check(:n)"), {"n": limit}).all()
    updated = 0
    for row in rows:
        try:
            status, error = notify.twilio_message_status(s, row.sid)
        except Exception as exc:  # checked again on the next tick
            log.warning("twilio_status_check_failed", error=type(exc).__name__)
            continue
        if status in notify.TWILIO_STATUSES:
            updated += int(_sql("select app.record_twilio_status(:s, :st, :e)", s=row.sid, st=status, e=error).scalar()
                           or 0)
    return updated


def _send_call(info: dict[str, Any], msg: notify.Message, s: Settings) -> str:
    to = info.get("call_number")
    if not to:
        raise notify.ProviderError("no_recipient", detail="No phone number for calls")
    return notify.send_call(s, to, msg, str(info["id"]))


SENDERS: dict[str, Callable[[dict[str, Any], notify.Message, Settings], str]] = {
    "email": _send_email, "push": _send_push, "whatsapp": _send_whatsapp, "call": _send_call}


def deliver(info: dict[str, Any], s: Settings) -> str:
    """Send one claimed delivery and record the outcome. Returns the final state."""
    row_id, channel = str(info["id"]), info["channel"]
    if info["kind"] == "vaccination_reminder" and info.get("reminder_state") != "pending":
        _finish(row_id, "skipped", error="reminder no longer pending")
        return "skipped"
    if info["kind"] == "vaccination_reminder" and not info.get(f"{channel}_enabled", True):
        _finish(row_id, "skipped", error=f"{channel} reminders were switched off")  # opt-out checked at send time
        return "skipped"
    sender = SENDERS.get(channel)
    if sender is None:
        _finish(row_id, "skipped", error=f"{channel} sending not available yet")
        return "skipped"
    try:
        provider_id = sender(info, notify.compose(info, s), s)
    except notify.ProviderError as err:
        if err.code not in RECIPIENT_CODES:  # problems with one recipient don't change the provider's status
            _status(channel, err.status, err.detail or err.code)
        if err.code in ("not_configured", "no_recipient", "not_confirmed"):
            _finish(row_id, "skipped", error=err.detail or err.code)
            return "skipped"
        if err.retry_in is not None and info["attempts"] < MAX_ATTEMPTS:
            _finish(row_id, "deferred", error=err.detail or err.code, retry_in=err.retry_in)
            return "deferred"
        _finish(row_id, "failed", error=err.detail or err.code)
        log.warning("notification_failed", channel=channel, code=err.code)
        return "failed"
    _status(channel, "ok", "")
    _finish(row_id, "sent", provider_id=provider_id)
    log.info("notification_sent", channel=channel, kind=info["kind"])
    return "sent"


def drain(limit: int = 20) -> dict[str, int]:
    """Claim and send one batch. Safe to run concurrently (SKIP LOCKED)."""
    s = get_settings()
    with worker_engine().begin() as c:
        rows = [r if isinstance(r, dict) else json.loads(r)
                for r in c.execute(text("select app.claim_notification_deliveries(:n)"), {"n": limit}).scalars()]
    counts: dict[str, int] = {}
    for info in rows:
        try:
            state = deliver(info, s)
        except Exception as exc:  # never leave a row stuck: it is reclaimed after its lock expires anyway
            log.error("notification_error", error=type(exc).__name__)
            _finish(str(info["id"]), "deferred", error=type(exc).__name__, retry_in=300)
            state = "deferred"
        counts[state] = counts.get(state, 0) + 1
    return counts
