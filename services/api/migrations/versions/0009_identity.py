"""Assisted identification plumbing: release gate, training runs, gallery embeddings, searches and decisions.

- `model_versions.release_gate`: an identity model can be *active* (offered to every organisation) only when its
  recorded release gate passed (ML_PLAN). `research_preview` lets a staged model run **in demo organisations
  only**, always labelled as research. `index_wanted` keeps embeddings for that model up to date, so a new model's
  collection can be built before switching and the previous one stays available for rollback.
- `training_runs`: lineage of every training/evaluation run (global, written by operator CLI).
- `animal_embeddings`: tenant gallery, one row per (photo, subject box, model version). Vectors from different
  model versions are never compared. Exact cosine search first (no approximate index until recall is measured).
  Only the worker reads or writes vectors; the API never returns them.
- `identity_searches` / `identity_decisions`: a search returns *possible matches*; a person decides. Decisions are
  append-only and record where the chosen animal ranked (correction feedback).

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-06
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
    alter table app.model_versions
      add column release_gate jsonb not null default '{}'::jsonb,
      add column research_preview boolean not null default false,
      add column index_wanted boolean not null default false,
      add constraint model_versions_identity_gate check (
        task <> 'identity_embedding' or state <> 'active' or coalesce((release_gate->>'passed')::boolean, false)),
      add constraint model_versions_preview_staged check (not research_preview or state = 'staged'),
      add constraint model_versions_identity_dim check (task <> 'identity_embedding' or embedding_dim = 384);
    create unique index model_versions_one_preview on app.model_versions (task) where research_preview;

    create table app.training_runs (
      id uuid primary key default extensions.gen_random_uuid(),
      task text not null check (task in ('dog_detection','identity_embedding')),
      run_label text not null unique,
      kind text not null check (kind in ('evaluation','training','export')),
      dataset_version_id uuid references app.dataset_versions(id),
      dataset_manifest_sha256 text,
      split_sha256 text,
      code_commit text,
      code_sha256 text,
      environment_lock_sha256 text,
      seed bigint,
      config jsonb not null default '{}'::jsonb,
      metrics jsonb not null default '{}'::jsonb,
      resources jsonb not null default '{}'::jsonb,
      artifacts jsonb not null default '{}'::jsonb,
      report_path text,
      decision text,
      model_version_id uuid references app.model_versions(id),
      created_at timestamptz not null default now()
    );
    alter table app.training_runs enable row level security;
    alter table app.training_runs force row level security;
    create policy training_runs_read on app.training_runs for select to pawguard_api using (true);
    grant select on app.training_runs to pawguard_api;

    create table app.animal_embeddings (
      id uuid primary key default extensions.gen_random_uuid(),
      org_id uuid not null references app.organisations(id),
      animal_id uuid not null,
      observation_media_id uuid not null,
      media_id uuid not null,
      crop_key text not null,            -- hash of the subject box used for the crop
      model_version_id uuid not null references app.model_versions(id),
      embedding extensions.vector(384) not null,
      normalised boolean not null default true,
      state text not null default 'active' check (state in ('active','excluded')),
      excluded_reason text,
      is_demo boolean not null default false,
      created_at timestamptz not null default now(),
      unique (media_id, crop_key, model_version_id),
      foreign key (animal_id, org_id) references app.animals(id, org_id),
      foreign key (media_id, org_id) references app.media_assets(id, org_id)
    );
    create index animal_embeddings_gallery on app.animal_embeddings (org_id, model_version_id) where state = 'active';
    create index animal_embeddings_animal on app.animal_embeddings (animal_id);
    alter table app.animal_embeddings enable row level security;
    alter table app.animal_embeddings force row level security;
    create policy animal_embeddings_tenant on app.animal_embeddings for all
      using (org_id = (select app.current_org_id())) with check (org_id = (select app.current_org_id()));
    create trigger animal_embeddings_demo_flag before insert on app.animal_embeddings
      for each row execute function app.inherit_demo_flag();
    grant select, insert, update on app.animal_embeddings to pawguard_worker;

    create table app.identity_searches (
      id uuid primary key default extensions.gen_random_uuid(),
      org_id uuid not null references app.organisations(id),
      media_id uuid not null,
      subject_bbox jsonb,
      model_version_id uuid references app.model_versions(id),
      mode text not null check (mode in ('assisted','research_preview','unavailable')),
      state text not null default 'pending' check (state in ('pending','completed','no_candidate','unavailable',
        'failed','insufficient_quality','stale_index','cancelled')),
      failure_code text,
      candidates jsonb not null default '[]'::jsonb,
      threshold numeric,
      gallery_animals integer,
      gallery_embeddings integer,
      index_coverage numeric,
      inference_ms numeric,
      search_ms numeric,
      requested_by uuid not null,
      is_demo boolean not null default false,
      created_at timestamptz not null default now(),
      completed_at timestamptz,
      row_version integer not null default 1,
      updated_at timestamptz not null default now(),
      unique (id, org_id),
      foreign key (media_id, org_id) references app.media_assets(id, org_id)
    );
    create index identity_searches_org_time on app.identity_searches (org_id, created_at desc);
    create trigger identity_searches_touch before update on app.identity_searches
      for each row execute function app.touch_row();
    alter table app.identity_searches enable row level security;
    alter table app.identity_searches force row level security;
    create policy identity_searches_tenant on app.identity_searches for all
      using (org_id = (select app.current_org_id())) with check (org_id = (select app.current_org_id()));
    create trigger identity_searches_demo_flag before insert on app.identity_searches
      for each row execute function app.inherit_demo_flag();
    grant select, insert, update on app.identity_searches to pawguard_api;
    grant select, update on app.identity_searches to pawguard_worker;

    create table app.identity_decisions (
      id uuid primary key default extensions.gen_random_uuid(),
      org_id uuid not null references app.organisations(id),
      search_id uuid not null,
      decision text not null check (decision in ('same_animal','new_animal','not_sure')),
      animal_id uuid,
      candidate_rank integer check (candidate_rank is null or candidate_rank >= 1),
      was_suggested boolean not null default false,
      reason text check (char_length(reason) <= 500),
      decided_by uuid not null,
      is_demo boolean not null default false,
      created_at timestamptz not null default now(),
      foreign key (search_id, org_id) references app.identity_searches(id, org_id),
      foreign key (animal_id, org_id) references app.animals(id, org_id),
      check ((decision = 'same_animal') = (animal_id is not null))
    );
    create index identity_decisions_search on app.identity_decisions (search_id, created_at desc);
    alter table app.identity_decisions enable row level security;
    alter table app.identity_decisions force row level security;
    create policy identity_decisions_tenant on app.identity_decisions for all
      using (org_id = (select app.current_org_id())) with check (org_id = (select app.current_org_id()));
    create trigger identity_decisions_demo_flag before insert on app.identity_decisions
      for each row execute function app.inherit_demo_flag();
    grant select, insert on app.identity_decisions to pawguard_api;

    -- Gallery counts for the caller's organisation without exposing vectors to the API role.
    create or replace function app.identity_gallery_stats(p_model uuid)
    returns table (animals bigint, photos bigint, eligible bigint)
    language sql stable security definer set search_path = '' as $$
      with elig as (
        select om.id, o.animal_id from app.observation_media om
          join app.animal_observations o on o.id = om.observation_id
          join app.media_assets m on m.id = om.media_id
          join app.animals a on a.id = o.animal_id
         where om.org_id = (select app.current_org_id()) and jsonb_typeof(om.subject_bbox) = 'object'
           and m.state = 'approved' and a.profile_state <> 'archived'
      ), done as (
        select distinct elig.id, elig.animal_id from elig
          join app.animal_embeddings e on e.observation_media_id = elig.id
         where e.model_version_id = p_model and e.state = 'active'
      )
      select (select count(distinct animal_id) from done), (select count(*) from done), (select count(*) from elig)
    $$;
    revoke all on function app.identity_gallery_stats(uuid) from public;
    grant execute on function app.identity_gallery_stats(uuid) to pawguard_api, pawguard_worker;
    """)


def downgrade() -> None:
    op.execute("""
    drop function if exists app.identity_gallery_stats(uuid);
    drop table if exists app.identity_decisions, app.identity_searches, app.animal_embeddings, app.training_runs;
    drop index if exists app.model_versions_one_preview;
    alter table app.model_versions drop constraint if exists model_versions_identity_gate,
      drop constraint if exists model_versions_preview_staged, drop constraint if exists model_versions_identity_dim,
      drop column if exists release_gate, drop column if exists research_preview, drop column if exists index_wanted;
    """)
