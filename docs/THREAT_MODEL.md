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

## Signed vaccination certificates (ADR 0010/0011)

| Threat | Control (status) |
|---|---|
| Forged QR (made-up clinic, edited date or pet) | COSE_Sign1/Ed25519 over the payload and protected header; any changed byte fails (✅ 40-position byte-flip browser test, every byte server test); unknown key id → "unknown or untrusted clinic"; trusted key id with another signature → "altered" (✅) |
| Fake trust list (attacker adds their key) | Trust and revocation lists are signed by the root key compiled into the app; tampered or other-root lists are rejected (✅ tests); older lists never replace newer cached ones (anti-rollback) |
| Stolen clinic private key | Keys sealed with AES-256-GCM under a master key outside the DB; `keys revoke` marks the key revoked → all its certificates verify as untrusted; `keys rotate --reissue` re-signs (✅ tested). Residual: verifiers offline since before the revocation keep trusting until they refresh (stale warning after 7 days) |
| Stolen master key + database | Attacker could sign as any clinic → revoke and rotate every key, change the master key. Residual risk documented |
| Compromised root key | Requires a new app build with a new root public key; no remote revocation of a compiled-in root. Production plan: offline root + short-lived list-signing key (not built) |
| Replay of a cancelled certificate | Revocation list (root-signed, versioned in the same transaction) → "replaced or cancelled" (✅); offline verifiers see cancellations only after their last refresh (freshness time always shown) |
| Real certificate shown for a different animal | Out of scope for cryptography: the result says "Check that this matches the animal in front of you" and shows pet details and, online, the photo on record |
| Private keys leaking through APIs, logs, errors or the web bundle | Never returned or logged; SQL parameters hidden in errors; automated checks in API tests (responses + logs) and `scripts/check_bundle_secrets.py` (bundle) (✅) |
| Decompression bomb / oversized QR | Text ≤ 2,000 characters, inflate capped at 4 KB, strict CBOR/COSE parsing (✅ tested both sides) |
| Privacy of the QR | Payload has no owner name, phone, email, address, location or photo (✅ tested); pet photo fetched online only for active certificates |
| WebAssembly needed by the QR reader | `'wasm-unsafe-eval'` (WebAssembly only; JavaScript `eval` stays blocked) is allowed **only** on `/[locale]/verify`; all other pages keep the stricter policy |

## "This pet bit someone" check

| Threat | Control (status) |
|---|---|
| Fake or malicious bite reports (to harass an owner) | No public listing of reports anywhere; 3 reports per client per hour and 5 per pet per day; a second report of the same pet and day joins the same observation and is flagged "possible duplicate"; the owner can dispute (clinic sees the flag; observation continues); no reporter details reach the owner unless the reporter chose to share them (✅ tested). Not built: staff moderation queue (disputes are flagged on the clinic dashboard instead) |
| Harassment of owners / doxxing through bite mode | Bite mode, reporter and doctor pages show the pet, clinic and records only — never the owner's name, phone, email, address or location (✅ API + browser tests) |
| Reporter's contact exposed | Stored only with consent to updates, sealed with AES-GCM under the master key (reference as associated data); the clinic view never shows it; the owner sees it only with the reporter's separate consent (✅ tested) |
| Share links leaking | 256-bit random tokens, only SHA-256 hashes stored; the reporter link expires 60 days after the bite, doctor links after 30 days; the reporter can turn all doctor links off; revoked or expired links return the same 404 with no data; every view is logged; pages are `noindex` with `Referrer-Policy: no-referrer` (✅ tested). Residual: anyone holding a live link can read it — the page says "Keep this link private" |
| Missed updates read as "fine" | A day without an update is "No update" everywhere; the period ends as "completed_with_gaps" and is flagged for the vet (✅ tested) |
| Wording that suggests skipping care | First aid first on every bite page; "See a doctor today, whatever this pet's vaccination status"; forbidden words ("safe", "rabies-free", "no treatment needed") checked automatically in API tests and browser tests across bite pages and languages (✅) |
| Rate-limit bypass via a spoofed client address | The client address is set by our own gateway from the proxy header (browser values are overwritten); only its hash is stored. Residual: many IPs can still send reports; the per-pet daily limit caps the impact |

