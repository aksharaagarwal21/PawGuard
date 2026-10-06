"""Expose the applied migration revision to runtime roles for readiness checks.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-05
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
    create or replace function app.schema_version() returns text
    language sql stable security definer set search_path = '' as $$
      select version_num::text from public.alembic_version limit 1;
    $$;
    revoke all on function app.schema_version() from public;
    grant execute on function app.schema_version() to pawguard_api, pawguard_worker;
    """)


def downgrade() -> None:
    op.execute("drop function if exists app.schema_version()")
