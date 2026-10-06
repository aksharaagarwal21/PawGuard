# Implementation status

Four separate dimensions are tracked and never merged: **software** (built / tested locally), **data** (available / permitted), **professional approval** (content, clinical, veterinary), **real-world validation** (partner-tested, pilot).

Legend: ✅ done and checked · 🟡 partly done · ⛔ blocked (external) · ⬜ not started

## Phase matrix

| Phase | Software | Data | Approval | Validation | Notes |
|---|---|---|---|---|---|
| 0 Investigate & plan | ✅ | — | — | — | See Phase 0 log |
| 1 Product & design | ✅ | — | ⛔ wording needs vet/clinical review | ⛔ no user testing yet | Journeys, wireframes, wording, tokens |
| 2 Foundation & shell | ✅ | — | ⛔ starter health content unreviewed | — | See Phase 2 log |
| 3 DB & authorisation | ✅ | demo fixtures only | — | — | See Phase 3 log |
| 4 Manual Prevention | ✅ | demo fixtures only | ⛔ wording not yet reviewed by vets/field staff | ⛔ no user testing | See Phase 4 log |
| 5 OpenCV + detector | ✅ | COCO licence-filtered sample (not field data) | — | ⛔ not evaluated on Indian field photos | See Phase 5 log |
| 6 Data prep & annotation | ✅ | DogFaceNet research benchmark prepared; ⛔ partner identity data | — | ⛔ 12 label-conflict groups await human adjudication | See Phase 6 log |
| 7 PawID train/eval | ✅ integration built and tested | DogFaceNet research benchmark only; ⛔ permissioned field identity data | — | ⛔ release gate not met → research preview in demo orgs only | See Phase 7 log |
| 8 Offline + planning | ✅ | demo data only; ⛔ no real travel-time matrix | — | ⛔ not field-tested on real devices/connectivity | See Phase 8 log |
| 9 Prevention release audit | ✅ demo-ready | fictional demo data only | ⛔ vet/clinical review of wording | ⛔ no field or real-phone testing | See Phase 9 log and RELEASE_REPORT_PREVENTION.md |
| Pet topic | ✅ demo-ready | fictional demo data only | ⛔ wording and templates not vet-reviewed; ta draft | ⛔ no owner/clinic testing | Hackathon topic: pet vaccination tracking and reminders (below) |
| 10–15 | ⬜ | | | | Not started; Prevention first |

## Phase 0 — Investigate, resolve dependencies, plan (2026-10-05) ✅

**Goal:** understand environment and dependencies; decide architecture; record risks and fallbacks.

**Findings (actual checks run):**
- Workspace `C:\PawGuard` was empty; `git init` performed (no commits made).
- Tools: Node 22.18.0, npm 10.9.3, corepack 0.33.0 (pnpm not installed globally), Python 3.13.5 + uv 0.7.12, Git 2.51.1, Docker 28.4.0 / Compose 2.39.2 (engine started; VM 12 CPU / 8 GB), Java 23 (unused). No psql/redis locally — both run in containers.
- Hardware: i7-1255U (10 cores/12 threads), 15.7 GB RAM, ~140 GB free disk, Intel Iris Xe only (no CUDA). **All ML is CPU-bound.**
- Network: npm, PyPI, GitHub, Hugging Face, Zenodo, Docker Hub reachable.
- Local Supabase stack started with Supabase CLI 2.119.0 (`infra/supabase/config.toml`): Postgres 17.11 with PostGIS 3.3.7 and pgvector 0.8.2 available; GoTrue issuing **ES256** tokens from a locally generated signing key (gitignored); private bucket `pawguard-media` created; Studio/realtime/edge/analytics disabled; sign-ups disabled; PostgREST auto-exposure disabled.
- Role check: `postgres` has `BYPASSRLS` and `CREATEROLE` → used for migrations only; runtime roles will be created without `BYPASSRLS`.
- Version research (registry queries 2026-10-05): typescript-eslint supports TS `<6.1` → pin TS 6.0.3 (ADR 0001).
- Sources checked (see `DATA_SOURCES.md`): WHO fact sheet (updated 17 Sep 2026) reachable; NRCP site reachable via curl but its TLS chain fails strict verification in an automated fetcher; helpline 15400 serves five named states only; DogFaceNet Zenodo record is CC-BY-4.0 with an uncurated-label disclaimer and web-collected images; YOLOX 0.1.1rc0 provides an official `yolox_s.onnx` (Apache-2.0); `facebook/dinov2-small` Apache-2.0 at a pinned revision.

**Produced:** `PRODUCT_BRIEF.md`, `ARCHITECTURE.md` (diagram, boundaries, dependency matrix, risk register), ADRs 0001–0006, `DATA_SOURCES.md`, this file, `HANDOFF.md`.

