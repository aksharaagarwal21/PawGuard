"""AI-assisted evidence check for the verification workbench.

For each certificate attached to a vaccination record:
1. Signed PawGuard certificate: finds a QR code in the image (OpenCV) and, if it is a `PG1:` certificate, verifies its
   signature against the trust list, the key's validity and the revocation list — and compares it with the record.
2. Reading: the certificate is read (OCR / Gemini vision for sample clinics) into fields that are compared with what was
   entered: date given, vaccine and batch.
3. Reuse: the same file attached to another vaccination record is flagged.

These checks assist the vet; they never verify or reject anything on their own, and they can be wrong.
"""

import io
import re
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import text

from pawguard_api.capabilities import Cap
from pawguard_api.deps import OrgContext
from pawguard_api.domain import certificates
from pawguard_api.errors import Forbidden, NotFound
from pawguard_api.integrations import cose, ocr
from pawguard_api.logging import get_logger
from pawguard_api.settings import get_settings

log = get_logger(__name__)
MAX_BYTES = 15 * 1024 * 1024


def _check(kind: str, status: str, message: str, **extra: Any) -> dict[str, Any]:
    """status: ok | warn | bad | info | unavailable."""
    return {"kind": kind, "status": status, "message": message, **extra}


# ---- image ---------------------------------------------------------------------------------------------------------

def page_image(media: Any) -> bytes | None:
    """JPEG of the certificate: the photo's display copy, or page 1 of a PDF rendered at ~200 dpi."""
    from pawguard_api.integrations.storage import get_storage

    derivatives = media.derivatives or {}
    if media.detected_mime == "application/pdf":
        key = derivatives.get("original")
        if not key:
            return None
        import pypdfium2 as pdfium  # BSD/Apache; renders PDFs without external programs

        pdf = pdfium.PdfDocument(get_storage().download(key, MAX_BYTES))
        try:
            pil = pdf[0].render(scale=200 / 72).to_pil().convert("RGB")
        finally:
            pdf.close()
        buf = io.BytesIO()
        pil.save(buf, "JPEG", quality=92)
        return buf.getvalue()
    key = derivatives.get("display")
    return get_storage().download(key, MAX_BYTES) if key else None


def find_qr(image: bytes) -> str | None:
    """A QR code's text from the image, preferring a signed PawGuard certificate (`PG1:`) when the page has several
    (the PawGuard PDF card has a link QR and a certificate QR). Several passes: as is, grey, enlarged."""
    import cv2
    import numpy as np
    from PIL import Image, UnidentifiedImageError

    # Decoding and resizing with Pillow; OpenCV only looks for QR codes. Inside the API process OpenCV's own image
    # functions and thread pool failed with "Unknown C++ exception" (other native libraries share the process), so
    # its threading is off and any OpenCV failure only skips that pass.
    cv2.setNumThreads(0)
    try:
        with Image.open(io.BytesIO(image)) as pil:
            pil.load()
            grey_pil = pil.convert("L")
    except (UnidentifiedImageError, OSError):
        return None
    grey = np.asarray(grey_pil)
    big = np.asarray(grey_pil.resize((grey_pil.width * 2, grey_pil.height * 2), Image.Resampling.BICUBIC))
    candidates = [grey, big]
    detectors = [cv2.QRCodeDetector()]
    if hasattr(cv2, "QRCodeDetectorAruco"):
        detectors.append(cv2.QRCodeDetectorAruco())
    found: list[str] = []
    for det in detectors:
        for candidate in candidates:
            try:
                ok, texts, _pts, _ = det.detectAndDecodeMulti(candidate)
            except Exception as exc:  # cv2.error or a native failure: try the next pass
                log.info("evidence_qr_pass_failed", error=type(exc).__name__)
                continue
            found.extend(str(t) for t in (texts if ok else []) if t)
            signed = next((t for t in found if t.strip().startswith(cose.PREFIX)), None)
            if signed:
                return signed
    return found[0] if found else None


# ---- signed certificate --------------------------------------------------------------------------------------------

def verify_signed(db: Any, qr: str) -> dict[str, Any]:
    """Server-side check of a `PG1:` certificate (same rules as the offline verifier)."""
    try:
        msg = cose.parse_sign1(cose.from_qr_text(qr))
    except cose.InvalidCertificate:
        return {"status": "unreadable"}
    key = db.execute(text("select * from app.trust_keys() where kid = :k"), {"k": msg.kid.hex()}).first()
    if key is None:
        return {"status": "unknown_clinic"}
    if key.status == "revoked":
        return {"status": "key_revoked", "clinic": key.org_name}
    if not cose.verify_sign1(msg, bytes(key.public_key)):
        return {"status": "altered", "clinic": key.org_name}
    p = msg.payload
    issued = datetime.fromtimestamp(int(p[7]), UTC)
    skew = timedelta(minutes=5)  # same tolerance as the offline verifier (issue times are whole seconds)
    if issued < key.valid_from - skew or (key.valid_to is not None and issued > key.valid_to + skew):
        return {"status": "outside_validity", "clinic": key.org_name}
    cid = UUID(bytes=bytes(p[2]))
    revoked = db.execute(text("select 1 from app.revoked_credentials() where id = :i"), {"i": cid}).scalar()
    cert = {"pet_reference": p[3].get(1), "pet_name": p[3].get(2), "vaccine": p[4].get(1), "given_on": p[4].get(3),
            "next_due_on": p[4].get(4), "clinic": p[5].get(2), "vet": p[6]}
    return {"status": "revoked" if revoked else "genuine", "clinic": key.org_name, "certificate": cert}


