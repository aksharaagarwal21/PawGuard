"""Drafts read from vaccination certificates by OCR.

Only the parsed fields are stored (dates, matched vaccine, batch, confidence, warnings) — never the certificate's full
text, which contains people's names and addresses. A draft pre-fills the owner's form and is shown to the vet beside
the image; it never verifies anything.

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-07
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
    create table app.certificate_drafts (
      media_id uuid primary key,
      org_id uuid not null references app.organisations(id),
      engine text not null check (engine in ('tesseract','gemini')),
      languages text[] not null default '{}',
      administered_on date,
      next_due_on date,
      product_id uuid,
      product_text text check (char_length(product_text) <= 200),
      lot_text text check (char_length(lot_text) <= 40),
      confidence real check (confidence is null or (confidence >= 0 and confidence <= 1)),
      warnings text[] not null default '{}',
      created_by uuid,
      created_at timestamptz not null default now(),
      is_demo boolean not null default false
    );
    create trigger certificate_drafts_demo_flag before insert on app.certificate_drafts
      for each row execute function app.inherit_demo_flag();
    alter table app.certificate_drafts enable row level security;
    alter table app.certificate_drafts force row level security;
    create policy certificate_drafts_tenant on app.certificate_drafts for all
      using (org_id = (select app.current_org_id())) with check (org_id = (select app.current_org_id()));
    grant select, insert, update on app.certificate_drafts to pawguard_api;
    """)


def downgrade() -> None:
    op.execute("drop table if exists app.certificate_drafts;")