**Gate check:** critical auth/data path has no unresolved contradiction (ADR 0002 resolves the httpOnly-vs-Supabase-default tension; ADR 0003 the RLS context). Every critical capability has an implementation path or explicit fallback (`PRODUCT_BRIEF.md` § "How the product works when things are missing"). → **Pass.**

## Phase 1 — Product and design (2026-10-05) ✅

**Produced:** `USER_JOURNEYS.md` (J1–J7 with step counts, recovery paths, screen→API map), `DESIGN_SYSTEM.md`
(tokens with measured contrast, typography, evidence-state wording table, forbidden strings, components,
page inventory, wireframes A–I, interaction specs). Contrast of the brief's palette re-computed: claims match
(11.46 / 5.15 / 7.76 / 6.33). Added `--pg-control-border #6F877C` (3.87:1) because the brief's divider
(1.47:1) cannot serve as a control boundary under WCAG 1.4.11.

**Gate:** the J2–J6 Prevention journeys can be followed through the wireframes; wording never states "safe",
"vaccinated" or a % match; mobile primary actions sit in the bottom bar. → Pass. **Not done:** testing the
wording with real field workers/vets (none available) — carried forward.

## Phase 2 — Runnable foundation and shell (2026-10-05) ✅

**Built**
- Monorepo: pnpm 11.28.4 workspace (`apps/web`, `packages/ui`, `packages/api-client`, `tests`) + uv workspace
  (`services/api`, `services/worker`); exact pins in `pnpm-lock.yaml` / `uv.lock`.
- FastAPI: settings, JSON structured logs with redaction and request IDs, uniform error shape, JWKS token
  verification (ES256/RS256 only), membership-based org context, `/health/live`, `/health/ready`, `/api/v1/me`
  (GET/PATCH with row_version), `/api/v1/system/providers` (system.view), `/api/v1/demo/accounts` (demo only).
- DB migrations 0001–0002: extensions, private `app` schema, runtime roles (SCRAM verifiers computed
  client-side), context functions, organisations / user_profiles / memberships / professional_approvals /
  audit_events with FORCE RLS; session-liveness function over `auth.sessions`.
- `pawguard-admin`: `bootstrap-admin`, `seed-demo` (idempotent, refuses outside dev/test+demo), `create-test-db`.
- Worker skeleton: Celery app (acks_late, no result backend), `pawguard-worker run|dispatch` (dispatcher is a
  stub until the outbox table lands in Phase 3).
- Web: Next 16 App Router with next-intl (en/ta/hi; ta/hi interface strings are labelled drafts), server-only
  Supabase session with forced httpOnly cookies, `proxy.ts` refresh, same-origin `/api/v1` gateway with
  Origin + double-submit CSRF, landing, urgent help (source + review status, no form/AI), learn / find-care /
  about / sources (honest "not yet" pages), sign-in with dev-only demo shortcuts, app shell (capability-filtered
  nav, org switcher, connection chip, mobile bottom bar), Today (empty state), System status.
- `packages/ui`: tokens (Tailwind v4 `@theme`), Button, Notice, StatusChip, EmptyState, Card, Field, inputs,
  RadioGroup, ErrorSummary, Dialog, Toast.
- Containers: `infra/docker/python.Dockerfile` (api/worker), `web.Dockerfile`, compose `--profile app`; CI
  workflow `.github/workflows/ci.yml` + local equivalent `scripts/check.sh`.

**Checks actually run (all on this machine, 2026-10-05)**
| Check | Result |
|---|---|
| `uv run pytest` (31 tests: token verification incl. HS256/wrong iss/aud/role/kid/expiry; org context incl. revoked/suspended/expired/foreign/nonexistent orgs; immediate revocation; RLS as `pawguard_api`; pooled-connection context leakage; self-approval blocked; append-only audit; session liveness) | 31 passed |
| `pnpm --filter @pawguard/ui test` (4) | passed |
| ruff, `pnpm -r typecheck`, `pnpm -r lint`, api-client freshness | clean |
| `next build` (all routes dynamic so runtime config is never baked into the image) | success |
| Playwright e2e, desktop 1440 + mobile 360 (public help without account, ta fallback notice, axe WCAG 2.2 AA scans on landing/help/today/system, wrong password, httpOnly + SameSite=Lax auth cookies, capability-filtered nav and 403 page, admin provider page has no secrets, sign-out, CSRF rejection, gateway read) | 20 passed |
| Session refresh (expired access token refreshed server-side, cookie stays httpOnly) and tampered-cookie rejection | 2 passed |
| Bundle secret scan of `.next/static` | 0 findings |
| Docker images built and smoke-tested (api ready + non-root uid 10001; web serves pages with runtime env; worker CLI) | api 369 MB, web 383 MB, worker 840 MB |
| First load (Pixel-7 emulation, 360 px, **no throttling**, local `next start`) | `/en` LCP 160 ms, CLS 0, 499 KB; `/en/help` LCP 92 ms, 44 KB (`docs/evidence/phase2-first-load.json`). Not representative of field networks. |

