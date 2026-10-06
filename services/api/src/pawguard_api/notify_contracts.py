"""API shapes for notification settings, test messages and the staff delivery overview."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from pawguard_api.contracts import Out, StrictModel

ChannelName = Literal["email", "push", "whatsapp"]


class ChannelsAvailableOut(Out):
    email: bool
    push: bool
    whatsapp: bool


class NotificationSettingsOut(Out):
    email_enabled: bool
    email_address: str | None
    push_enabled: bool
    push_devices: int
    whatsapp_enabled: bool
    whatsapp_number: str | None
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
    kind: Literal["vaccination_reminder", "test"]
    state: Literal["queued", "sending", "sent", "deferred", "failed", "skipped"]
    pet_name: str | None
    created_at: datetime
    sent_at: datetime | None
    last_error: str | None


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
