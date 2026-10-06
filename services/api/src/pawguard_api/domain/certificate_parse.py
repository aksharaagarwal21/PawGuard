"""Turn text read from a vaccination certificate into a *draft* (dates, vaccine, batch). Pure functions.

A draft only pre-fills the form for the person to check; the record stays unverified until a vet verifies it against
the image. Indian certificates usually write dates day-first (08/06/2026). Devanagari and Tamil digits are
normalised. Nothing here guesses a schedule: a "next due" date is taken only when the certificate labels it.
"""

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

_DIGITS = str.maketrans("०१२३४५६७८९௦௧௨௩௪௫௬௭௮௯", "01234567890123456789")
_MONTHS = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}

_NUMERIC = re.compile(r"(?<!\d)(\d{1,2})\s*[./-]\s*(\d{1,2})\s*[./-]\s*(\d{4}|\d{2})(?!\d)")
_ISO = re.compile(r"(?<!\d)(\d{4})-(\d{1,2})-(\d{1,2})(?!\d)")
_DAY_MON = re.compile(r"(?<!\d)(\d{1,2})(?:st|nd|rd|th)?[\s.-]*(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)"
                      r"[a-z]*\.?[\s,.-]*(\d{4})", re.IGNORECASE)
_MON_DAY = re.compile(r"(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+"
                      r"(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})", re.IGNORECASE)

_NEXT = re.compile(r"next|due|re-?vacc|booster|repeat|अगली|अगला|पुनः|அடுத்த|மீண்டும்", re.IGNORECASE)
_GIVEN = re.compile(r"date|given|vaccinat|administ|दिनांक|तारीख|टीकाकरण|தேதி|தடுப்பூசி", re.IGNORECASE)
_LOT = re.compile(r"(?:batch|lot|b\.\s*no|बैच|லாட்|தொகுதி)\s*(?:no\.?|number|#)?\s*[:.\-]?\s*([A-Z0-9][A-Z0-9\-/]{2,19})",
                  re.IGNORECASE)

# Vaccine words in English, Hindi and Tamil → a keyword used to match the clinic's product names.
KEYWORDS: dict[str, tuple[str, ...]] = {
    "rabies": ("rabies", "anti-rabies", "antirabies", "rabivac", "nobivac rabies", "रेबीज", "ரேபிஸ்", "வெறிநோய்"),
    "dhpp": ("dhpp", "dhppi", "dhlpp", "dapp", "distemper", "parvo", "canine 7", "megavac", "डिस्टेंपर", "பார்வோ"),
    "tricat": ("tricat", "feline", "fvrcp", "panleukopenia", "calici"),
    "lepto": ("lepto", "leptospir"),
}


@dataclass
class Draft:
    administered_on: date | None = None
    next_due_on: date | None = None
    vaccine_keyword: str | None = None
    product_id: Any = None
    product_name: str | None = None
    lot_text: str | None = None
    dates_found: list[date] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _valid(y: int, m: int, d: int) -> date | None:
    if y < 100:
        y += 2000
    if not (2000 <= y <= 2100):
        return None
    try:
        return date(y, m, d)
    except ValueError:
        return None


def dates_in(line: str) -> list[date]:
    s = line.translate(_DIGITS)
    out: list[date] = []
    for m in _ISO.finditer(s):
        if (d := _valid(int(m.group(1)), int(m.group(2)), int(m.group(3)))):
            out.append(d)
    s_wo_iso = _ISO.sub(" ", s)
    for m in _NUMERIC.finditer(s_wo_iso):
        if (d := _valid(int(m.group(3)), int(m.group(2)), int(m.group(1)))):  # day-first
            out.append(d)
    for m in _DAY_MON.finditer(s):
        if (d := _valid(int(m.group(3)), _MONTHS[m.group(2)[:3].lower()], int(m.group(1)))):
            out.append(d)
    for m in _MON_DAY.finditer(s):
        if (d := _valid(int(m.group(3)), _MONTHS[m.group(1)[:3].lower()], int(m.group(2)))):
            out.append(d)
    return out


def parse(text: str, products: list[tuple[Any, str]], today: date) -> Draft:
    """`products`: (id, name) of the clinic's vaccines. Dates after `today` can't be "given on" dates."""
    draft = Draft()
    lines = [ln.strip() for ln in text.translate(_DIGITS).splitlines() if ln.strip()]
    given: list[date] = []
    due: list[date] = []
    unlabelled: list[date] = []
    for i, ln in enumerate(lines):
        found = dates_in(ln)
        if not found:
            continue
        context = ln + " " + (lines[i - 1] if i else "")  # labels are often on the line above
        if _NEXT.search(ln) or (not _GIVEN.search(ln) and _NEXT.search(context)):
            due += found
        elif _GIVEN.search(context):
            given += found
        else:
            unlabelled += found
    draft.dates_found = sorted(set(given + due + unlabelled))
    past = [d for d in given + unlabelled if d <= today]
    if past:
        draft.administered_on = max(past) if given else min(past)
    future_or_later = [d for d in due if not draft.administered_on or d > draft.administered_on]
    if future_or_later:
        draft.next_due_on = min(future_or_later)
    if any(d > today for d in given):
        draft.warnings.append("A 'given' date is in the future — check the certificate.")
    if not draft.dates_found:
        draft.warnings.append("No date could be read.")

    low = text.lower()
    for keyword, words in KEYWORDS.items():
        if any(w in low for w in words):
            draft.vaccine_keyword = keyword
            break
    if draft.vaccine_keyword:
        names = KEYWORDS[draft.vaccine_keyword]
        for pid, name in products:
            n = name.lower()
            if draft.vaccine_keyword in n or any(w in n for w in names):
                draft.product_id, draft.product_name = pid, name
                break
    m = _LOT.search(text)
    if m:
        draft.lot_text = m.group(1).upper()
    return draft
