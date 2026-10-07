"""Signed certificate encoding (ADR 0010): COSE_Sign1 (RFC 9052) + EdDSA/Ed25519, zlib, Base45, prefix ``PG1:``.

Cryptographic primitives come from PyCA ``cryptography``; this module only assembles the RFC 9052 envelope with
``cbor2`` and applies the same size limits as the browser verifier. Clinic private keys are sealed with AES-256-GCM
under the master key (associated data = the key id).
"""

import base64
import os
import zlib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import base45
import cbor2
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from pawguard_api.settings import Settings

PREFIX = "PG1:"
ALG_EDDSA = -8
COSE_SIGN1_TAG = 18
MAX_QR_TEXT = 2000  # characters; a real certificate is ~400
MAX_INFLATED = 4096  # bytes after decompression (zip-bomb guard)


class SigningUnavailable(RuntimeError):
    """The master key or root key is not configured on this server."""


class InvalidCertificate(ValueError):
    """Not a readable PawGuard certificate (wrong prefix, bad encoding, too large, malformed CBOR/COSE)."""


# ---- COSE_Sign1 --------------------------------------------------------------------------------------------------

def _sig_structure(protected: bytes, payload: bytes) -> bytes:
    return cbor2.dumps(["Signature1", protected, b"", payload])


def sign1(payload: dict[int, Any], kid: bytes, key: Ed25519PrivateKey) -> bytes:
    """COSE_Sign1 with the algorithm and key id in the (signed) protected header."""
    protected = cbor2.dumps({1: ALG_EDDSA, 4: kid})
    body = cbor2.dumps(payload)
    signature = key.sign(_sig_structure(protected, body))
    return cbor2.dumps(cbor2.CBORTag(COSE_SIGN1_TAG, [protected, {}, body, signature]))


@dataclass(frozen=True)
class Sign1:
    kid: bytes
    payload: Any
    protected: bytes
    body: bytes
    signature: bytes


def parse_sign1(data: bytes) -> Sign1:
    try:
        obj = cbor2.loads(data)
    except Exception as exc:  # cbor2 raises several types for malformed input
        raise InvalidCertificate("not CBOR") from exc
    if not (isinstance(obj, cbor2.CBORTag) and obj.tag == COSE_SIGN1_TAG and isinstance(obj.value, (list, tuple))
            and len(obj.value) == 4):
        raise InvalidCertificate("not COSE_Sign1")
    protected, _unprotected, body, signature = obj.value
    if not (isinstance(protected, bytes) and isinstance(body, bytes) and isinstance(signature, bytes)):
        raise InvalidCertificate("bad COSE_Sign1 fields")
    try:
        header = cbor2.loads(protected)
        payload = cbor2.loads(body)
    except Exception as exc:
        raise InvalidCertificate("bad header or payload") from exc
    if not isinstance(header, dict) or header.get(1) != ALG_EDDSA or not isinstance(header.get(4), bytes):
        raise InvalidCertificate("unsupported algorithm or missing key id")
    return Sign1(header[4], payload, protected, body, signature)


def verify_sign1(msg: Sign1, public_key: bytes) -> bool:
    try:
        Ed25519PublicKey.from_public_bytes(public_key).verify(msg.signature, _sig_structure(msg.protected, msg.body))
        return True
    except (InvalidSignature, ValueError):
        return False


# ---- QR text -----------------------------------------------------------------------------------------------------

def to_qr_text(cose: bytes) -> str:
    return PREFIX + base45.b45encode(zlib.compress(cose, 9)).decode("ascii")


def from_qr_text(text: str) -> bytes:
    text = text.strip()
    if len(text) > MAX_QR_TEXT or not text.startswith(PREFIX):
        raise InvalidCertificate("not a PawGuard certificate")
    try:
        compressed = base45.b45decode(text[len(PREFIX):])
        d = zlib.decompressobj()
        out = d.decompress(compressed, MAX_INFLATED + 1)
    except Exception as exc:
        raise InvalidCertificate("bad encoding") from exc
    if len(out) > MAX_INFLATED or d.unconsumed_tail:
        raise InvalidCertificate("too large")
    return out


# ---- keys --------------------------------------------------------------------------------------------------------

def new_key() -> tuple[bytes, bytes]:
    """(raw private key, raw public key), 32 bytes each."""
    key = Ed25519PrivateKey.generate()
    raw = key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                            serialization.NoEncryption())
    return raw, key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


def _read_secret(value: str | None, file: str | None) -> str | None:
    if value:
        return value.strip()
    if file and Path(file).is_file():
        return Path(file).read_text(encoding="utf-8").strip()
    return None


def master_key(s: Settings) -> bytes:
    raw = _read_secret(s.signing_master_key, s.signing_master_key_file)
    if not raw:
        raise SigningUnavailable("Signing master key is not configured (PAWGUARD_SIGNING_MASTER_KEY[_FILE]).")
    key = base64.b64decode(raw)
    if len(key) != 32:
        raise SigningUnavailable("Signing master key must be 32 bytes (base64).")
    return key


def seal(private_raw: bytes, kid: str, s: Settings) -> bytes:
    nonce = os.urandom(12)
    return nonce + AESGCM(master_key(s)).encrypt(nonce, private_raw, kid.encode("ascii"))


def unseal_bytes(sealed: bytes, aad: str, s: Settings) -> bytes:
    """Open anything sealed with `seal` (clinic private keys; bite reporters' contact emails)."""
    return AESGCM(master_key(s)).decrypt(sealed[:12], sealed[12:], aad.encode("ascii"))


def unseal(sealed: bytes, kid: str, s: Settings) -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(unseal_bytes(sealed, kid, s))


@lru_cache(maxsize=4)
def _load_root(path: str, passphrase: str) -> Ed25519PrivateKey:
    key = serialization.load_pem_private_key(Path(path).read_bytes(), passphrase.encode("utf-8"))
    if not isinstance(key, Ed25519PrivateKey):
        raise SigningUnavailable("Root key file is not an Ed25519 key.")
    return key


def root_key(s: Settings) -> Ed25519PrivateKey:
    passphrase = _read_secret(s.root_key_passphrase, s.root_key_passphrase_file)
    if not (s.root_key_file and Path(s.root_key_file).is_file() and passphrase):
        raise SigningUnavailable("Root signing key is not configured (PAWGUARD_ROOT_KEY_FILE and passphrase).")
    return _load_root(s.root_key_file, passphrase)


def root_public_b64(s: Settings) -> str:
    pub = root_key(s).public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return base64.b64encode(pub).decode("ascii")


ROOT_KID = b"pg-root1"


def write_root_key(path: Path, passphrase: str) -> str:
    """Create the root key file (passphrase-encrypted PKCS#8). Returns the public key (base64). Refuses to overwrite."""
    if path.exists():
        raise FileExistsError(str(path))
    key = Ed25519PrivateKey.generate()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                       serialization.BestAvailableEncryption(passphrase.encode("utf-8"))))
    pub = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return base64.b64encode(pub).decode("ascii")
