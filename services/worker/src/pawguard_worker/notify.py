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


def _sql(sql: str, **params: Any) -> Any:
    with worker_engine().begin() as c:
        return c.execute(text(sql), params)


def queue_due() -> int:
    with worker_engine().begin() as c:
        return int(c.execute(text("select app.queue_due_notifications()")).scalar() or 0)


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


def _recipient(info: dict[str, Any], s: Settings) -> str | None:
    if info["channel"] == "email":
        return s.demo_notify_email if info["is_demo"] else info.get("email_address")
    if info["channel"] == "whatsapp":
        return s.demo_notify_whatsapp if info["is_demo"] else info.get("whatsapp_number")
    return None


def _send_email(info: dict[str, Any], msg: notify.Message, s: Settings) -> str:
    to = _recipient(info, s)
    if not to:
        raise notify.ProviderError("no_recipient", detail="No email address (demo: set PAWGUARD_DEMO_NOTIFY_EMAIL)")
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


SENDERS: dict[str, Callable[[dict[str, Any], notify.Message, Settings], str]] = {
    "email": _send_email, "push": _send_push}


def deliver(info: dict[str, Any], s: Settings) -> str:
    """Send one claimed delivery and record the outcome. Returns the final state."""
    row_id, channel = str(info["id"]), info["channel"]
    if info["kind"] == "vaccination_reminder" and info.get("reminder_state") != "pending":
        _finish(row_id, "skipped", error="reminder no longer pending")
        return "skipped"
    sender = SENDERS.get(channel)
    if sender is None:
        _finish(row_id, "skipped", error=f"{channel} sending not available yet")
        return "skipped"
    try:
        provider_id = sender(info, notify.compose(info, s), s)
    except notify.ProviderError as err:
        if err.status in ("not_configured", "token_expired", "cap_reached", "rate_limited", "error"):
            _status(channel, err.status, err.detail or err.code)
        if err.code in ("not_configured", "no_recipient"):
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