Screenshots: `docs/screenshots/phase2/*-{360,390,768,1440}.png` (landing, help, help-ta, sign-in, today).

**Known limitations**
- Health wording is unreviewed starter content; ta/hi interface strings are unreviewed drafts.
- CSP still allows inline scripts (Next.js bootstrap) — nonce CSP planned for Phase 14.
- CI workflow has not run on a hosted runner (no remote); `scripts/check.sh` is the exercised equivalent.
- Worker image currently includes the full API dependency set (840 MB); slim down when ML deps land.
- The worker's `celery_app` needs DB settings at import time (fine in deployment; noted for tooling).

## Phase 3 — Prevention database and authorisation boundary (2026-10-06) ✅

**Built**
- Migrations 0003–0005: 27 new tables (outbox, idempotency, background jobs, data sources, consent, sharing
  agreements, privacy requests, data-quality issues, areas, teams, animals, caregivers, observations, media,
  observation media, image quality, vaccine products/lots, vaccination events/evidence/reviews, merges, campaigns,
  tasks, sync operations) + `animal_followup_tasks` view. All 32 `app` tables have RLS **enabled and forced**.
  Database-level guards: no future administration dates, precision/date consistency, no self-review (trigger),
  append-only reviews and audit, reason-required states, tenant-consistent compound foreign keys,
  `client_operation_id` uniqueness for replay safety. Worker tenant context (`app.set_worker_context`) only for a
  claimed job. Derived `last_observed_at` does not bump `row_version` (0004).
- Command layer (`pawguard_api/domain`): animals, observations (exact vs ~500 m approximate locations), media
  intents/completion/signed links, vaccination submit/review/amend with conflict flags (never auto-resolved),
  tasks state machine, merges (propose → second-person approve → reversible via manifest). Each command checks
  capability + record scope, writes audit + outbox in the same transaction; Idempotency-Key support; row_version
  conflicts → 409; DB constraint violations → structured 4xx.
- 36 more API endpoints (44 operations in OpenAPI), each documenting its permission (`docs/PERMISSIONS.md`).
- Worker: outbox dispatcher (SKIP LOCKED, backoff, failed state), job claim/run framework (at-least-once,
  duplicate deliveries are no-ops), media validation from bytes (Pillow pixel budget, format vs declared type,
  EXIF transpose, metadata-free JPEG derivatives, quarantined original deleted, PDF header check, duplicate-hash flag).
- Demo seed: 2 organisations, 8 accounts, 6 synthetic areas, 50 animals (incl. sparse records and a duplicate),
  96 sightings (some > 6 months old), 28 vaccination records (verified, pending, correction requested, rejected,
  conflicting pair), 12 tasks (incl. blocked and auto-created correction task), a pending merge, a sync conflict.
- Generated docs: `docs/DATA_DICTIONARY.md` (from the live catalog, with ER diagram), `docs/PERMISSIONS.md`.

**Checks actually run**
| Check | Result |
|---|---|
| `uv run pytest` — 61 tests incl. 21 Prevention integration tests, 7 media-pipeline tests against real local Storage, seed repeatability, migration downgrade-to-base and upgrade | 61 passed |
| Cross-tenant: animal/event/observations/media reads, submit/review on another tenant's record, foreign area reference, org-header spoofing | refused (404 / 403 / 422) |
| Review authority: volunteer, unapproved vet, signed-out vet session, admin, self-review (API and direct SQL) | all refused with specific codes |
| Concurrency: two approved vets reviewing the same record simultaneously | exactly one 200, one 409, one review row |
| Replay: same Idempotency-Key (and same `client_operation_id`) | one record; key reuse with a different body → 422 |
| Revocation: membership revoked mid-session; professional approval revoked | next request refused |
| Media: EXIF rotation applied and stripped, GPS gone, disguised HTML, PNG-as-JPEG, 81 MP bomb, size mismatch, unfinished upload | handled as specified |
| ruff / typecheck / API client regenerated | clean |

**Limitations / carried forward**
- Export endpoint (and its scope test) lands with Phase 4 programme views.
- `vaccination.review` queue ordering is oldest-first only; no workload balancing yet.
- The worker uses a server-wide Storage key (residual risk in THREAT_MODEL).
- No user testing of wording yet.

## Phase 4 — Manual Prevention end to end (2026-10-06) ✅ (software); user validation not done

**User-visible capability**
- Today: quick actions, assigned tasks with start/complete/can't-complete, corrections requested, recent
  submissions with evidence state, review queue count (vets), pending merge proposals (merge holders).
