"""Evidence check helpers: comparing what a certificate shows with the record, and finding QR codes in a photo."""

from datetime import date
from types import SimpleNamespace

from pawguard_api.domain import credentials
from pawguard_api.domain.evidence_check import CARD_LINK, compare, find_qr


def _event(**kw):
    base = {"administered_on": date(2026, 9, 1), "product_id": "p1", "product_name": "Rabies vaccine",
            "product_text": None, "lot_number": "ARV-A-001", "lot_text": None}
    return SimpleNamespace(**{**base, **kw})


def _by_kind(checks):
    return {c["kind"]: c["status"] for c in checks}


def test_matching_certificate_is_ok():
    read = {"administered_on": date(2026, 9, 1), "product_text": "Rabies vaccine", "lot_text": "arv-a-001"}
    assert _by_kind(compare(_event(), read)) == {"date": "ok", "vaccine": "ok", "batch": "ok"}


def test_different_date_is_a_problem():
    read = {"administered_on": date(2026, 8, 1), "product_text": "Rabies vaccine"}
    checks = compare(_event(), read)
    assert _by_kind(checks)["date"] == "bad"
    assert "01 Aug 2026" in checks[0]["message"]


def test_nothing_readable_needs_a_look():
    assert _by_kind(compare(_event(), {})) == {"date": "warn", "vaccine": "warn"}


def test_finds_signed_qr_in_an_image():
    qr = "PG1:" + "A" * 60
    assert find_qr(credentials.qr_png(qr).getvalue()) == qr


def test_card_link_pattern():
    token = "x" * 40
    assert CARD_LINK.search(f"https://example.org/en/card/{token}").group(1) == token
    assert CARD_LINK.search("https://example.org/en/card/short") is None


def test_a_different_clinic_vaccine_is_a_clear_mismatch():
    read = {"administered_on": date(2026, 9, 1), "product_text": "Rabies vaccine", "product_id": "p-rabies"}
    checks = compare(_event(product_id="p-dhppi", product_name="DHPPi combination"), read)
    vaccine = next(c for c in checks if c["kind"] == "vaccine")
    assert vaccine["status"] == "bad" and vaccine["code"] == "vaccine_differs" and "Rabies vaccine" in vaccine["owner"]
