"""Alembic environment. Runs as the owner role from PAWGUARD_MIGRATE_DATABASE_URL."""

import os

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import create_engine, pool, text

from pawguard_api.settings import find_env_file, get_settings

# Role passwords used by migration 0001 are read from the environment; load the local .env if present.
_env_file = find_env_file()
if _env_file:
    load_dotenv(_env_file, override=False)


def _url() -> str:
    url = os.environ.get("PAWGUARD_MIGRATE_DATABASE_URL") or get_settings().migrate_database_url
    if not url:
        raise RuntimeError("PAWGUARD_MIGRATE_DATABASE_URL is required to run migrations")
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url.removeprefix("postgresql://")
    return url


def run_migrations_online() -> None:
    engine = create_engine(_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        connection.execute(text("set search_path = app, extensions, public"))
        connection.commit()
        context.configure(connection=connection, target_metadata=None, transaction_per_migration=True,
                          version_table_schema="public")
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    raise RuntimeError("Offline SQL generation is not supported; review migrations against a database.")
run_migrations_online()