- Animal registry: server-side search (reference, nickname, description) with area / profile state / evidence /
  recency / open-task filters, cursor pagination, filters kept in the URL, thumbnails from private storage.
- Registration: 3-step form (observed details with explicit "Unknown" options, area / date / opt-in device
  location / optional photo, review) → provisional profile; idempotent save.
- Animal profile: evidence-state panel with the approved wording (never "vaccinated/unvaccinated/safe"), details,
  vaccination records, sightings (exact vs ~500 m approximate by capability), tasks, history (audit.read only),
  dispute / review / activate / archive with reasons, duplicate-merge entry point.
- Photo / sighting capture with real upload → completion → worker validation status; without an animal the page
  states plainly that photo matching is unavailable and offers the manual paths.
- Vaccination evidence form: date precision (exact / month / year / unknown), product and lot from lists or as
  written, "not known" everywhere, evidence uploads (images + PDF), submit = "Submitted for review".
- Vaccination record page: state + explanation, conflicts, evidence (short-lived links), review history,
  correction flow (supersedes; original kept).
- Verification workbench (vets with approved authority only): oldest-first queue excluding own submissions,
  evidence beside submitted fields, animal context and other records, Verify / Request correction / Reject with
  confirmation and required reasons; stale/concurrent changes handled.
- Tasks: mine / all (coordinators), create, assign, transitions with required reasons.
- Merges: compare → propose (reason) → a different person approves or rejects → reversible.
- Map & areas: MapLibre (lazy, self-hosted worker), area outlines + sightings + open tasks with a text legend,
  equivalent table of registry measures labelled "not population coverage", data mode and time stamp, CSV export
  (report.aggregate; scoped, audited, declares demo/live).

**Fixes found by testing this phase:** Tailwind preflight removed link underlines (WCAG 1.4.1) → restored
globally; unlabeled hidden file inputs; gateway did not default the organisation for single-org users; MapLibre
worker could not load under the bundler → self-hosted; "last seen" displayed a fabricated midnight time; records
created in a demo organisation were not flagged demo → database trigger (migration 0006); mobile workbench showed
actions for an unselected record.

**Checks actually run (2026-10-06)**
| Check | Result |
|---|---|
| `uv run pytest` (incl. export scope/data mode, registry-not-coverage labelling, map precision, demo-flag inheritance) | 65 passed |
| Playwright full suite (desktop 1440 + mobile 360): foundation, session refresh, Prevention journey | 32 passed, 12 skipped (single-viewport cases) |
| Prevention journey (no AI anywhere): register with photo → submit evidence → other vet requests correction (reason enforced) → volunteer sees it on Today and amends → original shows "Replaced…" → vet verifies → profile shows "Last verified…" + disclaimer → map table shows registry measures → Hillview member gets 404 and empty search → volunteer proposes merge, proposer cannot approve, coordinator approves (alias banner) and reverses (history restored) → capture page says matching unavailable | 8/8 passed, repeatable |
| axe WCAG 2.2 AA scans on registration, profile, vaccination form, record page, workbench, registry, tasks | 0 violations after fixes |
| Forbidden wording check ("safe dog", "rabies-free", "unvaccinated" as a label, "% match", "AI verified") | none found |
| Screenshots | `docs/screenshots/phase4/` (360 and 1440 px) |

**Not done / limitations**
- No testing with real field workers or veterinarians (none available) — wording and step counts unvalidated.
- Tamil/Hindi: interface strings for Phase 4 screens fall back to English with the draft/partial notice.
- Corrections carry over field values but not the previous evidence files (they stay on the superseded record).
- Map uses OSM standard tiles in development only (attributed, interactive); production needs a provider.

## Phase 5 — OpenCV quality + genuine detector inference (2026-10-06) ✅ (assistive; field validation pending)

**Built**
- Migration 0007: `model_versions` (global registry: checksum, licence, preprocessing contract, thresholds,
  evaluation report, staged/active/retired, one active per task) and `detection_results` (tenant-scoped).
  `pawguard-admin models register|activate|retire|list` (activation requires an evaluation report + reason; audited).
- Worker: `vision/yolox.py` (ONNX Runtime, letterbox, grid decode, NMS, dog + person classes),
  `vision/quality.py` (Laplacian-variance sharpness normalised by intensity variance on the subject region,
  whole-frame darkness/over-exposure, resolution, subject size — advisory warnings only), `analysis.py`
  (`media.analyse` job queued by validation; results in original-image coordinates).
- API: `GET /media/{id}/analysis` with explicit states (pending / completed / no_animal / unavailable / failed /
  not_applicable); observations accept the chosen subject box (validated against image bounds) and require a
  `quality_override_reason` when an attached photo has warnings (stored on the quality result).
