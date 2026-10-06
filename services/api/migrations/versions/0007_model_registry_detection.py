"""Model registry and detection results.

`model_versions` is global (not tenant data): which artefact, checksum, licence, preprocessing contract and
thresholds a pipeline uses, and whether it is staged, active or retired. Writes happen only through the
administrative CLI (owner credentials) after evaluation; runtime roles can only read it.
`detection_results` are tenant data (one per media file and model version).

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-06
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
    create table app.model_versions (
      id uuid primary key default extensions.gen_random_uuid(),
      task text not null check (task in ('dog_detection','identity_embedding')),
      name text not null,
      family text not null,
      version_label text not null,
      artifact_path text not null,
      sha256 text not null check (sha256 ~ '^[0-9a-f]{64}$'),
      size_bytes bigint not null check (size_bytes > 0),
      licence text not null,
      source_url text not null,
      preprocessing jsonb not null,
      output_spec jsonb not null default '{}'::jsonb,
      thresholds jsonb not null default '{}'::jsonb,
      embedding_dim integer check (embedding_dim is null or embedding_dim > 0),
      evaluation_report text,
      state text not null default 'staged' check (state in ('staged','active','retired')),
      notes text,
      registered_at timestamptz not null default now(),
      activated_at timestamptz,
      retired_at timestamptz,
      unique (task, name, version_label),
      check (state <> 'active' or evaluation_report is not null)
    );
    create unique index model_versions_one_active on app.model_versions (task) where state = 'active';
    alter table app.model_versions enable row level security;
    alter table app.model_versions force row level security;
    create policy model_versions_read on app.model_versions for select to pawguard_api, pawguard_worker using (true);
    grant select on app.model_versions to pawguard_api, pawguard_worker;

    create table app.detection_results (
      id uuid primary key default extensions.gen_random_uuid(),
      org_id uuid not null references app.organisations(id),
      media_id uuid not null,
      model_version_id uuid not null references app.model_versions(id),
      pipeline_version text not null,
      status text not null check (status in ('completed','no_animal','failed')),
      detections jsonb not null default '[]'::jsonb,
      dog_count integer not null default 0 check (dog_count >= 0),
      person_count integer not null default 0 check (person_count >= 0),
      coordinate_space text not null default 'oriented_original',
      image_width integer,
      image_height integer,
      inference_ms numeric,
      is_demo boolean not null default false,
      created_at timestamptz not null default now(),
      unique (media_id, model_version_id),
      foreign key (media_id, org_id) references app.media_assets(id, org_id)
    );
    alter table app.detection_results enable row level security;
    alter table app.detection_results force row level security;
    create policy detection_results_tenant on app.detection_results for all
      using (org_id = (select app.current_org_id())) with check (org_id = (select app.current_org_id()));
    create trigger detection_results_demo_flag before insert on app.detection_results
      for each row execute function app.inherit_demo_flag();
    grant select on app.detection_results to pawguard_api;
    grant select, insert, update on app.detection_results to pawguard_worker;
    grant select, insert, update on app.image_quality_results to pawguard_worker;
    """)


def downgrade() -> None:
    op.execute("drop table if exists app.detection_results; drop table if exists app.model_versions;")
