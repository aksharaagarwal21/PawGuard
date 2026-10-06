"""Derived columns (animals.last_observed_at) must not bump row_version.

Otherwise recording a sighting would make a concurrent profile edit fail with a spurious conflict.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-05
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
    create or replace function app.touch_animal() returns trigger language plpgsql set search_path = '' as $$
    begin
      new.updated_at := now();
      if (to_jsonb(new) - 'last_observed_at' - 'updated_at' - 'row_version')
         is distinct from (to_jsonb(old) - 'last_observed_at' - 'updated_at' - 'row_version') then
        new.row_version := old.row_version + 1;
      else
        new.row_version := old.row_version;
      end if;
      return new;
    end $$;
    drop trigger animals_touch on app.animals;
    create trigger animals_touch before update on app.animals for each row execute function app.touch_animal();
    """)


def downgrade() -> None:
    op.execute("""
    drop trigger animals_touch on app.animals;
    create trigger animals_touch before update on app.animals for each row execute function app.touch_row();
    drop function app.touch_animal();
    """)
