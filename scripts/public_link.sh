#!/usr/bin/env bash
# Publish the locally running demo through a temporary HTTPS address (Cloudflare Quick Tunnel; no account).
# The address changes every time and works only while this laptop, the services and the tunnel are running.
# From PowerShell: .\scripts\public_link.ps1     Stop: .\scripts\public_link.ps1 --stop
set -euo pipefail
cd "$(dirname "$0")/.."
# shellcheck source=scripts/_tools.sh
source scripts/_tools.sh
LOG="${TEMP:-/tmp}"
CF=".tools/cloudflared.exe"

set_env() {  # set_env NAME VALUE — replace or append one line in .env (other lines untouched)
  python - "$1" "$2" <<'PY'
import pathlib, sys
name, value = sys.argv[1], sys.argv[2]
p = pathlib.Path(".env"); lines = p.read_text(encoding="utf-8").splitlines()
out = [l for l in lines if not l.startswith(name + "=")] + [f"{name}={value}"]
p.write_text("\n".join(out) + "\n", encoding="utf-8")
PY
}

stop_tunnel() {
  powershell -NoProfile -Command "Get-Process cloudflared -ErrorAction SilentlyContinue | Stop-Process -Force" || true
}

if [ "${1:-}" = "--stop" ]; then
  stop_tunnel
  set_env PAWGUARD_EXTRA_WEB_ORIGINS ""
  echo "Public link stopped. The app is still available locally at http://localhost:3000/en/sign-in"
  exit 0
fi

curl -sf http://127.0.0.1:8000/health/ready >/dev/null || { echo "Start the app first: .\\scripts\\demo_up.ps1" >&2; exit 1; }

if [ ! -x "$CF" ]; then
  echo "Downloading cloudflared (official Cloudflare release) to $CF"
  mkdir -p .tools
  curl -fsSL -o "$CF" https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe
fi

echo "1/4 Starting tunnel"
stop_tunnel
("$CF" tunnel --no-autoupdate --url http://localhost:3000 >"$LOG/pg_tunnel.log" 2>&1 &)
URL=""
for _ in $(seq 1 60); do
  URL=$(grep -oE "https://[a-z0-9-]+\.trycloudflare\.com" "$LOG/pg_tunnel.log" | head -1 || true)
  [ -n "$URL" ] && break
  sleep 1
done
[ -n "$URL" ] || { echo "Tunnel did not start; see $LOG/pg_tunnel.log" >&2; exit 1; }

echo "2/4 Allowing $URL and serving photos through the app"
set_env PAWGUARD_EXTRA_WEB_ORIGINS "$URL"
set_env PAWGUARD_STORAGE_SAME_ORIGIN "true"

echo "3/4 Restarting API and web"
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { \$_.Name -eq 'uvicorn.exe' } | ForEach-Object { Stop-Process -Id \$_.ProcessId -Force -ErrorAction SilentlyContinue }" || true
sleep 1
(pyrun uvicorn pawguard_api.main:app --port 8000 --no-access-log >"$LOG/pg_api.log" 2>&1 &)
for _ in $(seq 1 60); do curl -sf http://127.0.0.1:8000/health/ready >/dev/null && break; sleep 1; done
bash scripts/restart-web.sh

echo "4/4 Checking the public address"
for _ in $(seq 1 30); do
  code=$(curl -s -o /dev/null -m 15 -w '%{http_code}' "$URL/en/sign-in" || true)
  [ "$code" = "200" ] && break
  sleep 2
done
[ "$code" = "200" ] || { echo "Public address not answering yet (HTTP $code); try again in a minute." >&2; exit 1; }
echo
echo "PUBLIC LINK: $URL"
echo "(opens the demo instructions; \"Let's start\" leads to sign-in)"
echo "Anyone with this link can use the fictional demo accounts while this laptop, the services and the tunnel run."
echo "Stop it with: .\\scripts\\public_link.ps1 --stop"
