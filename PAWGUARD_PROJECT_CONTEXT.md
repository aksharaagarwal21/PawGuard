# PawGuard 360 — complete project context (single file)

> **Purpose of this file:** one place where any person or AI tool can learn everything about PawGuard 360:
> what it is, why it exists, every page and flow, every technology and version, how the AI models were built and
> measured, how data and security work, how to run and test it, what is finished, what is in progress (with the exact
> point where work paused), and the honest limitations.
>
> **Last updated:** 7 October 2026 (IST). **Repository:** `C:\PawGuard` (GitHub: `aksharaagarwal21/PawGuard`, public).
> **No secrets are in this file.** Environment variables are listed by name only; real values live in the
> git-ignored `.env` and `secrets/` folder.
>
> When this file and the code disagree, the code wins; detailed sources are named in each section (`docs/…`).

---

## 0. TL;DR

* **PawGuard 360** is a web platform for **rabies prevention**. It started as a community/municipal tool (registry of
  community dogs, verified vaccination evidence, field tasks, campaign planning, offline field kit, AI-assisted
  identification). For a **hackathon** it was extended into **pet vaccination tracking and reminders**: pet owners,
  vet clinics, reminders by email/push/WhatsApp/phone call, QR vaccination cards and collar tags, an AI assistant,
  certificate reading (OCR), and a lost-pet finder.
* **Stack:** Next.js 16 (React 19, TypeScript, Tailwind v4, next-intl en/ta/hi) → same-origin API gateway → FastAPI
  (Python 3.12, SQLAlchemy 2.1, Alembic) → PostgreSQL 17 on local **Supabase** (Auth + Storage, PostGIS, pgvector)
  with **row-level security**; **Celery** worker + outbox **dispatcher** on **Valkey**; ML with PyTorch (training) and
  ONNX Runtime + OpenCV (inference).
* **AI:** YOLOX-S dog detector (active, assistive); **PawID** identity model = frozen **DINOv2-small** + PawGuard-trained
  **ArcFace** projection head (research preview only; top-1 94.3 % on held-out DogFaceNet pet faces, release gate not
  met); **Ask PawGuard** assistant on **Gemini** (`gemini-flash-lite-latest`) with guardrails; **Tesseract** OCR for
  certificates (draft only).
* **Honesty principles** (tested): a QR or signature proves where a record came from, never that a pet is "safe";
  "verified vaccination" ≠ "cannot transmit disease"; unknown ≠ no; nothing ever says treatment can be skipped.
* **In progress now** (branch `signed-certs-bite-check`): (1) tamper-proof **signed vaccination certificates**
  (Ed25519 / COSE_Sign1 / CBOR / zlib / Base45 `PG1:` QR, offline verifier PWA at `/verify`), and (2) a
  **"This pet bit someone" instant check** (first aid first, bite reports, 10-day observation with daily check-ins,
  reporter tracking link, doctor link). Exact state in §21.

---

## 1. What problem it solves and for whom

### 1.1 Background
Rabies is vaccine-preventable; dog bites cause most human cases (WHO). Prevention depends on trustworthy
vaccination records and on people getting care quickly after a bite. Existing tools (e.g. WVS Rabies Launchpad)
already do field data collection and maps, so PawGuard does **not** claim a registry or map is novel. Its intended
contribution is the **combination** of: a review-gated vaccination evidence ledger with explicit uncertainty states;
human-confirmed, tenant-scoped assisted identification with measured open-set error; auditable merges; an offline
field workflow with explicit conflicts; and (hackathon) a pet-owner ↔ clinic loop with real reminders, verifiable QR
records and bite response.

### 1.2 Users
| User | Needs |
|---|---|
| Visitor / bitten person (no account) | Urgent first aid and contacts immediately; later: bite check from a pet's QR |
| Pet owner | Add pets, see status, reminders on chosen channels, QR card/tags, certificate reading, assistant, lost-pet help |
| Clinic vet (veterinary reviewer) | Verify owner uploads, record vaccines given, see who is overdue/due, messages, demo tools |
| Clinic manager (org admin) | Counts, members, settings (no vaccination review authority) |
| Field volunteer (NGO/municipal) | Tasks, find-or-register a community dog, submit vaccination evidence, offline kit |
| Programme coordinator | Campaigns, teams, surveys, plan generation, honest aggregates |
| Organisation administrator | Membership, capabilities, professional-approval path |

Primary context: India (Tamil Nadu demo region `IN-TN`), languages **English, Tamil, Hindi**. Nothing about regions or
medical rules is hard-coded; demo data is fictional and labelled.

### 1.3 Product invariants (non-negotiable; many are asserted by tests)
- Urgent help is reachable without account, photo, questionnaire, AI, or finding the animal.
- No rabies diagnosis from images/video/behaviour/wounds; **no "safe dog" classifier**; no "rabies-free" wording.
- A possible identity match is not a verified identity; a verified vaccine administration is not a declaration
  that the animal cannot transmit disease.
- `unknown` ≠ `no`; `not recorded` ≠ `not done`; `reported` ≠ `verified`; uploaded certificates are evidence
  awaiting review; OCR output is a draft; a QR code only identifies a record.
- Coverage is never "verified vaccinations ÷ animals in the app" — the clinic dashboard says "X of Y **registered**
  pets up to date — not population coverage".
- No precise community-animal location, caregiver detail or patient information on public pages.
- No LLM generates or changes any treatment schedule; the assistant never diagnoses or advises skipping care.
- Health wording names its source and review status (`docs/CONTENT_REGISTER.md`); it is **unreviewed starter
  content** until a qualified local reviewer approves it. Machine/AI-written translations of health wording are
  marked draft.

---

## 2. Repository, branches and current state

### 2.1 Branches (all commits authored as the user `aksharaagarwal21`, noreply email, no AI co-author lines)
| Branch | Contents | Pushed? |
|---|---|---|
| `main` | Phases 0–9 (Prevention platform) + hackathon pet-vaccination topic Parts 0–6 (`ca59ba7` … `1597211`); tag `pre-pet-topic` marks state before the pet topic | Yes (origin/main) |
| `ui-polish` | UI/text redesign Parts 1–7 (landing story, Get-started page, sign-in, welcome tour, owner screens, clinic dashboard, "How to use PawGuard" guide). No API/DB changes | No |
| `free-services` | Built on `ui-polish`: notifications core, email (Gmail SMTP), Web Push, WhatsApp (Meta + Twilio), Ask PawGuard assistant, voice, email confirmation, QR collar tags, OCR, lost-pet finder, Twilio calls, Twilio WhatsApp with delivery tracking, free hosting docs | No |
| `signed-certs-bite-check` | **Current branch**, from `free-services` (`6dd1d52`). Signed certificates + bite check (in progress, uncommitted) | No |

Latest commits on `free-services`: `6dd1d52` assistant app guide · `9bd0ba1` quiet Twilio SDK logging · `f3f654c`
Twilio WhatsApp + tracking · `42e2a45` Twilio calls · `1628c98` lost pet finder · `0bf5fcf` OCR · `5f08d88` free
hosting · `0b7426e` collar tags · `42256dd` voice · `4162f56`, `a224901` email confirmation · `18398d5` docs ·
`4ea2142` assistant · `4b2a892` WhatsApp Meta · `2fe5598`, `2fd86c8`, `9c204c5` Web Push · `b580c7d` notifications
core + email · `36efe48` setup guide.

### 2.2 Repository map
| Path | What |
|---|---|
| `apps/web` | Next.js 16 App Router app: public site + authenticated app (`src/app/[locale]/…`), components, i18n messages (`messages/en.json`, `ta.json`, `hi.json`), `public/` (service workers, icons, vendor files), vitest unit tests |
| `packages/ui` | Design tokens (CSS) + accessible primitives (Button, Field, TextInput, Notice, StatusChip, Card, …) |
| `packages/api-client` | `openapi.json` exported from FastAPI + generated TypeScript types (`openapi-typescript`) + typed `openapi-fetch` client. Regenerate: `pnpm run generate` in that folder |
| `services/api` | FastAPI app (`src/pawguard_api`): `routers/`, `domain/` (business rules), `integrations/` (email, push, WhatsApp, Twilio, LLM, OCR, storage, COSE), `models/` (SQLAlchemy), `seed/` (demo data + reset), `cli.py` (`pawguard-admin`), Alembic `migrations/versions/0001…0020`, pytest `tests/` |
| `services/worker` | Celery app + tasks (`media`, `identity`, `plan`, `notify`), outbox dispatcher with notification ticker, vision (`vision/quality.py`, `yolox.py`, `embed.py`), OR-Tools planner (`planning.py`) — CLI `pawguard-worker run|dispatch` |
| `ml` | Separate uv project `pawguard_ml` (CLI `pawid`): dataset prep, COCO sample, detector eval, DINOv2 identity selection/training/test/export, DogFaceNet evaluation |
| `data/manifests` | Small versioned dataset and model manifests (no images) |
| `models/` | Model weights (git-ignored), `models/tessdata` (Tesseract language data) |
| `infra/` | Supabase local config, docker compose (Valkey broker, app profile), Dockerfiles, `deploy/` (Caddyfile, Oracle compose) |
| `scripts/` | `check.sh` (all checks), `dev_env.py`, `demo_up.sh/.ps1`, `demo_prepare.py`, `restart-web.sh`, `public_link.sh/.ps1` (Cloudflare quick tunnel), `export_openapi.py`, `gen_data_dictionary.py`, `gen_permissions.py`, `check_bundle_secrets.py`, `ocr_eval.py`, `make_verify_vectors.py` (new), `make_demo_backup.sh` |
| `tests/` | Playwright e2e (`tests/e2e/*.spec.ts`, 25 specs; config `tests/playwright.config.ts`, projects `desktop` + `mobile`) |
| `docs/` | Product brief, architecture, ADRs 0001–0011, data dictionary, permissions, design system, journeys, evaluation, model card, ML plan, threat model, content register, data sources, demo guide, handoff, implementation status, free services setup, free deployment, roadmap, backup/restore |
| `secrets/` | **git-ignored** signing key files (master key, root key, passphrase) — new |

---

## 3. Technology stack (pinned versions)

