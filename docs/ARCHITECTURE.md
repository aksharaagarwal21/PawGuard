# Architecture

Modular monolith (FastAPI) + asynchronous workers (Celery) + Next.js web app, on PostgreSQL (PostGIS, pgvector) with Supabase Auth and private Supabase Storage. Decisions with trade-offs are recorded in `docs/adr/`.

## System diagram

```mermaid
flowchart LR
  subgraph Browser
    UI[Next.js pages / React]
    SW[Service worker + IndexedDB<br/>(Phase 8, field tasks only)]
  end
  subgraph Web["Next.js server (same origin)"]
    PX[proxy.ts<br/>locale + session refresh]
    GW[/api/v1 gateway route<br/>CSRF + origin check/]
    SA[Server actions:<br/>sign-in / sign-out]
  end
  subgraph API["FastAPI (services/api)"]
    AUTH[JWT verify via JWKS<br/>iss/aud/exp]
    CMD[Domain commands<br/>permission + audit + outbox<br/>in one transaction]
  end
  subgraph Workers["services/worker"]
    DISP[Outbox dispatcher]
    CEL[Celery tasks:<br/>media validation, OpenCV quality,<br/>YOLOX detection, DINOv2 embedding]
  end
  PG[(PostgreSQL 17<br/>app schema + RLS<br/>PostGIS · pgvector)]
  GT[Supabase Auth<br/>GoTrue]
  ST[Supabase Storage<br/>private bucket]
  RD[(Valkey broker<br/>Redis protocol)]

  UI -- cookie session --> GW
  UI -- signed upload URL (PUT) --> ST
  SA -- password grant --> GT
  PX -- refresh --> GT
  GW -- Bearer access token --> AUTH --> CMD
  AUTH -. JWKS .-> GT
  CMD -- pawguard_api role<br/>SET LOCAL context --> PG
  CMD -- sign URLs (server key) --> ST
  DISP -- poll outbox SKIP LOCKED --> PG
  DISP --> RD --> CEL
  CEL -- pawguard_worker role --> PG
  CEL -- read quarantine / write derivatives --> ST
```

## Service boundaries

- **Browser** never holds Supabase tokens or service keys. It talks to the same-origin Next.js server only, except for uploading bytes to a pre-signed, single-object Storage URL.
- **Next.js server** renders pages, refreshes the Supabase session in `proxy.ts`, and forwards `/api/v1/*` to FastAPI with the user's access token as `Authorization: Bearer`. It holds no business rules for vaccination, identity or clinical data. ([ADR 0002](adr/0002-session-boundary.md))
- **FastAPI** is the single business-rule boundary. Every privileged operation is a *command*: validate input → load current membership + capabilities → check record scope → mutate → write `audit_events` + `outbox_events` → commit. Reads also go through the API.
- **Workers** execute queued jobs with a separate DB role and per-job tenant scope; they import domain services from the API package instead of duplicating them.

## Authentication and tenant context ([ADR 0002](adr/0002-session-boundary.md), [ADR 0003](adr/0003-rls-context.md))

1. FastAPI verifies the bearer JWT against the Auth server's JWKS (`/auth/v1/.well-known/jwks.json`, ES256/RS256), checking signature, `iss` (`<SUPABASE_URL>/auth/v1`), `aud` (`authenticated`), `exp`, and `role = authenticated`. A client-supplied role, org or capability is never trusted.
2. The request names an organisation (`X-PawGuard-Org` header). The API looks up an **active membership** for `(sub, org)`; no membership → 403. The header is a *selector*, not proof.
3. Inside the transaction the API calls `app.set_request_context(user_id, org_id)` which uses `set_config(..., is_local => true)`; the context dies with the transaction, so pooled connections cannot leak it.
4. RLS policies compare `org_id = (select app.current_org_id())`. `app.current_org_id()` is a small `SECURITY DEFINER` function with a fixed `search_path` that returns the context org **only if** an active membership for the context user still exists (or, for the worker role, only if the referenced job is claimed and belongs to that org). RLS is therefore defence in depth, not the only check.
5. Request connections use role `pawguard_api` (LOGIN, NOBYPASSRLS, not table owner). Workers use `pawguard_worker`. Migrations use the owner role. Tables have `FORCE ROW LEVEL SECURITY`.
6. Sensitive commands (vaccination review, merges, membership/approval changes) additionally check that the token's `session_id` is still present in `auth.sessions` (server-side sign-out/revocation), via a narrow `SECURITY DEFINER` function.

## Storage ([ADR 0004](adr/0004-media-pipeline.md))

Private bucket `pawguard-media`. Object keys: `quarantine/<org>/<media_id>/original`, `derived/<org>/<media_id>/<variant>.jpg`. Upload intent → API creates `media_assets` row (`pending_upload`) and a signed upload URL for that exact key → browser PUTs → `POST /media/{id}/complete` → API checks object exists/size → outbox → worker decodes and validates from bytes (MIME sniff, pixel limits, decompression-bomb guard, EXIF orientation), writes derivatives, marks `approved`/`rejected`. Records may only reference media in `approved` state. Downloads use signed URLs valid ≤ 120 s, issued after an authorisation check. Abandoned `pending_upload` objects are deleted after a documented TTL.

## Jobs and events

`outbox_events` is written in the same transaction as the domain change. A dispatcher (`pawguard-worker dispatch`) claims rows with `FOR UPDATE SKIP LOCKED`, enqueues Celery tasks (Redis broker), and marks them dispatched. Tasks are **at-least-once** and idempotent: each checks `background_jobs` state before acting and records attempts, terminal error codes and timestamps. Clients poll job/resource state; push updates are an optional enhancement.