CARD_LINK = re.compile(r"/card/([A-Za-z0-9_-]{32,100})")


def _pet_card(db: Any, qr: str) -> dict[str, str] | None:
    """A PawGuard pet-card QR (link to /card/<token>) of this clinic: which pet it belongs to."""
    m = CARD_LINK.search(qr)
    if not m:
        return None
    row = db.execute(text("""select c.animal_id, coalesce(a.nickname, a.reference_code) as name
                             from app.pet_cards c join app.animals a on a.id = c.animal_id
                             where c.token = :t"""), {"t": m.group(1)}).first()
    return {"animal_id": str(row.animal_id), "name": row.name} if row else None


SIGNED_TEXT = {
    "genuine": ("ok", "Signed PawGuard certificate: genuine — issued by {clinic} and not changed."),
    "revoked": ("warn", "Signed PawGuard certificate from {clinic}, but the clinic has cancelled or replaced it."),
    "altered": ("bad", "Signed PawGuard QR found, but the certificate was changed after signing (signature does not "
                       "match)."),
    "unknown_clinic": ("bad", "Signed QR found, but it was not issued by a clinic in the PawGuard trust list."),
    "key_revoked": ("bad", "Signed QR found, but {clinic}'s signing key was withdrawn — treat it as untrusted."),
    "outside_validity": ("bad", "Signed QR found, but it was signed outside the period the clinic's key was valid."),
    "unreadable": ("warn", "A PawGuard-style QR was found but could not be read."),
}


# ---- comparison --------------------------------------------------------------------------------------------------

def _norm(s: str | None) -> str:
    return "".join(ch for ch in (s or "").lower() if ch.isalnum())


