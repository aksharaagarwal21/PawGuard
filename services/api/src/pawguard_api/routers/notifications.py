"""Notification settings (own), test messages, and the clinic's delivery overview."""

from fastapi import APIRouter, Response

from pawguard_api.deps import CurrentOrg, CurrentPrincipal
from pawguard_api.domain import notifications
from pawguard_api.notify_contracts import (
    NotificationSettingsIn,
    NotificationSettingsOut,
    NotificationsOverviewOut,
    ScanOut,
    TestMessageIn,
)

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
