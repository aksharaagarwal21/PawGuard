# PawGuard 360

Community rabies prevention and response platform — **in development**. The current release focus is
Prevention record-keeping for trained teams; see `docs/IMPLEMENTATION_STATUS.md` for exactly what works,
what is tested, and what is blocked. Nothing here is clinically validated or endorsed by any programme.

## Repository map

| Path | What |
|---|---|
| `apps/web` | Next.js 16 web app (public pages + authenticated app) |
| `packages/ui` | Design tokens and accessible UI components |
| `packages/api-client` | TypeScript types generated from the API's OpenAPI document |
| `services/api` | FastAPI service, domain rules, Alembic migrations, `pawguard-admin` CLI |
| `services/worker` | Celery worker and outbox dispatcher (`pawguard-worker` CLI) |
| `ml/` | Data preparation, training and evaluation (Phase 5+) |
| `infra/` | Supabase local config, docker compose, Dockerfiles |
| `tests/` | Playwright end-to-end tests |
| `docs/` | Product, architecture, data, design, ML and status documents |

## Prerequisites

- Docker Desktop (running) — hosts Supabase (Postgres 17 + PostGIS + pgvector, Auth, Storage) and the job broker
- Node.js ≥ 22.12 with corepack (`corepack enable pnpm`, or `corepack enable --install-directory ~/bin pnpm`
  if you cannot write to the Node install directory). pnpm 11.28.4 is pinned via `packageManager`.
- [uv](https://docs.astral.sh/uv/) ≥ 0.7 (installs Python 3.12 automatically)

## First run (local development)

```bash
# 1. Dependencies
uv sync
pnpm install

# 2. Local Supabase stack (first start downloads several images)
echo [] > infra/supabase/signing_keys.json            # only if the file does not exist yet
npx --yes supabase@2.119.0 gen signing-key --algorithm ES256 --append --workdir infra   # first time only
npx --yes supabase@2.119.0 start --workdir infra -x studio,realtime,edge-runtime,logflare,vector,imgproxy,supavisor,postgres-meta

# 3. Job broker (Valkey)
docker compose -f infra/docker-compose.yml up -d broker

# 4. Environment file (reads the running stack, generates DB role passwords)
uv run python scripts/dev_env.py

# 5. Database schema and fictional demo data
(cd services/api && uv run alembic upgrade head)
uv run pawguard-admin seed-demo

# 6. Run the services (separate terminals)
uv run uvicorn pawguard_api.main:app --reload --port 8000 --no-access-log
uv run pawguard-worker run
uv run pawguard-worker dispatch
pnpm dev:web                     # http://localhost:3000
```

Demo accounts (fictional, development only) are listed on the sign-in page with one-click sign-in while
`PAWGUARD_DEMO_MODE=true`. Their shared password is `PawGuard-demo-2026`. `seed-demo` refuses to run unless
`PAWGUARD_ENV` is `development`/`test` and demo mode is on; demo mode is refused in production.

### Provisioning a real first administrator

```bash
uv run pawguard-admin bootstrap-admin --email you@your-org.example --org-name "Your Organisation" --region-code IN-TN
```

The administrator can manage members and approve professional authority for *other* people; nobody can
grant themselves veterinary review authority.

## Checks

```bash
bash scripts/check.sh            # lint, typecheck, API tests, UI tests, build, bundle secret scan, e2e
bash scripts/check.sh --no-e2e
```

API tests create and migrate a separate `pawguard_test` database automatically and run as the restricted
`pawguard_api` role. End-to-end tests expect the API on :8000 and `pnpm --filter @pawguard/web start` on :3000
(build first), and install their browser with `pnpm --filter @pawguard/e2e install-browsers`.

After changing API routes or schemas, regenerate the client: `pnpm api-client:generate`.

## Containers

```bash
docker compose --env-file .env -f infra/docker-compose.yml --profile app up --build
```

Builds `api`, `worker`, `dispatcher` and `web` (web on http://localhost:3001) against the Supabase CLI stack on
the host. Images run as non-root and receive configuration only through environment variables.

## Where to read next

`docs/HANDOFF.md` (resume point) · `docs/IMPLEMENTATION_STATUS.md` · `docs/ARCHITECTURE.md` · `docs/adr/`
