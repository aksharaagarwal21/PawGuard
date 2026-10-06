# Roadmap

Free-tier plan (see `FREE_SERVICES_SETUP.md`). Status as of 7 October 2026, branch `free-services`.

| Part | Status |
|---|---|
| Email (Gmail SMTP / Brevo), daily cap, deferral, confirm-your-email step | Built and working (Gmail) |
| Web Push (VAPID) | Built and configured |
| WhatsApp Cloud API test number, webhook receipts | Built; needs your Meta test number values |
| Ask PawGuard assistant (Gemini free tier / Ollama) | Built; needs a Gemini key or Ollama |
| Certificate OCR (Tesseract / PaddleOCR, eng/hin/tam; optional Gemini vision) — draft only, vet verifies | Next |
| In-browser voice assistant (Web Speech API, en-IN / hi-IN / ta-IN, text fallback) | Built (needs the assistant configured) |
| Twilio trial calls to verified numbers (optional) | Next |
| Lost pet finder with in-app private messages (no phone masking) | Next |
| Printable QR collar tags (PDF) | Built |
| Deployment docs: Oracle Cloud Always Free (Docker Compose, Caddy/Let's Encrypt, DuckDNS); Vercel + Supabase free tier | Written (`DEPLOYMENT_FREE.md`), not yet tried on a real VM |

## Not possible for free (not built)
- **SMS to Indian numbers** needs a paid, DLT-registered SMS provider (sender ID and template registration). Use
  WhatsApp, push and email instead.
- **NFC collar tags** need physical tags you'd have to buy. QR tags only.

## Known issues
- `test_planning_api::test_plan_from_survey_to_published_team_tasks` fails between 00:00 and 05:30 IST: the survey
  date check uses the database's UTC date while the test (and a person in India) uses the local date. Fix: allow one
  day of tolerance in `survey_counts_observed_on_check`, as the vaccination date guard already does.
