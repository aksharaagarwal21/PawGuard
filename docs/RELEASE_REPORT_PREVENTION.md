# PawGuard 360 — Prevention release report (Phase 9)

Date: 2026-10-06 · Scope: Prevention module, demonstration build · Status: **ready for an honest demonstration on
fictional data; not validated in the field; photo matching is research-only.**

Everything shown runs locally on fictional demo organisations. Nothing here has been used by a real programme,
reviewed by clinicians, or tested on real phones in the field.

---

## 1. Feature matrix

| Area | Status | Notes |
|---|---|---|
| Sign-in, roles, organisation switching, demo accounts | **Working** | Server-side session; capabilities from the database on every request |
| Animal registry: search, register provisional profile with photo, history | **Working** | "Last seen" by calendar day in the organisation's timezone |
| Sightings (with or without photo, optional chosen subject) | **Working** | |
| Vaccination evidence → veterinary review (verify / request correction) → amended record | **Working** | Volunteers cannot verify; reviewers cannot verify their own submissions (API **and** database) |
| Tasks: assign, start, complete with note, block with reason, team tasks | **Working** | Team tasks are actionable by current team members |
| Duplicate merge: propose → second person approves → reversible | **Working** | |
| Map and area registry measures | **Working** | Labelled "registry measures, not population coverage" |
| Partner CSV import (dry run → apply → rollback) | **Working** | Raw file kept unchanged; unclear values flagged, never guessed |
| Photo quality checks + dog detection (YOLOX-S) | **Working, assistive** | Boxes are suggestions; person chooses the subject or "none" |
| Offline field kit: task start/complete/block and sightings without photo | **Working (desktop/emulated)** | Not yet tested on real phones or poor networks |
| Street counts → planning estimates | **Working** | Latest single count, not a population estimate |
| Campaign day planning (greedy baseline + OR-Tools), approve → publish as team tasks | **Working** | Straight-line travel **estimate**, labelled on every plan |
| Photo-based identity suggestions (DINOv2-S + trained head) | **Research-only** | Demo organisations only, labelled "Research preview — not validated"; release gate **not met**; real organisations see "unavailable" |
| Offline photos, offline vaccination evidence, offline registration | **Unsupported** | Need a connection by design (evidence must stay reviewable; no bulk media caching) |
| Manual box drawing; carrying a lookup photo into registration | **Unsupported (planned)** | |
| Road routing / travel-time matrix; dose inventory ledger | **Unsupported (planned)** | Needs a provider |
| Notifications (SMS / email / WhatsApp) | **Unsupported** | Preview-only notices |
| Awareness content, bite response, surveillance, One Health (Phases 10–13) | **Planned** | Paused until this audit is complete |
| Tamil / Hindi | **Partial drafts** | English fallback with a visible "draft translation" notice |

## 2. What was audited and what changed

| # | Finding | Impact | Fix |
|---|---|---|---|
| 1 | Tasks published to a **team** showed no actions to team members and read "Not assigned yet" to coordinators | Demo-breaking for the planner → field flow | API returns `team_id`, `team_name`, `assigned_to_me`; UI uses them |
| 2 | "Last seen: yesterday" for a sighting recorded today (day-precision dates stored at local midnight, compared as elapsed hours) | Misleading date on every profile | Calendar-day comparison in the organisation's timezone; asserted in the walkthrough |
| 3 | The API database role could update `organisations.is_demo` (which unlocks the research preview) and `activation_state` — no endpoint did, but a bug could | Boundary weakness | Migration 0011: column-level privileges; tests prove the API role cannot change them, the model registry, the release gate, or read embeddings |
| 4 | Planner said "Animals covered" | Could be read as vaccination coverage | "Expected animals within the plan"; explanation of how estimates work and their limits |
| 5 | Suggested estimates did not say which count or when | Unsupported population reading | "Suggested 22: one street count on 2026-10-03" / "registered animals with this home area" |
| 6 | Signed-in pages in Tamil/Hindi mixed languages without explanation | Confusing | Draft-translation notice in the app shell |
| 7 | Profile tabs cut off at 360 px | Hidden navigation on phones | Tabs wrap |
| 8 | Test helper could not switch organisation on phones | Test gap | Uses the "More" page on every viewport |
| 9 | Browser IDs used `crypto.randomUUID`, unavailable on plain-HTTP phone access | Forms and offline queue would fail on a LAN phone demo | v4 UUIDs from `getRandomValues` fallback |
| 10 | ESLint reported 1,126 warnings, all from the copied MapLibre worker | Real warnings would be hidden | Vendor folder excluded; ESLint clean |
| — | Demo data accumulated across runs | Unrepeatable demo | `pawguard-admin demo-reset` + `scripts/demo_prepare.py` + `scripts/demo_up.sh` |

