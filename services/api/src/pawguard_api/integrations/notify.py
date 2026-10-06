"""Outbound message providers (free tiers): email over SMTP (Gmail app password or Brevo), Web Push, WhatsApp.

Each sender raises `ProviderError` with a stable code. `retry_in` (seconds) means try again later; `status` is what
staff should see for the provider (e.g. "token_expired" → "WhatsApp token expired — renew it"). Message text holds
only what a reminder needs (pet name, vaccine, date, clinic) — no notes, photos or contact details.
"""

import smtplib
import ssl
from dataclasses import dataclass
from datetime import date
from email.message import EmailMessage
from email.utils import make_msgid
from typing import Any

from pawguard_api.settings import Settings


class ProviderError(Exception):
    def __init__(self, code: str, *, retry_in: int | None = None, status: str = "error", detail: str = "") -> None:
        super().__init__(code)
        self.code, self.retry_in, self.status, self.detail = code, retry_in, status, detail


@dataclass(frozen=True)
class Message:
    subject: str
    text: str
    short: str  # one or two lines: push body, WhatsApp text
    link: str


def _when(d: date) -> str:
    return f"{d.day} {d:%b %Y}"


def compose(info: dict[str, Any], s: Settings) -> Message:
    """Build the message from facts only (no free text from users)."""
    link = f"{s.public_app_url}/en/app/reminders"
    demo = "\n\n(Demo — fictional pets and clinics. Not for real medical use.)" if info.get("is_demo") else ""
    footer = ("\n\nPawGuard only reminds you; your vet decides what your pet needs."
              "\nTo stop these messages, open PawGuard → Notifications.")
    if info["kind"] == "verify_email":
        return Message("", "", "", link)  # built by compose_verification when the token is issued
    if info["kind"] == "test":
        subject = "PawGuard test message"
        short = "PawGuard: this is a test message. Your notifications are working."
        return Message(subject, f"Hello,\n\n{short}\n\n{link}{footer}{demo}", short, link)
    due = date.fromisoformat(str(info["due_on"]))
    today = date.fromisoformat(str(info["today"]))
    pet, vaccine, clinic = info["pet"], info["vaccine"], info["clinic"]
    verb = "was due on" if due < today else "is due on"
    subject = f"Reminder: {pet}'s {vaccine} vaccination {verb} {_when(due)}"
    short = f"{pet}'s {vaccine} vaccination {verb} {_when(due)}. Please contact {clinic}."
    text = (f"Hello,\n\nThis is a reminder from {clinic}: {pet}'s {vaccine} vaccination {verb} {_when(due)}.\n"
            f"Please contact your vet to book a visit. If it has been given, mark it as done in the app:\n{link}"
            f"{footer}{demo}")
    return Message(subject, text, short, link)


def compose_verification(token: str, s: Settings) -> Message:
    """The confirmation email: fixed text and the one-time link; nothing typed by anyone else."""
    link = f"{s.public_app_url}/en/verify-email?token={token}"
    short = "Please confirm your email address for PawGuard reminders."
    text = ("Hello,\n\nSomeone (hopefully you) asked PawGuard 360 to send vaccination reminders to this address.\n"
            f"To confirm, open this link within 48 hours:\n{link}\n\n"
            "If this wasn't you, ignore this email — nothing will be sent to you.\n\n— PawGuard 360 (demo)")
    return Message("Confirm your email for PawGuard reminders", text, short, link)


# ---- email -------------------------------------------------------------------------------------------------------

def email_configured(s: Settings) -> bool:
    return bool(s.smtp_user and s.smtp_password and s.smtp_host)


