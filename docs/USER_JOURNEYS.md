# User journeys (Prevention release)

Each journey lists screens (letters refer to `DESIGN_SYSTEM.md` § Wireframes), the step count, and where uncertainty or permissions change the path. "Step" = one decision or input the person must make.

## J1 — First-time resident after a dog bite (no account)

| # | Step | Screen | Notes |
|---|---|---|---|
| 1 | Opens site from a link/search | Public landing | "Get help after a bite" is the first action, above the fold at 360 px |
| 2 | Taps "Get help after a bite" | `/help` | Immediate first-aid wording (source + review status visible), then "Seek medical care today" |
| 3 | Reads contact options | `/help` | 112 general emergency; 15400 with its stated state coverage; "Find care" link |
| 4 | (Optional) opens Find care | `/find-care` | Prevention release: explains facility directory is not yet connected — no fabricated clinics |

**Steps: 2 to reach first-aid wording.** No sign-in, photo, questionnaire or AI anywhere on this path. Animal identity is never asked for.

## J2 — Field volunteer: assigned task → known dog → vaccination evidence

| # | Step | Screen | Uncertainty / permission branch |
|---|---|---|---|
| 1 | Signs in, selects organisation (if >1) | Sign in → org picker | Revoked membership → "You no longer have access to <org>" |
| 2 | Opens Today, picks assigned task | A Today | No tasks → empty state explains assignment |
| 3 | Taps "Find an animal" | B Registry | Search by reference / nickname / descriptor / QR reference |
| 4a | Finds the dog in results, opens profile | F Profile | — |
| 4b | *or* "Add photo to search" (existing photo) | C Capture → D Possible matches | Model unavailable → "Assisted matching unavailable — search manually" (back to B) |
| 5 | Confirms identity by comparing marks/photos | D | Choices: "This appears to be the same animal" / "None of these" / "Not sure" — nothing preselected |
| 6 | "Record vaccination" | G Vaccination entry | Fields allowed to be unknown are marked |
| 7 | Enters date (+precision), product, lot, professional, location, evidence | G | Missing lot → allowed, flagged for reviewer |
| 8 | Submits | G → F | Status reads **"Submitted for review"**, never "Vaccinated" |
| 9 | Marks task complete (or blocked with reason) | A | Offline → "Saved on this device" until server acceptance |

**Steps: 9 (manual path) / 10–11 with assisted lookup.** Volunteer cannot verify their own submission (UI hides action; API rejects).

## J3 — Field volunteer: unknown dog → provisional profile

1. C Capture/upload existing photo (or skip photo) → 2. D shows "None of these" / no candidates / matching unavailable → 3. E step 1 observed details (species, sex can be *unknown*, coat, marks) → 4. E step 2 optional evidence → 5. E step 3 review → 6. Save → confirmation shows reference (e.g. `PG-7K3M-Q9XD`), state **Provisional**, next action "Record vaccination evidence" or "Back to task".
**Steps: 6.** Location can be approximate; precision is recorded. Geolocation denied → manual area selection.

## J4 — Veterinary reviewer: verify / correct / reject

1. Opens H Verification workbench (requires `vaccination.review` capability **and** an active professional approval; otherwise the nav item is absent and the API returns 403) → 2. Picks queue item (oldest submitted first; conflicts flagged) → 3. Compares evidence with submitted fields and animal history side-by-side → 4. Chooses Verify / Request correction / Reject → 5. Correction/rejection requires a written reason → 6. Confirms. Submitter sees the outcome on their Today list with a next action.
**Steps: 5–6 per record.** Bulk verify is not offered (each record needs evidence review). Reviewer cannot review an event they submitted.

## J5 — Volunteer: correction requested

1. Today shows "Correction requested" item → 2. Opens G prefilled with previous values + reviewer reason → 3. Amends / attaches new evidence → 4. Resubmits (creates an amendment; original evidence retained) → back to J4.

## J6 — Coordinator: duplicate profiles → merge

1. Opens a disputed/duplicate review task → 2. Merge preview shows both profiles, all linked records that will move, and conflicts → 3. Approves with reason (requires `animal.merge`) → 4. Source profile becomes `merged_alias`; links preserved in the merge manifest → 5. Reverse merge available from History tab with reason.

## J7 — Coordinator: campaign (Phase 8 detail)

Define areas, dates, teams, stock → generate plan (greedy baseline vs optimised) → review infeasibilities → approve → tasks published to assigned team members only → resource change creates plan v2 with visible diff.

## Recovery paths (all must exist in UI)

| Situation | What the person sees | Next action offered |
|---|---|---|
| No match / unknown dog | "No similar animals found among records you can access." | Register new animal · Search manually |
| Model failure / timeout | "Photo comparison isn't available right now. Your photo is saved." | Search manually · Try again later |
| Geolocation denied | "Location not shared. Choose an area instead." | Area picker; approximate entry |
| Bad upload (corrupt/oversize/unsupported) | Specific reason (e.g. "File is larger than 15 MB") | Choose another file · Continue without photo |
| Several dogs detected | Boxes with numbers; "Which dog is this record about?" | Select one · Draw/adjust crop · Continue manually |
| Possible duplicate record | Banner on profile "Possible duplicate of PG-… — under review" | Open review task (coordinator) |
| Offline | Header chip "Offline — changes saved on this device" | Continue working; Sync centre |
| Sync conflict | Sync centre item with server vs device values | Keep server · Apply mine (if still permitted) · Discard |

## Screen → API dependency map

| Screen | Reads | Writes |
|---|---|---|
| A Today | `GET /me`, `GET /tasks?assignee=me&state=open`, `GET /vaccination-events?submitted_by=me&state=needs_correction` | `POST /tasks/{id}/transitions` |
| B Registry | `GET /animals?q=&area=&review_state=&cursor=` | — |
| C Capture | `POST /media/upload-intents`, Storage PUT, `POST /media/{id}/complete`, `GET /media/{id}` (processing state) | `POST /observations` |
| D Possible matches | `POST /identity-searches`, `GET /identity-searches/{id}` | `POST /identity-decisions` |
| E Register | `GET /areas` | `POST /animals` (Idempotency-Key) |
| F Profile | `GET /animals/{id}`, `/animals/{id}/timeline`, `/vaccination-events?animal_id=`, `/observations?animal_id=`, `/tasks?animal_id=` | `POST /animals/{id}/reports` (report incorrect info) |
| G Vaccination entry | `GET /vaccine-products`, `/vaccine-lots` | `POST /vaccination-events` (Idempotency-Key), `POST /vaccination-events/{id}/amendments` |
| H Workbench | `GET /vaccination-events?state=submitted`, `GET /vaccination-events/{id}` | `POST /vaccination-events/{id}/reviews` |
| I Map/area | `GET /areas/{id}/summary`, `GET /map/layers?bbox=` | — |
| J Planner | `GET/POST /campaigns`, `/campaigns/{id}/plans` | `POST /campaigns/{id}/plans/{v}/approve` |
| K Sync centre | local queue, `POST /sync/operations`, `GET /sync/changes` | — |
| Merge | `POST /animal-merges/preview` | `POST /animal-merges`, `POST /animal-merges/{id}/reverse` |
