#!/usr/bin/env bash
# Rebuild and restart the production web server on :3000 (local development helper, Windows + Git Bash).
set -euo pipefail
cd "$(dirname "$0")/.."
# shellcheck source=scripts/_tools.sh
source scripts/_tools.sh
cd apps/web
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id \$_.OwningProcess -Force -ErrorAction SilentlyContinue }" || true
$PNPM build 2>&1 | grep -E "Compiled|rror" || true
($PNPM start > "${TEMP:-/tmp}/pg_web.log" 2>&1 &)
for _ in $(seq 1 60); do curl -s -o /dev/null http://localhost:3000/en && echo "web ready" && exit 0; sleep 1; done
echo "web did not start" >&2; exit 1
