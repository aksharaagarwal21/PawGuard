# PawGuard 360 — Product brief

Status: working brief derived from `PawGuard360_Claude_Build_Prompt.md` (the master brief, 5 Oct 2026). Where this file and the master brief disagree, the master brief wins until an ADR records a change.

## Promise

Help communities maintain trustworthy animal vaccination records, find gaps in prevention activity, connect exposure reports to appropriate care and investigation, and coordinate follow-up.

## Scope order

1. **Prevention (current focus, Phases 2–9):** animal registry, verified vaccination-event ledger, assisted (never automatic) animal identification, field tasks, campaign planning, offline field work.
2. Awareness (Phase 10) → Response (11) → Surveillance + inventory (12) → One Health coordination (13).
3. From the foundation onward a small **static, source-backed urgent-help page** exists so a person can reach first-aid wording and a contact pathway without an account. It is labelled as unreviewed starter content until a qualified local reviewer approves it.

Primary context: an Indian community/municipal programme. Initial languages: English, Tamil, Hindi. Nothing about region, administrative boundaries or medical rules is hard-coded.

## Users (Prevention release)

| User | What they need from Prevention |
|---|---|
| Visitor / resident | Urgent guidance and a contact pathway, no account; later, their own reports |
| Field volunteer | Assigned tasks, find-or-register an animal fast, submit vaccination evidence, work offline |
| Veterinary reviewer | A queue of evidence to verify, reject or send back; identity disputes and merges |
| Programme coordinator | Campaigns, teams, surveys, honest aggregates with denominators |
| Organisation administrator | Membership, capabilities, professional-approval path |

## Product invariants (non-negotiable, tested)

- Urgent information is reachable without account, photo, questionnaire, AI or animal investigation.
- No rabies diagnosis from images, video, sound, behaviour or wounds; no "safe dog" classifier.
- A possible identity match is not a verified identity; a verified vaccine administration is not a declaration that the animal cannot transmit disease.
- `unknown` ≠ `no`; `not recorded` ≠ `not done`; `reported` ≠ `verified`.
- Uploaded certificates are evidence awaiting review; OCR is a draft; a QR code only identifies a record.
- Population coverage is never "verified vaccinations ÷ animals in the app". Registry completeness and survey-based coverage are different measures and are labelled as such.
- A low report count is not low burden; completeness and uncertainty are shown.
- No precise community-animal location, caregiver detail or patient information on a public map.
- No claimed endorsement, partnership, "rabies-free" status, clinical validation or impact that has not been established.
- No LLM generates, changes or discontinues an individual treatment schedule.

## How the product works when things are missing

| Missing | Behaviour |
|---|---|
| Trained identity model / model weights | Manual search and registration remain the full workflow; the "find similar" action shows "Assisted matching unavailable" and never fabricates candidates |
| Detector weights or worker down | Upload still stores evidence; quality/detection step shows a recoverable "not processed" state; manual entry continues |
| External map tiles | Maps render boundaries and markers on a plain background, and every map has an equivalent list; no tile scraping |
| LLM key (Phase 10) | Reviewed lessons and lexical/semantic evidence search still work; generation stays off |
| Partner data | Labelled synthetic fixtures in an isolated demo tenant; real-world claims remain blocked |
| Notification provider | In-app notices and previews only; no real SMS/email/WhatsApp |

## Success measures (definitions, not achieved results)

Definitions live in `docs/EVALUATION.md` (identity retrieval, duplicate resolution, time-to-find, completeness of verified vaccination events, field-task completion, sync reliability, staff workload). No target is reported as achieved until measured with a stated denominator, window and missingness.

## Differentiation (honest)

Existing systems — notably the WVS Rabies Launchpad / data-collection app — already provide field data collection, campaign tracking and GIS dashboards. A registry plus map is not novel. PawGuard's intended contribution is the combination of: a review-gated vaccination evidence ledger with explicit uncertainty states; human-confirmed, tenant-scoped assisted identification with measured open-set error; transactional, auditable merges; and an offline field workflow with explicit conflict handling. Whether that is useful is an empirical question for a pilot.
