"""Defence in depth: the API role may only edit an organisation's descriptive fields.

`is_demo` decides whether the research-preview identity model is offered, and `activation_state` gates access;
neither may be changed by the runtime API role (only operators via the CLI with owner credentials). Previously the
API role held table-wide UPDATE on `organisations`, although no endpoint used it.

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-06
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
    revoke update on app.organisations from pawguard_api;
    grant update (name, contact_email, timezone, region_code, updated_at, row_version) on app.organisations
      to pawguard_api;
    """)


def downgrade() -> None:
    op.execute("grant update on app.organisations to pawguard_api")
