# Restoring the PawGuard demonstration from a local backup

Created by `bash scripts/make_demo_backup.sh` in `backups/demo-backup-<date>/` (ignored by Git). Keep it on this
laptop and copy it to a USB stick. **Do not share or upload it**: the database dump contains the demo accounts'
password hashes and session records.

## Contents

| Path | What | Needed for |
|---|---|---|
| `repo/pawguard.bundle` | Full Git history (all commits) | Restoring the code anywhere |
| `models/` | `yolox/yolox_s.onnx` (detector), `dinov2-small/<rev>/` (DINOv2 safetensors + configs + the exported `dinov2_small_arcface_head.onnx`), `identity-head/head.safetensors` | Detection and the research-preview lookup; no retraining needed |
| `database/pawguard-demo.dump` | `pg_dump -Fc` of the `app` and `auth` schemas (demo state when the backup was made) | Last-resort exact restore |
| `database/storage-objects/` | Supabase Storage file backend (`/mnt/stub`) | Photos referenced by that dump |
| `demo-media/` | Licence-filtered COCO sample (incl. the prepared query photo `000000392818.jpg`), its manifest, the synthetic fixtures | Re-running `demo_prepare.py`; uploading during the demo |
| `video/` | Recorded demo journey | Fallback if the live demo fails |
| `SHA256SUMS.txt` | Checksums of everything above | Verifying the copy: `sha256sum -c SHA256SUMS.txt` |

**Not included (credentials, keep separately):** `.env` and `infra/supabase/signing_keys.json`. On the same laptop
they are already in place. On another machine they are regenerated (steps below); if you want to keep the existing
ones, copy them to a separate private location yourself — never into the shared repository.

## Restore on this laptop (code or data broken)

```bash
cd /c/PawGuard
git log --oneline -5                 # pick the demo commit (see docs/HANDOFF.md)
git checkout <commit> -- .           # restores files; history is kept
cp -r backups/demo-backup-<date>/models/. models/    # only if model files are missing or damaged
bash scripts/demo_up.sh --reset      # recreates demo data the supported way
```

The `--reset` path rebuilds the demo state from code (guarded reset of demo organisations only + seed +
`demo_prepare.py`); it needs `data/raw/coco/val2017_sample/` — if that is missing:
`mkdir -p data/raw/coco && cp -r backups/demo-backup-<date>/demo-media/coco-val2017-sample data/raw/coco/val2017_sample`.

## Restore on another machine (Windows + Git Bash, Docker Desktop, Node ≥ 22.12 with corepack, uv)

```bash
git clone backups/demo-backup-<date>/repo/pawguard.bundle PawGuard && cd PawGuard
cp -r <backup>/models/. models/
mkdir -p data/raw/coco && cp -r <backup>/demo-media/coco-val2017-sample data/raw/coco/val2017_sample
uv sync && pnpm install
echo [] > infra/supabase/signing_keys.json
npx --yes supabase@2.119.0 gen signing-key --algorithm ES256 --append --workdir infra
npx --yes supabase@2.119.0 start --workdir infra -x studio,realtime,edge-runtime,logflare,vector,imgproxy,supavisor,postgres-meta
docker compose -f infra/docker-compose.yml up -d broker
uv run python scripts/dev_env.py        # writes a new .env (new local DB role passwords)
(cd services/api && uv run alembic upgrade head)
uv run pawguard-admin seed-demo
uv run pawguard-admin models register data/manifests/models/yolox_s-coco-0.1.1rc0.json
uv run pawguard-admin models activate yolox_s_coco 0.1.1rc0-onnx --reason "restore"
uv run pawguard-admin models register data/manifests/models/dinov2_small_arcface_head-v1.json
uv run pawguard-admin models research-preview dinov2_small_arcface_head ed25f3a3-resize224-head-v1 --reason "restore: demo research preview"
bash scripts/demo_up.sh --reset
```

The identity model stays **staged with a failed release gate**; the last two commands only re-enable the labelled
research preview for demo organisations. Nothing is retrained.

## Last resort: exact database restore

Only if the supported path above fails and you need the exact recorded state. It replaces the `app` and `auth`
schemas of the local development database (demo data only on this laptop):

```bash
docker exec -i supabase_db_pawguard pg_restore -U postgres -d postgres --clean --if-exists --no-owner \
  < backups/demo-backup-<date>/database/pawguard-demo.dump
docker cp backups/demo-backup-<date>/database/storage-objects/. supabase_storage_pawguard:/mnt/stub/
bash scripts/demo_up.sh
```

Expect harmless warnings about objects owned by Supabase roles. If sign-in fails afterwards, run
`bash scripts/demo_up.sh --reset` instead.