## Data model

See `docs/DATA_DICTIONARY.md` (field-level) and the ER diagram there. Business tables live in schema `app`; PostgREST exposes only `public` and auto-exposure of new tables is disabled. Alembic is the only migration authority ([ADR 0005](adr/0005-migrations.md)).

## ML serving ([ADR 0006](adr/0006-vision-models.md))

Lean inference in the worker with ONNX Runtime + OpenCV (no PyTorch in the worker image). Training/export lives in `ml/` with PyTorch. Models are registered in `model_versions` with checksum, licence, preprocessing contract and state (`staged/active/retired`). Embeddings are keyed by model version; vectors from different versions are never compared.

## Repository layout

| Path | Contents |
|---|---|
| `apps/web/` | Next.js App Router app (public site + authenticated app) |
| `packages/ui/` | Design tokens (CSS) and accessible UI primitives |
| `packages/api-client/` | Types generated from FastAPI OpenAPI + typed fetch client |
| `services/api/` | FastAPI app, domain commands, SQLAlchemy models, Alembic migrations, admin CLI |
| `services/worker/` | Celery app, outbox dispatcher, media/vision tasks |
| `ml/` | Data preparation, training, evaluation, export CLIs (`pawid …`) |
| `data/manifests/` | Small, versioned dataset manifests (no images, no private data) |
| `infra/` | Supabase local config, docker compose, Dockerfiles |
| `scripts/` | Dev helper scripts |
| `tests/` | Cross-service end-to-end tests (Playwright) |

## Dependency matrix (pinned in lockfiles; checked 2026-10-05)

| Concern | Package / artefact | Pinned | Notes |
|---|---|---|---|
| Runtime | Node.js / pnpm | 22.18 (local) / 11.28.4 | pnpm 12 cannot be launched by corepack 0.33 |
| Runtime | Python | 3.12 | uv-managed; container base `python:3.12-slim` |
| Web | next / react | 16.3.8 / 19.3.0 | App Router |
| Web | typescript | 6.0.3 | 7.x not yet supported by typescript-eslint (`<6.1`) |
| Web | tailwindcss | 4.3.3 | CSS-first `@theme` tokens |
| Web | next-intl | 4.14.9 | en / ta / hi |
| Web | @supabase/ssr / supabase-js | 0.12.7 / 2.117.2 | server-side only |
| Web | radix-ui, lucide-react | 1.6.7, 1.52.0 | |
| Web | react-hook-form, zod, @tanstack/react-query | 7.89.0, 4.6.5, 5.104.1 | |
| Web | maplibre-gl | 6.12.0 | lazy-loaded |
| Tests | @playwright/test, @axe-core/playwright, vitest | 1.63.0, 4.13.0, 5.0.3 | |
| API | fastapi, pydantic, sqlalchemy, psycopg, alembic | 0.142.2, 2.13.5, 2.1.3, 3.3.6, 1.20.0 | final pins in `uv.lock` |
| API | geoalchemy2, pgvector, pyjwt[crypto] | 0.20.0, 0.5.0, 2.15.1 | |
| Jobs | celery, redis (client) | 5.6.3, 6.4.0 | kombu requires redis-py < 6.5; broker is Valkey 8.1.10 (BSD-3) in compose |
| Vision | opencv-python-headless, onnxruntime | 5.0.0.93, 1.30.0 | worker image |
| ML | torch, torchvision | 2.14.1, 0.29.1 | CPU wheels; `ml/` only |
| DB | Supabase Postgres image | 17.11.0.002 | PostGIS 3.3.7, pgvector 0.8.2 |
| Auth/Storage | Supabase CLI | 2.119.0 | local stack |
| Detector | YOLOX-S COCO (official ONNX, release 0.1.1rc0) | sha256 recorded in model registry | Apache-2.0 |
| Retrieval | facebook/dinov2-small @ `ed25f3a31f01632728cabb09d1542f84ab7b0056` | safetensors | Apache-2.0 |

## Risk register

| # | Risk | Likelihood / impact | Mitigation |
|---|---|---|---|
| R1 | No permissioned real dog-identity data from a partner | High / High | Manual workflow is complete without ML; DogFaceNet used only as labelled research benchmark; assisted matching stays research-only until the pilot gate passes |
| R2 | Users read a candidate match as a verified identity, or a verified vaccination as "safe" | Medium / High | Wording reviewed in `DESIGN_SYSTEM.md`; no pre-selected candidate; no "safe" label anywhere; tests assert absent strings |
| R3 | Cross-tenant leakage via vector search, counts or job polling | Medium / High | Tenant filter applied in SQL before ranking; RLS; integration tests per surface |
| R4 | Context leakage across pooled connections | Low / High | `set_config(..., true)` only; pool-reuse test |
| R5 | Unreviewed starter health content mistaken for approved guidance | Medium / High | Visible review status on every content block; content register |
| R6 | Laptop-only CPU compute (i7-1255U, 16 GB, no CUDA) limits training | High / Medium | Frozen-backbone baseline first; bounded runs; GPU optional and documented |
| R7 | Supabase local stack differs from hosted (keys, issuer) | Medium / Medium | Verify issuer/JWKS at startup; config-driven; staging check in Phase 14 |
| R8 | Map tile policy breach | Low / Medium | Configurable provider; no bulk/offline OSM tiles; list fallback |
| R9 | Offline device loss exposes cached data | Medium / Medium | Trusted-device opt-in, minimal cache, sign-out purge, documented residual risk |
| R10 | Health helpline coverage is regional (15400 serves five states per NRCP page, 2026-10-05) | High / Medium | Show coverage caveat; 112 general emergency; locale/region-configurable contacts |