| Concern | Technology | Version / note |
|---|---|---|
| Runtimes | Node.js / pnpm / Python / uv | 22.18 / 11.28.4 / 3.12 / ≥0.7 |
| Web framework | Next.js (App Router) + React | 16.3.8 / 19.3.0 |
| Language | TypeScript | 6.0.3 |
| Styling | Tailwind CSS (CSS-first `@theme` tokens) | 4.3.3 |
| i18n | next-intl (en, ta, hi; English fallback for untranslated keys) | 4.14.9 |
| Auth (web side) | @supabase/ssr + supabase-js (server-side only; browser never holds tokens) | 0.12.7 / 2.117.2 |
| UI libs | Radix UI, lucide-react icons, react-hook-form, zod, TanStack Query | 1.6.7, 1.52.0, 7.89.0, 4.6.5, 5.104.1 |
| Maps | MapLibre GL (lazy-loaded; OSM attribution; list fallback) | 6.12.0 |
| Fonts | Manrope, Source Sans 3, Noto Sans Tamil, Noto Sans Devanagari (fontsource) | 5.3.0 |
| API | FastAPI, Pydantic, pydantic-settings, Uvicorn | 0.142.2, 2.13.5, 2.15.0, 0.54.0 |
| ORM / DB driver / migrations | SQLAlchemy, psycopg 3, Alembic | 2.1.3, 3.3.6, 1.20.0 |
| Geo / vectors | GeoAlchemy2, pgvector | 0.20.0, 0.5.0 |
| JWT | PyJWT[crypto] (ES256/RS256 via JWKS) | 2.15.1 |
| Logging | structlog (JSON logs, request IDs) | 26.1.0 |
| Jobs | Celery + redis client; broker **Valkey** 8.1.10 | 5.6.3, 6.4.0 |
| DB | Supabase Postgres image (PostgreSQL 17, PostGIS 3.3.7, pgvector 0.8.2); Supabase CLI | 17.11.0.002; 2.119.0 |
| Vision | OpenCV headless, ONNX Runtime | 5.0.0.93, 1.30.0 |
| ML training | PyTorch, torchvision (CPU) | 2.14.1, 0.29.1 |
| Planner | Google OR-Tools (vehicle routing) | 9.15.6755 |
| QR / PDF | segno, fpdf2 | 1.6.6, 2.8.5 |
| Email | Python `smtplib` (STARTTLS) via Gmail SMTP app password | — |
| Web Push | pywebpush (VAPID) | 2.0.3 |
| Twilio | twilio Python SDK (calls via REST, WhatsApp via SDK, `RequestValidator` for signatures) | 9.8.3 |
| OCR | pytesseract + Tesseract (eng/hin/tam) | 0.3.13 |
| LLM | Gemini REST API (`x-goog-api-key`) or local Ollama (`qwen2.5:3b`) | model `gemini-flash-lite-latest` |
| Signing (new) | cryptography (Ed25519, AES-GCM), cbor2, base45, uharfbuzz (PDF text shaping), pycose (tests only) | 50.0.2, 6.1.5, 0.4.4, 0.56.3, 1.1.0 |
| Verify page (new) | @noble/curves (Ed25519), cborg (CBOR), barcode-detector (ZXing WASM ponyfill) | 2.4.0, 6.1.3, 3.2.2 (zxing-wasm 3.1.3) |
| Tests | pytest, hypothesis, vitest, Playwright, axe-core | 9.1.1, 6.168.4, 5.0.3, 1.63.0, 4.13.0 |
| Lint/type | ruff, mypy, eslint, tsc | 0.16.10, 2.4.0 |

---

## 4. Architecture

```
Browser ──cookie session──► Next.js server (same origin)
   │                         ├─ proxy.ts: locale routing + Supabase session refresh
   │                         ├─ /api/v1/[...path] gateway: CSRF double-submit + Origin check → forwards to FastAPI
   │                         │    with the user's access token as Bearer; webhooks/* exempt from CSRF; forwards
   │                         │    x-hub-signature-256 and x-twilio-signature; optional x-pawguard-org selector
   │                         └─ server actions: sign-in / sign-out (password grant to Supabase Auth)
   └─ signed upload URL (PUT) ─► Supabase Storage (private bucket `pawguard-media`)

FastAPI (single business-rule boundary)
   ├─ verifies JWT via JWKS (iss/aud/exp/role); org from X-PawGuard-Org is only a selector → active membership check
   ├─ every command: validate → load membership + capabilities → check scope → mutate → audit_events + outbox_events
   │    → commit (one transaction)
   ├─ DB role `pawguard_api` (LOGIN, NOBYPASSRLS); per-transaction context via app.set_request_context(user, org)
   └─ sensitive commands also check the session is still live in auth.sessions

PostgreSQL (schema `app`, FORCE ROW LEVEL SECURITY; policies use app.current_org_id())
   ├─ narrow SECURITY DEFINER functions for worker/public access (e.g. public_card, claim_notification_deliveries)
   └─ append-only audit (UPDATE/DELETE blocked even for owner)

Workers (`pawguard-worker`)
   ├─ dispatch: polls outbox (FOR UPDATE SKIP LOCKED) → Celery tasks on Valkey; NotificationTicker:
   │    every 600 s app.queue_due_notifications(), every 15 s app.notifications_ready() → publish pawguard.notify.drain,
   │    every 60 s Twilio delivery-status polling fallback
   └─ run: Celery tasks pawguard.media.validate, media.analyse, identity.enrol, identity.search, plan.solve,
        notify.drain (role `pawguard_worker`)
```

Key ADRs (`docs/adr/`): 0001 stack and shape · 0002 session boundary (browser never sees Supabase tokens) · 0003 RLS
context (set_config local) · 0004 media pipeline (quarantine → validate from bytes → derivatives; signed URLs ≤120 s)
· 0005 migrations (Alembic only) · 0006 vision models (ONNX in worker) · 0007 prevention data model · 0008 assisted
identification · 0009 offline and planning · **0010 signed certificate format** · **0011 signing key management**.

---

## 5. Data model (migrations, in order)

| Rev | Adds |
|---|---|
| 0001 foundation | Roles `pawguard_api`/`pawguard_worker`, context functions (`set_request_context`, `current_org_id`, `current_user_id`), organisations (types: animal_welfare_ngo, municipal_programme, veterinary_service, health_facility, community_group, other; activation pending/active/suspended/closed; `is_demo`; `contact_email`; `timezone` default Asia/Kolkata), memberships (capabilities array), professional approvals, user profiles, audit (append-only), outbox, idempotency |
| 0002 | schema version function |
| 0003 prevention | animals (reference code `PG-XXXX-XXXX`, nickname, species, sex, sterilisation, age, coat, marks, ownership, profile state), observations + media links, media assets, areas, caregivers, **vaccine products/lots**, **animal_vaccination_events** (states draft/submitted/verified/needs_correction/rejected/superseded; date precision; source types field_entry/certificate_upload/partner_record/owner_entry/clinic_record; `next_review_on` + `next_review_source` vet/demo_template), reviews (evidence snapshot), field tasks, data-quality issues, merges |
| 0004–0006 | animal touch trigger, reference-code default, demo-flag inheritance |
| 0007 | model registry + detection results |
| 0008 | datasets, imports (dry-run/apply/rollback) |
| 0009 | identity: gallery embeddings (pgvector, per model version), searches, decisions, feedback |
| 0010 | planning: campaigns, teams, plans, surveys |
| 0011 | org column privileges |
| 0012 pet care | owner links, **vaccination_reminders** (14/7/1 days before, overdue; snooze; done), **demo_clock** (demo date offset), **pet_cards** (random revocable 256-bit token), `public_card()` function |
| 0013 notifications | notification_preferences (email/push/whatsapp opt-in), **notification_deliveries** queue (unique dedupe_key; states queued/sending/sent/deferred/failed/skipped), push_subscriptions, provider_status, claim/finish functions |
| 0014 | WhatsApp delivery status recording (Meta webhooks) |
| 0015 | email confirmation (double opt-in token, only hash stored), `queue_due_notifications(needs_confirmation)` |
| 0016 | certificate_drafts (OCR drafts) |
| 0017 lost pets | lost_reports, lost_threads, lost_messages, public lost status, finder start/post functions, lost_message notification kind |
| 0018 Twilio calls | call_enabled/call_number prefs, channel `call`, delivery `reply` (keypad 1/2), `record_call_reply` |
| 0019 Twilio WhatsApp | deliveries: provider, recipient_masked, provider_status (accepted…read/undelivered/failed), provider_status_at, provider_error_code, provider_body, send_started_at (no blind resend); kind `demo_reminder`; forward-only `record_twilio_status`; `twilio_status_to_check`; `cancel_demo_delivery` |
| **0020 signed credentials (new, uncommitted)** | signing_list_versions, clinic_signing_keys (sealed private keys, RLS with no policies), vaccination_credentials, functions `signing_org_ok`, `add_signing_key`, `signing_key_for_issue`, `trust_keys`, `revoked_credentials`, `signing_list_version`, `store_credential`, `revoke_credential`, `credential_photo_key` |

Field-level documentation: `docs/DATA_DICTIONARY.md` (generated by `scripts/gen_data_dictionary.py`).

---

## 6. Roles, capabilities, demo organisations and accounts

### 6.1 Capabilities (role templates; admins can adjust per member)
| Capability | resident (pet owner) | field_volunteer | veterinary_reviewer | programme_coordinator | org_admin |
|---|---|---|---|---|---|
| animal.read / write | | ✓/✓ | ✓/✓ | ✓/✓ | ✓/ |
| animal.merge, animal.location.exact, caregiver.read | | | ✓ | ✓ | |
| observation.write, identity.search/decide, vaccination.submit, task.work, survey.write | | ✓ | ✓ | ✓ | |
| media.upload | ✓ | ✓ | ✓ | ✓ | |
| **pet.own** | ✓ | | | | |
| **vaccination.review** (+ approved `veterinary_review` scope; nobody can approve themselves) | | | ✓ | | |
| task.manage, campaign.manage, data.import, caregiver.write | | | | ✓ | |
| report.aggregate | | | | ✓ | ✓ |
| member.manage, professional.approve, audit.read, system.view, model.manage | | | | | ✓ |
`org_admin` deliberately lacks vaccination review. Full endpoint table: `docs/PERMISSIONS.md`.