## 3. Test results (actual, 2026-10-06, this laptop)

| Suite | Passed | Failed | Skipped | Notes |
|---|---|---|---|---|
| API + worker tests (`uv run pytest`) | **89** | 0 | 0 | Includes walkthrough-relevant authorisation, sync, identity, planning, demo-reset and boundary tests |
| ML tooling tests (`cd ml && uv run --group dev pytest tests`) | **3** | 0 | 0 | Synthetic fixture (pipeline mechanics only) |
| Playwright end-to-end (desktop 1440 px + mobile 360 px projects) | **57** | 0 | **29** | 28 skips are mobile-project duplicates of specs that are desktop-only or set their own viewport; 1 performance spec runs only in the mobile project |
| ML evidence trace (`scripts/check_ml_evidence.py`) | all checks | 0 | — | Manifest checksum, counts, thresholds and published numbers match |
| Gate script (`bash scripts/check.sh --no-e2e`) | see §3.1 | | | lint, typecheck, ESLint, client freshness, migrations, tests, UI tests, build, bundle secret scan, ML trace |

### 3.1 Gate script

`bash scripts/check.sh --no-e2e` exited 0: Python lint ✓, TypeScript typecheck ✓, ESLint ✓ (0 errors; the 1,126
warnings it reported all came from the copied third-party MapLibre worker, now excluded — ESLint is clean), API client
fresh ✓, migrations at head (0011) ✓, API + worker tests 89 passed ✓, UI unit tests 4 passed ✓, production web build ✓,
bundle secret scan ✓, ML evidence trace ✓.

After the last two fixes (secure-context-independent IDs; ESLint ignore) the demonstration-critical specs were re-run:
`release-walkthrough`, `offline`, `identity`, `planning`, `prevention` — **13 passed, 0 failed, 11 skipped**
(mobile duplicates of desktop-only specs).

### 3.2 The role-based walkthrough (`tests/e2e/release-walkthrough.spec.ts`, desktop and 360 px)

Coordinator assigns a task → volunteer starts it → searches the registry → registers a new animal with a photo →
records a sighting ("Last seen: today") → submits vaccination evidence → **a forged "verify" request from the
volunteer's own browser returns 403 `missing_capability` and the record stays "submitted"** → completes the task
with a note → **another organisation gets 404 for the animal, the record, the task and the page** → an approved
veterinary reviewer (a different person) verifies → after reload the profile shows "Last verified vaccination
record" with the disclaimer, the vaccination tab shows "Verified administration record", the sighting is listed, and
the task is completed with its note. Screenshots: `docs/screenshots/phase9/`.

## 4. Research-preview boundary (photo matching)

- The model `dinov2_small_arcface_head / ed25f3a3-resize224-head-v1` is **staged** with `release_gate.passed = false`.
  The database forbids `state = 'active'` for an identity model without a passed gate; the CLI also refuses.
- It runs only for organisations with `is_demo = true` (research preview, labelled). For any other organisation:
  status `unavailable` / reason `research_only`; a search request is stored as `unavailable` and no job runs.
- There is **no HTTP route** that writes models, previews, gates or organisations (tested against the OpenAPI
  surface). The API database role cannot change `is_demo`/`activation_state`, cannot update the model registry and
  cannot read embeddings (tested). Only operators with owner database credentials can change these, via the CLI.
- Thresholds were chosen on validation and **not** changed after seeing test results; the failed gate is preserved.

## 5. Model evidence and its limits

