"""API shapes for notification settings, test messages and the staff delivery overview."""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from pawguard_api.contracts import Out, StrictModel

ChannelName = Literal["email", "push", "whatsapp", "call"]


class ChannelsAvailableOut(Out):
    email: bool
    push: bool
    whatsapp: bool
    call: bool


class NotificationSettingsOut(Out):
    email_enabled: bool
    email_address: str | None
    email_verified: bool  # reminders go only to a confirmed address
    email_pending: bool  # a confirmation email was sent and not yet clicked
    push_enabled: bool
    push_devices: int
    whatsapp_enabled: bool
    whatsapp_number: str | None
    call_enabled: bool
    call_number: str | None
    demo_recipients: bool  # demo memberships: messages go to the team's test inbox/number instead
    demo_email_set: bool
    demo_whatsapp_set: bool
    available: ChannelsAvailableOut


class NotificationSettingsIn(StrictModel):
    email_enabled: bool = False
    email_address: str | None = Field(default=None, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    push_enabled: bool = False
    whatsapp_enabled: bool = False
    whatsapp_number: str | None = Field(default=None, pattern=r"^\+[1-9][0-9]{7,14}$")
    call_enabled: bool = False
    call_number: str | None = Field(default=None, pattern=r"^\+[1-9][0-9]{7,14}$")


class TestMessageIn(StrictModel):
    channel: ChannelName


class ProviderOut(Out):
    provider: ChannelName
    configured: bool
    state: Literal["ok", "not_configured", "token_expired", "rate_limited", "cap_reached", "error"]
    detail: str | None
    updated_at: datetime | None


class DeliveryOut(Out):
    id: UUID
    channel: ChannelName
    kind: Literal["vaccination_reminder", "test", "verify_email", "lost_message"]
    state: Literal["queued", "sending", "sent", "deferred", "failed", "skipped"]
    pet_name: str | None
    created_at: datetime
    sent_at: datetime | None
    last_error: str | None
    reply: Literal["1", "2"] | None = None  # phone-call keypad answer


class NotificationsOverviewOut(Out):
    providers: list[ProviderOut]
    deliveries: list[DeliveryOut]
    whatsapp_webhook_url: str | None = None  # paste into Meta's dashboard (changes with the public tunnel)


class ScanOut(Out):
    queued: int


class PushKeyOut(Out):
    public_key: str | None


class PushSubscriptionKeys(StrictModel):
    p256dh: str = Field(min_length=10, max_length=200)
    auth: str = Field(min_length=8, max_length=100)


class PushSubscriptionIn(StrictModel):
    endpoint: str = Field(min_length=10, max_length=1000, pattern=r"^https://")
    keys: PushSubscriptionKeys
    user_agent: str | None = Field(default=None, max_length=300)


class PushUnsubscribeIn(StrictModel):
    endpoint: str = Field(min_length=10, max_length=1000)


# ---- assistant ---------------------------------------------------------------------------------------------------

AssistantAction = Literal["open_reminders", "mark_done", "add_calendar", "open_pets", "open_card", "notifications",
                          "how_to", "bite_help"]


class AssistantStatusOut(Out):
    available: bool
    provider: Literal["gemini", "ollama", "off"]
    shares_with_google: bool  # Gemini free tier: Google may use and human-review prompts


class AssistantMessageIn(StrictModel):
    role: Literal["user", "assistant"]
    text: str = Field(min_length=1, max_length=1000)


class AssistantIn(StrictModel):
    messages: list[AssistantMessageIn] = Field(min_length=1, max_length=12)
    language: Literal["en", "hi", "ta"] = "en"


class AssistantOut(Out):
    reply: str
    actions: list[AssistantAction]
    guarded: bool  # true when a safety rule replaced or limited the answer


class ConfirmEmailIn(StrictModel):
    token: str = Field(min_length=20, max_length=100)


class ConfirmEmailOut(Out):
    confirmed: bool


# ---- certificate OCR ---------------------------------------------------------------------------------------------

class OcrStatusOut(Out):
    available: bool
    engine: Literal["tesseract", "gemini", "off"]
    languages: list[str]
    reason: str | None


class CertificateDraftOut(Out):
    media_id: UUID
    engine: Literal["tesseract", "gemini"]
    languages: list[str]
    administered_on: date | None
    next_due_on: date | None
    product_id: UUID | None
    product_text: str | None
    lot_text: str | None
    confidence: float | None
    warnings: list[str]


# ---- lost pets ---------------------------------------------------------------------------------------------------

class LostReportIn(StrictModel):
    last_seen_on: date | None = None
    area_text: str | None = Field(default=None, max_length=120)
    note: str | None = Field(default=None, max_length=300)


class LostMessageOut(Out):
    sender: Literal["finder", "owner"]
    body: str
    created_at: datetime


class LostThreadOut(Out):
    id: UUID
    finder_contact: str | None
    created_at: datetime
    unread: int
    messages: list[LostMessageOut]


class LostReportOut(Out):
    report_id: UUID
    pet_id: UUID
    pet_name: str
    state: Literal["open", "found", "cancelled"]
    last_seen_on: date | None
    area_text: str | None
    note: str | None
    created_at: datetime
    threads: list[LostThreadOut]


class MessageIn(StrictModel):
    message: str = Field(min_length=1, max_length=500)


class FinderStartIn(StrictModel):
    message: str = Field(min_length=1, max_length=500)
    contact: str | None = Field(default=None, max_length=120)


class FinderStartOut(Out):
    conversation_token: str  # the finder's private link: /found/<token>


class LostStatusOut(Out):
    lost: bool
    last_seen_on: date | None
    area_text: str | None


class FinderThreadOut(Out):
    pet_name: str
    species: str
    clinic: str
    is_demo: bool
    open: bool
    found: bool
    messages: list[LostMessageOut]
