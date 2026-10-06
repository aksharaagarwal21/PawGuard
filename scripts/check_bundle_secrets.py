"""Fail if server secrets or connection strings appear in the browser-delivered build output.

Scans apps/web/.next/static (everything shipped to browsers) for: the configured Supabase secret key,
database role passwords, publishable key (kept server-side by design), JWT-looking service keys, and
connection strings.
"""

import os
import re
import sys
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "apps" / "web" / ".next" / "static"


def main() -> int:
    if not STATIC.is_dir():
        print("apps/web/.next/static not found — build the web app first")
        return 2
    env = {**dotenv_values(ROOT / ".env"), **os.environ}
    literals = {k: v for k, v in env.items() if v and len(v) >= 12 and k in {
        "PAWGUARD_SUPABASE_SECRET_KEY", "PAWGUARD_DB_API_PASSWORD", "PAWGUARD_DB_WORKER_PASSWORD",
        "PAWGUARD_SUPABASE_PUBLISHABLE_KEY", "PAWGUARD_DATABASE_URL", "PAWGUARD_MIGRATE_DATABASE_URL"}}
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
    print(f"scanned {len(files)} files in {STATIC.relative_to(ROOT)}")
    for p in problems:
        print("  LEAK:", p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
