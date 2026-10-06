"""Certificate draft parsing (pure): dates, vaccine, batch — in English, Hindi and Tamil."""

from datetime import date

from pawguard_api.domain.certificate_parse import dates_in, parse

TODAY = date(2026, 10, 7)
PRODUCTS = [("p-rabies", "Rabies vaccine (demo product)"), ("p-dhppi", "DHPPi combination (demo product)"),
            ("p-tricat", "Feline tricat combination (demo product)")]


def test_english_certificate():
    text = ("PET VACCINATION CERTIFICATE\nOwner: (name)\nDate of vaccination: 08/06/2026\n"
            "Vaccine: Nobivac Rabies   Batch No: a123b45\nNext due date: 08-06-2027\nDr. (vet), Reg. 1234")
    d = parse(text, PRODUCTS, TODAY)
    assert (d.administered_on, d.next_due_on) == (date(2026, 6, 8), date(2027, 6, 8))
    assert (d.vaccine_keyword, d.product_id, d.lot_text) == ("rabies", "p-rabies", "A123B45")
    assert d.warnings == []


def test_hindi_digits_and_labels():
    text = "टीकाकरण दिनांक: ०८/०६/२०२६\nटीका: रेबीज\nअगली तारीख: ०८/०६/२०२७"
    d = parse(text, PRODUCTS, TODAY)
    assert (d.administered_on, d.next_due_on, d.product_id) == (date(2026, 6, 8), date(2027, 6, 8), "p-rabies")


def test_tamil_labels():
    text = "தடுப்பூசி தேதி: 15.07.2026\nரேபிஸ் தடுப்பூசி\nஅடுத்த தேதி 15.07.2027"
    d = parse(text, PRODUCTS, TODAY)
    assert (d.administered_on, d.next_due_on, d.vaccine_keyword) == (date(2026, 7, 15), date(2027, 7, 15), "rabies")


def test_month_names_and_combination_vaccine():
    d = parse("DHPPi given on 3rd Jan 2026\nBooster due Jan 3, 2027", PRODUCTS, TODAY)
    assert (d.administered_on, d.next_due_on, d.product_id) == (date(2026, 1, 3), date(2027, 1, 3), "p-dhppi")


def test_no_next_due_date_is_invented():
    d = parse("Rabies\n12/03/2026\n15/04/2026", PRODUCTS, TODAY)
    assert d.administered_on == date(2026, 3, 12) and d.next_due_on is None


def test_invalid_and_future_dates():
    assert dates_in("31/02/2026 and 2026-13-01 and 10/10/1899") == []
    d = parse("Date of vaccination: 20/12/2026", PRODUCTS, TODAY)
    assert d.administered_on is None and "future" in d.warnings[0]
    assert parse("nothing useful here", PRODUCTS, TODAY).warnings == ["No date could be read."]
