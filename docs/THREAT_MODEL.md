# Threat model

Living document; reviewed against the implementation at each phase and fully in Phase 14. STRIDE-style,
focused on the assets that matter.

## Assets

Patient-linked exposure data (Phase 11+) · caregiver contact details · exact community-animal locations ·
vaccination evidence and its verification state · professional-approval records · membership/capability data ·
audit trail · media (photos, certificates) · model weights and embeddings · credentials (Supabase secret key,
DB role passwords, signing keys).

## Trust boundaries

Browser ↔ Next.js server (cookie session, CSRF) · Next.js ↔ FastAPI (bearer token, internal network) ·
FastAPI ↔ PostgreSQL (`pawguard_api` role + RLS) · Worker ↔ PostgreSQL (`pawguard_worker` role, per-job scope) ·
Browser ↔ Storage (single-object signed URLs) · Operators ↔ admin CLI (owner credentials).

## Threats and current controls

| Threat | Control (status) |
|---|---|
| Token theft via XSS | Auth cookies httpOnly, browser has no Supabase client (✅ tested e2e); CSP restricts sources, but `script-src 'unsafe-inline'` remains until nonce CSP (Phase 14) |
| CSRF on cookie-authenticated mutations | Gateway requires same-origin `Origin` + double-submit header (✅ tested); server actions use Next.js origin checks |
| Forged/altered tokens | API verifies ES256/RS256 signature via JWKS, `iss`, `aud`, `exp`, `role`; HS256 refused (✅ tested) |
| Spoofed organisation / role | `X-PawGuard-Org` is only a selector; active membership + DB capabilities checked per request; token claims ignored (✅ tested) |
| Revoked member keeps access until token expiry | Membership read on every request (✅ tested); server-side session liveness for sensitive commands via `auth.sessions` (function ✅ tested; commands in Phase 3+) |
| Cross-tenant reads via API bugs | RLS with `FORCE`, runtime role without BYPASSRLS, context verified against membership (✅ tested) |
| Context leakage across pooled connections | `set_config(..., true)` only (✅ tested with forced connection reuse) |
| Self-granted professional authority | DB check `reviewer_user_id <> user_id` + RLS insert policy (✅ tested) |
| Audit tampering | Append-only trigger blocks UPDATE/DELETE even for owner (✅ tested); TRUNCATE by owner remains possible (operator control) |
| Secrets in frontend bundle | No `NEXT_PUBLIC_` secrets; bundle scan in CI (✅ passing) |
| Role password exposure in migration logs | SCRAM verifiers computed client-side; plaintext never sent (✅) |
| Demo data/accounts in production | `seed-demo` refuses outside dev/test; demo mode refused when `ENV=production` in API and web (✅ code path; Phase 14 deployment check) |
| Malicious uploads (decompression bombs, polyglots) | Phase 4/5: quarantine, byte-level validation in worker, pixel limits |
| Worker holds broad Storage key | Residual risk: Supabase lacks per-prefix machine keys; worker isolated in its own container |
| Public map de-anonymisation | Phase 4/12: aggregation + suppression; exact coordinates only with `animal.location.exact` |
| Model/data supply chain | Pinned revisions + checksums; no `trust_remote_code`; safetensors (Phase 5/7) |
| Using photo search to learn about another organisation's animals | Gallery search runs in the worker under the job's organisation (RLS); results, counts and timings come only from that organisation; the API never reads or returns vectors (✅ `test_identity.py`) |
| Over-trust in a "match" | No scores or percentages; "possible match" wording; side-by-side photos; separate confirmation before linking; decisions + rank recorded; real organisations get no suggestions until a model passes the release gate (DB-enforced) (✅ tested) |
| Silent misses from an incomplete gallery index | Searches report `stale_index` below 90% coverage; model switch refused until the new index is complete (✅ tested) |
| Lost or shared phone with offline data | Explicit opt-in with a stated risk; minimal fields; 72 h expiry; wipe on stop and sign-out (✅ e2e); not encrypted — residual risk below |
| Replaying old offline changes with revoked rights or on another account | Replay uses current permissions; actor and organisation must match; suspended members get 403 (✅ `test_sync.py`) |
| Plans dispatching work automatically | Approve then publish, both explicit and audited; earlier tasks are never changed silently (✅ tested) |

## Residual risks accepted for now

`'unsafe-inline'` scripts (Next.js bootstrap) · a compromised API process can set any context (RLS is defence in
depth, not a substitute for API integrity) · owner credentials can bypass everything (operational control).
- Offline field data in IndexedDB is readable by anyone with the unlocked device and browser profile; we rely on the opt-in warning, minimal fields, expiry and wipe rather than claiming encryption.