def send_email(s: Settings, to: str, msg: Message) -> str:
    """Send one plain-text email over SMTP with STARTTLS. Returns the Message-ID."""
    if not email_configured(s):
        raise ProviderError("not_configured", status="not_configured", detail="SMTP user or app password not set")
    em = EmailMessage()
    em["From"] = s.email_from or s.smtp_user or ""
    em["To"] = to
    em["Subject"] = msg.subject
    msg_id = make_msgid(domain="pawguard360.demo")
    em["Message-ID"] = msg_id
    em.set_content(msg.text)
    try:
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=20) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            smtp.login(s.smtp_user or "", s.smtp_password or "")
            smtp.send_message(em)
    except smtplib.SMTPAuthenticationError as exc:
        raise ProviderError("auth_failed", status="error",
                            detail="SMTP login rejected — check the app password") from exc
    except smtplib.SMTPRecipientsRefused as exc:
        raise ProviderError("recipient_refused", detail="The recipient address was refused") from exc
    except (smtplib.SMTPDataError, smtplib.SMTPSenderRefused) as exc:
        code = getattr(exc, "smtp_code", 0) or 0
        text = str(getattr(exc, "smtp_error", b""))
        if "limit" in text.lower() or code in (421, 450, 451, 452, 454):
            raise ProviderError("cap_reached", retry_in=3600, status="cap_reached",
                                detail="Provider sending limit reached — will retry later") from exc
        raise ProviderError("rejected", detail=f"SMTP {code}") from exc
    except (smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError, TimeoutError, OSError) as exc:
        raise ProviderError("unreachable", retry_in=300, detail="SMTP server not reachable") from exc
    return msg_id


# ---- Web Push (VAPID) --------------------------------------------------------------------------------------------

# Browsers' push services. Subscriptions pointing anywhere else are refused, so the server never posts to arbitrary
# addresses (no server-side request forgery through a crafted "subscription").
PUSH_HOSTS = ("fcm.googleapis.com", "updates.push.services.mozilla.com", "push.services.mozilla.com",
              "web.push.apple.com", ".push.apple.com", ".notify.windows.com", "push.api.chrome.google.com")


def push_endpoint_allowed(endpoint: str) -> bool:
    from urllib.parse import urlparse

    u = urlparse(endpoint)
    host = (u.hostname or "").lower()
    return u.scheme == "https" and any(host == h.lstrip(".") or (h.startswith(".") and host.endswith(h))
                                       for h in PUSH_HOSTS)


def push_configured(s: Settings) -> bool:
    return bool(s.vapid_public_key and s.vapid_private_key and s.vapid_contact)


def generate_vapid_keys() -> tuple[str, str]:
    """(public applicationServerKey, private raw key), both base64url without padding."""
    import base64

    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    key = ec.generate_private_key(ec.SECP256R1())
    raw = key.private_numbers().private_value.to_bytes(32, "big")
    pub = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)

    def b64(b: bytes) -> str:
        return base64.urlsafe_b64encode(b).rstrip(b"=").decode()

    return b64(pub), b64(raw)