- UI: subject picker with numbered SVG boxes drawn from returned coordinates (viewBox = original size), matching
  radio list, nothing preselected when several dogs, "none of these", privacy notice when people are detected,
  plain-language quality warnings with a required reason; detection-unavailable/no-dog states keep the flow open.
- `ml/` project (separate lockfile): `pawid coco-sample | detector-verify | detector-eval` reusing the worker code.

**Checks actually run**
| Check | Result |
|---|---|
| Preprocessing verification (15 images) | raw pixels recall 0.789 vs legacy normalisation 0.0 → raw pixels |
| Detector evaluation (29 dog + 25 dog-free images) | precision 0.931 [0.818–1.0], recall 0.675 [0.486–0.857], 0/25 false dog images, 150 ms median CPU |
| Dark-coat bias check of quality rules | blurry-warning rate 0.00 / 0.10 / 0.11 dark→bright tertiles (small n) |
| `uv run pytest` (incl. 3 analysis tests: real detection through Storage + jobs, no-active-model → unavailable, warned photo needs reason, out-of-bounds box rejected, tenant isolation of analysis) | 68 passed |
| Playwright `detection.spec.ts` (real boxes in UI + chosen subject saved; dark photo requires reason) | 2 passed |
| Screenshot | `docs/screenshots/phase5/subject-picker-*.png` (two real detections, none preselected) |

**Limitations:** not evaluated on Indian community-dog field photos; quality thresholds uncalibrated; ONNX↔PyTorch
parity not re-verified locally; no manual box-drawing (person chooses a detection or "none"); video/tracking not
implemented (optional per brief). Test suite run time rose to ~18 min on this machine under heavy external load
(normally ~30 s).

## Phase 6 — Data preparation, annotation and partner import (2026-10-06) ✅ (tooling; partner data blocked)

**Built**
- Migration 0008: `dataset_versions` (draft/frozen, manifest checksum, purpose, rights), `dataset_samples`
  (split/role/flags/exclusion per image), `annotation_events` (append-only decisions), `import_jobs` (immutable raw
  file + sha256, dry-run report, created-record ids, rollback fields). All tenant tables under FORCE RLS.
- `ml/src/pawguard_ml/datasets.py` + `pawid` commands: `dataset-prepare` (ingest with decode/greyscale checks,
  sha256, DCT pHash, union-find near-duplicate graph, cross-identity duplicates excluded as label conflicts,
  identity-disjoint open-set split with duplicate groups kept together, independent leakage re-check, manifest),
  `annotate-export` (static review page + decisions CSV), `annotate-import` (validated decisions → events),
  `dataset-register` (frozen version + samples in the DB).
- Partner CSV import (animals, vaccinations): versioned vocabulary mapping (`vocab-1`), dry-run report with row
  statuses valid / warning / rejected / skip, nothing created until an authorised person applies, apply in one
  transaction (animals provisional, vaccinations "submitted"), re-import of a source row is skipped, identical file
  refused, rollback archives (never deletes) records unused since the import. UI at `/app/imports`
  (capability `data.import`), with nav entry.
- Partner collection brief: `docs/ML_PLAN.md` § "Partner collection brief". Label-quality audit:
  `docs/EVALUATION.md` § "DogFaceNet 224 v1".

**Data actually prepared:** DogFaceNet 224resized (Zenodo 12578449) downloaded, all MD5s matched after a
truncated first attempt; frozen as `dogfacenet-224` v1 (8,363 images, 1,393 identities; 26 excluded; leakage
check passed). Research benchmark only — see S05 rights note.

**Checks actually run**
| Check | Result |
|---|---|
| `ml/tests/test_datasets.py` (synthetic fixture: decode failure, exact + near duplicates, label-conflict exclusion, identity-disjoint split, injected leak caught, pHash stability) | 3 passed |
| `services/api/tests/test_imports.py` (volunteer 403; dry-run statuses incl. Tamil text preserved; future date, out-of-range latitude and in-file duplicate rejected; identical file 409; nothing created before apply; re-sent source row skipped; rollback archives; rollback refused (409 `records_in_use`) once an imported record was edited, nothing archived; volunteer cannot roll back; vaccination rows: unknown animal and malformed lot rejected, created as `submitted` partner records, batch rollback refused) | 3 passed |
| Playwright `imports.spec.ts` (volunteer has no access; coordinator checks → applies 1 of 3 rows → rolls back; axe on upload and report) | 2 passed |
| Playwright `prevention.spec.ts` re-run after moving org switching into a shared helper | 8 passed |
| `tsc --noEmit`, eslint, `ruff check services scripts ml` (ml/ now in check.sh and CI) | clean |
| Visual check of one DogFaceNet conflict group (identities 278 / 959) | same photograph under two identities |
| Full `uv run pytest` (before the third import test was added) | 70 passed in 18.6 s |