Traceable with `PYTHONIOENCODING=utf-8 uv run python scripts/check_ml_evidence.py` (all checks pass).

| | Validation | Test |
|---|---|---|
| Split manifest | `data/manifests/datasets/dogfacenet-224-v1.json`, sha256 `10a6554b…40ca` | same |
| Enrolled identities / gallery images | 146 / 407 | 147 / 387 |
| Known queries | 481 | 479 |
| Unknown identities / unknown queries | 62 / 376 | 63 / 336 |

Thresholds: adapted head τ = **0.53846** (deployed), frozen baseline τ = 0.74833, both chosen where validation
false-suggestion rate ≤ 0.10; at most 3 candidates. Test results, run once: adapted head — right animal among
shown candidates **0.887** [0.852–0.920], false suggestion for unknown animals **0.107** [0.056–0.169], top-1 0.954;
frozen baseline — 0.800 and 0.167. Evidence: `docs/evidence/identity-*.json`; details `docs/EVALUATION.md`,
`docs/MODEL_CARD.md`. The training run's environment hash (`2c136cbe…`) is `ml/uv.lock` as committed in `2c1bb08`;
the lock changed afterwards only because the worker gained OR-Tools for planning.

**Limitations (must stay visible):** a research benchmark of aligned **face crops of pet dogs** with unreviewed labels
(12 duplicate-photo groups excluded pending review); no community dogs, no field photos, no full-body crops, no
subgroup metadata; false suggestions rise as the gallery grows; the demo lookup uses the same photo that was enrolled,
so it demonstrates the workflow, not accuracy. Release gate (field data, top-3 ≥ 0.80, unknown false suggestions ≤
0.10): **not met**.

## 6. Offline field work

Supported offline: open the field kit, see assigned tasks (72 h cache), start / complete / block tasks, record a
sighting without a photo. On reconnect changes are sent automatically and replayed with the person's **current**
permissions: applied, conflict (someone changed it — nothing overwritten, person decides), or refused (with the
reason; the change stays on the device). Re-sent changes are recognised as duplicates. Sign-out warns about unsent
changes and then removes all offline data (storage, caches, service worker).

**Not supported offline:** photo upload, vaccination evidence, registering animals, the map, photo lookup. These
need a connection.

Tested: `tests/e2e/offline.spec.ts` (disconnect → reload while offline → queue → reconnect → applied; duplicate
replay; refused access keeps changes with an explanation; conflict; sign-out wipe) and
`services/api/tests/test_sync.py` (real permission removal and suspension).

### Physical phone checklist (Android Chrome or iOS Safari)

1. **The phone must reach the app as a secure context** — offline storage, the service worker and the browser's
   random IDs are disabled on plain `http://<laptop-ip>`. Easiest on Android: connect by USB, enable USB debugging,
   open `chrome://inspect` on the laptop → *Port forwarding* → `3000 → localhost:3000`, then open
   `http://localhost:3000/en/sign-in` on the phone. (iOS needs HTTPS, e.g. a local certificate; a public tunnel
   would expose the demo and needs your authorisation.) Sign in as **Priya (volunteer)**.
2. Menu → **Offline field kit** → read the notice → **Use this device for field work**. Expect "Ready. N tasks…".
3. Turn on **airplane mode**. Pull to refresh / reopen the field kit URL. Expect the kit to open and say **Offline**.
4. On a task: **Start**; on a task with an animal: **Record a sighting** with a note. Expect "Not sent yet" and
   "2 changes are saved on this device".
5. Close the browser tab completely; reopen the field kit (still offline). Expect the same changes still listed.
6. Turn airplane mode **off**. Expect "Sent: 2 applied…" within a few seconds (or tap **Send changes now**).
7. On the laptop as **Meena (coordinator)**, cancel one of Priya's tasks. On the phone, go offline, **Complete** that
   task, go online. Expect "Changes that need your decision … It is now: cancelled. Nothing was overwritten."
8. Permission check: as **Kavya (admin)** revoke Priya's membership is *not* reversible from the UI — only try it if
   you will run `uv run pawguard-admin demo-reset --yes` afterwards. Expected: the phone keeps the change and says
   access has changed.
