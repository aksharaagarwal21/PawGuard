"""Fail if server secrets or connection strings appear in the browser-delivered build output.

Scans apps/web/.next/static (everything shipped to browsers) for: the configured Supabase secret key,
database role passwords, publishable key (kept server-side by design), JWT-looking service keys, connection
strings, and the certificate signing secrets (master key, root private key and passphrase, every clinic private
key — decrypted in memory only for the comparison, never printed).
"""

import os
import re
import sys
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "apps" / "web" / ".next" / "static"


def signing_secrets() -> dict[str, str]:
    """Encodings of the signing secrets to look for (ADR 0011). Skipped quietly when signing is not set up."""
    import base64

    out: dict[str, str] = {}
    try:
        from cryptography.hazmat.primitives import serialization
        from sqlalchemy import text

        from pawguard_api.cli import owner_conn
        from pawguard_api.integrations import cose
        from pawguard_api.settings import get_settings

        s = get_settings()
        raw_keys = {"root private key": cose.root_key(s).private_bytes(
            serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())}
        out["signing master key"] = base64.b64encode(cose.master_key(s)).decode()
        if s.root_key_passphrase_file:
            out["root key passphrase"] = Path(s.root_key_passphrase_file).read_text(encoding="utf-8").strip()
        with owner_conn() as c:
            for row in c.execute(text("select kid, private_key_sealed from app.clinic_signing_keys")):
                raw_keys[f"clinic key {row.kid}"] = cose.unseal(bytes(row.private_key_sealed), row.kid, s).private_bytes(
                    serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
        for name, raw in raw_keys.items():
            out[f"{name} (hex)"] = raw.hex()
            out[f"{name} (base64)"] = base64.b64encode(raw).decode()
            out[f"{name} (base64url)"] = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    except Exception as exc:  # optional check; report why it was skipped
        print(f"signing secrets not checked ({type(exc).__name__})")
    return out


def main() -> int:
    if not STATIC.is_dir():
        print("apps/web/.next/static not found — build the web app first")
        return 2
    env = {**dotenv_values(ROOT / ".env"), **os.environ}
    literals = {k: v for k, v in env.items() if v and len(v) >= 12 and k in {
        "PAWGUARD_SUPABASE_SECRET_KEY", "PAWGUARD_DB_API_PASSWORD", "PAWGUARD_DB_WORKER_PASSWORD",
        "PAWGUARD_SUPABASE_PUBLISHABLE_KEY", "PAWGUARD_DATABASE_URL", "PAWGUARD_MIGRATE_DATABASE_URL"}}
    literals.update(signing_secrets())
    patterns = [re.compile(p) for p in (r"sb_secret_[A-Za-z0-9_-]{10,}", r"postgres(ql)?://[^\s\"']+@",
                                         r"service_role", r"PAWGUARD_[A-Z_]+_(KEY|PASSWORD)")]
    problems = []
    files = [p for p in STATIC.rglob("*") if p.is_file() and p.suffix in {".js", ".css", ".html", ".json", ".map"}]
    for path in files:
        text = path.read_text(encoding="utf-8", errors="ignore")
        for name, value in literals.items():
            if value in text:
                problems.append(f"{path.relative_to(ROOT)}: contains value of {name}")
        for pat in patterns:
            if pat.search(text):
                problems.append(f"{path.relative_to(ROOT)}: matches {pat.pattern}")
    print(f"scanned {len(files)} files in {STATIC.relative_to(ROOT)} for {len(literals)} secret values")
    for p in problems:
        print("  LEAK:", p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