**Not done / limitations**
- No annotation decisions recorded yet: the 12 conflict groups need a person to adjudicate (review page ready).
- No partner data, agreements or contacts — nothing was requested from anyone. PetFace application not submitted.
- Import UI and messages are English-only (Tamil/Hindi fall back with the draft notice).
- Vaccination imports cannot be rolled back as a batch by design; they are corrected through review.
- The API process must be restarted after router changes (found when the e2e run hit a stale server).

## Phase 7 — PawID: DINOv2 baseline, adaptation, assisted matching integration (2026-10-06) ✅ built · ⛔ capability research-only

**Built**
- `ml/`: `pawid model-fetch` (pinned DINOv2-S safetensors verified against Hub hashes; refuses pickle/code files),
  `embed` (cached), `identity-select` (validation-only grid + gallery-size / enrolled-count / masking / margin
  analyses), `identity-train` (head-only SupCon / ArcFace experiments with pre-registered adoption rule),
  `identity-test` (protected: refuses a second run without an explicit reason), `identity-export` (ONNX + parity +
  latency/memory + manifest). Shared preprocessing lives in the worker (`vision/embed.py`), so evaluation measures
  production code.
- Migration 0009: release gate on `model_versions` (identity models cannot become active unless the gate passed —
  enforced by a check constraint), `research_preview` (demo organisations only), `index_wanted`; `training_runs`;
  `animal_embeddings` (vector(384), tenant RLS, worker-only); `identity_searches`; append-only
  `identity_decisions`; `app.identity_gallery_stats()` (counts without exposing vectors).
- Worker jobs `identity.enrol` (linked, chosen-subject photos → gallery; queued on sighting creation and on photo
  approval) and `identity.search` (exact cosine in SQL, centroid rule, threshold + top-3, merged aliases mapped to
  the canonical animal, archived never suggested, `stale_index` / `no_candidate` / `insufficient_quality` /
  `failed` states).
- API `/api/v1/identity/status|searches|searches/{id}|searches/{id}/decision|feedback`; candidates carry rank +
  supporting photos only (no scores). System page shows research-only status and decision counts.
- Admin CLI: `models register` (records release gate), `models research-preview`, `models reindex`, `models
  activate` (refuses identity models without a passed gate or with an incomplete index), `runs register`.
- UI: capture page "Find an animal from a photo" (only when the API reports assisted / research preview):
  research-preview notice, subject choice, side-by-side photos, "possible match" wording, same / none / not sure,
  confirmation dialog before linking, honest no-candidate and incomplete-index messages, manual paths always shown.
- ADR 0008; MODEL_CARD §2; EVALUATION "Identity retrieval"; ML_PLAN reproduction steps; THREAT_MODEL rows.

**Results (research benchmark, not field evidence)** — test split, once: adopted ArcFace head top-1 0.954,
coverage@3 0.887 [0.852–0.920], FPIR 0.107 [0.056–0.169] at the validation threshold; frozen baseline coverage@3
0.800, FPIR 0.167. Adaptation improved open-set behaviour; release gate not met (no permissioned field data; FPIR
above 0.10). Details and limitations: EVALUATION.md.

**Checks actually run**
| Check | Result |
|---|---|
| Preprocessing vs Hugging Face image processor (6 images) | CLS cosine ≥ 0.9996 |
| ONNX vs PyTorch parity (1,264 validation images) | max abs diff 2.9e-5; cosine 1.0; identical ranks and metrics |
| `services/api/tests/test_identity.py` (unavailable without model; research preview only in demo orgs; real enrolment → search → candidate with photo and no score; decision rules; feedback; cross-tenant 404 / no candidates / cannot choose foreign animal; archived never suggested; incomplete index → `stale_index`; DB refuses activation without gate) | 5 passed |
| Full `uv run pytest` | 76 passed |
| `ml` tests | 3 passed |
| Playwright `identity.spec.ts` (research notice; enrol → lookup → candidate side by side; no percentages; axe; cancel then confirm links the sighting; decision recorded) | passed twice |
| Full Playwright suite (desktop + mobile) | 44 passed, 27 skipped (desktop-only/mobile-only by design), 3 failed: two tests asserted "no identity model" in the demo org, which now intentionally shows the research preview. Updated to the stronger invariant (status is `unavailable` or `research_preview`, never validated; manual paths always present) → foundation + prevention re-run: 28 passed, 8 skipped |
| `tsc --noEmit`, eslint, ruff | clean |
| Screenshot | `docs/screenshots/phase7/lookup-candidates-1440.png` |

**Bugs found and fixed during the phase:** aggregation SQL referenced the wrong alias; the API role could not
count gallery rows (now a security-definer count function); photos saved without a box stored JSON `null`, which
`is not null` treated as a box (all eligibility checks now use `jsonb_typeof(...) = 'object'`, and the ORM stores
SQL NULL).