### 6.2 Sample organisations (`is_demo`; shown with a small "Sample data" tag)
Riverside Animal Welfare Trust (NGO), Hillview Municipal Programme, **Lotus Pet Clinic**, **Banyan Veterinary Centre** —
region IN-TN. (Renamed 7 Oct 2026 from "Demo — … (fictional)": the user asked for no "demo/fictional" wording in the UI.
The data is still flagged `is_demo`, and the app shows one small "Sample data" tag in the sidebar and footer instead of
a full-width banner.)

### 6.3 Demo accounts (development only; shared password `PawGuard-demo-2026`; one-click sign-in in demo mode)
| Email | Name | Role |
|---|---|---|
| owner.neha@example.org | Neha | Pet owner at Lotus — pets **Bruno** (dog, rabies + DHPPi given 120 days ago, due in 245), **Misty** (cat, tricat, due in 10 days), **Coco** (dog, rabies overdue by 5 days) |
| vet.kiran@example.org | Dr Kiran | Clinic vet at Lotus (veterinary_reviewer, approved) |
| clinic.asha@example.org | Asha | Clinic manager, Lotus (org_admin) |
| clinic.vikram@example.org | Vikram | Clinic manager, Banyan (org_admin) |
| admin.kavya@example.org | Kavya | Org admin, Riverside |
| volunteer.priya@example.org | Priya | Field volunteer, Riverside (Tamil UI) |
| vet.arun@example.org | Dr Arun | Vet reviewer, Riverside (approved) |
| coordinator.meena@example.org | Meena | Coordinator Riverside; volunteer Hillview |
| vet.joseph@example.org | Dr Joseph | Vet role WITHOUT approval (shows the approval rule) |
| volunteer.ravi@example.org | Ravi | Volunteer Hillview (Hindi UI) |
| vet.sana@example.org | Dr Sana | Vet reviewer Hillview |
| admin.farhan@example.org | Farhan | Org admin Hillview |
Sample vaccine products (Lotus/Banyan): "Rabies vaccine", "DHPPi combination", "Feline tricat combination", each with a
365-day **standard schedule** labelled "Standard schedule — confirm with your vet". Riverside/Hillview: "Anti-rabies
vaccine A/B", lots `ARV-A-001`… ; wards `W-A`…`W-F` "Ward A — North" etc.; teams "Team 1/2"; campaign "October
vaccination round"; field vet name "Dr Meera Rao"; sample bite references `BR-7K2M-4QXA` (Bruno) / `BR-9PRT-3HWD`
(Misty).
The dev database also contains pets added during testing (e.g. Laxmi) and community dogs (Rani, Whitey, Brownie,
Sona, Lucky).

---

## 7. Every page and the full site flow

### 7.1 Public pages (no account)
| Route | Purpose |
|---|---|
| `/[locale]` | Landing page told as a guided story; "Get help after a bite" first; role picker; status guide; FAQ |
| `/[locale]/help` | **Bitten or scratched?** Wash wound ≥15 min with soap and running water; get medical care today; 112 (national emergency) and 15400 (National Rabies Helpline, with its five-state coverage caveat); sources; review status. Health wording shown in English with a notice in ta/hi (policy) |
| `/[locale]/(info)/about`, `/learn`, `/sources`, `/find-care` | About, learning content, source register, find-care (explains facility directory not connected — never fabricated) |
| `/[locale]/guide` | "How to use PawGuard": guides by role (owners, clinic vets, clinic managers, volunteers), colour meanings, FAQ |
| `/[locale]/welcome` | "Before you begin" / get started |
| `/[locale]/sign-in` | Sign in (demo accounts listed with one-click sign-in in demo mode) |
| `/[locale]/verify-email` | Confirms an email address from the one-time link |
| `/[locale]/card/[token]` | **Public pet vaccination card** behind the QR: pet name, species, photo, clinic, status, verified vaccinations only, disclaimer "This card shows recorded vaccinations. It is not a health guarantee." No owner data, no location. Revoked/unknown tokens → same 404. Also "I found this pet" if reported lost |
| `/[locale]/found/[token]` | Private finder ↔ owner message thread (lost pet), no account needed |
| `/[locale]/field` | Offline field kit opt-in page |
| **`/[locale]/verify`** (in progress) | Offline certificate verifier PWA (§21) |

### 7.2 Pet owner (Neha) — menu: My pets, Reminders, Lost & found, Ask PawGuard, Notifications
| Route | Purpose and flow |
|---|---|
| `/app/pets` | My pets list with status chips: **Up to date** (verified, next dose > 14 days away), **Due soon** (≤ 14 days), **Overdue**, **Entered by owner (unverified)**, **No verified record** (never "unvaccinated") |
| `/app/pets/new` | Add a pet (name, species, sex, clinic, photo) |
| `/app/pets/[id]` | Pet profile: "Next step" box, stepper, timeline with "Verified by vet" / "Waiting for vet" labels, add past vaccination (owner record + certificate photo → goes to the vet's queue), **Read certificate** (OCR draft to check), lost/found buttons |
| `/app/pets/[id]/card` | QR vaccination card: QR (random revocable token), regenerate (old printed codes stop working), turn off, download **PDF card**, download **collar tags PDF** (A4 sheet of 16 tags 45×62 mm) |
| `/app/reminders` | Reminders: due/overdue list, **Mark as done** (vet then verifies; rejection brings the reminder back), snooze 1 or 3 days, add to calendar (`.ics` RFC 5545), notification preview; bell icon with count |
| `/app/notifications` | Channel settings, each opt-in: **Email** (address → confirmation link must be clicked; daily cap), **Browser notifications** (Web Push, per device), **WhatsApp** (number with country code), **Phone call (test only)**; "Send me a test" per channel (5/hour) |
| `/app/assistant` | **Ask PawGuard** chat (+ voice in en-IN/hi-IN/ta-IN via Web Speech API with text fallback; language select) |
| `/app/lost` | Report lost / found; private message threads with finders |

### 7.3 Clinic vet (Dr Kiran) — menu: Today, Clinic, Animals, Add photo, Review, Tasks, Map & areas, Offline field kit, Model evidence, (More on phones)
| Route | Purpose |
|---|---|
| `/app` Today | Greeting, role; Find/Register an animal; your tasks; your recent submissions |
| `/app/clinic` **Clinic dashboard** | "1 of 4 registered pets up to date — not population coverage"; counts of no-verified / unverified-only; tiles (tap to filter): **Awaiting verification** (first), **Overdue**, **Due this week**, **Due in 8–14 days**, each pet showing "Due date set by the vet" vs template; **Record a vaccination given at the clinic** (pet, vaccine, date, optional next due, optional batch; saved as verified by the vet; reminders update at once); **Messages** panel (provider status: Email/Notifications/WhatsApp/Calls; recent deliveries without addresses; "Send due reminders now" demo button; Meta webhook address); **Presenter tools** (sample-data orgs only: preview date +1/+7/back to real date; **WhatsApp (Twilio trial)** panel) |
| `/app/animals`, `/app/animals/[id]`, `/new`, `/[id]/vaccinations/new` | Registry search ("not a census"), profile tabs (Overview, Vaccination records, Sightings, Tasks, History), record vaccination evidence, add sighting, report incorrect info, possible duplicate, archive; 3-step register form ("record only what you observed", default Unknown) |
| `/app/capture` | Find an animal from a photo — research preview, suggestions only, safety note |
| `/app/review` | **Verification workbench**: oldest first, own submissions hidden; Verify (with next due date) / Request correction (creates a task for the submitter) / Reject (reason) |
| `/app/vaccinations/[id]`, `/amend` | Record detail and amendment |
| `/app/tasks`, `/app/map`, `/field`, `/app/model-evidence`, `/app/more` | Field tasks; map + area table ("not a disease-risk map"; exact locations only for authorised roles); offline kit; model evidence report; overflow menu |

### 7.4 Coordinator / admin / volunteer extras
`/app/campaigns`, `/app/campaigns/[id]` (plan generation greedy vs OR-Tools, approve, publish tasks), `/app/surveys/new`,
`/app/imports` (CSV dry run → apply → rollback), `/app/merges` (preview → approve by a different person → reverse),
`/app/system` (provider health: email, push, WhatsApp, calls, OCR, model registry, identity feedback), audit.

### 7.5 End-to-end hackathon flow (what to demo)
1. Neha adds a past vaccination with a certificate photo (OCR drafts it) → "Waiting for vet".
2. Dr Kiran: Clinic → Awaiting verification → verify with next due date (or correction/reject).
3. Pet becomes **Up to date**; reminders scheduled (14/7/1 days before, overdue).
4. Dispatcher queues due reminders; worker sends via email/push/WhatsApp/call even with no browser open; Messages
   panel shows results; the Twilio panel shows accepted → sent → delivered → read with Message SIDs (IST times).
5. Demo date tools move "today" to show status changes; QR card/collar tag shows verified records publicly.
6. (In progress) Signed certificate QR scanned offline on `/verify`; bite mode from the collar QR.

---

## 8. Notifications (email, push, WhatsApp, calls)

* **Queue:** `app.notification_deliveries` (dedupe key per reminder × channel; states queued, sending, sent, deferred,
  failed, skipped). Claimed with `SKIP LOCKED` by `app.claim_notification_deliveries` (returns channel opt-in flags so
  opt-out is re-checked at send time), finished by `app.finish_notification_delivery`. Max 5 attempts with deferral.
* **Scheduling:** dispatcher ticker scans every 600 s (`queue_due_notifications`), checks readiness every 15 s and
  publishes `pawguard.notify.drain`. Works with every browser closed.
* **Recipients:** each person's own confirmed address; optional demo override recipients (`PAWGUARD_DEMO_NOTIFY_*`).
  Recipient-level errors never change provider status. Provider status table: ok, not_configured, token_expired,
  rate_limited, cap_reached, error.
* **Email:** Gmail SMTP (STARTTLS) with an app password; **double opt-in** confirmation link (48 h; only the token hash
  stored; 3 confirmation emails/hour); daily cap 100.
* **Web Push:** VAPID keys (`pawguard-admin push keys`), endpoint allow-list (known push services), revoke gone devices;
  service worker `public/push-sw.js` (scope `/push/`).
* **WhatsApp (Meta Cloud API, Graph v26.0):** template or text; error mapping (190/0 token, rate limits, 131047
  outside 24-h window, 132001 template); webhook `/api/v1/webhooks/whatsapp` (verify token + HMAC SHA-256).
* **WhatsApp (Twilio trial, current provider):** official SDK, sends only From / To (`whatsapp:` prefix once) /
  ContentSid (trial pre-approved template, no variables) / StatusCallback. Demo organisation + configured demo
  recipient only (masked ••••1527 in UI); never real vaccination reminders through the generic template; intent
  persisted before sending (`send_started_at`) and result after (SID, status, Twilio-reported body); **no blind resend**
  after a timeout or crash; signed status callback `/api/v1/webhooks/twilio/status` (Twilio `RequestValidator`
  against the exact public URL; AccountSid check; forward-only statuses); polling fallback every 60 s (last 2 h,
  bounded). Clinic panel: "Send test WhatsApp", "Schedule demo reminder in 2 minutes" (fictional pet "Biscuit",
  cancellable, 5 sends/hour, double-submit protection), IST history with failure explanations (63015, 63016, 21610…).
  **Live results (7 Oct 2026):** two messages to the demo phone, both accepted (HTTP 201) → sent → delivered; later
  read. SIDs `MM63db8c3b…2115`, `MMd41c510a…fddb` (the scheduled one sent by the server with no browser open).
* **Phone calls (Twilio trial, optional):** TwiML `<Say>` reminder (XML-escaped) + `<Gather>` keypad: 1 = "I'll book a
  visit", 2 = remind again in 3 days (snooze); signed callback `/api/v1/webhooks/twilio/gather`. Trial: verified
  numbers only.
* **SMS to Indian numbers** is not built (needs paid DLT registration). **NFC tags** not built (hardware).

---

## 9. AI and machine learning

### 9.1 Ask PawGuard assistant (`domain/assistant.py`, `integrations/llm.py`)
* Provider: **Gemini** REST (`gemini-flash-lite-latest`, ~2 s answers; chosen because `gemini-2.5-flash` is closed to
  new keys and thinking-Flash models took 8–10 s) or local **Ollama** (`qwen2.5:3b`). Off when not configured
  (page says "The assistant isn't set up").
* Pet owners only; 20 questions/hour; replies in English/Hindi/Tamil, under 90 words.
* **Grounding:** facts from the owner's own clinic records (pets, status, due dates) + a fixed **app guide** (menus,
  how to turn on email/push/WhatsApp, reminders, cards, lost & found, bite help).
