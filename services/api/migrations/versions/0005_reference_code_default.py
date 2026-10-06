"""Generate animal reference codes in the database by default.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-06
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("alter table app.animals alter column reference_code set default app.new_reference_code()")


def downgrade() -> None:
    op.execute("alter table app.animals alter column reference_code drop default")
