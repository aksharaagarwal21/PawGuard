"""Dataset lineage, annotation and operational import jobs.

- dataset_versions / dataset_samples / annotation_events: what data a model saw, under which rights, how it was
  cleaned and split. org_id NULL = a global research dataset maintained by operators through the CLI; otherwise the
  dataset belongs to (and is visible only to) one organisation.
- import_jobs: partner CSV imports. The raw file is kept immutable (sha256 + bytes, restricted); the validation
  report is produced by a dry run; nothing touches domain tables until a person approves.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-06
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
    create table app.dataset_versions (
      id uuid primary key default extensions.gen_random_uuid(),
      org_id uuid references app.organisations(id),
      name text not null,
      version text not null,
      purpose text not null check (purpose in ('research_benchmark','partner_pilot','evaluation_frozen','synthetic_fixture')),
      source_reference text not null,
      rights_summary text not null,
      consent_scope text not null check (consent_scope in ('research_only','operational','operational_and_training',
                                                            'synthetic')),
      modality text not null default 'unknown' check (modality in ('face','full_body','mixed','unknown')),
      manifest_path text not null,
      manifest_sha256 text not null check (manifest_sha256 ~ '^[0-9a-f]{64}$'),
      split_manifest_path text,
      split_sha256 text check (split_sha256 is null or split_sha256 ~ '^[0-9a-f]{64}$'),
      counts jsonb not null default '{}'::jsonb,
      status text not null default 'draft' check (status in ('draft','frozen','retired')),
      notes text,
      created_at timestamptz not null default now(),
      frozen_at timestamptz,
      unique (name, version),
      check (status <> 'frozen' or (split_sha256 is not null and frozen_at is not null))
    );

    create table app.dataset_samples (
      id uuid primary key default extensions.gen_random_uuid(),
      dataset_version_id uuid not null references app.dataset_versions(id),
      sample_key text not null,                -- path within the dataset or media reference
      media_id uuid,                           -- for partner photos stored in PawGuard media
      source_sha256 text not null check (source_sha256 ~ '^[0-9a-f]{64}$'),
      phash text,
      identity_label text,                     -- as asserted by the source (may be wrong)
      label_confidence text not null default 'asserted'
        check (label_confidence in ('asserted','reviewed','disputed','rejected')),
      session_group text,
      site_group text,
      captured_on date,
      modality text not null default 'unknown' check (modality in ('face','full_body','unknown')),
      quality_flags text[] not null default '{}',
      dup_group text,
      split text check (split in ('train','val','test','excluded')),
      split_role text check (split_role in ('gallery','query','unknown_query','training')),
      exclusion_reason text,
      adjudication_state text not null default 'none' check (adjudication_state in ('none','pending','agreed',
                                                                                 'adjudicated')),
      transform_version text,
      unique (dataset_version_id, sample_key),
      check ((split = 'excluded') = (exclusion_reason is not null))
    );
    create index dataset_samples_identity on app.dataset_samples (dataset_version_id, identity_label);

    create table app.annotation_events (
      id uuid primary key default extensions.gen_random_uuid(),
      dataset_sample_id uuid not null references app.dataset_samples(id),
      annotator text not null,                 -- pseudonymous annotator id (no personal data)
      task text not null check (task in ('identity_same','identity_group','subject_box','usable_for_id')),
      outcome text not null check (outcome in ('agree','disagree','cannot_tell','not_dog','multiple_dogs','usable',
                                               'not_usable')),
      proposed_label text,
      proposed_box jsonb,
      adjudicator text,
      adjudicated_outcome text,
      note text check (char_length(note) <= 1000),
      created_at timestamptz not null default now()
    );
    create index annotation_events_sample on app.annotation_events (dataset_sample_id);

    alter table app.dataset_versions enable row level security;
    alter table app.dataset_versions force row level security;
    create policy dataset_versions_read on app.dataset_versions for select to pawguard_api, pawguard_worker
      using (org_id is null or org_id = (select app.current_org_id()));
    alter table app.dataset_samples enable row level security;
    alter table app.dataset_samples force row level security;
    create policy dataset_samples_read on app.dataset_samples for select to pawguard_api, pawguard_worker
      using (exists (select 1 from app.dataset_versions d where d.id = dataset_version_id
                     and (d.org_id is null or d.org_id = (select app.current_org_id()))));
    alter table app.annotation_events enable row level security;
    alter table app.annotation_events force row level security;
    grant select on app.dataset_versions, app.dataset_samples to pawguard_api, pawguard_worker;

    create table app.import_jobs (
      id uuid primary key default extensions.gen_random_uuid(),
      org_id uuid not null references app.organisations(id),
      import_type text not null check (import_type in ('animals_csv','vaccinations_csv')),
      source_label text not null check (char_length(source_label) between 3 and 200),
      raw_filename text,
      raw_sha256 text not null check (raw_sha256 ~ '^[0-9a-f]{64}$'),
      raw_bytes bytea not null check (octet_length(raw_bytes) <= 2097152),
      mapping_version text not null,
      row_count integer not null default 0,
      valid_count integer not null default 0,
      rejected_count integer not null default 0,
      warning_count integer not null default 0,
      report jsonb not null default '{}'::jsonb,
      state text not null default 'validated' check (state in ('validated','applied','rolled_back','discarded')),
      created_record_ids jsonb not null default '{}'::jsonb,
      created_by uuid not null,
      applied_by uuid,
      applied_at timestamptz,
      rolled_back_by uuid,
      rolled_back_at timestamptz,
      rollback_reason text,
      is_demo boolean not null default false,
      created_at timestamptz not null default now(),
      updated_at timestamptz not null default now(),
      row_version integer not null default 1,
      unique (org_id, raw_sha256, import_type)
    );
    create trigger import_jobs_touch before update on app.import_jobs for each row execute function app.touch_row();
    create trigger import_jobs_demo_flag before insert on app.import_jobs
      for each row execute function app.inherit_demo_flag();
    alter table app.import_jobs enable row level security;
    alter table app.import_jobs force row level security;
    create policy import_jobs_tenant on app.import_jobs for all
      using (org_id = (select app.current_org_id()) and (select app.has_capability('data.import')))
      with check (org_id = (select app.current_org_id()) and (select app.has_capability('data.import')));
    grant select, insert, update on app.import_jobs to pawguard_api;
    """)


def downgrade() -> None:
    op.execute("""drop table if exists app.import_jobs, app.annotation_events, app.dataset_samples,
                  app.dataset_versions cascade""")