* **Guardrails:** never diagnose; never recommend/change/skip/delay a vaccine or give doses ("your vet decides"); bite
  → tell them to open bite help and get care now; no personal details; personal data redacted before sending
  (no owner names, phones, addresses, photos); fixed action buttons only (`open_reminders`, `mark_done`,
  `add_calendar`, `open_pets`, `open_card`, `notifications`, `how_to`, `bite_help`).
* Verified live: correct due-date answer + email setup steps; refuses "can I skip the rabies shot / what dose".
* Gemini free-tier terms: prompts may be used to improve products; not for apps aimed at under-18s — documented.

### 9.2 Certificate reading (OCR) — `integrations/ocr.py`, `domain/certificate_parse.py`, `certificates.py`
* Tesseract (eng + hin + tam, language data in `models/tessdata`), optional Gemini vision for demo orgs only.
* Produces a **draft** (vaccine, date, batch, vet) that the owner checks; stored in `certificate_drafts` and shown to
  the vet beside the evidence. Never auto-verifies. Accuracy measured only on synthetic certificates
  (`scripts/ocr_eval.py`). Tesseract itself needs an admin install on this laptop (`winget install --id
  UB-Mannheim.TesseractOCR -e`).

### 9.3 Photo pipeline and models (`docs/MODEL_CARD.md`, `docs/ML_PLAN.md`, `docs/EVALUATION.md`)
Pipeline: permitted upload → quarantine → validation from bytes (decode, MIME sniff, pixel budget, EXIF orientation,
metadata-free derivatives) → **OpenCV quality** (blur/darkness; provisional thresholds) → **YOLOX dog detection** →
person picks the subject or "none" → crop → **embedding** → tenant-scoped gallery search → up to 3 "possible matches"
→ **human decision** (same / none / not sure) → audited link. Every step has a typed failure state; manual search and
registration always remain.

**Model 1 — Dog detector `yolox_s_coco` (active, assistive):** official YOLOX-S ONNX (release 0.1.1rc0, 35.9 MB,
Apache-2.0), trained by its authors on COCO 2017; **not retrained**. Letterbox 640, raw 0–255 pixels (verified:
ImageNet normalisation found 0/19 dogs), NMS 0.45, score ≥ 0.35. Evaluated on a licence-filtered COCO val2017 sample:
precision 0.93 (0.82–1.00), recall 0.68 (0.49–0.86), 0/25 false dog images, ~150 ms CPU.

**Model 2 — PawID identity embedding `dinov2_small_arcface_head` (staged; research preview in demo orgs only):**
* Backbone: `facebook/dinov2-small` @ `ed25f3a3…` (safetensors, sha256-verified), **frozen**.
* Head trained by PawGuard: Linear 768→384 on [L2(CLS) ‖ L2(mean patch)], **ArcFace** (s = 30, m = 0.3), L2-normalised.
* Training data: **DogFaceNet 224 v1** train split (974 identities, 5,871 images); AdamW 1e-3, weight decay 0.05,
  2-epoch warm-up + cosine, batches of 16 identities × 4 images, seed 20261006, early stopping (best epoch 25/33),
  **17 s on a laptop CPU** (i7-1255U, no GPU).
* Selection on validation only: 18 frozen configurations (resize/pooling/aggregation) → 224 resize, CLS, centroid;
  four heads compared (SupCon linear 0.809, SupCon MLP 0.784, **ArcFace linear 0.865**, SupCon + flip 0.817 coverage@3).
* Export: ONNX opset 18 (89.6 MB); parity vs PyTorch on 1,264 images: max diff 2.9e-5, identical ranks; 103 ms
  median per image on CPU.
* Search: exact cosine within the organisation's gallery for that model version; centroid score; threshold
  0.538/0.5125; at most 3 candidates with 2 supporting photos; no percentages shown.
* **Results (test once):** top-1 0.954, top-3 0.988, mAP 0.922; unknown-animal false suggestions 0.107. Second real-data
  evaluation (6 Oct 2026, held-out identities): **top-1 94.3 %** (vs backbone 91.7 %, colour histogram 37.3 %, chance
  0.4 %), top-3 99.0 %; but **16 % false matches** for unknown dogs at the validation threshold (target 5 %).
* **Release gate (written before results):** top-3 ≥ 0.80 and false suggestions ≤ 0.10 on permissioned field photos of
  the target population → **not met** (no such data; DogFaceNet is aligned pet-dog face crops). So real organisations
  see "Assisted matching unavailable"; demo orgs see a labelled research preview. `/app/model-evidence` shows all of
  this with charts.
* Data tooling: sha256 + 64-bit pHash duplicate graph, label-conflict exclusion (12 groups/25 images found filed under
  two identities), identity-disjoint open-set splits, leakage checks, manifests, annotation round-trip, partner CSV
  import. Partner collection brief and data rights requirements are written (nothing requested from anyone).
* Reproduce: `cd ml && uv run pawid model-fetch | dataset-prepare | identity-select | identity-train | identity-test |
  identity-export`, DogFaceNet eval `pawid dfn-clean | dfn-split | dfn-eval`; register with `pawguard-admin models
  register` and `models research-preview … --reason`.

---

## 10. Other features

* **Pet care rules** (`domain/reminders.py`): `pet_status`, `reminder_plan`, `schedule_reminders` (idempotent; run in
  the vet's review transaction), `after_review` (vet's due date wins, else product demo template), ICS events with
  RFC 5545 line folding, `org_today` with demo clock.
* **QR card / PDF / collar tags** (`domain/petcards.py`): 256-bit random token (`secrets.token_urlsafe(32)`), never
  derived from pet/owner; regenerate/revoke; PDF A5 card; A4 sheet of 16 laminate-ready tags. (PDF currently Latin font
  only — Tamil/Hindi names print as "?"; fix is part of the in-progress work.)
* **Clinic demo clock:** staff-only, demo orgs only; shifts "today" for reminders without changing stored dates.
* **Lost pet finder:** owner reports lost; the public card shows "I found this pet"; finder writes a message without an
  account; owner is notified (email) and replies in-app; neither side sees the other's contact details unless they
  choose to share; rate limits (300 public messages/hour globally).
* **Offline field kit** (`/field`, ADR 0009): explicit device opt-in; IndexedDB stores assigned tasks for 72 h (no
  photos, caregivers, exact locations or vaccination records); `public/sw.js` caches the field page + static assets;
  operations replayed via `/api/v1/sync/operations` with current permissions (accepted / conflict / rejected); sign-out
  wipes caches.
* **Campaign planning:** greedy transparent baseline vs **OR-Tools** vehicle routing with time windows, dose capacity,
  pinned and droppable areas; plan versions with diffs; publish tasks to teams.
* **Surveys, imports, merges, map, audit, system page** — see §7.4.

---

## 11. Security and privacy design

* Browser never holds Supabase tokens; httpOnly cookies; CSRF double-submit + Origin check on the gateway; webhook
  paths exempt but signature-checked (Meta HMAC, Twilio `RequestValidator`).
* JWT verified via JWKS (ES256), `iss`, `aud`, `exp`, `role`; HS256 refused. Org header is only a selector.
* RLS `FORCE` on all tenant tables, runtime role without BYPASSRLS, per-transaction context (no pooled-connection
  leakage — tested), live-session check for sensitive commands.
* Audit is append-only (trigger blocks UPDATE/DELETE). Demo reset only touches demo orgs and rolls back if any
  non-demo row count changes.
* Media: quarantine + byte-level validation; downloads by signed URLs ≤ 120 s after authorisation.
* No `NEXT_PUBLIC_` secrets; `scripts/check_bundle_secrets.py` scans the built bundle.
* **SQL errors never echo parameters** (`hide_parameters=True` on the API/worker/CLI engines — added for the signing work).
* Twilio SDK request logging silenced (it logged URLs with the Account SID).
* Public pages never show owner name/phone/address/location. Notification history shows states, never addresses.
* `.env` and `secrets/` are git-ignored; `.env.example` contains placeholders only. Credentials shared during the
  session (Gmail app password, Twilio auth token, Gemini key) should be **rotated after the hackathon**.

