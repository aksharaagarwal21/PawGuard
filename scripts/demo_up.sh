#!/usr/bin/env bash
# Start (or restart) everything needed for the PawGuard demonstration on this machine.
# Run with Git Bash (from PowerShell use scripts\demo_up.ps1, because `bash` there is WSL's Linux bash).
# Idempotent: services already listening are stopped and started again so the latest code runs.
#   bash scripts/demo_up.sh            # start stack, migrate, start API/worker/dispatcher/web, health check
#   bash scripts/demo_up.sh --reset    # also reset the demo organisations and prepare the photo-lookup demo
set -euo pipefail
cd "$(dirname "$0")/.."
# shellcheck source=scripts/_tools.sh
source scripts/_tools.sh
LOG="${TEMP:-/tmp}"

echo "1/6 Supabase (Docker Desktop must be running)"
docker info >/dev/null 2>&1 || { echo "Docker is not running: start Docker Desktop, wait for 'Engine running', then retry." >&2; exit 1; }
npx --yes supabase@2.119.0 start --workdir infra -x studio,realtime,edge-runtime,logflare,vector,imgproxy,supavisor,postgres-meta \
  >"$LOG/pg_supabase.log" 2>&1 || grep -q "already running" "$LOG/pg_supabase.log" || { cat "$LOG/pg_supabase.log"; exit 1; }

echo "2/6 Job broker"
docker compose --env-file .env -f infra/docker-compose.yml up -d broker >/dev/null 2>&1

echo "3/6 Database migrations"
(cd services/api && pyrun alembic upgrade head >/dev/null)

echo "4/6 API, worker, dispatcher"
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { \$_.Name -in @('uvicorn.exe','pawguard-worker.exe') } | ForEach-Object { Stop-Process -Id \$_.ProcessId -Force -ErrorAction SilentlyContinue }" || true
sleep 2
(pyrun uvicorn pawguard_api.main:app --port 8000 --no-access-log >"$LOG/pg_api.log" 2>&1 &)
(pyrun pawguard-worker run >"$LOG/pg_worker.log" 2>&1 &)
(pyrun pawguard-worker dispatch >"$LOG/pg_dispatch.log" 2>&1 &)
for _ in $(seq 1 60); do curl -sf http://127.0.0.1:8000/health/ready >/dev/null && break; sleep 1; done
curl -sf http://127.0.0.1:8000/health/ready >/dev/null || { echo "API not ready; see $LOG/pg_api.log" >&2; exit 1; }

if [ "${1:-}" = "--reset" ]; then
  echo "5/6 Demo reset + photo-lookup preparation"
  pyrun pawguard-admin demo-reset --yes | tail -2
  PYTHONIOENCODING=utf-8 pyrun python scripts/demo_prepare.py
else
  echo "5/6 Demo data left as is (use --reset for a clean demo)"
fi

echo "6/6 Web (production build on :3000)"
bash scripts/restart-web.sh
curl -s http://127.0.0.1:8000/health/ready; echo
echo "Open http://localhost:3000/en/sign-in — use the 'Sign in as …' demo buttons."
