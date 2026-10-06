# ADR 0009 — Offline field work and campaign planning

Date: 2026-10-06 · Status: accepted

## Offline

1. **Explicit opt-in per device.** Nothing is stored for offline use until a person chooses "Use this device for
   field work" on the field kit (`/[locale]/field`), which states what is stored, for how long, and the shared-device
   risk. Stopping, or signing out, wipes IndexedDB, Cache Storage and the service worker (the worker is told to stop
   caching first, because an unregistered worker keeps controlling open pages).
2. **Minimal data.** IndexedDB holds open tasks assigned to the person or their team (title, type, state, area name,
   animal reference, due date, instructions, row version) for 72 hours, plus queued changes. No photos, caregivers,
   exact locations or vaccination records. Storage is not encrypted; see THREAT_MODEL.
3. **Narrow service worker.** It caches only the field-kit page (its HTML carries no personal data) and
   content-hashed `/_next/static` assets. It never caches `/api`, auth traffic, media or other pages.
4. **Operations, not state.** Offline changes are operations (`task.transition` start/complete/block,
   `observation.create` sighting without photo) carrying an operation id, actor, organisation and the row version
   the device last saw. `POST /api/v1/sync/operations` replays each one in its own savepoint with the sender's
   **current** permissions: accepted / conflict (server changed since — nothing overwritten, server state returned)
   / rejected (permission removed, wrong account or organisation, invalid). Re-sent operations return the stored
   outcome as duplicates. A suspended membership cannot replay anything.
5. **People resolve conflicts.** The kit shows each conflict or refusal with "discard my change" or "apply my
   change to the latest version" (a new operation on the new row version); the choice is recorded on the server.
   Vaccination evidence and photos still require a connection (evidence must stay reviewable and media unbounded
   caching is out of scope).

## Planning

1. **Solver in the worker.** `plan.solve` runs a transparent greedy baseline and OR-Tools routing (time windows,
   dose capacity, pinned areas, droppable areas with priority × size penalties) over an immutable input snapshot,
   validates every route independently, and shows the better of the two (more animals, then less travel).
2. **Honest travel.** No travel-time matrix is configured, so travel is straight-line distance × 1.3 at a chosen
   speed, labelled on every plan (`travel_basis = straight_line_estimate`).
3. **Explanations, not silence.** Every unplanned area carries reasons (left out, not accessible, no location, no
   estimate, longer than any shift, more doses than any team, access window outside shifts, or ran out of
   time/doses).
4. **Human gate.** Plans are proposals: approve (recorded with a note) then publish, which creates ordinary field
   tasks assigned to teams with planned times. Re-planning creates a new version; publishing it marks the earlier
   published version superseded and leaves its tasks for people to review. Pins and exclusions carry into the next
   version.
5. **Estimates with provenance.** Each area's expected animals come from a manual entry, else the latest street
   count, else registry records — and the plan snapshot records which.
6. **Team tasks.** Tasks assigned to a team appear in "my tasks" for every current team member, who may work them.
