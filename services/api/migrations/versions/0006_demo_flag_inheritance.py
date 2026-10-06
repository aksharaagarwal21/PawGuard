"""Records created inside a demo organisation are always flagged is_demo.

Demo isolation must not depend on every code path remembering to set the flag.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-06
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
    create or replace function app.inherit_demo_flag() returns trigger
    language plpgsql security definer set search_path = '' as $$
    begin
      if not new.is_demo and exists (select 1 from app.organisations o where o.id = new.org_id and o.is_demo) then
        new.is_demo := true;
      end if;
      return new;
    end $$;
    revoke all on function app.inherit_demo_flag() from public;

    do $$
    declare t text;
    begin
      for t in select c.table_name from information_schema.columns c
               join information_schema.columns o on o.table_schema = c.table_schema and o.table_name = c.table_name
                 and o.column_name = 'org_id'
               join information_schema.tables tb on tb.table_schema = c.table_schema and tb.table_name = c.table_name
                 and tb.table_type = 'BASE TABLE'
               where c.table_schema = 'app' and c.column_name = 'is_demo'
      loop
        execute format('create trigger %I before insert on app.%I for each row execute function app.inherit_demo_flag()',
                       t || '_demo_flag', t);
        -- Backfill mutable tables only; append-only review rows already copy the flag from their event.
        if t <> 'vaccination_reviews' then
          execute format('update app.%I x set is_demo = true from app.organisations o where o.id = x.org_id '
                         'and o.is_demo and not x.is_demo', t);
        end if;
      end loop;
    end $$;
    """)


def downgrade() -> None:
    op.execute("""
    do $$
    declare r record;
    begin
      for r in select event_object_table as t, trigger_name as n from information_schema.triggers
               where trigger_schema = 'app' and trigger_name like '%_demo_flag'
      loop
        execute format('drop trigger %I on app.%I', r.n, r.t);
      end loop;
    end $$;
    drop function if exists app.inherit_demo_flag();
    """)
