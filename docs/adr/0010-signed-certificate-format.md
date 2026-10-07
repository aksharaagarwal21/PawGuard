# ADR 0010 — Signed vaccination certificate format

Date: 2026-10-07 · Status: accepted

## Decision

A verified vaccination becomes a **COSE_Sign1** (RFC 9052) message with a **CBOR** (RFC 8949) payload, signed with
**EdDSA / Ed25519** (RFC 8037 algorithm `-8`), **zlib**-compressed and **Base45**-encoded (RFC 9285) behind the
prefix `PG1:`. This is the structure of the EU Digital COVID Certificate (`HC1:`), which was built to fit printed QR
codes and to be verified offline by anyone holding a trust list.

```
PG1: + Base45( zlib( COSE_Sign1 = Tag18[ protected{1: -8, 4: kid}, {}, payload, signature ] ) )
```

The signature covers `Sig_structure = ["Signature1", protected, h'', payload]` (RFC 9052 §4.4), so the key id and
the algorithm are signed too.

### Payload (integer keys keep the QR small; version 1)

| Key | Field | Notes |
|---|---|---|
| 1 | version | `1` |
| 2 | credential id | random UUID, 16 bytes |
| 3 | pet | map: 1 public reference (`PG-XXXX-XXXX`, random, not sequential), 2 name, 3 species, 4 sex, 5 short coat description |
| 4 | vaccination | map: 1 product name, 2 batch/lot (if recorded), 3 date given (`YYYY-MM-DD`, date only), 4 next due (`YYYY-MM-DD` or absent), 5 next-due source (`vet` / `template`) |
| 5 | clinic | map: 1 organisation id (16 bytes), 2 name |
| 6 | vet name | the person who verified or recorded it |
| 7 | issued at | Unix seconds |

Never included: owner name, phone, email, address, location, photos, notes. The key id (`kid`, 8 random bytes) is in
the protected header.

### Lists

* **Trust list** (`PG-TL1`): COSE_Sign1 by the platform **root key**; payload `{1: version, 2: issued_at,
  3: [ {1: kid, 2: org id, 3: clinic name, 4: Ed25519 public key, 5: valid_from, 6: valid_to | null, 7: status,
  8: is_demo} ], 4: stale_after_days}`. Served at `GET /api/v1/public/trust-list`.
* **Revocation list** (`PG-RL1`): COSE_Sign1 by the root key; payload `{1: version, 2: issued_at,
  3: [credential id (16 bytes)]}`. Served at `GET /api/v1/public/revocations`.

Both are signed when requested from the current database state, so a revocation committed in a transaction is in the
next list served (the version number is bumped in the same transaction by a trigger).

### Verification (in the browser, offline-capable)

1. Strip `PG1:`, Base45-decode, inflate with the browser's `DecompressionStream` (output capped at 4 KB), CBOR-decode
   strictly (tag 18 required, sizes capped).
2. Verify the cached trust list's signature with the **root public key built into the app**, then look up the `kid`.
3. Verify the certificate signature over the Sig_structure with that clinic key.
4. The key must have been valid at the issue time (`valid_from ≤ iat ≤ valid_to`); revoked keys are untrusted.
5. Check the cached revocation list.

## Libraries (checked on the official registries, 2026-10-07; pinned)

| Purpose | Server (Python) | Browser |
|---|---|---|
| Ed25519 | `cryptography` 50.0.2 (PyCA) | `@noble/curves` 2.4.0 (audited, no dependencies besides `@noble/hashes`) |
| CBOR | `cbor2` 6.1.5 | `cborg` 6.1.3 |
| Base45 | `base45` 0.4.4 | own 30-line decoder (`apps/web/src/lib/verify/base45.ts`) — the npm `base45` 2.0.1 needs Node's `Buffer` and accepts invalid input |
| zlib | standard library | `DecompressionStream("deflate")` (built into browsers) |
| QR | `segno` (already used) | `BarcodeDetector`, else `barcode-detector` 3.2.2 (ZXing WebAssembly, served from our own origin) |

No cryptographic primitive is written here. The COSE_Sign1 envelope is assembled with the CBOR libraries because the
Python COSE library (`pycose` 1.1.0) has had no release since December 2023 and there is no maintained browser COSE
library; `pycose` is used **only in tests** as an independent implementation that must verify our output.
Base45 is a text encoding, not cryptography: the Python package is old but implements a fixed RFC, and the browser decoder is checked against the RFC 9285 examples (`verify.test.ts`). Note: `cborg` 6 tag decoders must call the supplied `decode()`; `cbor2` 6 returns tuples and read-only maps inside tags (both handled).

## Measured size (7 Oct 2026, Bruno's rabies certificate)

433 characters (`PG1:` + Base45), 282 bytes of COSE; QR in alphanumeric mode: **version 13 (69 × 69 modules) at error-correction M**, version 11 at L, version 16 at Q. Printed at 3.5 cm or more it scans reliably with phone cameras; the PDF card prints it at 46 mm.

## Why not JWS

A compact JWS (EdDSA) with a JSON payload is about 40–60 % longer once Base64url-encoded, and Base64url is not in the
QR alphanumeric set, so the QR would be in byte mode and noticeably denser. COSE + Base45 keeps the QR in
alphanumeric mode.

## What a valid signature means (shown in the UI)

It proves that a clinic in the PawGuard trust list issued this record and that it was not changed. It does **not**
prove the pet is healthy or that the animal in front of you is the one on the certificate.
