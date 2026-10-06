"""Surveys and campaign planning.

- `campaign_areas` gain the planning inputs for each area (estimated animals and where the estimate came from,
  minutes per animal, access window, whether the area is accessible, priority).
- `teams` gain defaults used to pre-fill a plan (shift, doses carried, starting area).
- `survey_counts`: street counts recorded by field workers (source for estimates and later surveillance).
- `campaign_plans`: versioned plans — an immutable snapshot of the inputs, the solver output (routes, unassigned
  areas with reasons, comparison with the greedy baseline), and explicit approval and publication. Nothing is
  dispatched until a person approves and publishes; publication creates ordinary field tasks.

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-06
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
    alter table app.campaign_areas
      add column est_animals integer check (est_animals is null or est_animals between 0 and 100000),
      add column est_source text check (est_source in ('survey','registry','manual')),
      add column service_minutes_per_animal numeric not null default 4
        check (service_minutes_per_animal > 0 and service_minutes_per_animal <= 120),
      add column access_start time,
      add column access_end time,
      add column accessible boolean not null default true,
      add column access_note text check (char_length(access_note) <= 300),
      add column priority smallint not null default 2 check (priority between 1 and 3),
      add constraint campaign_areas_window check (access_start is null or access_end is null or access_end > access_start);

    alter table app.teams
      add column shift_start time not null default '08:00',
      add column shift_end time not null default '13:00',
      add column doses_per_day integer not null default 60 check (doses_per_day between 0 and 10000),
      add column start_area_id uuid,
      add constraint teams_shift check (shift_end > shift_start),
      add constraint teams_start_area foreign key (start_area_id, org_id) references app.areas(id, org_id);

    create table app.survey_counts (
      id uuid primary key default extensions.gen_random_uuid(),
      org_id uuid not null references app.organisations(id),
      campaign_id uuid,
      area_id uuid not null,
      field_task_id uuid,
      observed_on date not null,
      dogs_counted integer not null check (dogs_counted between 0 and 100000),
      marked_count integer not null default 0 check (marked_count >= 0),
      puppies_count integer not null default 0 check (puppies_count >= 0),
      method text not null default 'street_count' check (method in ('street_count','household','other')),
      notes text check (char_length(notes) <= 1000),
      observer_user_id uuid not null,
      client_operation_id uuid,
      is_demo boolean not null default false,
      created_at timestamptz not null default now(),
      unique (org_id, client_operation_id),
      check (marked_count <= dogs_counted and puppies_count <= dogs_counted),
      check (observed_on <= current_date),
      foreign key (campaign_id, org_id) references app.campaigns(id, org_id),
      foreign key (area_id, org_id) references app.areas(id, org_id),
      foreign key (field_task_id, org_id) references app.field_tasks(id, org_id)
    );
    create index survey_counts_area on app.survey_counts (area_id, observed_on desc);
    alter table app.survey_counts enable row level security;
    alter table app.survey_counts force row level security;
    create policy survey_counts_tenant on app.survey_counts for all
      using (org_id = (select app.current_org_id())) with check (org_id = (select app.current_org_id()));
    create trigger survey_counts_demo_flag before insert on app.survey_counts
      for each row execute function app.inherit_demo_flag();
    grant select, insert on app.survey_counts to pawguard_api;
    grant select on app.survey_counts to pawguard_worker;

    create table app.campaign_plans (
      id uuid primary key default extensions.gen_random_uuid(),
      org_id uuid not null references app.organisations(id),
      campaign_id uuid not null,
      version integer not null check (version >= 1),
      plan_date date not null,
      state text not null default 'solving'
        check (state in ('solving','ready','failed','approved','published','superseded')),
      inputs jsonb not null,
      result jsonb not null default '{}'::jsonb,
      travel_basis text not null default 'straight_line_estimate'
        check (travel_basis in ('straight_line_estimate','travel_time_matrix')),
      solver_version text,
      failure_code text,
      created_by uuid not null,
      approved_by uuid,
      approved_at timestamptz,
      approval_note text check (char_length(approval_note) <= 500),
      published_by uuid,
      published_at timestamptz,
      task_ids uuid[] not null default '{}',
      is_demo boolean not null default false,
      created_at timestamptz not null default now(),
      updated_at timestamptz not null default now(),
      row_version integer not null default 1,
      unique (campaign_id, version),
      unique (id, org_id),
      foreign key (campaign_id, org_id) references app.campaigns(id, org_id),
      check ((state in ('approved','published')) <= (approved_by is not null)),
      check ((state = 'published') = (published_at is not null) or state = 'superseded')
    );
    create trigger campaign_plans_touch before update on app.campaign_plans
      for each row execute function app.touch_row();
    alter table app.campaign_plans enable row level security;
    alter table app.campaign_plans force row level security;
    create policy campaign_plans_tenant on app.campaign_plans for all
      using (org_id = (select app.current_org_id())) with check (org_id = (select app.current_org_id()));
    create trigger campaign_plans_demo_flag before insert on app.campaign_plans
      for each row execute function app.inherit_demo_flag();
    grant select, insert, update on app.campaign_plans to pawguard_api;
    grant select, update on app.campaign_plans to pawguard_worker;
    grant select on app.campaigns, app.campaign_areas, app.teams, app.team_members to pawguard_worker;
    grant insert, update on app.teams, app.campaign_areas to pawguard_api;
    """)


def downgrade() -> None:
    op.execute("""
    drop table if exists app.campaign_plans, app.survey_counts;
    alter table app.teams drop constraint if exists teams_start_area, drop constraint if exists teams_shift,
      drop column if exists shift_start, drop column if exists shift_end, drop column if exists doses_per_day,
      drop column if exists start_area_id;
    alter table app.campaign_areas drop constraint if exists campaign_areas_window,
      drop column if exists est_animals, drop column if exists est_source, drop column if exists service_minutes_per_animal,
      drop column if exists access_start, drop column if exists access_end, drop column if exists accessible,
      drop column if exists access_note, drop column if exists priority;
    """)
