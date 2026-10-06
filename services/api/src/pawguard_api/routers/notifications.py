"""Notification settings (own), test messages, and the clinic's delivery overview."""

from uuid import UUID

from fastapi import APIRouter, Response

from pawguard_api.deps import CurrentOrg, CurrentPrincipal
from pawguard_api.domain import notifications, whatsapp_demo
from pawguard_api.notify_contracts import (
    ConfirmEmailIn,
    ConfirmEmailOut,
    NotificationSettingsIn,
    NotificationSettingsOut,
    NotificationsOverviewOut,
    PushKeyOut,
    PushSubscriptionIn,
    PushUnsubscribeIn,
    ScanOut,
    TestMessageIn,
    WhatsAppDemoOut,
    WhatsAppDemoQueuedOut,
)
from pawguard_api.settings import get_settings

router = APIRouter(prefix="/api/v1", tags=["notifications"])


@router.get("/my/notification-settings", response_model=NotificationSettingsOut, summary="My notification settings")
def get_settings_(p: CurrentPrincipal) -> NotificationSettingsOut:
    """Permission: any signed-in user, own settings only."""
    return NotificationSettingsOut(**notifications.get_prefs(p))


@router.put("/my/notification-settings", response_model=NotificationSettingsOut,
            summary="Turn email, push or WhatsApp reminders on or off")
def put_settings(body: NotificationSettingsIn, p: CurrentPrincipal) -> NotificationSettingsOut:
    """Permission: any signed-in user, own settings only. Every channel is opt-in."""
    return NotificationSettingsOut(**notifications.update_prefs(p, body.model_dump()))


@router.post("/my/notification-settings/test", status_code=202, summary="Send myself a test message")
def send_test(body: TestMessageIn, ctx: CurrentOrg) -> Response:
    """Permission: any member. At most 5 test messages an hour. Sent by the worker within about 15 seconds."""
    with ctx.tx() as db:
        notifications.send_test(db, ctx, body.channel)
    return Response(status_code=202)


@router.get("/clinic/notifications", response_model=NotificationsOverviewOut,
            summary="Provider status and recent deliveries")
def overview(ctx: CurrentOrg) -> NotificationsOverviewOut:
    """Permission: clinic staff. Shows delivery states and provider status (e.g. "token expired"), never addresses."""
    with ctx.tx() as db:
        return NotificationsOverviewOut(**notifications.overview(db, ctx))


@router.post("/clinic/notifications/run", response_model=ScanOut, summary="Queue due reminders now (demo)")
def run_now(ctx: CurrentOrg) -> ScanOut:
    """Permission: clinic staff in a demo organisation with demo mode on. Normally runs every 10 minutes."""
    with ctx.tx() as db:
        return ScanOut(queued=notifications.run_now(db, ctx))


@router.get("/push/public-key", response_model=PushKeyOut, summary="Web Push application server key")
def push_public_key() -> PushKeyOut:
    """Permission: public (the public half of the VAPID key pair). Null when push is not set up."""
    s = get_settings()
    return PushKeyOut(public_key=s.vapid_public_key if notifications.channel_available()["push"] else None)


@router.post("/my/push-subscriptions", status_code=204, summary="Turn on notifications in this browser")
def add_push(body: PushSubscriptionIn, p: CurrentPrincipal) -> Response:
    """Permission: any signed-in user, own subscriptions only. Only known browser push services are accepted."""
    notifications.add_push_subscription(p, body.endpoint, body.keys.p256dh, body.keys.auth, body.user_agent)
    return Response(status_code=204)


@router.post("/my/push-subscriptions/remove", status_code=204, summary="Turn off notifications in this browser")
def remove_push(body: PushUnsubscribeIn, p: CurrentPrincipal) -> Response:
    """Permission: any signed-in user, own subscriptions only."""
    notifications.remove_push_subscription(p, body.endpoint)
    return Response(status_code=204)


@router.post("/my/notification-settings/resend-confirmation", status_code=202,
             summary="Send the email confirmation link again")
def resend_confirmation(p: CurrentPrincipal) -> Response:
    """Permission: any signed-in user, own address only. At most 3 confirmation emails an hour."""
    notifications.resend_verification(p)
    return Response(status_code=202)


@router.post("/notify/confirm-email", response_model=ConfirmEmailOut, summary="Confirm an email address")
def confirm_email(body: ConfirmEmailIn) -> ConfirmEmailOut:
    """Permission: public — the one-time token from the confirmation email is the proof (48 hours)."""
    return ConfirmEmailOut(confirmed=notifications.confirm_email(body.token))


@router.get("/clinic/whatsapp-demo", response_model=WhatsAppDemoOut, summary="Twilio WhatsApp demo: status and history")
def whatsapp_demo_status(ctx: CurrentOrg) -> WhatsAppDemoOut:
    """Permission: clinic staff in the demo organisation with demo mode on. Shows which settings are missing (names
    only), the masked demo recipient, the template preview and recent demo sends with Twilio's delivery status."""
    with ctx.tx() as db:
        return WhatsAppDemoOut(**whatsapp_demo.status(db, ctx))


@router.post("/clinic/whatsapp-demo/test", status_code=202, response_model=WhatsAppDemoQueuedOut,
             summary="Send a test WhatsApp now (demo recipient only)")
def whatsapp_demo_test(ctx: CurrentOrg) -> WhatsAppDemoQueuedOut:
    """Permission: as above. Sent by the worker within about 15 seconds. Refused while another one is waiting."""
    with ctx.tx() as db:
        return WhatsAppDemoQueuedOut(**whatsapp_demo.queue(db, ctx, "test"))


@router.post("/clinic/whatsapp-demo/schedule", status_code=202, response_model=WhatsAppDemoQueuedOut,
             summary="Schedule a demo WhatsApp reminder 2 minutes ahead")
def whatsapp_demo_schedule(ctx: CurrentOrg) -> WhatsAppDemoQueuedOut:
    """Permission: as above. For a fictional pet; no records change. Sent by the server even if the page is closed."""
    with ctx.tx() as db:
        return WhatsAppDemoQueuedOut(**whatsapp_demo.queue(db, ctx, "demo_reminder"))


@router.post("/clinic/whatsapp-demo/{delivery_id}/cancel", status_code=204,
             summary="Cancel a scheduled demo reminder")
def whatsapp_demo_cancel(delivery_id: UUID, ctx: CurrentOrg) -> Response:
    """Permission: as above. Only before it has been sent."""
    with ctx.tx() as db:
        whatsapp_demo.cancel(db, ctx, str(delivery_id))
    return Response(status_code=204)
