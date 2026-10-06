#!/usr/bin/env bash
# Local equivalent of .github/workflows/ci.yml. Requires the local stack to be running
# (Supabase CLI stack + broker) and a generated .env. Usage: bash scripts/check.sh [--no-e2e]
set -euo pipefail
cd "$(dirname "$0")/.."

step() { printf '\n\033[1m== %s\033[0m\n' "$1"; }

step "Python lint";            uv run ruff check services scripts ml
step "TypeScript typecheck";   pnpm -r typecheck
step "ESLint";                 pnpm -r lint
step "API client is fresh";    pnpm --filter @pawguard/api-client check-fresh
step "Migrations (dev DB)";    (cd services/api && uv run alembic upgrade head)
step "API tests";              uv run pytest -q -W ignore::DeprecationWarning
step "UI unit tests";          pnpm --filter @pawguard/ui test
step "Web build";              pnpm --filter @pawguard/web build
step "Bundle secret scan";     uv run python scripts/check_bundle_secrets.py
step "ML evidence trace";      PYTHONIOENCODING=utf-8 uv run python scripts/check_ml_evidence.py

if [[ "${1:-}" != "--no-e2e" ]]; then
  step "End-to-end (expects API on :8000 and 'pnpm --filter @pawguard/web start' on :3000)"
  uv run pawguard-admin seed-demo
  pnpm --filter @pawguard/e2e exec playwright test --grep-invert "first-load|visual review"
fi
printf '\nAll checks passed.\n'
