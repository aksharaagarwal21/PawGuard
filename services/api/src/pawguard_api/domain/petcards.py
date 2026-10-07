"""Pet vaccination card: a random, revocable token behind a QR code, a PDF, and a public status page.

The public card shows only the pet's name, species, photo, the clinic's name and *verified* vaccinations (vaccine,
date given, next due date). Nothing about the owner or any location. Revoking or regenerating the token makes old
QR codes stop working at once. The card shows recorded vaccinations; it is not a health guarantee.
"""

import io
import secrets
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

import segno
from fpdf import FPDF
from sqlalchemy import text

from pawguard_api.auth import Principal
from pawguard_api.db import public_tx
from pawguard_api.domain import credentials, petcare, reminders
from pawguard_api.domain.common import record_audit
from pawguard_api.errors import NotFound, Unprocessable
from pawguard_api.pet_contracts import CardOut, PetStatusOut, PublicCardOut, PublicVaccinationOut

DISCLAIMER = "This card shows recorded vaccinations. It is not a health guarantee."


def card_path(token: str) -> str:
    return f"/card/{token}"


def _base(base_url: str | None) -> str:
    if base_url is None:
        return ""
    b = base_url.rstrip("/")
    if not (b.startswith(("http://", "https://")) and len(b) <= 200 and b.count("/") == 2):
        raise Unprocessable("Invalid base URL.", code="invalid_base_url")
    return b


def _qr_svg(url: str) -> str:
    buf = io.BytesIO()
    # No <title>: the page wraps the SVG in one labelled image for screen readers.
    segno.make(url, error="m").save(buf, kind="svg", scale=6, border=2, xmldecl=False, svgns=True)
    return buf.getvalue().decode("utf-8")


def _live_card(db: Any, ctx: Any, animal_id: UUID, *, regenerate: bool) -> Any:
    live = db.execute(text("select token, created_at from app.pet_cards where animal_id = :a and revoked_at is null"),
                      {"a": animal_id}).one_or_none()
    if live is not None and not regenerate:
        return live
    if live is not None:
        db.execute(text("update app.pet_cards set revoked_at = now() where animal_id = :a and revoked_at is null"),
                   {"a": animal_id})
    row = db.execute(text("""insert into app.pet_cards (org_id, animal_id, token, created_by)
                             values (:o, :a, :t, :u) returning token, created_at"""),
                     {"o": ctx.org_id, "a": animal_id, "t": petcare_token(), "u": ctx.user_id}).one()
    record_audit(db, ctx, "pet_card.regenerated" if live is not None else "pet_card.created", "animal", animal_id, {})
    return row


def petcare_token() -> str:
    return secrets.token_urlsafe(32)  # 256 bits; never derived from the pet or owner


def owner_card(p: Principal, animal_id: UUID, base_url: str | None, *, regenerate: bool = False,
               request_id: str | None = None) -> CardOut:
    base = _base(base_url)
    ctx = petcare.owned_context(p, animal_id, request_id)
    with ctx.tx() as db:
        row = _live_card(db, ctx, animal_id, regenerate=regenerate)
    path = card_path(row.token)
    return CardOut(token=row.token, url_path=path, qr_svg=_qr_svg(base + path), created_at=row.created_at)


def revoke(p: Principal, animal_id: UUID, request_id: str | None = None) -> None:
    ctx = petcare.owned_context(p, animal_id, request_id)
    with ctx.tx() as db:
        n = db.execute(text("update app.pet_cards set revoked_at = now() where animal_id = :a and revoked_at is null"),
                       {"a": animal_id}).rowcount
        if n:
            record_audit(db, ctx, "pet_card.revoked", "animal", animal_id, {})


