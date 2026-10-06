"""Seed repeatability and migration round-trip on the test database."""

import os
import subprocess
import sys
import uuid
from pathlib import Path

from sqlalchemy import text

from pawguard_api.seed.runner import run_seed

API_DIR = Path(__file__).resolve().parents[1]
COUNTED = ["organisations", "memberships", "animals", "animal_observations", "animal_vaccination_events",
           "vaccination_reviews", "field_tasks", "animal_merge_operations", "sync_operations", "areas"]


class FakeAuth:
    """Stands in for Supabase Auth admin: stable fake user ids per email (no network)."""

    def ensure_user(self, email: str, password: str, *, display_name: str | None = None) -> uuid.UUID:
        return uuid.uuid5(uuid.NAMESPACE_URL, f"test-seed:{email}")


def _counts(c) -> dict[str, int]:  # type: ignore[no-untyped-def]
    return {t: c.execute(text(f"select count(*) from app.{t} where is_demo")).scalar_one()
            for t in COUNTED}


def test_seed_is_repeatable(owner_engine):
    with owner_engine.begin() as c:
        run_seed(c, FakeAuth())  # type: ignore[arg-type]
        first = _counts(c)
    with owner_engine.begin() as c:
        run_seed(c, FakeAuth())  # type: ignore[arg-type]
        second = _counts(c)
    assert first == second
    assert first["animals"] >= 40 and first["vaccination_reviews"] > 0 and first["sync_operations"] == 2
    with owner_engine.connect() as c:
        states = set(c.execute(text("select state from app.animal_vaccination_events where is_demo")).scalars())
    assert {"verified", "submitted", "needs_correction", "rejected"} <= states


def test_migrations_downgrade_and_upgrade_cleanly():
    env = dict(os.environ)
    run = lambda *args: subprocess.run([sys.executable, "-m", "alembic", *args], cwd=API_DIR, env=env,  # noqa: E731,S603
                                       capture_output=True, text=True)
    down = run("downgrade", "base")
    assert down.returncode == 0, down.stderr[-2000:]
    up = run("upgrade", "head")
    assert up.returncode == 0, up.stderr[-2000:]
    cur = run("current")
    assert "(head)" in cur.stdout