---

## 12. Design system, accessibility, languages

* Tokens in `packages/ui` (contrast measured with the WCAG formula), fonts Manrope (display) + Source Sans 3 (body) +
  Noto Sans Tamil/Devanagari. Status always uses **icon + text + colour** (never colour alone).
* Evidence-state wording is authoritative in `docs/DESIGN_SYSTEM.md` (e.g. "Submitted for review", never
  "Vaccinated"; "Waiting for vet"; "No verified record").
* Playwright tests run axe (WCAG 2.2 A/AA tags) at 390 px and desktop; no horizontal scroll at 390 px.
* Welcome tour per area (`components/tour/welcome-tour.tsx`, "Show tour again" in Help).
* i18n: `messages/en.json` is complete; Tamil/Hindi are **draft translations pending native-speaker review**; English
  fallback for missing keys.

---

## 13. Running it locally

Prerequisites: Docker Desktop, Node 22 + pnpm 11 (corepack), uv.
```bash
uv sync && pnpm install
npx --yes supabase@2.119.0 start --workdir infra -x studio,realtime,edge-runtime,logflare,vector,imgproxy,supavisor,postgres-meta
docker compose -f infra/docker-compose.yml up -d broker            # Valkey on 6379
uv run python scripts/dev_env.py                                   # writes .env (first time)
(cd services/api && uv run alembic upgrade head)
uv run pawguard-admin seed-demo
uv run uvicorn pawguard_api.main:app --port 8000 --no-access-log   # API
uv run pawguard-worker run                                         # Celery worker
uv run pawguard-worker dispatch                                    # outbox + notification ticker
bash scripts/restart-web.sh                                        # build + start web on :3000
bash scripts/public_link.sh                                        # Cloudflare quick tunnel (URL changes on restart)
```
Ports: web 3000, API 8000, Supabase API 54321, Postgres 54322, Mailpit 54324, Valkey 6379. The last public tunnel URL
was `https://considers-reflected-sydney-weeks.trycloudflare.com` (set as `PAWGUARD_EXTRA_WEB_ORIGINS`; changes when the
tunnel restarts). On Windows, restart API/worker by stopping `uvicorn.exe` / `pawguard-worker.exe` processes, then
start them again (see HANDOFF).

Useful admin commands: `pawguard-admin seed-demo`, `demo-reset --yes` (demo orgs only), `push keys`, `models …`,
`create-test-db`, **`keys init | backfill | list | rotate --org <id> [--reissue] | revoke --kid <kid> --reason …`** (new).

---

## 14. Configuration (`.env`; names only)

* Core: `PAWGUARD_ENV`, `PAWGUARD_DEMO_MODE`, `PAWGUARD_DATABASE_URL` (pawguard_api), `PAWGUARD_WORKER_DATABASE_URL`,
  `PAWGUARD_MIGRATE_DATABASE_URL`, Supabase URL/keys, `PAWGUARD_WEB_ORIGIN`, `PAWGUARD_EXTRA_WEB_ORIGINS`.
* Demo recipients: `PAWGUARD_DEMO_NOTIFY_EMAIL` (empty = each person's own confirmed address),
  `PAWGUARD_DEMO_NOTIFY_WHATSAPP`.
* Email: `PAWGUARD_SMTP_HOST/PORT/USER/PASSWORD`, `PAWGUARD_EMAIL_FROM`, `PAWGUARD_EMAIL_DAILY_CAP`.
* Push: `PAWGUARD_VAPID_PUBLIC_KEY/PRIVATE_KEY/CONTACT`.
* WhatsApp Meta: `PAWGUARD_WHATSAPP_TOKEN/PHONE_NUMBER_ID/APP_SECRET/VERIFY_TOKEN/TEMPLATE/API_VERSION`.
* WhatsApp Twilio: `PAWGUARD_WHATSAPP_PROVIDER=twilio`, `PAWGUARD_TWILIO_ACCOUNT_SID`, `PAWGUARD_TWILIO_AUTH_TOKEN`,
  `PAWGUARD_TWILIO_WHATSAPP_FROM`, `PAWGUARD_TWILIO_CONTENT_SID`; calls `PAWGUARD_TWILIO_FROM_NUMBER`.
* Assistant: `PAWGUARD_LLM_PROVIDER` (gemini|ollama|off), `PAWGUARD_GEMINI_API_KEY`, `PAWGUARD_GEMINI_MODEL`,
  `PAWGUARD_OLLAMA_URL`, `PAWGUARD_OLLAMA_MODEL`.
* OCR: `PAWGUARD_OCR_ENGINE`, `PAWGUARD_TESSERACT_CMD`, `PAWGUARD_TESSDATA_DIR`.
* **Signing (new):** `PAWGUARD_SIGNING_MASTER_KEY` or `PAWGUARD_SIGNING_MASTER_KEY_FILE`, `PAWGUARD_ROOT_KEY_FILE`,
  `PAWGUARD_ROOT_KEY_PASSPHRASE` or `PAWGUARD_ROOT_KEY_PASSPHRASE_FILE`, `PAWGUARD_VERIFY_STALE_AFTER_DAYS` (default 7).
  On this machine the three file paths point into `C:/PawGuard/secrets/`.

---

## 15. Testing

* **API (pytest):** `cd services/api && uv run pytest` — runs as the restricted `pawguard_api` role against a separate
  auto-created database `pawguard_test`. Last full run: **148 passed, 1 known failure**
  (`test_planning_api::test_plan_from_survey_to_published_team_tasks` fails 00:00–05:30 IST because a survey date check
  uses the DB's UTC date; documented in ROADMAP). Includes 8 mocked Twilio WhatsApp tests (request params, send-once,
  double click, schedule/cancel, demo-org/staff restrictions, opt-out at send time, signed forward-only callbacks,
  bounded polling, no resend after timeout/crash).
* **Web unit (vitest):** `cd apps/web && pnpm exec vitest run`.
* **E2E (Playwright):** `cd tests && pnpm exec playwright test e2e/<spec> --project=desktop|mobile` (25 specs incl.
  `pet-journey`, `pet-card`, `pets-screens`, `notify-screens`, `whatsapp-demo`, `lost-journey`, `ui-polish-screens`,
  `identity`, `offline`, `planning`, `demo-journey`). Note: `pet-journey` needs a freshly reset demo (it expects an
  overdue Coco reminder that earlier runs marked done).
* **All checks:** `bash scripts/check.sh` (lint, typecheck, API tests, UI tests, build, bundle secret scan, e2e).
* If the test DB gets stuck after a failed downgrade test: `uv run python -c "from pawguard_api.cli import
  ensure_test_database; ensure_test_database('pawguard_test', recreate=True)"`.

---

## 16. Deployment (free tiers)

`docs/DEPLOYMENT_FREE.md`: Oracle Cloud Always Free VM with Docker Compose (`infra/deploy/docker-compose.oracle.yml`),
Caddy + Let's Encrypt (`infra/deploy/Caddyfile`), DuckDNS; or Vercel + Supabase free tier (partial). Not yet tried on a
real VM. `docs/FREE_SERVICES_SETUP.md` explains every manual account step (Gmail app password, VAPID, Meta WhatsApp test
number, Gemini key, Tesseract, Twilio trial). Constraint from the user: **free tiers, trial credits and open source
only**.

---

## 17. Innovative ideas in PawGuard (summary)

1. **Review-gated evidence ledger** — every vaccination record has an explicit state (draft → submitted → verified /
   needs correction / rejected / superseded) with the reviewer's evidence snapshot; owner uploads never count until a
   vet verifies; nobody can verify their own submission or self-approve professional authority (DB constraints).
2. **Honest numbers** — "registered pets up to date, not population coverage"; unknown ≠ no; statuses never say
   "unvaccinated" or "safe".
3. **Human-in-the-loop AI identification** with measured open-set error, release gate written before results,
   research preview only in demo orgs, correction feedback recorded with rank.
4. **Revocable QR card + printable collar tags** with no owner data; regenerate to kill old prints.
5. **Reminders that work with the browser closed** across email/push/WhatsApp/calls, with opt-in per channel,
   double opt-in email, send-time opt-out re-check, dedupe keys, deferrals and provider health.
6. **Keypad phone reminders** (press 1/2) and **WhatsApp delivery tracking** (accepted → sent → delivered → read) with
   signed callbacks, forward-only states and no-blind-resend safety.
7. **Guardrailed multilingual assistant + voice** grounded only in the owner's own records and a fixed app guide.
8. **Certificate OCR as a draft** for the owner and the vet, never auto-trusted.
9. **Lost-pet relay** — finders message owners from the collar QR without accounts or shared phone numbers.
10. **Offline field kit** with operation replay and explicit conflicts; **OR-Tools campaign planner** vs a transparent
    greedy baseline.
11. **Demo clock** to show time-based behaviour live without touching stored dates.
12. **(In progress) Tamper-proof, offline-verifiable vaccination certificates** in the EU-DCC style (COSE/CBOR/Base45
    QR, per-clinic Ed25519 keys sealed with a master key, root-signed trust and revocation lists, verifier PWA that
    works in airplane mode) — and **bite mode**: first aid first, the pet's signed vaccination proof shown inline for
    the doctor, 10-day observation with daily owner check-ins where a missed day shows "No update" (never assumed fine),
    urgent banners, a private reporter link and an expiring, revocable, access-logged doctor link.

---

## 18. Safety wording sources (verified 7 Oct 2026)

* **WHO rabies fact sheet** (updated 17 Sep 2026): "wash the wound with water and soap for at least 15 minutes";
  "seek medical attention".
* **WHO "Frequently asked questions about rabies for the General Public"** (14 Feb 2018): wash ~15 minutes with soap
  and copious water; take the person to a health care facility as soon as possible; "Keep the biting animal confined
  and under observation for 10 days"; "AVOID applying irritants to the wounds such as chili powder, plant juices, acids
  and alkalis"; it also asks whether simply observing the animal instead of starting PEP is justified (the app must
  never suggest that).
* **NCDC National Action Plan for Dog Mediated Rabies Elimination** (rabiesfreeindia.mohfw.gov.in), p.131: "Wash the
  wound immediately with plenty of soap & water", "Consult your doctor immediately", "Do not apply chillies, mustard
  oil or any other irritant on the bite wounds"; p.90: suspect rabid animal signs "within 10 days following exposure".
