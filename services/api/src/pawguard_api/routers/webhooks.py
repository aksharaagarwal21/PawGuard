"""Provider webhooks (public; authenticated by the provider's signature, not by a session)."""

import hmac
import json
from typing import Annotated

from fastapi import APIRouter, Header, Query, Request, Response

from pawguard_api.db import public_tx
from pawguard_api.domain import notifications
from pawguard_api.errors import Forbidden
from pawguard_api.integrations import notify
from pawguard_api.logging import get_logger
from pawguard_api.settings import get_settings

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])
log = get_logger(__name__)


@router.get("/whatsapp", summary="WhatsApp webhook verification", response_class=Response)
def whatsapp_verify(mode: Annotated[str | None, Query(alias="hub.mode")] = None,
                    token: Annotated[str | None, Query(alias="hub.verify_token")] = None,
                    challenge: Annotated[str | None, Query(alias="hub.challenge", max_length=200)] = None) -> Response:
    """Permission: public. Meta calls this once when you save the webhook; we echo the challenge only when the
    verify token matches PAWGUARD_WHATSAPP_VERIFY_TOKEN."""
    expected = get_settings().whatsapp_verify_token
    if mode == "subscribe" and expected and token and hmac.compare_digest(token, expected) and challenge:
        return Response(challenge, media_type="text/plain")
    raise Forbidden("Verification failed.", code="webhook_verification_failed")


@router.post("/whatsapp", summary="WhatsApp delivery receipts")
async def whatsapp_receive(request: Request,
                           signature: Annotated[str | None, Header(alias="X-Hub-Signature-256")] = None) -> Response:
    """Permission: public, but the body must carry Meta's HMAC-SHA256 signature (app secret). Records failed
    deliveries; stores no message content."""
    raw = await request.body()
    if len(raw) > 512_000 or not notify.whatsapp_signature_valid(get_settings(), raw, signature):
        raise Forbidden("Invalid signature.", code="webhook_signature_invalid")
    try:
        payload = json.loads(raw)
    except ValueError:
        return Response(status_code=200)  # acknowledge; nothing usable
    with public_tx() as db:
        n = notifications.whatsapp_receipts(db, payload)
    log.info("whatsapp_webhook", receipts_updated=n)
    return Response(status_code=200)
