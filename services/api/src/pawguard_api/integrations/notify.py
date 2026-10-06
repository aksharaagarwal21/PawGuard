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
