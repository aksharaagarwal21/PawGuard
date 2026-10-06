# Free hosting for PawGuard

Two free options, checked against the providers' own pages on 7 October 2026. **Neither has been deployed and tested
by us yet** — treat this as a checklist and expect to adjust. Use it only for a demo or pilot with fictional or
low-risk data: the local Supabase stack has no backups and uses development defaults.

## Option A (recommended): Oracle Cloud Always Free — one VM runs everything

**What's free (Oracle "Always Free Resources" page):** Arm (Ampere A1) compute of 1,500 OCPU hours and 9,000 GB hours
a month — "equivalent to 2 OCPUs and 12 GB of memory"; 200 GB of boot + block storage; 10 TB a month outbound data;
only in your home region. Oracle asks for a card to verify identity.

**Watch out — idle reclamation:** Oracle may reclaim an Always Free instance if, over 7 days, 95th-percentile CPU,
network and (on A1) memory use are all under 20%. A quiet demo VM can be reclaimed: keep a backup
(`bash scripts/make_demo_backup.sh`) and the steps below to redeploy.

### Steps

1. **Create the VM:** Oracle Cloud console → Compute → Instances → Create → image *Ubuntu 24.04*, shape
   *VM.Standard.A1.Flex* (2 OCPU, 12 GB) → add your SSH key → create. Note the public IP.
2. **Open only web ports:** the instance's VCN → Security List → add ingress TCP 80 and 443 from `0.0.0.0/0`
   (SSH 22 is there already). Do **not** open 54321–54324, 5432/54322, 6379 or 8000.
3. **Free domain (DuckDNS):** sign in at <https://www.duckdns.org>, create a subdomain (e.g. `pawguard`) and set it
   to the VM's public IP. Your address is `pawguard.duckdns.org`.
4. **Install on the VM** (SSH in):
   ```bash
   sudo apt-get update && sudo apt-get install -y docker.io docker-compose-v2 git
   sudo usermod -aG docker $USER && newgrp docker
   # Ubuntu's own firewall rules on Oracle images block 80/443 until opened:
   sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
   sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
   sudo netfilter-persistent save
   # Supabase CLI (arm64 build) and Node 22 for it:
   curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash - && sudo apt-get install -y nodejs
   git clone https://github.com/aksharaagarwal21/PawGuard.git && cd PawGuard
   ```
5. **Configuration:** copy your `.env` to the VM (it is git-ignored, so `scp` it — never commit it) and change:
   ```
   PAWGUARD_WEB_ORIGIN=https://pawguard.duckdns.org
   PAWGUARD_EXTRA_WEB_ORIGINS=
   PAWGUARD_STORAGE_SAME_ORIGIN=true
   ```
   Also copy `infra/supabase/signing_keys.json` (git-ignored) if you want existing sign-ins to keep working.
6. **Start the database/auth/storage stack and migrate:**
   ```bash
   npx --yes supabase@2.119.0 start --workdir infra -x studio,realtime,edge-runtime,logflare,vector,imgproxy,supavisor,postgres-meta
   docker compose -f infra/docker-compose.yml up -d broker
   # one-off: run migrations and (optionally) the demo seed from the API image
   PAWGUARD_DOMAIN=pawguard.duckdns.org docker compose -f infra/docker-compose.yml -f infra/deploy/docker-compose.oracle.yml --profile app run --rm api alembic upgrade head
   ```
7. **Start the app with HTTPS:**
   ```bash
   PAWGUARD_DOMAIN=pawguard.duckdns.org docker compose -f infra/docker-compose.yml \
     -f infra/deploy/docker-compose.oracle.yml --profile app up -d --build
   ```
   Caddy (`infra/deploy/Caddyfile`) gets a free Let's Encrypt certificate automatically on first request and renews
   it. Open `https://pawguard.duckdns.org`.
8. **WhatsApp webhook:** the address is now stable — paste `https://pawguard.duckdns.org/api/v1/webhooks/whatsapp`
   into Meta once (WhatsApp → Configuration).
9. **Model weights (optional):** photo matching needs the files under `models/` (git-ignored); without them the app
   says "Assisted matching unavailable" and everything else works.

## Option B: Vercel (web) + Supabase free tier (database, auth, storage) — partial

**What's free:** Vercel Hobby — "restricts users to non-commercial, personal use only"; 100 GB fast data transfer,
1,000,000 function invocations, functions up to 300 s a month (Hobby limits table). Supabase Free — "500 MB database
size", "1 GB file storage", "5 GB egress", "Limit of 2 active projects", **"Free projects are paused after 1 week of
inactivity"**, and no backups.

**Why it's only partial:** Vercel hosts the Next.js web app only. PawGuard's Python API, background worker,
dispatcher and the Valkey queue still need a server (e.g. the Oracle VM from option A, without its local Supabase).
Also, our migrations create database roles and rely on the migration user bypassing row security inside
security-definer functions; on Supabase's hosted service the `postgres` user is not a full superuser, so **this must be
tested before relying on it**.

### Steps (outline)
1. Supabase: create a project (region near India) → Project Settings → Database → copy the connection string; enable
   the `postgis`, `vector` and `pgcrypto` extensions → run `alembic upgrade head` against it from your laptop with
   `PAWGUARD_MIGRATE_DATABASE_URL` set → check the security-definer functions return rows (e.g. the public QR card).
2. Server for API + worker + dispatcher + Valkey: as in option A, but point `PAWGUARD_DATABASE_URL`,
   `PAWGUARD_WORKER_DATABASE_URL` and `PAWGUARD_SUPABASE_URL` at the Supabase project.
3. Vercel: import the GitHub repo → root directory `apps/web` → set the `PAWGUARD_*` web variables (API internal URL =
   the server's HTTPS address, web origin = your `*.vercel.app` address).
4. Keep it awake: a free Supabase project pauses after a week without activity; open the app (or restore it from the
   Supabase dashboard) before a demo.

## What stays the same everywhere
- Demo organisations, fictional accounts and the demo reset work the same.
- Free email (Gmail app password), Web Push, WhatsApp test number and Gemini/Ollama — see `FREE_SERVICES_SETUP.md`.
- SMS to Indian numbers is not free (DLT registration) and is not built.
