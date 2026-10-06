"""Pet-owner assistant ("Ask PawGuard"): short answers about using PawGuard and the owner's own reminders.

Guardrails (docs/PRODUCT_BRIEF.md non-negotiables, Gemini free-tier terms):
- It never diagnoses, never recommends, changes, skips or schedules a vaccine or treatment, never gives doses —
  the vet decides. Replies that look like dosing are replaced with a safe answer.
- It only uses facts PawGuard sends it: pet name, species, status, vaccine, dates, clinic name. No owner name,
  phone, email, address or photos. Emails and phone-like numbers typed by the user are removed before sending.
- Anything about a bite or scratch always gets the bite-help action, whatever the model says.
- Actions are chosen from a fixed allow-list and rendered by the app as buttons; the model cannot add links.
- Per-person rate limit; provider rate limits become "try again shortly".
"""

import re
import time
from collections import defaultdict, deque
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from pawguard_api.auth import Principal
from pawguard_api.domain import petcare
from pawguard_api.errors import ApiError, Forbidden
from pawguard_api.integrations import llm
from pawguard_api.settings import get_settings

ACTIONS = ("open_reminders", "mark_done", "add_calendar", "open_pets", "open_card", "notifications", "how_to",
           "bite_help")
LANGUAGES = {"en": "English", "hi": "Hindi", "ta": "Tamil"}
PER_HOUR = 20
_recent: dict[str, deque[float]] = defaultdict(deque)

_EMAIL = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+")
_PHONE = re.compile(r"(?:\+?\d[\d\s().-]{7,}\d)")
_DOSE = re.compile(r"\b\d+(?:[.,]\d+)?\s?(?:mg|mcg|µg|ml|mL|cc|iu|IU|units?)\b")
_BITE = re.compile(r"\b(bit|bite|bitten|biting|scratch|scratched|rabies)\b|काट|खरोंच|ரேபிஸ்|கடி|கீறல்", re.IGNORECASE)
_ACTIONS_LINE = re.compile(r"^\s*ACTIONS?\s*:\s*(.*)$", re.IGNORECASE | re.MULTILINE)

SAFE_FALLBACK = {
    "en": "I can't advise on doses, schedules or treatment — your vet decides that. I can help you find your "
          "reminders or your pet's vaccination card.",
    "hi": "मैं खुराक, टीकों के समय या इलाज पर सलाह नहीं दे सकता — यह आपके पशु-चिकित्सक तय करते हैं।",
    "ta": "மருந்தளவு, தடுப்பூசி அட்டவணை அல்லது சிகிச்சை பற்றி என்னால் ஆலோசனை வழங்க முடியாது — உங்கள் கால்நடை மருத்துவர் முடிவு செய்வார்.",
}


def status() -> dict[str, Any]:
    s = get_settings()
    p = llm.provider(s)
    return {"available": p != "off", "provider": p, "shares_with_google": p == "gemini"}


def redact(text: str) -> str:
    return _PHONE.sub("[number removed]", _EMAIL.sub("[email removed]", text))


def _rate_limit(user_id: str) -> None:
    now = time.monotonic()
    q = _recent[user_id]
    while q and now - q[0] > 3600:
        q.popleft()
    if len(q) >= PER_HOUR:
        raise ApiError("You've asked a lot of questions this hour. Try again later.", code="rate_limited",
                       status_code=429)
    q.append(now)


def _facts(p: Principal) -> tuple[str, str, list[Any]]:
    pets = petcare.list_pets(p)
    if not pets:
        return "The owner has no pets registered yet.", "", pets
    ctxs = petcare.owner_contexts(p)
    tz = ctxs[0].timezone if ctxs else "Asia/Kolkata"
    today = datetime.now(ZoneInfo(tz)).date()
    lines = []
    for pet in pets:
        st = pet.status
        due = (f"; next due {st.next_due_on:%d %b %Y} for {st.vaccine} ({st.days_until_due} days from today)"
               if st.next_due_on else "")
        waiting = (f"; {pet.awaiting_verification} owner record(s) waiting for the vet"
                   if pet.awaiting_verification else "")
        lines.append(f"- {pet.name} ({pet.species}), clinic {pet.clinic_name}: status {st.status}{due}{waiting}")
    return "\n".join(lines), f"{today:%d %b %Y}", pets


def _system(facts: str, today: str, language: str) -> str:
    return (
        "You are PawGuard's helper for pet owners in India. You help people use the PawGuard app and understand "
        "their pets' vaccination reminders.\n"
        f"Today is {today}. Facts from the owner's clinic records (the only facts you may use):\n{facts}\n\n"
        "Rules:\n"
        "1. Never diagnose. Never recommend, change, skip, delay or schedule any vaccine or treatment, and never give "
        "doses. Say that their vet decides.\n"
        "2. Use only the facts above. If something isn't there, say you don't know and suggest asking the clinic.\n"
        "3. If anyone was bitten or scratched by an animal, tell them to open bite help in the app and get medical "
        "care straight away.\n"
        "4. Statuses: up_to_date = verified and next dose more than 2 weeks away; due_soon = within 14 days; "
        "overdue = due date passed; unverified_record = owner added a record the vet hasn't checked; "
        "no_verified_record = no vet-confirmed vaccine in the app yet (this does NOT mean unvaccinated).\n"
        "5. Don't ask for or repeat personal details such as phone numbers or addresses.\n"
        f"6. Reply in {LANGUAGES.get(language, 'English')}, kindly and plainly, in under 90 words.\n"
        "7. End with one final line exactly like 'ACTIONS: code1, code2' using at most two of: "
        + ", ".join(ACTIONS) + " — or 'ACTIONS: none'."
    )


def ask(p: Principal, messages: list[dict[str, str]], language: str) -> dict[str, Any]:
    if not petcare.owner_contexts(p):
        raise Forbidden("The assistant is for pet owners.", code="owners_only")
    s = get_settings()
    if llm.provider(s) == "off":
        raise ApiError("The assistant isn't set up on this server.", code="assistant_unavailable", status_code=409)
    _rate_limit(str(p.user_id))
    language = language if language in LANGUAGES else "en"
    turns = [llm.Turn("assistant" if m["role"] == "assistant" else "user", redact(m["text"])[:1000])
             for m in messages[-10:]]
    last_user = next((t.text for t in reversed(turns) if t.role == "user"), "")
    facts, today, _ = _facts(p)
    try:
        raw = llm.generate(s, _system(facts, today, language), turns)
    except llm.LLMError as err:
        if err.code == "rate_limited":
            raise ApiError("The assistant is busy right now — try again shortly.", code="assistant_busy",
                           status_code=503) from err
        if err.code == "blocked":
            return {"reply": SAFE_FALLBACK[language], "actions": ["open_reminders"], "guarded": True}
        raise ApiError("The assistant can't answer right now — try again shortly.", code="assistant_error",
                       status_code=503) from err
    m = _ACTIONS_LINE.search(raw)
    codes = [c.strip().lower() for c in (m.group(1) if m else "").split(",")]
    actions = [c for c in codes if c in ACTIONS][:2]
    reply = _ACTIONS_LINE.sub("", raw).strip()
    guarded = False
    if _DOSE.search(reply):
        reply, actions, guarded = SAFE_FALLBACK[language], ["open_reminders"], True
    if _BITE.search(last_user) and "bite_help" not in actions:
        actions = ["bite_help", *actions][:2]
    return {"reply": reply[:1200], "actions": actions, "guarded": guarded}