def public_card(token: str, *, with_photo: bool = True) -> PublicCardOut:
    if not (32 <= len(token) <= 100):
        raise NotFound("Card not found.", code="card_not_found")
    with public_tx() as db:
        rows = db.execute(text("select * from app.public_card(:t)"), {"t": token}).all()
    if not rows:
        raise NotFound("Card not found.", code="card_not_found")  # unknown or revoked: same answer
    first = rows[0]
    today = datetime.now(ZoneInfo(first.timezone)).date() + timedelta(days=first.offset_days)
    records = [reminders.Record("verified", r.vaccine, r.administered_on, r.next_due_on, r.next_due_source)
               for r in rows if r.vaccine is not None]
    status = reminders.pet_status(records, today) if records else PetStatusOut(status="no_verified_record")
    latest = reminders.latest_verified(records)
    photo_url = None
    if with_photo and first.photo_key:
        from pawguard_api.integrations.storage import get_storage

        try:
            photo_url = get_storage().signed_download_urls([first.photo_key]).get(first.photo_key)
        except Exception:
            photo_url = None
    return PublicCardOut(
        pet_name=first.animal_name, species=first.species, photo_url=photo_url, clinic_name=first.clinic_name,
        status=status, is_demo=first.is_demo,
        vaccinations=[PublicVaccinationOut(vaccine=r.vaccine, administered_on=r.administered_on,
                                           next_due_on=r.next_due_on)
                      for r in sorted(latest.values(), key=lambda r: r.vaccine)],
        disclaimer=DISCLAIMER)


# ---- PDF ---------------------------------------------------------------------------------------------------------

FONTS = Path(__file__).resolve().parent.parent / "fonts"  # Noto Sans (SIL Open Font License, fonts/OFL.txt)


def _pdf(**kw: Any) -> FPDF:
    """A PDF with Noto Sans embedded: Latin, Tamil and Devanagari (fallback fonts), shaped with HarfBuzz so Tamil and
    Hindi names print correctly instead of "?"."""
    pdf = FPDF(**kw)
    for family, stem in (("Noto", "NotoSans"), ("NotoTamil", "NotoSansTamil"), ("NotoDeva", "NotoSansDevanagari")):
        pdf.add_font(family, "", str(FONTS / f"{stem}-Regular.ttf"))
        pdf.add_font(family, "B", str(FONTS / f"{stem}-Bold.ttf"))
    pdf.set_fallback_fonts(["NotoTamil", "NotoDeva"])
    pdf.set_text_shaping(True)
    return pdf


def _latin(s: str) -> str:
    """Kept for call sites: with Unicode fonts embedded, text is printed as is."""
    return s


STATUS_TEXT = {"up_to_date": "Up to date", "due_soon": "Due soon", "overdue": "Overdue",
               "unverified_record": "Entered by owner (unverified)", "no_verified_record": "No verified record"}