def compare(event: Any, read: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    given: date | None = read.get("administered_on")
    if given is None:
        out.append(_check("date", "warn", "Date given: not found on the document — it may not be a vaccination "
                                          "certificate."))
    elif event.administered_on is None:
        out.append(_check("date", "info", f"Certificate shows the date given as {given:%d %b %Y}; none was entered."))
    elif given == event.administered_on:
        out.append(_check("date", "ok", f"Date given matches the certificate ({given:%d %b %Y})."))
    else:
        out.append(_check("date", "bad", f"Date given differs: certificate shows {given:%d %b %Y}, record says "
                                         f"{event.administered_on:%d %b %Y}."))
    product = read.get("product_text")
    entered = event.product_name or event.product_text
    if not product:
        out.append(_check("vaccine", "warn", "Vaccine: not found on the document."))
    elif entered and (str(read.get("product_id")) == str(event.product_id) or _norm(product) in _norm(entered)
                      or _norm(entered).startswith(_norm(product)[:6])):
        out.append(_check("vaccine", "ok", f"Vaccine matches the certificate ({product})."))
    else:
        out.append(_check("vaccine", "warn", f"Vaccine differs: certificate mentions “{product}”, record says "
                                             f"“{entered or 'not recorded'}”."))
    lot_read, lot_entered = read.get("lot_text"), event.lot_number or event.lot_text
    if lot_read and lot_entered:
        same = _norm(lot_read) == _norm(lot_entered)
        out.append(_check("batch", "ok" if same else "warn",
                          f"Batch matches ({lot_read})." if same else
                          f"Batch differs: certificate shows {lot_read}, record says {lot_entered}."))
    elif lot_read:
        out.append(_check("batch", "info", f"Certificate shows batch {lot_read}; none was entered."))
    return out


# ---- the check ---------------------------------------------------------------------------------------------------

_EVENT = """
select e.id, e.animal_id, e.administered_on, e.product_id, e.product_text, e.lot_text, p.name as product_name,
       l.lot_number, a.reference_code as animal_reference, a.nickname
  from app.animal_vaccination_events e
  join app.animals a on a.id = e.animal_id
  left join app.vaccine_products p on p.id = e.product_id
  left join app.vaccine_lots l on l.id = e.lot_id
 where e.id = :e"""


def check_event(db: Any, ctx: OrgContext, event_id: UUID) -> dict[str, Any]:
    if not (ctx.can(Cap.VACCINATION_REVIEW) or ctx.can(Cap.ANIMAL_READ)):
        raise Forbidden("Clinic staff only.", code="staff_only")
    event = db.execute(text(_EVENT), {"e": event_id}).first()
    if event is None:
        raise NotFound("Vaccination record not found.", code="vaccination_event_not_found")
    s = get_settings()
    media_rows = db.execute(text("""
        select m.id, m.state, m.detected_mime, m.derivatives, m.sha256
          from app.vaccination_evidence ve join app.media_assets m on m.id = ve.media_id
         where ve.event_id = :e order by m.created_at"""), {"e": event_id}).all()
    files = []
    for m in media_rows:
        checks: list[dict[str, Any]] = []
        kind = "pdf" if m.detected_mime == "application/pdf" else "photo"
        if m.state != "approved":
            files.append({"media_id": m.id, "kind": kind, "checks": [
                _check("file", "info", "The file is still being processed — check again in a moment.")]})
            continue
        try:
            image = page_image(m)
        except Exception as exc:  # unreadable PDF or storage hiccup: say so, keep the other checks
            log.warning("evidence_image_failed", error=type(exc).__name__)
            image = None
        # 1. Signed PawGuard certificate
        try:
            qr = find_qr(image) if image else None
        except Exception as exc:  # QR reading is one pass of several; the others still run
            log.warning("evidence_qr_failed", error=type(exc).__name__)
            qr = None
        if qr and qr.strip().startswith(cose.PREFIX):
            result = verify_signed(db, qr)
            status, template = SIGNED_TEXT[result["status"]]
            checks.append(_check("signature", status, template.format(clinic=result.get("clinic") or "a clinic"),
                                 certificate=result.get("certificate")))
            cert = result.get("certificate")
            if cert and result["status"] in ("genuine", "revoked"):
                if cert["pet_reference"] != event.animal_reference:
                    checks.append(_check("signature", "bad", f"The signed certificate is for another pet "
                                                             f"({cert['pet_name'] or cert['pet_reference']})."))
                elif event.administered_on and cert["given_on"] != event.administered_on.isoformat():
                    checks.append(_check("signature", "warn", "The signed certificate shows a different date given "
                                                              f"({cert['given_on']})."))
        elif qr and (card := _pet_card(db, qr)) is not None:
            if card["animal_id"] != str(event.animal_id):
                checks.append(_check("signature", "bad", f"This is the PawGuard pet card of another pet "
                                                         f"({card['name']}), not a vaccination certificate."))
            else:
                checks.append(_check("signature", "warn", "This is the pet's own PawGuard card, not a vaccination "
                                                          "certificate from a vet."))
        elif qr and "/card/" in qr:
            checks.append(_check("signature", "warn", "This document shows a PawGuard pet-card QR from another clinic "
                                                      "or an old card — it is not a vaccination certificate."))
        elif qr:
            checks.append(_check("signature", "info", "A QR code was found, but it is not a signed PawGuard "
                                                      "certificate."))
        else:
            checks.append(_check("signature", "info", "No signed PawGuard QR on this certificate (most paper "
                                                      "certificates have none)."))
        # 2. Reading and comparison
        stored = db.execute(text("select * from app.certificate_drafts where media_id = :m"), {"m": m.id}).first()
        read: dict[str, Any] | None = None
        if stored is not None:
            read = {"administered_on": stored.administered_on, "product_text": stored.product_text,
                    "product_id": stored.product_id, "lot_text": stored.lot_text, "engine": stored.engine}
        elif image is not None and ocr.status(s).get("available"):
            try:
                draft = certificates.draft_from_image(db, ctx, m.id, image, s)
                read = {**draft, "engine": draft["engine"]}
            except Exception as exc:  # reading is optional; the vet can still compare by eye
                log.warning("evidence_read_failed", error=type(exc).__name__)
                checks.append(_check("reading", "unavailable", "The certificate could not be read automatically "
                                                               "just now."))
        else:
            checks.append(_check("reading", "unavailable", "Automatic reading is not set up on this server."))
        if read is not None:
            engine = "Gemini" if read.get("engine") == "gemini" else "OCR"
            checks.append(_check("reading", "info", f"Read by {engine} — compare with the image before deciding."))
            checks.extend(compare(event, read))
        # 3. The same file used for another record
        if m.sha256:
            reused = db.execute(text("""
                select distinct a.reference_code, e2.administered_on from app.media_assets m2
                  join app.vaccination_evidence ve2 on ve2.media_id = m2.id
                  join app.animal_vaccination_events e2 on e2.id = ve2.event_id
                  join app.animals a on a.id = e2.animal_id
                 where m2.sha256 = :h and m2.id <> :m and ve2.event_id <> :e limit 5"""),
                                {"h": m.sha256, "m": m.id, "e": event_id}).all()
            if reused:
                refs = ", ".join(r.reference_code for r in reused)
                checks.append(_check("reuse", "bad", f"The same file was already used as evidence for {refs}."))
            else:
                checks.append(_check("reuse", "ok", "This file has not been used for any other record."))
        files.append({"media_id": m.id, "kind": kind, "checks": checks})
    worst = {"bad": 3, "warn": 2, "unavailable": 1, "info": 0, "ok": 0}
    level = max((worst[c["status"]] for f in files for c in f["checks"]), default=0)
    return {"summary": {3: "problems", 2: "check", 1: "partial", 0: "consistent"}[level], "files": files}
