# Handoff

**Last updated:** 2026-10-06 · **Current phase:** 9 (Prevention release audit) — not started
**Completed:** Phases 0–8 (Phase 7 capability is research-only; see IMPLEMENTATION_STATUS) (see `IMPLEMENTATION_STATUS.md` for evidence)

## Resume checklist
1. Read `PawGuard360_Claude_Build_Prompt.md` (master brief — ask the user for it if it is not in the repo),
   `docs/IMPLEMENTATION_STATUS.md`, `docs/adr/`.
2. Start Docker Desktop, then follow README "First run" steps 2–6. The `.env` already exists locally; do not
   regenerate it unless needed (`--force` rotates DB role passwords; re-run `alembic upgrade head` afterwards so
   the roles get the new verifiers — migration 0001 re-sets them).
3. Verify: `bash scripts/check.sh --no-e2e`.

## Environment notes
- pnpm is provided by a corepack shim in `~/bin` (user-level; Program Files not writable).
- Local Supabase project id `pawguard`; ports 54321 (API), 54322 (DB), 54324 (Mailpit). Broker on 6379.
- `infra/supabase/signing_keys.json` (ES256) is gitignored; tokens are ES256 with issuer
  `http://127.0.0.1:54321/auth/v1`.
- Avoid killing processes by command-line substring (it can kill the calling shell); stop the web server by
  port: `Get-NetTCPConnection -LocalPort 3000 | Stop-Process -Id {OwningProcess}`.
- Long multi-file bash heredocs have failed to parse in this harness; write files with the editor tool or a
  scratch Python file. Always open files with `encoding='utf-8'` in Python (cp1252 default once truncated
  pyproject.toml when a write failed mid-way).
- Running stack for e2e: API :8000 (`uvicorn`, no reload — **restart it after router/domain changes**),
  `pawguard-worker run`, `pawguard-worker dispatch`, web via `bash scripts/restart-web.sh` (rebuild + start on :3000).
- Playwright runs from `tests/`: `cd tests && pnpm exec playwright test e2e/<spec> --project=desktop`.
  Multi-org demo accounts (coordinator) must call `switchOrg(page, ORGS.riverside)` from `e2e/helpers.ts`.
- ML tooling is a separate uv project: `cd ml && uv run pawid --help`; tests `uv run --group dev pytest tests`.

## State
- No git commits yet (the user has not asked for commits). `git init` done on `main`.
- Migration head: `0010`. Dataset `dogfacenet-224` v1 registered frozen (raw data under `data/raw/` is gitignored;
  re-download per `DATA_SOURCES.md` S05, then `pawid dataset-prepare` with seed 20261006 is expected to reproduce manifest
  sha256 10a6554b… — reproducibility not yet verified by a second run).
- Identity model `dinov2_small_arcface_head` / `ed25f3a3-resize224-head-v1` is registered **staged** with
  `research_preview` ON in the dev DB (demo organisations see a labelled research preview). Turn off with
  `pawguard-admin models research-preview dinov2_small_arcface_head ed25f3a3-resize224-head-v1 --off --reason …`.
  Weights: `models/dinov2-small/<rev>/dinov2_small_arcface_head.onnx` (gitignored) — rebuild with the
  `pawid` sequence in ML_PLAN ("Reproducing the identity results"); the head is under `data/derived/runs/`. Detector weights: `models/yolox/yolox_s.onnx` (gitignored; re-download from the URL in
  `data/manifests/models/yolox_s-coco-0.1.1rc0.json`, then `pawguard-admin models register <manifest>` and `activate`). After pulling schema changes: `alembic upgrade head`, `pawguard-admin seed-demo`,
  `pnpm api-client:generate`, `uv run python scripts/gen_data_dictionary.py`, `uv run python scripts/gen_permissions.py`.

## Next exact step
Phase 9 — finish and audit the complete Prevention release (brief §9 Phase 9):
1. Role walkthrough on desktop and 360 px: assigned task → photo lookup / manual search → uncertain/new identity →
   record → evidence → vet review → map/task update → offline return → conflict recovery → audited correction.
   Write it as `tests/e2e/release-walkthrough.spec.ts` with screenshots to `docs/screenshots/phase9/`.
2. Audit: compare every visible UI claim with backend behaviour; wording audit (forbidden phrases, "possible match",
   evidence states); empty states; permissions per role (PERMISSIONS.md vs UI); dataset isolation (research data
   never in product); demo flags; Tamil/Hindi coverage list.
3. Fix concrete issues found; then write `docs/RELEASE_REPORT_PREVENTION.md` (what works, test results, limits,
   external validation status, operator guidance, demo script).
Open items: adjudicate DogFaceNet conflict groups; carry the lookup photo into registration; manual box drawing;
real devices for offline testing; a travel-time provider for planning.