**Not done / limitations**
- No permissioned field identity data → the capability stays research-only; real organisations see "unavailable".
- Face-crop benchmark vs full-body field crops: the product crops the detector box, which the model was not
  evaluated on. The e2e journey enrols and looks up the *same* COCO photo, so it proves the integration, not accuracy.
- "None of these — register a new animal" opens registration without carrying the photo over (re-add it there).
- No manual box drawing: photos where the detector finds no dog cannot be enrolled or searched by subject.
- Partial-backbone fine-tuning, ViT-B/14 and calibrated probabilities not attempted (no field data to justify).
- Tamil/Hindi strings for the lookup fall back to English with the draft notice.

## Phase 8 — Offline field work, surveys and campaign planning (2026-10-06) ✅ (demo data; not field-tested)

**Built**
- Offline: installable manifest + icons; explicit trusted-device opt-in on the field kit (`/[locale]/field`); narrow
  service worker (field-kit page + hashed static assets only, wipe message); IndexedDB with 72 h expiry holding
  minimal task fields and queued operations; auto-send on reconnect; conflict/refusal UI (discard or apply to the
  latest version); sign-out warns about unsent changes and wipes IndexedDB, caches and the worker.
- Sync API `POST /api/v1/sync/operations` (+ `/resolve`): per-operation savepoints, current-permission replay,
  duplicate detection, row-version conflicts with server state, actor and organisation checks; recorded in
  `sync_operations`. `GET /api/v1/me/organisation` binds the kit to the account and organisation.
- Surveys: `survey_counts` + `POST /api/v1/surveys` + street-count form (linked from survey tasks).
- Planning: migration 0010 (area inputs with estimate provenance, team defaults, `campaign_plans` versions);
  worker `planning.py` (greedy baseline, OR-Tools 9.15 routing, independent validator, reasons) and `plan.solve`
  job; API for campaigns, area inputs, teams, plans, approve, publish; UI `/app/campaigns` and the planner page;
  publication creates team-assigned field tasks; team tasks count as "mine" for team members.
- Demo fixture: three more synthetic wards, two teams, two street counts, a draft campaign. ADR 0009.

**Checks actually run**
| Check | Result |
|---|---|
| `test_sync.py` (accepted + duplicate replay applied once; server cancel while offline → conflict, nothing overwritten, resolution recorded; permission removed → `missing_capability`, other ops still applied; actor and organisation mismatch rejected; suspended member → 403, nothing recorded) | 3 passed |
| `services/worker/tests/test_planning.py` (shifts, doses, uniqueness; specific reasons for every unplanned area; pins; overload; optimiser never worse than baseline shown) | 4 passed |
| `test_planning_api.py` (survey → suggested estimate; invalid count refused; volunteer cannot create campaigns; manual inputs; real `plan.solve` job; publish refused before approval; approve → publish → team tasks visible to and workable by a team member; revised inputs → version 2, version 1 superseded, its tasks untouched) | 1 passed |
| Playwright `offline.spec.ts` (opt-in with risk statement; offline reload served by the worker; start + sighting queued; auto-replay on reconnect; duplicate re-send; coordinator cancel → conflict shown; axe; sign-out warning then IndexedDB, caches and worker removed) | passed |
| Playwright `planning.spec.ts` (suggested estimate from a count; "leave out" respected and explained; travel-estimate note; baseline comparison; nothing dispatched on approval; publish creates tasks seen by team member; fewer doses → new version with dose reasons; decisions carried over; axe) | passed |
| Full `uv run pytest` | 84 passed |
| Full Playwright (desktop + mobile) | 49 passed, 29 skipped (single-viewport specs), 0 failed |
| Screenshots | `docs/screenshots/phase8/` |

**Bugs found and fixed during the phase:** the gateway skipped organisation resolution for every `/me/*` path
(broke `/me/organisation` on a fresh session); an unregistered service worker re-created its cache after sign-out
(now told to stop and wipe first); cancelled tasks offered "record a sighting".

**Not done / limitations**
- Not tested on real phones, flaky networks or low storage; iOS Safari storage eviction behaviour unverified.
- Offline covers task progress and sightings without photos only; registration, photos and vaccination evidence
  need a connection.
- IndexedDB is not encrypted (device lock is the only protection) — documented residual risk.
- Travel is a straight-line estimate; no road network or travel-time matrix; one day per plan; areas larger than
  a shift must be split by hand.
- Stock is "doses carried per team per day" — no inventory ledger yet.
- Tamil/Hindi strings for these screens fall back to English.

## Phase 9 — Prevention release audit and demonstration preparation (2026-10-06) ✅ (demo-ready; not field-validated)