* Note: **turmeric** is not named in these sources (they name chilli/chillies, mustard oil, plant juices, irritants);
  the user's requested wording includes turmeric — the content register must say so. All wording is "pending clinical
  review".

---

## 19. Docs index
`README.md`, `docs/HANDOFF.md` (resume point), `docs/IMPLEMENTATION_STATUS.md` (phase-by-phase evidence),
`docs/PRODUCT_BRIEF.md`, `docs/ARCHITECTURE.md`, `docs/USER_JOURNEYS.md`, `docs/DESIGN_SYSTEM.md`,
`docs/PERMISSIONS.md`, `docs/DATA_DICTIONARY.md`, `docs/MODEL_CARD.md`, `docs/ML_PLAN.md`, `docs/EVALUATION.md`,
`docs/THREAT_MODEL.md`, `docs/CONTENT_REGISTER.md`, `docs/DATA_SOURCES.md`, `docs/DEMO_GUIDE.md` (§3a pet walkthrough),
`docs/RELEASE_REPORT_PREVENTION.md`, `docs/FREE_SERVICES_SETUP.md`, `docs/DEPLOYMENT_FREE.md`, `docs/ROADMAP.md`,
`docs/BACKUP_RESTORE.md`, `docs/adr/0001…0011`.

---

## 20. Open items for the user (not code)
* Click the email confirmation link that was sent; rotate the Gmail app password, Twilio auth token and Gemini key
  after the hackathon (all were shared in chat).
* Install Tesseract as admin: `winget install --id UB-Mannheim.TesseractOCR -e`.
* Decide whether to push `ui-polish`, `free-services` and `signed-certs-bite-check` (nothing pushed without asking).
* An untracked file `Paws_for_Protection_Circular (1).docx` sits in the repo root (left untouched).

---

## 21. IN PROGRESS — Signed certificates + "This pet bit someone" check (branch `signed-certs-bite-check`)

### 21.1 The task (user's specification, summarised)
**Global rules:** work on `signed-certs-bite-check`; commit after each part; never push without asking; user's Git
identity only, no AI co-author lines; write two ADRs first; verify every library from official docs and pin; use
maintained crypto libraries, never own crypto. **Medical safety:** never "no treatment needed", "safe", "rabies-free";
bite guidance always says wash the wound and see a doctor today whatever the vaccination status; first aid always
first in bite mode; first-aid wording from WHO / India's programme, cited, marked "pending clinical review".
**Privacy:** never show owner name/phone/address/exact location publicly or to a scanner/bite reporter; never show the
reporter's details to the owner unless the reporter chooses; minimal data in signed QR codes. **Honesty:** a signature
proves issuance by a registered clinic and no alteration — not the pet's health or that the animal in front of you is
the one on the card; say this in the UI. **Never fabricate; demo data labelled demo.**

**Part 1 – signed certificates:** per-clinic Ed25519 keys (kid, active/retired/revoked, timestamps) created on clinic
activation + backfill; private keys encrypted at rest with a master key from env/secrets manager, never logged/returned/
sent to the browser; root-signed versioned **trust list** at a public endpoint (retired keys keep verifying older
certificates, revoked keys untrusted); rotate and revoke commands, audited; root key never in the app DB (documented
handling). Credential issued in the same transaction as vet verification and for clinic-recorded vaccinations, plus a
backfill; minimal payload (credential id, version, pet public ref, name, species, sex, coat; vaccine, lot, date given,
next due + source; clinic id + name; vet name; issued-at; kid; no owner data/location/photo); format CBOR + COSE_Sign1
(EdDSA) + zlib + Base45 with prefix `PG1:` (EU DCC style), measure QR length/version; corrections revoke old and issue
new. Root-signed versioned **revocation list** updated in the same transaction as revocations. **Card (web + PDF):**
signed QR for the latest verified rabies vaccination ("Scan to verify this certificate"), other verified vaccinations
with "Show verify QR", existing link QR relabelled "Scan for this pet's page", Noto Sans Tamil + Devanagari embedded in
PDFs, "Owner-entered (unverified)" note (never signed). **`/verify` page:** public, installable PWA, offline after first
visit; camera via BarcodeDetector or a pinned maintained JS QR library; photo upload; paste text; camera permission only
on tap; all verification in the browser (root-verified cached trust list, cached revocation list, key validity at issue
date); results with icon + text + colour: Genuine (green, issuer/vet/date/vaccine/next due/pet details + "Check that
this matches the animal in front of you"), Altered or not genuine (red), Revoked/replaced (amber), Unknown/untrusted
clinic (red), Overdue (amber with Genuine), Can't read (neutral); "Trust list and cancellations last updated: <time>";
online refresh + pet photo; offline > 7 days (configurable) warning; links in public header/footer and clinic
dashboard; footer note "Verification confirms the record came from a registered clinic and wasn't changed. It does not
confirm the pet's health." **Tests:** byte change fails; foreign key fails; tampered trust list rejected; revoked
credential → Revoked; revoked key → untrusted; retired key still verifies older; correction revokes + reissues;
owner-entered cannot get a credential; offline verification with network disabled (browser test); malformed/oversized/
non-PawGuard QR safe; private key never in API response/log/bundle (automated scan); report QR size. Commit.

**Part 2 – bite check:** tables `bite_reports` (pet, random reference, bite date/time + precision, coarse area,
description, species bitten person/other animal, reporter contact optional + encrypted + consent flags, status open/
under observation/closed/disputed/withdrawn), `observation_periods` (start = bite date, length from a reviewed policy
default 10 days for dogs and cats per WHO, "pending clinical review", status, outcome), `observation_checkins` (day
number, date, state normal / not eating / unusual behaviour / pet missing / pet died / other, note, photo, source
owner-reported or vet-recorded), `share_links` (purpose reporter tracking / doctor view, random token, expiry, revoked,
access log); reuse notifications and audit. **Bite mode** on the public pet page: big button "Did this pet bite
someone? Get help now"; order: (1) first aid red panel ("Wash the wound with soap and running water for 15 minutes.",
"See a doctor today, whatever this pet's vaccination status.", "Don't apply turmeric, chilli or other home remedies.",
find facilities + emergency call), (2) the pet's verified rabies vaccination with the Part 1 Genuine check inline or "No
verified rabies vaccination record" + "Show this screen to your doctor. Your doctor decides your treatment.", (3)
"Report this bite" and "Get a link for your doctor"; en/ta/hi with a language switch; one-handed phone use; no account,
no photo, no questionnaire before first aid. **Report form:** when, who bitten, optional coarse area, note, optional
contact with consent → bite report + observation period + private tracking link (sent if contact given); rate limits
per device/IP and per pet; duplicate detection (same pet, same day); owner can respond/dispute; staff moderation queue;
never shown publicly on the pet page. **Owner side:** instant private notification ("Bruno was reported in a bite on
<date>. Please keep him under observation for 10 days and contact your vet today."), owner bite case page (non-
identifying details, tracker, Contact your vet, dispute with reason), daily check-in with optional note/photo, daily
reminder if not done by afternoon; any non-Normal state → owner sees "Contact your vet now", reporter + doctor link get
an urgent banner ("The owner reported a change. Tell your doctor right away."), clinic dashboard alert; a missed day
shows **"No update"** everywhere (never assumed fine); vet can record an examination ("Vet-recorded"). **Reporter
page:** first aid at top, verification result, day-by-day timeline with source labels, urgent banners, relay message or
"Contact through the clinic". **Doctor link:** read-only, signature check result, bite date, timeline with sources,
"Information provided to support your clinical decision. Owner reports are not vet-verified unless marked.", expires
after 30 days, reporter can revoke, access logged; never implies treatment can be skipped. **Closing:** "Observation
period completed — owner reported no changes" (never "rabies-free"/"safe"); missed days or changes stated and flagged for
the vet; notify reporter and owner; surveillance map at area level with small-number suppression. **Tests:** first aid
renders first in all three languages at 390 px; no owner data on public/reporter/doctor pages (API + browser); reporter
contact hidden without consent; day calculation with date-only Asia/Kolkata (bite at 11:30 pm, month boundaries); missed
check-in shows "No update"; non-normal check-in triggers urgent updates; share links expire/revoke (revoked returns
nothing); rate limits + duplicates; automated forbidden-text check ("no treatment needed", "safe", "rabies-free");
re-run all suites. Commit.

**Demo data:** Bruno genuine signed rabies certificate; a sample with one changed date (red); a revoked certificate
(amber); a bite case on day 4 with check-ins days 1–3, one missed day, and an urgent "unusual behaviour" example on
another demo pet; all in the demo reset. **Docs:** ADRs (format; key management/rotation), THREAT_MODEL (forged QR,
stolen clinic key, replayed revoked certificate, fake bite reports, harassment of owners, share-link leaks), OPERATIONS
(key setup/rotation/revocation, master and root key handling), CONTENT_REGISTER (first-aid wording, sources, pending
review), DEMO_GUIDE (2-minute script: genuine green → tampered red → airplane mode → scan Bruno's collar in bite mode →
first aid first → reporter submits → owner alert + check-in → doctor link). **Final report:** what was built/skipped,
real test numbers incl. QR size and offline results, key commands, demo steps, honest limitations.

**Agreed reduced scope (user asked for the fastest version, ~5 h):** keep all of the above except — staff moderation
queue (disputes stored + flagged on the clinic dashboard instead), area-level bite surveillance map, photos in daily
check-ins, separate afternoon reminder (case page shows "Today's check-in needed"), and long docs (short OPERATIONS/
THREAT_MODEL sections). These are reported as "not built".

### 21.2 Decisions taken
* **Format:** COSE_Sign1 + CBOR (integer keys) + EdDSA/Ed25519 + zlib + Base45 + `PG1:` (ADR 0010, written). JWS
  rejected (≈40–60 % longer and not QR-alphanumeric).
* **Keys:** per-org Ed25519, private key sealed with AES-256-GCM under a 32-byte master key (kid as associated data);
  root key = passphrase-encrypted PKCS#8 PEM file (scrypt + AES) outside the DB; root public key compiled into the web
  app (`apps/web/src/lib/verify/root-key.ts`); production plan = offline root signing a short-lived list-signing key
  (documented, not built) (ADR 0011, written).
