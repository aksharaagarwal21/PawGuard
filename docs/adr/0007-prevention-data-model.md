# ADR 0007 — Prevention data model choices

Date: 2026-10-05 · Status: accepted

## Decisions

1. **One task table.** The brief lists `animal_followup_tasks` and `field_tasks`. They share the same state
   machine, assignment and audit needs, so both are stored in `field_tasks` with `task_type`
   (`animal_followup`, `evidence_correction`, `identity_review`, `vaccination_round`, `survey`, `other`) and
   optional `animal_id` / `campaign_id` / `source_event_*`. A view `app.animal_followup_tasks` exposes the
   follow-up subset under the brief's name. Human care plans stay entirely separate (Phase 11).
2. **Dates keep their precision.** Vaccination administration is `administered_on date` +
   `date_precision` (`day`/`month`/`year`/`unknown`) and an optional `administered_at timestamptz` only when an
   exact time was recorded. Month/year precision store the first day of the period; the UI renders by precision.
3. **Exact vs approximate location.** Exact points live in `animal_observations.location`
   (`geography(Point,4326)`) with accuracy and method. The API returns exact coordinates only to members with
   `animal.location.exact`; everyone else receives `location_approx` (snapped to a ~500 m grid) and area.
   Public outputs only ever use area aggregates with suppression.
4. **Vaccination evidence is append-only in meaning.** Events are never edited after submission; a correction
   creates a new event (`supersedes_event_id`) and marks the old one `superseded`. Reviews are immutable rows.
   A trigger refuses a review by the event's submitter, even if application code is wrong.
5. **"Vaccinated" is never stored.** There is no boolean on `animals`; summaries are derived from verified
   events at read time and worded per `DESIGN_SYSTEM.md`.
6. **Deferred tables.** Survey/coverage tables arrive with the planner (Phase 8); identity-search, model registry
   and embedding tables with the vision phases (5–7); dataset/annotation tables in Phase 6.
7. **Dispatcher visibility.** `outbox_events` and `background_jobs` carry identifiers only and are readable
   across tenants by the `pawguard_worker` role (dispatcher). All domain tables remain tenant-scoped for the
   worker through `app.set_worker_context(job_id)`.