9. Sign out on the phone with a change still unsent: expect a warning; choose **Sign out and delete them**.
10. Note the phone model, browser version and anything that failed; storage eviction on iOS is unverified.

## 7. Planning assumptions

- **Estimates:** each area uses, in order, the coordinator's own number, else the **latest single street count**
  (never a sum of counts, so repeated counts of the same dogs are not added up), else the number of **registered**
  animals whose home area it is. The source and date are shown. A street count is what one person saw on one day.
- These numbers schedule time and doses. They are **not population sizes or vaccination coverage**, and the plan
  says so.
- **Travel:** straight-line distance × 1.3 at the chosen speed (default 15 km/h), labelled on every plan.
- **Output:** a proposal compared with a simple baseline, with a reason for every unplanned area. Nothing reaches
  teams until a coordinator **approves** and **publishes**; re-planning creates a new version and earlier tasks are
  not changed.

## 8. Demo dataset and reset

- Fictional data only, in two organisations flagged `is_demo`: *Demo — Riverside Animal Welfare Trust* and
  *Demo — Hillview Municipal Programme*. Every record in them is flagged demo; the UI shows a demo banner.
- `uv run pawguard-admin demo-reset` (dry run) / `--yes`: deletes operational rows **only** where `org_id` is a demo
  organisation, removes their stored photos, re-seeds, and records the reset in the audit log. Accounts, memberships,
  professional approvals and global research/model records are kept. Non-demo row counts are compared inside the same
  transaction; any change rolls everything back. Refused unless `PAWGUARD_ENV` is development/test and demo mode is on.
- `uv run python scripts/demo_prepare.py` enrols one licence-filtered COCO dog photo so the photo lookup has a
  candidate.

## 9. Startup and recovery (this laptop: Windows + Git Bash)

**Before the demo (≈ 3–5 min):**

```bash
# Docker Desktop running first
cd /c/PawGuard
bash scripts/demo_up.sh --reset     # stack, migrations, API/worker/dispatcher, demo reset, lookup prep, web build
```

Then open three browser windows (separate profiles or one normal + two private): sign in as **Priya** (volunteer),
**Dr Arun** (vet) and **Meena** (coordinator, switch to Riverside under More). In Priya's window open
`/en/field` and choose **Use this device for field work** once.

| Problem | Do this |
|---|---|
| Demo data got messy | `uv run pawguard-admin demo-reset --yes && PYTHONIOENCODING=utf-8 uv run python scripts/demo_prepare.py` (≈ 30 s) |
| A page errors / API stopped | `bash scripts/demo_up.sh` (no reset) — restarts API, worker, dispatcher and web |
| Web only | `bash scripts/restart-web.sh` |
| Photo checks stay "Checking…" | Worker or dispatcher stopped → `bash scripts/demo_up.sh`; logs in `%TEMP%\pg_worker.log`, `pg_dispatch.log` |
| Photo lookup says "unavailable" | Research preview off: `uv run pawguard-admin models research-preview dinov2_small_arcface_head ed25f3a3-resize224-head-v1 --reason "demo"` |
| Model files missing | Detector: `models/yolox/yolox_s.onnx` (URL in `data/manifests/models/yolox_s-coco-0.1.1rc0.json`). Identity: `models/dinov2-small/ed25f3a3…/dinov2_small_arcface_head.onnx` — rebuild with the `pawid` steps in `docs/ML_PLAN.md` (needs DogFaceNet + about 20 min). **Keep a copy of `models/` on a USB stick.** |
| Database lost | `bash scripts/demo_up.sh --reset` recreates schema and demo data; then `pawguard-admin models register` both manifests in `data/manifests/models/` and re-enable the research preview (row above) |
| Code broken | `git log --oneline` then `git checkout <reviewed commit>`; the pre-audit checkpoint is `2c1bb08` |
| Total failure | Present from the screenshots in `docs/screenshots/phase9/` and `phase7/` / `phase8/` |

Pre-audit database backup: `backups/pre-phase9-*.dump` (local only, gitignored).

## 10. Three-minute demonstration script

