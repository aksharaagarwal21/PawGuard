# Operations: signing keys and verification lists

Signed vaccination certificates (ADR 0010) and key management (ADR 0011). All commands run from `services/api`
with `uv run pawguard-admin …`. No command prints a secret.

## First-time setup (per environment)

```bash
uv run pawguard-admin keys init            # writes secrets/signing-master.key, secrets/root-key.pem (encrypted),
                                           # secrets/root-key.passphrase — and prints only paths + the root PUBLIC key
```
1. Add the three printed `PAWGUARD_…_FILE=` lines to `.env` (or mount the files from a secrets manager and point the
   variables at them; `PAWGUARD_SIGNING_MASTER_KEY` / `PAWGUARD_ROOT_KEY_PASSPHRASE` may be set directly instead).
2. Put the printed root public key into `apps/web/src/lib/verify/root-key.ts` (`ROOT_PUBLIC_KEYS_B64`) and rebuild the
   web app — the verifier trusts only the keys compiled into it.
3. `uv run pawguard-admin keys backfill` — gives every active organisation a key and signs verified records that have
   no certificate yet. New clinics get a key automatically on their first verification.
4. Back up `secrets/` offline (encrypted). Losing the master key means every clinic key must be replaced (rotate all)
   and certificates re-issued; losing the root key means a new app build with a new root.

## Routine

| Task | Command | Effect |
|---|---|---|
| List keys (public info) | `keys list` | kid, status, valid-from, organisation |
| Rotate a clinic key | `keys rotate --org <org-id> [--reissue]` | Active key → retired (still verifies what it signed); new key active; `--reissue` re-signs that clinic's active certificates. Audited (`signing_key.rotated`) |
| Revoke a compromised key | `keys revoke --kid <kid> --reason "…"` | Key → revoked: its certificates now show "issued by an untrusted clinic". Then `keys rotate --org <org-id> --reissue`. Audited |
| Re-issue one certificate | `POST /api/v1/vaccination-events/{id}/certificate` (vet) | Old certificate revoked (pointing at the new one), new one issued |
| Correct a verified record | `POST /api/v1/vaccination-events/{id}/correction` (vet) | New verified record supersedes the old; old certificate revoked, new issued — one transaction |

The trust list (`GET /api/v1/public/trust-list`) and the revocation list (`GET /api/v1/public/revocations`) are signed
on request by the root key from the current database state; their version numbers change in the same transaction as
the key or revocation change. Verifiers refresh them whenever they are online and warn after
`PAWGUARD_VERIFY_STALE_AFTER_DAYS` (default 7) without an update.

## Master key and root key handling

* **Master key** (32 bytes): seals each clinic private key with AES-256-GCM (key id as associated data). Never in the
  database, logs, API responses or the web bundle (`scripts/check_bundle_secrets.py` checks the bundle; API tests check
  responses and logs).
* **Root key**: passphrase-encrypted PKCS#8 file, outside the database and the repository. In this hackathon setup the
  API server reads it to sign the two lists. **Production:** keep the root offline (hardware token or KMS signing-only
  access) and let it sign a short-lived list-signing key that the server uses instead (not built).
* **Root rotation:** add the new public key to `root-key.ts` next to the old one, ship the app, switch the server to
  the new root file, then remove the old public key in a later build.
* SQL error messages never include parameters (`hide_parameters=True`), so sealed keys cannot leak through errors.
