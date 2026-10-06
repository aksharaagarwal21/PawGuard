"""WhatsApp delivery receipts from Meta's webhook.

Meta reports each message's status (sent, delivered, read, failed) to the webhook. The API (unauthenticated webhook,
signature-checked) records a failure against the matching delivery through one narrow security-definer function;
it cannot read or change anything else.

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-07
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
    create or replace function app.record_whatsapp_status(p_message_id text, p_status text, p_error text)
    returns integer language plpgsql volatile security definer set search_path = '' as $$
    declare n integer;
    begin
      if p_status = 'failed' then
        update app.notification_deliveries set state = 'failed', last_error = left(coalesce(p_error, 'failed'), 300)
         where channel = 'whatsapp' and provider_message_id = p_message_id and state = 'sent';
      else
        update app.notification_deliveries set last_error = null
         where channel = 'whatsapp' and provider_message_id = p_message_id and state = 'sent';
      end if;
      get diagnostics n = row_count;
      return n;
    end $$;
    revoke all on function app.record_whatsapp_status(text, text, text) from public;
    grant execute on function app.record_whatsapp_status(text, text, text) to pawguard_api;
    """)


def downgrade() -> None:
    op.execute("drop function if exists app.record_whatsapp_status(text, text, text);")