| Time | Who / where | Say and do |
|---|---|---|
| 0:00–0:20 | Landing page | "PawGuard helps community rabies programmes keep trustworthy vaccination records. Everything you'll see is fictional demo data." Sign in as **Priya**. |
| 0:20–1:05 | Priya | Tasks → **Start** her round. Animals → search "brindle" (find first), then **Register an animal** (coat, sex, area, `tests/fixtures/synthetic-animal.jpg`) → profile says *provisional*, *no verified vaccination record* — "that does not mean unvaccinated". **Record vaccination evidence** (yesterday, DEMO vaccine A, lot DEMO-A-001, certificate `tests/fixtures/synthetic-certificate.jpg`) → "Submitted for review" — "a volunteer can't verify their own work; even a hand-made request is refused." |
| 1:05–1:30 | Dr Arun (vet) | Review → open the record → **Verify** → read the dialog: verification records administration evidence, not that the dog can't carry disease. Back in Priya's window, reload: "Last verified vaccination record" with the disclaimer. |
| 1:30–2:05 | Priya, Add photo | "Research preview" notice → upload the prepared COCO photo (path printed by `demo_prepare.py`) → **Dog 1** → **Look for possible matches** → photos side by side, no percentages. "Research only: on a pet-dog face benchmark it shows the right dog among 3 suggestions 89% of the time but suggests a dog for 11% of unknown animals — above our 10% limit and not tested on street dogs. Real organisations can't turn it on." Choose **Not sure**. |
| 2:05–2:35 | Priya, Offline field kit | DevTools → Network → **Offline** (or airplane mode on a phone) → reload: kit still works → **Start** a task → "Not sent yet" → back **Online** → "Sent: 1 applied". "Photos and vaccination evidence need a connection." |
| 2:35–3:00 | Meena (coordinator) | Campaign planning → *Demo October vaccination round* → **Make plan** → proposal vs simple baseline, straight-line travel estimate, reasons for unplanned wards → "Nothing goes to teams until a coordinator approves and publishes." Close: "Field validation, partner data and clinical review are the next steps." |

## 11. Remaining issues, ranked by impact

| Rank | Issue | Impact | Owner / next step |
|---|---|---|---|
| 1 | Photo matching not validated on permissioned field photos of community dogs; test false-suggestion rate 0.107 > 0.10 | Capability stays research-only | Partner data + agreement (external) |
| 2 | Live demo depends on one laptop (Docker, Supabase, worker, dispatcher) | Demo risk | `demo_up.sh`, rehearsal, screenshot fallback, copy of `models/` |
| 3 | Offline mode not tested on real phones, poor networks or iOS storage eviction | Field reliability unknown | Phone checklist §6 |
| 3b | Phones on plain `http://<laptop-ip>` are not a secure context: the service worker (offline reload) does not register there. Forms and queued IDs now work regardless (fixed) | Offline-reload demo on a phone needs USB forwarding or HTTPS | Production must be HTTPS; checklist §6 step 1 |
| 4 | Health/first-aid starter content not reviewed by clinicians | Must not be relied on | Qualified reviewers (external) |
| 5 | Tamil/Hindi are partial, unreviewed drafts | Accessibility for field teams | Native-speaker review (external) |
| 6 | "None of these — register" does not carry the lookup photo; no manual box drawing | Extra steps; some photos unusable for lookup | Planned |
| 7 | Planning uses straight-line travel, one day per plan, doses per team (no inventory ledger) | Plans are rough | Travel-time provider; inventory module |
| 8 | Offline data is not encrypted at rest (device lock only) | Lost-phone exposure of task essentials | Documented; minimal fields, expiry, wipe |
| 9 | Planner is long on phones | Coordinators should use a laptop | Later layout work |
| 10 | DogFaceNet duplicate-photo groups await human adjudication | Research data quality | Annotator time |
| 11 | CI defined but never run on a hosted runner; all results are from this laptop | Reproducibility | Push to an authorised remote and run CI |

## 12. External dependencies (unchanged)

Partner organisation, permissioned field photos and data agreements; authorisation before any PetFace application;
qualified clinical/veterinary reviewers; native-speaker translators; map/travel-time and notification providers;
hosting target; an Anthropic API key for Phase 10. No partner, clinic or applicant has been contacted.
