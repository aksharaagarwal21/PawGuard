# ADR 0011 — Signing keys: clinic keys, root key, rotation and revocation

Date: 2026-10-07 · Status: accepted

## Clinic keys

* One **active Ed25519 key per active organisation** (clinics and programmes whose vets verify records). Created
  when an organisation is activated or seeded, on first use if missing, and by `pawguard keys backfill`.
* Table `app.clinic_signing_keys`: `kid` (8 random bytes, hex), organisation, public key (32 bytes), encrypted
  private key, status `active | retired | revoked`, created/retired/revoked timestamps and reason.
* **Encryption at rest:** the raw private key is sealed with **AES-256-GCM** (`cryptography`'s `AESGCM`) under a
  32-byte **master key**, with the `kid` as associated data (a sealed key cannot be swapped to another row). The master
  key comes from `PAWGUARD_SIGNING_MASTER_KEY` (base64) or the file named by `PAWGUARD_SIGNING_MASTER_KEY_FILE`
  (production: a secrets manager mounting the file). The database never holds the master key.
* The table has row-level security with **no policies** for the API or worker roles. The API reaches it only through
  two security-definer functions: one returns the sealed active key **for the caller's own organisation** inside the
  vet's transaction; the other lists public keys for the trust list. Private keys are decrypted in memory, used, and
  never logged, returned by any endpoint or sent to the browser (automated scan in the tests).
* **Rotation** (`pawguard keys rotate --org <id>`): the active key becomes `retired` with `valid_to = now`, a new key
  becomes active. Retired keys stay in the trust list so certificates they signed earlier still verify.
* **Revocation** (`pawguard keys revoke --kid <kid> --reason "..."`): status `revoked`; every certificate signed with
  it then shows "issued by an untrusted clinic". Both commands write audit events.

## Root key

* One Ed25519 **platform root key** signs the trust list and the revocation list. Its public key is compiled into
  the web app (`apps/web/src/lib/verify/root-key.ts`), so the browser can verify the lists offline.
* Generated with `pawguard keys root-init`, written as a **passphrase-encrypted PKCS#8 PEM file** (scrypt +
  AES-256-CBC via `cryptography`'s `BestAvailableEncryption`) outside the repository (`secrets/`, git-ignored). The
  passphrase comes from `PAWGUARD_ROOT_KEY_PASSPHRASE` or `PAWGUARD_ROOT_KEY_PASSPHRASE_FILE`. **It is never stored in
  the database.**
* **Hackathon deployment:** the API server reads the root key file to sign lists on demand. **Production plan:** keep
  the root key offline (hardware token or KMS with signing-only access), and have it sign a short-lived *list-signing
  key* entry in the trust list; the online server then holds only that key. This is documented, not built.
* **Root rotation:** generate a new root, ship an app build that trusts both old and new root public keys, switch
  signing, then drop the old key from the next build. A compromised root requires a new app build (published root
  keys cannot be revoked remotely) — the main residual risk, listed in THREAT_MODEL.

## Consequences

* A stolen database alone cannot sign (private keys are sealed; the master key is outside the database).
* A stolen master key plus database can sign as any clinic until the keys are revoked and rotated.
* Verification needs no server, so it keeps working offline; freshness of the lists is shown to the user.
