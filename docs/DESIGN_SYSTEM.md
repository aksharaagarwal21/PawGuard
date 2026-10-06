# Design system

Character: warm civic healthcare with restrained animal-welfare cues. Calm, credible, humane. Operational screens are quieter than the public landing page. Implemented as CSS custom properties in `packages/ui/src/tokens.css` (Tailwind v4 `@theme`).

## Colour tokens (contrast measured 2026-10-05 with the WCAG relative-luminance formula)

| Token | Value | Use | Measured contrast |
|---|---|---|---|
| `--pg-canvas` | `#F7F8F3` | Page background | text 11.46 · text-2 5.15 |
| `--pg-surface` | `#FFFFFF` | Forms, tables, drawers | text 12.24 · text-2 5.50 |
| `--pg-text` | `#203A34` | Headings and body | — |
| `--pg-text-2` | `#576E64` | Explanations, metadata | ≥ 4.75 on every surface below |
| `--pg-primary` | `#205C4F` | Primary buttons (white text 7.76), links (7.27 on canvas) | |
| `--pg-primary-hover` | `#174538` | Hover/pressed (white 10.80) | |
| `--pg-sage` | `#E8F1E9` | Prevention / reassuring panels | text 10.60 · text-2 4.76 |
| `--pg-sky` | `#EAF2F8` | Informational sections | text 10.81 · text-2 4.86 |
| `--pg-lavender` | `#F0EDF7` | Education accents | text 10.58 · text-2 4.75 |
| `--pg-sand` | `#FBF1DE` | Pending / review context | text 10.92 · urgent 5.65 |
| `--pg-urgent` | `#A43E35` | Help emphasis, errors (white 6.33; on canvas 5.93) | |
| `--pg-urgent-soft` | `#F8E9E7` | Help strip / urgent notice background (added) | urgent text 5.36 · ink 10.37 |
| `--pg-divider` | `#CBD8CE` | **Decorative separators only** (1.47 on white) | |
| `--pg-control-border` | `#6F877C` | Input/checkbox/select borders (3.87 on white, 3.62 on canvas — meets 1.4.11 non-text 3:1) | added token |
| `--pg-focus` | `#205C4F` | 2 px focus outline + 2 px offset | |

Pastels are backgrounds only, never text colours. Status is always text + icon, never colour alone. Dark mode: not in scope for the Prevention release (field use outdoors favours the light theme); tokens are structured so it can be added.

## Typography

- **Manrope** (variable, OFL) — display, headings, navigation. **Source Sans 3** (variable, OFL) — body and long content. **Noto Sans Tamil** / **Noto Sans Devanagari** (OFL) as script fallbacks via `unicode-range`, so Latin-only pages never download them. All self-hosted from `@fontsource` packages; licences retained in `apps/web/public/fonts/LICENSES.md`.
- Body 16–18 px, line-height 1.6 (1.75 for Tamil — taller glyph stacks). Operational tables 14–16 px. Measure ≈ 65ch.
- Scale: 14 / 16 / 18 / 20 / 24 / 30 / 38 px. Weights: 400, 600, 700. No light grey thin type.

## Space, shape, motion

4/8 px rhythm; card padding 16–24 px; card radius 12–16 px; controls radius 8–10 px; chips fully rounded. Min touch target 44 × 44 px. Desktop content width 1240 px max; mobile gutter 16 px (20 px ≥ 390 px). Borders subtle, shadows minimal (`0 1px 2px rgb(32 58 52 / 0.06)`). Transitions 150 ms ease-out; disabled under `prefers-reduced-motion`. No autoplay media, no glow/gradient/glass, no sparkle icons.

## Evidence-state wording (authoritative; used in UI copy and tests)

Vaccination events:

| State | Label | Explanation shown | Chip |
|---|---|---|---|
| `draft` | Draft | Not yet sent for review. | neutral |
| `submitted` | Submitted for review | A veterinary reviewer has not checked this record yet. | sand + clock icon |
| `needs_correction` | Correction requested | The reviewer asked for changes: <reason>. | sand + pencil icon |
| `verified` | Verified administration record | Reviewed by <reviewer role>, <date>. This confirms a vaccine was recorded as given. It does not mean the animal cannot carry or transmit disease. | sage + check icon |
| `rejected` | Not accepted | The reviewer did not accept this record: <reason>. | urgent outline + x icon |
| `superseded` | Replaced by a later correction | — | neutral |

Animal-level vaccination summary (derived, never stored as a boolean):

| Situation | Wording | Never say |
|---|---|---|
| ≥1 verified event | "Last verified vaccination record: <date> (<precision>)" | "Vaccinated", "Safe", "Protected", "Rabies-free" |
| Only submitted events | "Vaccination evidence submitted — not yet verified" | "Vaccinated" |
| No events | "No verified vaccination record" | "Unvaccinated", "Not vaccinated" |
| Next due date | Shown **only** if recorded by an authorised person/policy: "Next review recorded by <source>: <date>" | Computed due dates |

Identity:

| State | Wording |
|---|---|
| Animal `provisional` | Provisional profile — details not yet reviewed |
| `reviewed`/`active` | Reviewed profile |
| `disputed` | Identity under review |
| `merged_alias` | Merged into <reference> |
| Candidate in search | "Possible match" (never "Match", never a %) |
| Confirmed decision | "Linked by <role> on <date>" |

Location precision: "Exact (authorised view)", "Approximate (~500 m)", "Area only", "Not recorded".

**Forbidden strings** (asserted absent by tests): "safe dog", "rabies-free" (as an animal or area status), "unvaccinated" as a derived label, "% match", "AI verified", "diagnos" in any animal/image context.

## Components (packages/ui)

Button (primary / secondary / quiet / danger; loading state keeps width), Field (label, hint, error, required/optional marker), TextInput, Textarea, Select, RadioGroup, Checkbox, DatePrecisionInput (exact date / month / year / unknown), StatusChip, Card, Notice (info / pending / urgent / success), EmptyState, ErrorSummary (links to fields), Dialog (Radix), Drawer, Tabs, Pagination (cursor), Skeleton, DemoBanner, SyncIndicator, OrgSwitcher.

## Page inventory

| Route | Audience | Phase |
|---|---|---|
| `/[locale]` | public landing | 2 |
| `/[locale]/help` | urgent bite guidance (starter, review status shown) | 2 |
| `/[locale]/learn`, `/find-care`, `/about`, `/sources` | public | 2 (Learn/Find-care honest "coming in a later phase" content) |
| `/[locale]/sign-in` | team | 2 |
| `/[locale]/app` (Today) | field | 2 shell → 4 |
| `/app/animals`, `/app/animals/new`, `/app/animals/[id]` | field, vet, coordinator | 4 |
| `/app/capture` | field | 4 (manual) → 5 (detection) |
| `/app/identify/[searchId]` | field | 7 |
| `/app/animals/[id]/vaccinations/new` | field | 4 |
| `/app/review` | vet | 4 |
| `/app/tasks` | field, coordinator | 4 |
| `/app/map` | coordinator, field | 4 |
| `/app/merges/[id]` | coordinator, vet | 4 |
| `/app/campaigns` | coordinator | 8 |
| `/app/sync` | field | 8 |
| `/app/admin/members` | org admin | 3/4 |
| `/app/system` | maintainers | 2 |

Navigation by capability (not role label): field → Today, Animals, Capture, Tasks (mobile bottom bar: Today · Animals · Capture · More). Vet adds Review. Coordinator adds Map, Campaigns. Admin adds Members, System.

## Wireframes (Prevention)

