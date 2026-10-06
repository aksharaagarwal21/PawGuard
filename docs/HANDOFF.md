# Handoff

**Last updated:** 2026-10-06 · **Current phase:** 9 complete — demonstration build; Phases 10–14 paused by request
**Completed:** Phases 0–9 (Phase 7 capability is research-only; see IMPLEMENTATION_STATUS) (see `IMPLEMENTATION_STATUS.md` for evidence)

## Resume checklist
1. Read `PawGuard360_Claude_Build_Prompt.md` (master brief — ask the user for it if it is not in the repo),
   `docs/IMPLEMENTATION_STATUS.md`, `docs/adr/`.
2. Start Docker Desktop, then follow README "First run" steps 2–6. The `.env` already exists locally; do not
   regenerate it unless needed (`--force` rotates DB role passwords; re-run `alembic upgrade head` afterwards so
   the roles get the new verifiers — migration 0001 re-sets them).
3. Verify: `bash scripts/check.sh --no-e2e`.

## Demo day
`bash scripts/demo_up.sh --reset`, then follow `docs/RELEASE_REPORT_PREVENTION.md` §9–10.

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
- Local git commits authorised (no push). Pre-audit checkpoint `84249ff`; see `git log` for the reviewed build.
- Migration head: `0011`. Dataset `dogfacenet-224` v1 registered frozen (raw data under `data/raw/` is gitignored;
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
Phase 9 is complete; expansion (Phases 10–14) is paused until the user resumes it after the hackathon.
If resuming: first run the phone checklist in `docs/RELEASE_REPORT_PREVENTION.md` §6 and address the ranked issues
(§11) that matter for the pilot; then Phase 10 (Awareness content workflow + bounded AI; needs an Anthropic API key
and qualified content reviewers).
