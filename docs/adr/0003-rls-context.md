# ADR 0003 — Transaction-local tenant context and RLS as defence in depth

Date: 2026-10-05 · Status: accepted

## Decision
- Business tables in schema `app`, `ENABLE` + `FORCE ROW LEVEL SECURITY`, owned by the migration role.
- Runtime roles: `pawguard_api` and `pawguard_worker` — LOGIN, NOSUPERUSER, NOBYPASSRLS, not owners, least-privilege grants (no `DELETE` on evidence tables, no `TRUNCATE`).
- Context is set only via `app.set_request_context(user uuid, org uuid)` / `app.set_worker_context(job uuid)`, which call `set_config(..., true)` (transaction-local).
- Policies use `org_id = (select app.current_org_id())`. The function is `SECURITY DEFINER`, `SET search_path = ''`, `STABLE`, and returns the org only if (API) an active, unrevoked membership exists for the context user, or (worker) the context job is in `processing` state for that org. Otherwise `NULL` → no rows.
- Capability-restricted tables (audit, caregiver contacts) additionally require `app.has_capability('<cap>')`.
- The API still performs explicit membership/capability/record checks in each command; RLS catches mistakes.

## Rejected
Accepting `org_id` from a header as proof (spoofable); session-level `SET` (leaks across pooled connections); a single service role for all requests (bypasses policies).

## Consequences
One extra indexed lookup per statement (initPlan-cached). Tests must run as `pawguard_api`, not as the owner.