### A. Today (mobile 360)
```
┌───────────────────────────────┐
│ PawGuard 360   [Org ▾]  ● Online│
│ Good morning, Priya            │
│ Ward 12 Animal Welfare Trust   │
├───────────────────────────────┤
│ [ Find an animal ]  [+ Observation]
├ Your tasks today (3) ──────────┤
│ ◷ 09:30 Vaccination round      │
│   Anna Nagar block C · Assigned│
│   [Start]                      │
│ ✎ Correction requested         │
│   PG-7K3M… lot number unclear  │
│   [Open]                       │
├ Area preview (small map/list) ─┤
└─[Today]─[Animals]─[Capture]─[More]┘
```
### B. Registry
Search box (reference, nickname, descriptor) + filter chips (Area, Review state, Seen in last 30 days, Open tasks) → compact list rows: thumbnail | `PG-7K3M-Q9XD` · nickname · "Brown, white chest blaze" · Last seen 2 Oct (approx.) · evidence chip. Toggle list/cards. Cursor "Load more". Filters kept in URL.

### C. Capture / upload
"Add an existing photo of the animal. Only use photos taken safely — never approach an unfamiliar or worried animal for a photo." → [Take photo] [Choose photo] · constraints "JPEG, PNG or WebP · up to 15 MB" → progress → processing status (validated / quality notes / detected dogs) → actions: Continue · Choose another photo · Continue without photo.

### D. Possible matches
```
Your photo            Possible matches (none selected)
┌──────┐   ┌────────────┐ ┌────────────┐ ┌────────────┐
│query │   │ PG-…  ▢ ▢  │ │ PG-…  ▢ ▢  │ │ PG-…  ▢ ▢  │
└──────┘   │ marks, area│ │ marks, area│ │ marks, area│
           │ last seen  │ │ last seen  │ │ last seen  │
           │ (•) Same?  │ │ (•) Same?  │ │ (•) Same?  │
Check ear notches, markings and collar before confirming.
[This appears to be the same animal] [None of these] [Not sure]
```
### E. New animal (3 steps)
1 Observed details (species · sex [female/male/unknown] · age band [puppy/young/adult/senior/unknown] · coat · identifying marks · nickname optional · ownership category) → 2 Evidence (photo optional, location + precision, area) → 3 Review → Save → "Provisional profile PG-… created".

### F. Animal profile
Header: photo · reference · nickname · identity-state chip · [Report incorrect information]. Tabs: Overview · Vaccination records · Sightings · Tasks · History. Vaccination panel uses the evidence wording table above.

### G. Vaccination entry
Animal confirmation strip → Date + precision → Product (select; "Not known") → Lot (optional, "Not recorded") → Administered by (name / registration as recorded; "Not recorded") → Location/area → Evidence upload (optional) → "What happens next: a veterinary reviewer will check this record." → [Submit for review].

### H. Verification workbench (desktop)
Left: queue (oldest first; conflict flag) · Centre: evidence viewer · Right: submitted fields + animal history + conflicts → [Verify] [Request correction] [Reject] (reason required for the last two).

### I. Map / area
Map (lazy) + equivalent list; legend uses colour + shape; dataset date; "This map shows sightings and records in this programme's registry. It is not a disease-risk map." Public map: area aggregates with small-count suppression only.

### J. Planner — Phase 8. ### K. Sync centre — Phase 8.

## Interaction specs

- **Upload:** one file at a time initially; client checks type/size before requesting an intent; progress via XHR; cancel aborts the PUT and calls `DELETE /media/{id}` (intent cancelled → object removed by cleanup). Retries reuse the same intent while valid.
- **Matching:** never auto-selects; "Not sure" records a `deferred` decision and keeps the observation unlinked; decisions are audited and correctable.
- **Verification:** reviewer cannot act on own submission; concurrent review → second reviewer gets 409 with current state.
- **Sync:** every queued item shows "Saved on this device" until the server returns accepted; rejected items are red-outlined with reason and never shown as done.
- **States per route:** loading (skeleton), empty, validation error (summary + inline), permission denied, offline, timeout, stale, partial success, success.