def send_push(s: Settings, subscriptions: list[dict[str, str]], msg: Message, *,
              on_gone: Any = None, on_ok: Any = None) -> str:
    """Send to every device of the person. Returns how many devices accepted it. Expired devices are revoked."""
    import json

    from pywebpush import WebPushException, webpush

    if not push_configured(s):
        raise ProviderError("not_configured", status="not_configured", detail="VAPID keys or contact not set")
    subs = [x for x in subscriptions if push_endpoint_allowed(x.get("endpoint", ""))]
    if not subs:
        raise ProviderError("no_recipient", detail="No browser has turned on notifications")
    payload = json.dumps({"title": msg.subject, "body": msg.short, "url": "/en/app/reminders", "tag": "pawguard"})
    ok, last_error = 0, ""
    for sub in subs:
        try:
            webpush({"endpoint": sub["endpoint"], "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]}},
                    data=payload, vapid_private_key=s.vapid_private_key,
                    vapid_claims={"sub": s.vapid_contact or ""}, ttl=86400, timeout=15)
            ok += 1
            if on_ok:
                on_ok(sub["endpoint"])
        except WebPushException as exc:
            code = getattr(getattr(exc, "response", None), "status_code", 0)
            if code in (404, 410) and on_gone:
                on_gone(sub["endpoint"])  # the browser unsubscribed or the subscription expired
            elif code == 429:
                raise ProviderError("rate_limited", retry_in=600, status="rate_limited",
                                    detail="Push service is rate limiting — will retry") from exc
            last_error = f"push service answered {code}"
    if ok == 0:
        raise ProviderError("push_failed", retry_in=600 if last_error else None, detail=last_error or "no device")
    return f"{ok} device(s)"


# ---- WhatsApp Cloud API (test number) ----------------------------------------------------------------------------

# Error codes from Meta's "WhatsApp error codes" page.
_WA_TOKEN = {190, 0}
_WA_RATE = {4, 80007, 130429, 131056}
_WA_TEMPORARY = {131000, 131016}


def whatsapp_configured(s: Settings) -> bool:
    return bool(s.whatsapp_token and s.whatsapp_phone_number_id)


def send_whatsapp(s: Settings, to: str, msg: Message, info: dict[str, Any]) -> str:
    """Send a reminder: the approved template when configured (works outside the 24-hour window), otherwise a plain
    text message (only inside the 24-hour window that opens when the recipient messages the test number)."""
    import httpx

    if not whatsapp_configured(s):
        raise ProviderError("not_configured", status="not_configured",
                            detail="WhatsApp token or phone number id not set")
    url = f"https://graph.facebook.com/{s.whatsapp_api_version}/{s.whatsapp_phone_number_id}/messages"
    number = to.lstrip("+")
    if s.whatsapp_template and info.get("kind") == "vaccination_reminder":
        due = date.fromisoformat(str(info["due_on"]))
        params = [info["clinic"], info["pet"], info["vaccine"], _when(due)]
        body: dict[str, Any] = {"messaging_product": "whatsapp", "to": number, "type": "template",
                                "template": {"name": s.whatsapp_template, "language": {"code": "en"},
                                             "components": [{"type": "body", "parameters": [
                                                 {"type": "text", "text": str(p)[:100]} for p in params]}]}}
    else:
        body = {"messaging_product": "whatsapp", "to": number, "type": "text",
                "text": {"preview_url": False, "body": f"{msg.short}\n{msg.link}"}}
    try:
        r = httpx.post(url, json=body, headers={"Authorization": f"Bearer {s.whatsapp_token}"}, timeout=15)
    except httpx.HTTPError as exc:
        raise ProviderError("unreachable", retry_in=300, detail="WhatsApp API not reachable") from exc
    if r.status_code < 300:
        try:
            return str(r.json()["messages"][0]["id"])
        except (ValueError, KeyError, IndexError) as exc:
            raise ProviderError("bad_response", detail="Unexpected WhatsApp response") from exc
    try:
        err = r.json().get("error", {})
    except ValueError:
        err = {}
    code = int(err.get("code", -1)) if str(err.get("code", "")).lstrip("-").isdigit() else -1
    text_ = str(err.get("message", ""))[:160]
    if code in _WA_TOKEN or r.status_code == 401:
        raise ProviderError("token_expired", status="token_expired",
                            detail="WhatsApp token expired — renew it in Meta's dashboard and update "
                                   "PAWGUARD_WHATSAPP_TOKEN")
    if code in _WA_RATE:
        raise ProviderError("rate_limited", retry_in=600, status="rate_limited", detail=f"WhatsApp rate limit ({code})")
    if code == 131047:
        raise ProviderError("outside_window", detail="More than 24 hours since the recipient last messaged the test "
                                                     "number — reply 'hi' on WhatsApp, or set an approved template")
    if code == 132001:
        raise ProviderError("template_not_approved", status="error",
                            detail="The WhatsApp template isn't approved (or wrong name/language)")
    if code in _WA_TEMPORARY or r.status_code >= 500:
        raise ProviderError("temporary", retry_in=300, detail=f"WhatsApp temporary error ({code})")
    raise ProviderError("rejected", detail=f"WhatsApp error {code}: {text_}")


def whatsapp_signature_valid(s: Settings, raw_body: bytes, header: str | None) -> bool:
    """Meta signs webhook POSTs: X-Hub-Signature-256 = 'sha256=' + HMAC-SHA256(app secret, raw body)."""
    import hashlib
    import hmac

    if not (s.whatsapp_app_secret and header and header.startswith("sha256=")):
        return False
    expected = hmac.new(s.whatsapp_app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header.removeprefix("sha256="))