Full report, test counts, feature matrix, demo script and recovery steps: `docs/RELEASE_REPORT_PREVENTION.md`.

**Done:** pre-audit checkpoint commit `2c1bb08` + local DB backup; role walkthrough as an e2e spec on desktop and
360 px (`release-walkthrough.spec.ts`) including forged self-verification (403) and cross-organisation isolation
(404); research-preview boundary audit (migration 0011 column privileges, `test_boundaries.py`); ML evidence trace
script (`scripts/check_ml_evidence.py`, in `check.sh`); offline access-change UI test; planning wording and estimate
provenance; draft-translation notice in the app; demo reset (`pawguard-admin demo-reset`), lookup preparation
(`scripts/demo_prepare.py`) and one-command startup (`scripts/demo_up.sh`).

**Fixed:** team tasks not actionable by team members; "Last seen" off by a day (timezone); API role could change
`is_demo`; "Animals covered" wording; estimates without source/date; Tamil/Hindi mixed text without notice; profile
tabs hidden at 360 px; `crypto.randomUUID` failing outside secure contexts; ESLint noise from vendored files.

**Results:** pytest 89 passed / 0 failed / 0 skipped; ML tests 3 passed; Playwright 57 passed / 0 failed / 29
skipped (full run) and 13 / 0 / 11 on the demo-critical re-run after the final fixes; gate script exit 0.

**Not done:** real-phone and poor-network testing; clinical review; translation review; field identity data.

## Hackathon topic — Pet vaccination tracking and reminders (2026-10-06) ✅ (demo-ready; fictional data)

Built on the existing ledger, workbench, row security, outbox and design system (migration `0012_pet_care`).
Safety tag before the work: `pre-pet-topic`.

**Built:** pet owner role (`resident` → `pet.own`; no registry-wide read) and *My pets* (add pet with photo, status,
timeline with "verified by vet" / "entered by owner (unverified)" / "no verified record"); owner-entered records with
certificate go to the vet workbench; reminders 14/7/1 days before and overdue, idempotent and rescheduled in the
vet's review transaction, snooze 1/3 days, mark done with certificate (rejection brings it back), bell, real `.ics`,
notification preview (nothing sent); staff-only demo date (demo organisations only); QR card with random revocable
token, public page (verified only, disclaimer), PDF; clinic dashboard (due this week / 8–14 days / overdue /
awaiting verification, "X of Y registered pets up to date — not population coverage"); vet clinic record with next
due date; next due date in the existing review dialog; landing/welcome reframed; Tamil labels (draft, pending
review); seed: 2 fictional clinics, 1 owner with 3 pets, 1 vet, 2 clinic managers, 1 owner upload awaiting
verification (`demo_prepare.py`), included in demo reset.

**Fixed on the way:** the ignore rule `models/` had kept the API's ORM package and the model manifests out of Git
(commit `70d63c9`).

**Tests:** see the final report in the session log; pytest `tests/test_petcare.py` covers status boundaries,
reminder idempotency/rescheduling, owner/vet/clinic permissions, demo clock and cards; Playwright `pet-journey`,
`pet-card`, `pets-screens` (390 px and desktop, axe).

**Not done / demo-only:** no real messages; schedule templates are demo data; Tamil labels unreviewed; PDF Latin
font only; no testing with real owners or clinics.

## Backlog mapped to phases

- **P1:** user journeys with step counts; wireframes A–K; evidence-state wording; token system; page inventory; screen → API map.
- **P2:** pnpm + uv workspaces; compose (Redis); Dockerfiles; CI workflow; `.env.example`; FastAPI health/readiness + structured logs + request IDs; OpenAPI → TS client; Next.js shell (public + app layouts, i18n en/ta/hi, UI primitives); server-side Supabase session; dev accounts; provider-health page; starter urgent-help page.
- **P3:** Alembic baseline (roles, context functions, foundation + Prevention + ML-metadata tables, RLS, indexes); command layer (audit, outbox, idempotency, row_version); seed (demo tenant); permission integration tests incl. pool leakage.
- **P4:** animals, observations, media upload flow, profile timeline, caregivers, vaccination submission → review → correction, field tasks, map/list, merge preview/approve/reverse; Playwright journey with AI disabled.
- **P5:** worker media validation; OpenCV quality; YOLOX job; subject selection UI; small COCO sample evaluation.
- **P6:** import dry-run; manifests; dedup graph; grouped splits; DogFaceNet ingestion (research-only); partner collection brief.
- **P7:** DINOv2 frozen baseline; ONNX export parity; gallery embeddings; search API + candidate UI; evaluation with CIs; model card.
- **P8:** PWA, IndexedDB task cache, sync operations + conflicts; surveys; OR-Tools planner with greedy baseline.
- **P9:** full role walkthrough, screenshots, wording audit, release report.
