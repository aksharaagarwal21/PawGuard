"""Provider webhooks (public; authenticated by the provider's signature, not by a session)."""

import hmac
import json
from typing import Annotated
from urllib.parse import parse_qsl
from uuid import UUID

from fastapi import APIRouter, Header, Query, Request, Response
from sqlalchemy import text

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


@router.post("/twilio/gather", summary="Phone-call keypad answer (Twilio)", response_class=Response)
async def twilio_gather(request: Request, d: Annotated[str, Query(max_length=40)],
                        signature: Annotated[str | None, Header(alias="X-Twilio-Signature")] = None) -> Response:
    """Permission: public, but the request must carry Twilio's signature (checked with Twilio's own validator
    against the public address Twilio called). 1 = "I'll book a visit"; 2 = remind again in 3 days."""
    from twilio.request_validator import RequestValidator

    s = get_settings()
    raw = await request.body()
    if len(raw) > 20_000:
        raise Forbidden("Invalid request.", code="webhook_signature_invalid")
    form = dict(parse_qsl(raw.decode("utf-8", "replace"), keep_blank_values=True))  # Twilio posts URL-encoded forms
    public_url = f"{s.public_app_url}/api/v1/webhooks/twilio/gather?d={d}"
    if not (s.twilio_auth_token and signature and RequestValidator(s.twilio_auth_token).validate(
            public_url, form, signature)):
        raise Forbidden("Invalid signature.", code="webhook_signature_invalid")
    digit = form.get("Digits", "")
    try:
        delivery = str(UUID(d))
    except ValueError:
        delivery = ""
    ok = False
    if delivery and digit in ("1", "2"):
        with public_tx() as db:
            ok = bool(db.execute(text("select app.record_call_reply(:d, :g)"), {"d": delivery, "g": digit}).scalar())
    say = {"1": "Thank you. Please book your visit with the clinic. Goodbye.",
           "2": "OK. We will remind you again in 3 days. Goodbye."}.get(digit if ok else "", "Goodbye.")
    return Response(f"<Response><Say>{say}</Say></Response>", media_type="text/xml")


@router.post("/twilio/status", summary="WhatsApp delivery status (Twilio)", status_code=204)
async def twilio_status(request: Request,
                        signature: Annotated[str | None, Header(alias="X-Twilio-Signature")] = None) -> Response:
    """Permission: public, but the request must carry Twilio's signature, checked with Twilio's own validator against
    the exact public address we gave Twilio as StatusCallback. Status only moves forward (late or repeated callbacks
    never undo "delivered" or "read")."""
    from twilio.request_validator import RequestValidator

    s = get_settings()
    raw = await request.body()
    if len(raw) > 20_000:
        raise Forbidden("Invalid request.", code="webhook_signature_invalid")
    form = dict(parse_qsl(raw.decode("utf-8", "replace"), keep_blank_values=True))
    public_url = f"{s.public_app_url}/api/v1/webhooks/twilio/status"
    if not (s.twilio_auth_token and signature and RequestValidator(s.twilio_auth_token).validate(
            public_url, form, signature)):
        raise Forbidden("Invalid signature.", code="webhook_signature_invalid")
    sid, status = form.get("MessageSid", ""), form.get("MessageStatus", "")
    n = 0
    if form.get("AccountSid") == s.twilio_account_sid and sid and status in notify.TWILIO_STATUSES:
        with public_tx() as db:
            n = int(db.execute(text("select app.record_twilio_status(:s, :st, :e)"),
                               {"s": sid[:64], "st": status, "e": (form.get("ErrorCode") or None)}).scalar() or 0)
    log.info("twilio_status_webhook", status=status, updated=n)
    return Response(status_code=204)


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
