"""Certificate reading: owner-only reads, refusals, no full-text storage, drafts for the vet."""

import uuid
from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from pawguard_api.domain import certificates
from pawguard_api.integrations import ocr
from pawguard_api.settings import get_settings

REAL_EXTRACT = ocr.extract  # kept before fixtures replace it
CERT_TEXT = ("PET VACCINATION CERTIFICATE\nOwner: Private Person, 12 Some Street\n"
             f"Date of vaccination: {(date.today() - timedelta(days=3)):%d/%m/%Y}\n"
             "Vaccine: Anti-Rabies  Batch No: RB2026X\n"
             f"Next due date: {(date.today() + timedelta(days=362)):%d-%m-%Y}")


def _h(t, org=None):
    h = {"Authorization": f"Bearer {t}"}
    if org:
        h["X-PawGuard-Org"] = str(org)
    return h


def _media(owner_engine, org, uploader, *, state="approved", mime="image/jpeg"):
    with owner_engine.begin() as c:
        return c.execute(text("""insert into app.media_assets (org_id, bucket, object_key, purpose, declared_mime,
                                 detected_mime, declared_bytes, state, uploader_user_id, derivatives)
                                 values (:o, 'media', :k, 'vaccination_evidence', :m, :m, 1000, :s, :u,
                                         cast(:d as jsonb)) returning id"""),
                         {"o": org, "k": f"t/{uuid.uuid4()}", "m": mime, "s": state, "u": uploader,
                          "d": '{"display": "t/display.jpg"}'}).scalar_one()


@pytest.fixture
def owner(world, make_token, owner_engine, client, monkeypatch):
    org = world.org("OCR clinic", demo=False)
    a, b = world.member(org, "resident"), world.member(org, "resident")
    vet = world.member(org, "veterinary_reviewer")
    world.approve(org, vet)
    tok = {k: make_token(u, session_id=world.session(u)) for k, u in {"a": a, "b": b, "vet": vet}.items()}
    with owner_engine.begin() as c:
        product = c.execute(text("insert into app.vaccine_products (org_id, name, species) values "
                                 "(:o, 'Rabies vaccine (ocr)', '{dog}') returning id"), {"o": org}).scalar_one()
    pet = client.post("/api/v1/my/pets", headers=_h(tok["a"]),
                      json={"clinic_org_id": str(org), "name": "Coco", "species": "dog"}).json()
    s = get_settings()
    monkeypatch.setattr(s, "ocr_engine", "tesseract")
    calls = []

    def fake_extract(_s, image, *, demo_org):
        calls.append((image, demo_org))
        return ocr.OcrResult(CERT_TEXT, 0.82, "tesseract", ("eng", "hin", "tam"))

    monkeypatch.setattr(ocr, "extract", fake_extract)
    import pawguard_api.integrations.storage as storage

    monkeypatch.setattr(storage, "get_storage", lambda: SimpleNamespace(download=lambda key, max_bytes: b"jpeg-bytes"))
    certificates._recent.clear()
    return SimpleNamespace(org=org, a=a, b=b, tok=tok, product=product, pet=pet, calls=calls, settings=s)


def test_owner_reads_own_certificate_into_a_draft(client, owner, owner_engine):
    m = _media(owner_engine, owner.org, owner.a)
    r = client.post(f"/api/v1/my/certificates/{m}/read", headers=_h(owner.tok["a"]))
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["administered_on"] == str(date.today() - timedelta(days=3))
    assert d["next_due_on"] == str(date.today() + timedelta(days=362))
    assert d["product_id"] == str(owner.product) and d["lot_text"] == "RB2026X"
    assert d["confidence"] == pytest.approx(0.82) and d["warnings"] == []
    assert owner.calls == [(b"jpeg-bytes", False)]
    with owner_engine.begin() as c:  # only parsed fields are kept, never the certificate text
        row = c.execute(text("select * from app.certificate_drafts where media_id = :m"), {"m": m}).one()
    assert "Private Person" not in str(dict(row._mapping))
    # Another owner can't read it; it looks like it doesn't exist.
    assert client.post(f"/api/v1/my/certificates/{m}/read", headers=_h(owner.tok["b"])).status_code == 404


def test_refusals(client, owner, owner_engine, monkeypatch):
    pdf = _media(owner_engine, owner.org, owner.a, mime="application/pdf")
    r = client.post(f"/api/v1/my/certificates/{pdf}/read", headers=_h(owner.tok["a"]))
    # PDFs are read from page 1 now; this test PDF has no stored file, so it can't be read.
    assert r.status_code == 422 and r.json()["error"]["code"] == "no_display_copy"
    pending = _media(owner_engine, owner.org, owner.a, state="validating")
    r = client.post(f"/api/v1/my/certificates/{pending}/read", headers=_h(owner.tok["a"]))
    assert r.status_code == 409 and r.json()["error"]["code"] == "media_not_ready"
    # Gemini vision is for demo organisations only (real certificates carry personal details).
    monkeypatch.setattr(owner.settings, "ocr_engine", "gemini")
    monkeypatch.setattr(ocr, "extract", REAL_EXTRACT)
    m = _media(owner_engine, owner.org, owner.a)
    r = client.post(f"/api/v1/my/certificates/{m}/read", headers=_h(owner.tok["a"]))
    assert r.status_code == 409 and r.json()["error"]["code"] == "gemini_demo_only"


def test_vet_sees_drafts_for_the_record(client, owner, owner_engine):
    m = _media(owner_engine, owner.org, owner.a)
    client.post(f"/api/v1/my/certificates/{m}/read", headers=_h(owner.tok["a"]))
    rec = client.post(f"/api/v1/my/pets/{owner.pet['id']}/vaccinations", headers=_h(owner.tok["a"]),
                      json={"product_id": str(owner.product), "administered_on": str(date.today() - timedelta(days=3)),
                            "certificate_media_ids": [str(m)]})
    assert rec.status_code == 201, rec.text
    event_id = rec.json()["timeline"][0]["event_id"]
    r = client.get(f"/api/v1/vaccination-events/{event_id}/certificate-drafts", headers=_h(owner.tok["vet"], owner.org))
    assert r.status_code == 200 and r.json()[0]["lot_text"] == "RB2026X"
    assert client.get(f"/api/v1/vaccination-events/{event_id}/certificate-drafts",
                      headers=_h(owner.tok["a"], owner.org)).status_code == 403


def test_status_reports_missing_tesseract(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "ocr_engine", "tesseract")
    monkeypatch.setattr(ocr, "tesseract_cmd", lambda _s: None)
    st = ocr.status(s)
    assert st["available"] is False and "not installed" in st["reason"]