* **Libraries:** server `cryptography` 50.0.2, `cbor2` 6.1.5, `base45` 0.4.4; browser `@noble/curves` 2.4.0, `cborg`
  6.1.3, `barcode-detector` 3.2.2 (ZXing WASM served from `/vendor/zxing/` so it works offline). `pycose` 1.1.0 (last
  release Dec 2023) only as a test oracle. npm `base45` was rejected (needs Node `Buffer`, no input validation) → own
  tiny RFC 9285 decoder (`base45.ts`) with RFC test vectors — ADR 0010's table still says `base45 2.0.1` for the browser
  and **must be updated**.
* **Operator vs API access:** functions accept the caller's own org (`current_org_id()`) or an operator session (role
  with superuser/BYPASSRLS, e.g. the migration owner used by CLI/seed) via `app.signing_org_ok()`.
* **No blind writes from the API:** credentials are written only through `store_credential` / `revoke_credential`;
  `replaced_by` FK is DEFERRABLE INITIALLY DEFERRED so a re-issue revokes the old certificate pointing at the
  pre-generated new id, then stores the new one (one active certificate per record).
* Signing not configured → verification still succeeds (credential skipped via savepoint; backfill later).
* Demo reset NOT run on the dev DB (it would wipe the user's demo activity); only the new seed step was run.

### 21.3 Done so far (all uncommitted on `signed-certs-bite-check`)
| File | State |
|---|---|
| `docs/adr/0010-signed-certificate-format.md`, `0011-signing-key-management.md` | Written (update base45 row) |
| `services/api/pyproject.toml`, root `pyproject.toml`, `uv.lock` | cryptography, cbor2, base45, uharfbuzz pinned; pycose dev |
| `apps/web/package.json`, `pnpm-lock.yaml` | @noble/curves 2.4.0, cborg 6.1.3, barcode-detector 3.2.2 |
| `apps/web/scripts/copy-maplibre-worker.mjs` | Also copies `zxing_reader.wasm` + LICENSE to `public/vendor/zxing/` (git-ignored) |
| `.gitignore` | `/secrets/`, `apps/web/public/vendor/zxing/` |
| `services/api/src/pawguard_api/settings.py` | signing_master_key(_file), root_key_file, root_key_passphrase(_file), verify_stale_after_days |
| `services/api/src/pawguard_api/integrations/cose.py` | sign1/parse_sign1/verify_sign1, to_qr_text/from_qr_text (2000-char and 4 KB inflate caps), new_key, seal/unseal (AES-GCM), master_key, root_key (cached), write_root_key, ROOT_KID `pg-root1`. cbor2 6 decodes tag arrays as tuples (handled) |
| `services/api/migrations/versions/0020_signed_credentials.py` | Applied to dev DB (head 0020) |
| `services/api/src/pawguard_api/domain/credentials.py` | Actor, ensure_key, rotate_key, revoke_key, build_payload, issue, try_issue, ACTIVE_FOR_EVENT, issue_replacing, revoke_for_event, reissue_after_correction, backfill, trust_list, revocation_list (signed on demand, cached per version 300 s), credential_photo, qr_svg/qr_png, is_rabies, pet_certificates, tampered_copy (demo), demo_samples |
| `services/api/src/pawguard_api/credential_contracts.py` | VaccinationCorrect, CertificateOut, PetCertificatesOut, SignedListOut, CredentialPhotoOut, IssuedOut, DemoSample(s)Out |
| `services/api/src/pawguard_api/routers/credentials.py` (registered in `main.py`) | `GET /api/v1/public/trust-list`, `GET /api/v1/public/revocations`, `GET /api/v1/public/credentials/{id}/photo`, `GET /api/v1/public/demo-certificates` (demo mode), `GET /api/v1/my/pets/{pet_id}/certificates`, `POST /api/v1/vaccination-events/{id}/certificate` (vet; 409 not_verified), `POST /api/v1/vaccination-events/{id}/correction` (vet) |
| `domain/vaccinations.py` | `review()` issues a credential when verified (same transaction); new `correct_verified()` (new verified record supersedes old; old credential revoked → new issued) |
| `domain/clinic.py` | `record_clinic_vaccination()` issues a credential |
| `services/api/src/pawguard_api/cli.py` | `keys init|backfill|list|rotate|revoke`; owner engine `hide_parameters=True` |
| `services/api/src/pawguard_api/db.py` | `hide_parameters=True` |
| `services/api/src/pawguard_api/seed/credentials.py` + `seed/runner.py` | Demo keys, certificates for all verified demo records, Bruno's replaced (revoked) sample; demo reset already covers tables with `org_id` |
| `secrets/` + `.env` | `keys init` ran: master key, root key PEM (passphrase-encrypted), passphrase file; three `*_FILE` paths added to `.env`. Root PUBLIC key `pa9Iv86uCAZm7BOiizW7G/Y28zaXhlqoedj4nChNZBs=` |
| Dev DB | 22 demo certificates issued + 1 replaced sample (Bruno). **Measured: 433 characters, 282-byte COSE; QR version 13 (69×69 modules) at error level M, version 11 at L, 16 at Q; alphanumeric mode.** Recommend ≥ 3.5 cm print width. Python verification of Bruno's certificate: OK |
| `scripts/make_verify_vectors.py` → `apps/web/src/lib/verify/__fixtures__/vectors.json` | Cross-language vectors from the server's signing code with TEST-ONLY keys (genuine 406 chars) |
| `apps/web/src/lib/verify/base45.ts`, `cose.ts`, `verify.ts`, `root-key.ts`, `verify.test.ts` | Browser verifier library + vitest suite (written) |

### 21.3a Part 1 COMPLETED (7 Oct 2026)
Fixed the pause point (cborg 6 tag decoders must call the supplied `decode()`), then built: cached root-verified lists
(`lists-store.ts`, anti-rollback, staleness), QR reading (`scanner.ts`: BarcodeDetector or ZXing WASM ponyfill from
`/vendor/zxing/`), `/[locale]/verify` page + `components/verify/verifier.tsx` (scan / upload / paste, results with icon +
text + colour, freshness line, offline and stale warnings, online pet photo, honesty footer), `/[locale]/verify/samples`
(demo only, via the security-definer `app.demo_sample_certificates()`), `public/verify.webmanifest`, service worker caches
the verify page and the WASM reader, CSP `'wasm-unsafe-eval'` only on `/verify`, "Verify a certificate" links (header,
footer, clinic dashboard), owner card section `components/pets/signed-certificates.tsx` (featured rabies QR "Scan to
verify this certificate", others behind "Show verify QR", owner-entered note, honesty note; link QR captioned "Scan for
this pet's page"), PDF with embedded Noto Sans (Latin/Tamil/Devanagari, HarfBuzz shaping) + signed rabies QR,
`app.animal_vaccination_events` verifier rule changed so superseded records keep their verifier, version bumps robust to
missing rows, bundle secret scan covers master/root/clinic keys, `docs/OPERATIONS.md`, THREAT_MODEL section, ADR 0010
updated (own base45 decoder, measured size). Tests: vitest 19/19; pytest `test_credentials.py` 6/6 (incl. pycose interop
and leak scan); full API suite 155 passed; Playwright `verify.spec.ts` 6/6 (incl. offline + photo/WASM), `pet-card`,
`offline`, `pets-screens`, `ui-polish-screens`, `foundation`, `welcome` all pass; bundle scan: 23 secret values, 0 leaks.

### 21.4 (Resolved) pause point
Running `pnpm exec vitest run src/lib/verify` failed at module load: `parseTrustList(vectors.trust)` threw
`ListRejected("unreadable list")`, i.e. `parseSign1(b64ToBytes(doc.cose))` failed in the browser library for the
root-signed trust list (the certificate path was not yet exercised). Likely causes to check first: (a) `cborg`
decoding of the tag-18 COSE structure with `useMaps: true` + `tags[18]` (maybe the tag decoder receives the array
differently, or cborg needs `tags` as a sparse array of functions that returns the value), (b) `cborg` rejecting
something in the trust payload (nested maps with integer keys inside an array, booleans, or large integers), (c)
`b64ToBytes` in the node test environment. I was about to run a small debug test that decodes the outer structure
and payload separately to see which step fails.

### 21.5 Remaining checklist (Part 1)
1. Fix the vitest failure; get all `verify.test.ts` cases green (base45 RFC vectors, lists, genuine, altered, byte flips,
   unknown key, kid swap, revoked credential, revoked key, retired before/after, overdue, unreadable set, no lists,
   inflate bomb, length cap).
2. Browser list store (`lists-store.ts`): fetch `/api/v1/public/trust-list` + `/revocations`, verify with root key,
   anti-rollback (keep higher version), cache in localStorage with fetched-at time, staleness from the signed
   `stale_after_days`.
3. `/[locale]/verify` page + client component: Scan (BarcodeDetector → `barcode-detector/ponyfill` with
   `prepareZXingModule({overrides:{locateFile: → /vendor/zxing/zxing_reader.wasm}})`, camera permission only on tap),
   upload photo, paste text; result panels (icon + text + colour, en/ta/hi strings); freshness line; stale warning;
   online pet photo; honesty footer; demo samples page (`/[locale]/verify/samples`, demo mode only).
4. Offline: extend `public/sw.js` to cache `/(en|ta|hi)/verify` navigations and `/vendor/zxing/`; the page registers
   `/sw.js` and pre-caches its own static assets; `public/verify.webmanifest` + page `manifest` metadata (installable).
5. Links: "Verify a certificate" in public header and footer (`components/public-shell.tsx`) and on the clinic dashboard.
6. Owner card UI (`/app/pets/[id]/card` and/or pet page): featured rabies signed QR "Scan to verify this certificate",
   others with "Show verify QR" (`<details>`), "Owner-entered (unverified) records are never signed" note, honesty note,
   relabel link QR "Scan for this pet's page".
7. PDF: download Noto Sans + Noto Sans Tamil + Noto Sans Devanagari TTFs (OFL) into `services/api/src/pawguard_api/
   fonts/`; fpdf2 `add_font` + `set_fallback_fonts` + `set_text_shaping(True)` (uharfbuzz); add the signed rabies QR to
   the card PDF; replace `_latin()` usage.
8. Vet correction UI (optional small button) — API exists.
9. Pytest `tests/test_credentials.py`: issue on review and clinic record in the same transaction; payload has no owner
   fields; owner-entered/unverified → 409; correction revokes old (replaced_by) and issues new; revocation list contains
   the old id and version bumps; trust list verifies with the root public key; rotation keeps the retired key; key
   revoke marks revoked; pycose verifies our COSE (interop); byte-flip fails server-side; malformed/oversized QR
   rejected; **leak scan** (private key raw/hex/base64 never in API responses or caplog; `scripts/check_bundle_secrets.py`
   extended to scan the web bundle for root/clinic private key encodings). Test fixture must create temp key files and
   monkeypatch settings.
10. Playwright `verify.spec.ts`: genuine green, altered red, cancelled amber; **offline**: load once online, then
    `context.setOffline(true)`, reload and verify Bruno's sample → Genuine.
11. Regenerate API client (`pnpm run generate` in `packages/api-client`), restart API/worker/web, update ADR 0010 base45
    row, CONTENT_REGISTER + DATA_SOURCES (WHO FAQ 2018, NCDC NAPRE), commit Part 1.

### 21.6 Remaining checklist (Part 2, reduced scope)
Migration 0021 (`organisations.contact_phone` nullable; `bite_reports`, `observation_periods`, `observation_checkins`,
`share_links` + access log; security-definer public functions; reporter contact sealed with the master key; rate limits
and same-day duplicate detection), domain `bites.py`, routers (public bite mode data by card token, report, reporter page
by token, doctor page by token, revoke/expire; owner case + check-ins + dispute; vet-recorded exam; clinic alerts),
notifications kind `bite_alert` / `bite_update`, owner day calculation in Asia/Kolkata date-only, "No update" for missed
days, closing logic, web pages (bite mode on `/card/[token]` with first aid first + language switch; report form; reporter
tracking page; doctor page; owner bite case page with check-ins; clinic dashboard alert list), en/ta/hi strings
(ta/hi marked draft translations pending clinical + language review), demo data (bite case on day 4 with days 1–3
check-ins, one missed day, an urgent "unusual behaviour" case on another pet), tests listed in §21.1, docs
(THREAT_MODEL/OPERATIONS/CONTENT_REGISTER/DEMO_GUIDE sections), full test re-run, commit Part 2, final report.

### 21.6a Part 2 BUILT (7 Oct 2026, reduced scope)
* **Migration 0021** (`0021_bite_check.py`): `organisations.contact_phone`; `observation_periods` (one per pet + bite
  date; 10 days; policy note "pending clinical review"; status active/completed/completed_with_gaps/change_reported),
  `bite_reports` (reference `BR-XXXX-XXXX`, date, optional time, person/animal, coarse area, note, reporter email sealed
  with the master key only with consent, consent flags, status incl. disputed, duplicate_of, client hash),
  `observation_checkins` (day, state normal/not_eating/unusual_behaviour/missing/died/other, note, source owner/vet),
  `share_links` (reporter/doctor, SHA-256 token hash, expiry, revoked) + `share_link_access` (view log); delivery kinds
  `bite_alert` / `bite_closed` with `observation_period_id`; security-definer functions `public_bite_pet`,
  `public_create_bite_report` (limits 3/client/hour, 5/pet/day, date within 30 days, duplicates join the period, owner
  alert queued once), `share_view` (logs access), `share_create_doctor_link` (30 days, max 5), `share_revoke_doctor_links`,
  `bite_update_contacts`, `close_due_observations`, `queue_bite_notice`; claim function returns bite date/pet sex.
* **API** (`domain/bites.py`, `routers/bites.py`, `bite_contracts.py`): `GET /public/cards/{token}/bite`,
  `POST /public/cards/{token}/bites`, `GET /public/bites/{token}`, `POST /public/bites/{token}/doctor-links`,
  `POST /public/bites/{token}/doctor-links/revoke`, `GET /my/bites`, `GET /my/bites/{id}`, `POST /my/bites/{id}/checkins`,
  `POST /my/bites/{id}/dispute`, `GET /clinic/bites`, `POST /clinic/bites/{id}/exams`. Day counting with the clinic's local
  date (Asia/Kolkata) + demo clock; "No update" for missed days; urgent on any non-normal; reporter emails (tracking link
  once, urgent change, closing) via BackgroundTasks / dispatcher; gateway forwards `x-pawguard-client-ip`.
* **Dispatcher**: every 10 minutes `close_bite_observations()` ends periods and sends closing notices.
* **Web**: `/[locale]/card/[token]/bite` (bite mode: minimal shell with language switch, first aid first, record +
  in-browser signature check, report form), `/[locale]/bite/[token]` (reporter: first aid, urgent banner, record,
  timeline, contact through the clinic, doctor links; doctor: read-only + clinical note), `/[locale]/app/bites` (owner:
  contact vet / "Contact your vet now", one-tap daily update, timeline, reports, dispute), card page red button, My pets
  banner, clinic dashboard "Bite reports" (urgent/missed/disputed/duplicate flags, vet examination form). en + ta/hi
  (draft) strings in `bite.*`.
* **Demo data** (`seed/bites.py`, part of seed and demo reset): Bruno day 4 with updates on days 1 and 3, day 2 missed;
  Misty urgent "unusual behaviour" on day 2; fixed demo reporter links `pawguard-demo-reporter-link-bruno-0001` /
  `-misty-0002`; Lotus contact email `clinic.lotus@example.org`.
* **Tests**: `test_bites.py` 9/9 (day counting across midnight IST, month/leap/year boundaries; "No update"; privacy;
  urgent fan-out; share links expire/revoke + access log; rate limits/dates/duplicates; dispute + closing; forbidden
  wording incl. en.json `bite.*`); Playwright `bite.spec.ts` 3 tests × mobile + desktop (first aid first in en/ta/hi at
  390 px; report → private link → doctor link → revoke; owner update → urgent banners → clinic view; forbidden wording).
* **Not built (agreed reduced scope)**: staff moderation queue (disputes flagged on the dashboard instead), area-level
  bite surveillance map, photos in daily check-ins, the separate afternoon reminder (case page and My pets banner show
  "Today's update is needed"), reporter contact by phone (email only), in-app relay messaging (pages say "Contact through
  the clinic").

### 21.7 How to resume
```bash
git checkout signed-certs-bite-check          # uncommitted work is in the working tree
cd services/api && uv run alembic current     # expect 0020 (head)
cd ../../apps/web && pnpm exec vitest run src/lib/verify    # start at §21.4
```
Services may need restarting (API, worker, dispatcher, web) after code changes — see §13.

### 21.8 Evidence check, clinic map, wording polish (7 Oct 2026)
User asked: (1) "AI to verify the certificates" on the Review page, like the tampered-certificate demo; (2) the map was
empty — add points with details; (3) remove "demo / fictional" wording everywhere ("it should be fully polished").
* **Evidence check** (`domain/evidence_check.py`, `GET /api/v1/vaccination-events/{id}/evidence-check`, web
  `components/vaccinations/evidence-check.tsx` under each item on `/app/review`): for each evidence file it renders the
  image (PDF page 1 via `pypdfium2`), finds QR codes (OpenCV `QRCodeDetector`/`Aruco`, prefers `PG1:`), verifies a signed
  PawGuard QR server-side (trust list, revoked keys, signature, validity ±5 min, revocation list), flags a pet-card QR
  of another pet as a problem, reads date/vaccine/batch (Gemini vision for sample orgs; `PAWGUARD_OCR_ENGINE=gemini`) and
  compares with the record (date differs = problem; missing = needs a look), and flags the same file (sha256) used on
  another record. Summary: problems / check / partial / consistent. Advisory only — the vet decides. Deps added:
  `pypdfium2==5.14.0`, `opencv-python-headless==5.0.0.93`. Tests: `tests/test_evidence_check.py` (5).
* **Clinic map**: `seed/clinic_map.py` (Lotus outreach areas T. Nagar/Mylapore/Adyar `LOTUS-TNG/MYL/ADY`, 12 community
  dogs with mixed rabies status, sightings, clinic-visit sightings for Bruno/Misty/Coco, 4 tasks). `/map/layers`
  sightings carry name/species/status/last_verified/next_due. `area-map.tsx` colours points by status and opens popups
  (DOM text nodes only) for sightings, tasks and areas; legend per status.
* **Wording polish**: full-width `DemoBanner` removed (public + app shells); bite pages keep a small footer line; the
  sidebar chip says "Sample data". ~60 en.json strings rewritten (welcome, sign-in, clinic "Presenter tools", "Preview
  date", "Standard schedule", WhatsApp "practice reminder" …); ta/hi banner/chip strings. Seed files and the dev DB
  renamed in place (SQL, no reset; audit log left untouched). Pet-card PDF: one grey "Sample data" line. Email footer
  "(Sample data — not for real medical use.)". All 34 active sample certificates were re-signed (`issue_replacing`) so
  QR payloads carry the new names; Bruno's rabies record re-issued once more so the "cancelled" sample also shows them;
  trust list version bumped. Tests and `docs/DEMO_GUIDE.md` updated to the new names.

### 21.9 Automatic evidence gate for owner uploads (7 Oct 2026)
User asked that clearly wrong uploads never reach the vet, with failures shown at upload time, and that owner and
vet are linked end to end. The vet still makes the final "Verified" decision (the app's core promise).
* `evidence_check.check_files()` is shared by the vet's check and `gate_owner_submission()`, which runs inside
  `petcare._submit_owner_record` before anything is saved. It refuses (422 `evidence_rejected`, field
  `certificate_media_ids`, owner wording that names no other pet or record) on: another pet's or the pet's own
  PawGuard card, a changed/cancelled/untrusted signed certificate, a signed certificate for another pet, a file with
  neither a vaccination date nor a vaccine name, a date different from the certificate, a different clinic vaccine
  than the certificate shows, or a file already used for a different pet. Uncertain results still go to the vet. It
  waits up to 15 s for upload scanning, then 409 `media_not_ready`.
* Owner form (`owner-record-form.tsx`): certificate read automatically after upload (retries while the scan runs; PDFs
  read from page 1), vaccine and date pre-filled; a refusal returns to the certificate step with the reasons.
* Vet (`review-actions.tsx`): "Request correction"/"Reject" pre-fill the reason from the check's `owner_message`s.
* Per-pet sample certificates: `apps/web/public/demo/certificate-{bruno,misty,coco}.jpg` (marked SAMPLE, 06 Oct 2026).