def owner_card_pdf(p: Principal, animal_id: UUID, base_url: str | None, request_id: str | None = None) -> bytes:
    card = owner_card(p, animal_id, base_url, request_id=request_id)
    data = public_card(card.token, with_photo=False)
    url = _base(base_url) + card.url_path
    pdf = _pdf(format="A5", orientation="portrait")
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.add_page()
    pdf.set_title(_latin(f"Vaccination card - {data.pet_name}"))
    if data.is_demo:  # one quiet line, not a banner
        pdf.set_font("Noto", "", 7)
        pdf.set_text_color(110, 110, 110)
        pdf.cell(0, 4, "Sample data", new_x="LMARGIN", new_y="NEXT", align="R")
        pdf.set_text_color(0, 0, 0)
    pdf.set_font("Noto", "B", 18)
    pdf.cell(0, 10, _latin(data.pet_name), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Noto", "", 10)
    pdf.cell(0, 6, _latin(f"{data.species.capitalize()} - {data.clinic_name}"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Noto", "B", 11)
    pdf.cell(0, 8, _latin(f"Status: {STATUS_TEXT[data.status.status]}"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    pdf.set_font("Noto", "B", 9)
    widths = (62, 33, 33)
    for w, h in zip(widths, ("Vaccine (verified by vet)", "Given on", "Next due"), strict=True):
        pdf.cell(w, 7, h, border="B")
    pdf.ln()
    pdf.set_font("Noto", "", 9)
    if not data.vaccinations:
        pdf.cell(0, 7, "No verified record.", new_x="LMARGIN", new_y="NEXT")
    for v in data.vaccinations:
        pdf.cell(widths[0], 7, _latin(v.vaccine)[:40])
        pdf.cell(widths[1], 7, f"{v.administered_on:%d %b %Y}" if v.administered_on else "-")
        pdf.cell(widths[2], 7, f"{v.next_due_on:%d %b %Y}" if v.next_due_on else "-")
        pdf.ln()
    pdf.ln(4)
    png = io.BytesIO()
    segno.make(url, error="m").save(png, kind="png", scale=8, border=2)
    png.seek(0)
    top = pdf.get_y()
    pdf.image(png, x=pdf.l_margin, y=top, w=40)
    pdf.set_xy(pdf.l_margin, top + 41)
    pdf.set_font("Noto", "B", 8)
    pdf.cell(40, 4, "Scan for this pet's page", align="C")
    signed = _signed_rabies(p, animal_id, request_id)
    if signed:
        pdf.image(credentials.qr_png(signed["qr_text"], scale=6), x=pdf.l_margin + 52, y=top, w=46)
        pdf.set_xy(pdf.l_margin + 52, top + 47)
        pdf.cell(46, 4, "Scan to verify this certificate", align="C")
        pdf.set_xy(pdf.l_margin + 102, top)
        pdf.set_font("Noto", "", 7.5)
        pdf.multi_cell(0, 3.8, f"Signed by the clinic: {signed['vaccine']}, given {signed['given']}. "
                               "Check it at /verify (works offline). The signature shows a registered clinic issued "
                               "this record and that it was not changed — not that the pet is healthy.", align="L")
    pdf.set_xy(pdf.l_margin, top + 54)
    pdf.set_font("Noto", "", 8)
    pdf.multi_cell(0, 4.5, f"Pet page (current status): {url}", new_x="LMARGIN", new_y="NEXT", align="L")
    pdf.ln(2)
    pdf.set_font("Noto", "B", 9)
    pdf.multi_cell(0, 5, DISCLAIMER, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Noto", "", 8)
    pdf.multi_cell(0, 4.5, "Only vaccinations verified by a vet are listed. Owner-entered (unverified) records are "
                           "never signed. PawGuard only reminds; your vet decides treatment.",
                   new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


def _signed_rabies(p: Principal, animal_id: UUID, request_id: str | None) -> dict[str, str] | None:
    """The latest verified rabies vaccination's signed QR text, if one has been issued."""
    ctx = petcare.owned_context(p, animal_id, request_id)
    with ctx.tx() as db:
        certs = credentials.pet_certificates(db, animal_id)
    item = next((i for i in certs["items"] if i["event_id"] == certs["featured_event_id"]), None)
    if not item or not item["qr_text"]:
        return None
    return {"qr_text": item["qr_text"], "vaccine": item["vaccine"] or "",
            "given": f"{item['administered_on']:%d %b %Y}" if item["administered_on"] else "-"}


def owner_tags_pdf(p: Principal, animal_id: UUID, base_url: str | None, request_id: str | None = None) -> bytes:
    """Printable QR collar tags: an A4 sheet of 16 tags (45 x 62 mm) to cut out and laminate. Each QR opens the
    pet's public vaccination card; making a new QR code (or turning the card off) makes printed tags stop working."""
    card = owner_card(p, animal_id, base_url, request_id=request_id)
    data = public_card(card.token, with_photo=False)
    url = _base(base_url) + card.url_path
    png = io.BytesIO()
    segno.make(url, error="q").save(png, kind="png", scale=10, border=1)
    pdf = _pdf(format="A4", orientation="portrait")
    pdf.set_auto_page_break(auto=False)
    pdf.add_page()
    pdf.set_font("Noto", "B", 12)
    pdf.cell(0, 7, _latin(f"PawGuard collar tags - {data.pet_name}"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Noto", "", 8)
    pdf.multi_cell(0, 4, "Print at 100% scale, cut along the dashed lines and laminate. The QR code shows only the "
                         "pet's name, photo, clinic and vaccinations verified by a vet - never your contact details. "
                         "Making a new QR code in the app makes these tags stop working."
                   + ("  Sample data." if data.is_demo else ""), new_x="LMARGIN", new_y="NEXT")
    top, left, w, h, cols, rows = 30.0, 12.5, 45.0, 62.0, 4, 4
    pdf.set_draw_color(150, 150, 150)
    pdf.set_dash_pattern(dash=1.5, gap=1.5)
    for r in range(rows):
        for c in range(cols):
            x, y = left + c * (w + 1.5), top + r * (h + 2.0)
            pdf.rect(x, y, w, h)
            png.seek(0)
            pdf.image(png, x=x + 5.5, y=y + 3, w=34)
            pdf.set_xy(x, y + 39)
            pdf.set_font("Noto", "B", 10)
            pdf.cell(w, 5, _latin(data.pet_name)[:22], align="C")
            pdf.set_xy(x, y + 45)
            pdf.set_font("Noto", "", 7)
            pdf.multi_cell(w, 3.4, "Scan for this pet's\nvaccination card\nPawGuard 360", align="C")
    pdf.set_dash_pattern()
    return bytes(pdf.output())
