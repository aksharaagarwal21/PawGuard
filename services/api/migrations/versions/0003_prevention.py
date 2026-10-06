"""Prevention domain, operational plumbing (outbox, idempotency, jobs), foundation records, RLS.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-05
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Tables whose rows belong to exactly one organisation and follow the standard tenant policy.
TENANT_TABLES = [
    "outbox_events", "idempotency_records", "background_jobs", "data_sources", "consent_records",
    "privacy_requests", "areas", "teams", "team_members", "animals", "animal_caregivers", "animal_observations",
    "media_assets", "observation_media", "image_quality_results", "vaccine_products", "vaccine_lots",
    "animal_vaccination_events", "vaccination_evidence", "vaccination_reviews", "animal_merge_operations",
    "campaigns", "campaign_areas", "field_tasks", "sync_operations", "data_quality_issues",
]

STD = "org_id uuid not null references app.organisations(id)"
AUDIT_COLS = """
      is_demo boolean not null default false,
      created_at timestamptz not null default now(),
      created_by uuid,
      updated_at timestamptz not null default now(),
      row_version integer not null default 1"""


def _touch(table: str) -> str:
    return (f"create trigger {table}_touch before update on app.{table} "
            f"for each row execute function app.touch_row();")


def upgrade() -> None:
    # ------------------------------------------------------------------ operational plumbing
    op.execute(f"""
    create table app.outbox_events (
      id uuid primary key default extensions.gen_random_uuid(),
      {STD},
      event_type text not null check (event_type ~ '^[a-z_]+(\\.[a-z_]+)+$'),
      aggregate_type text not null,
      aggregate_id uuid not null,
      payload jsonb not null default '{{}}'::jsonb,  -- identifiers only, never record content
      state text not null default 'pending' check (state in ('pending','dispatched','failed')),
      attempts integer not null default 0 check (attempts >= 0),
      available_at timestamptz not null default now(),
      dispatched_at timestamptz,
      last_error text check (char_length(last_error) <= 500),
      created_at timestamptz not null default now()
    );
    create index outbox_pending on app.outbox_events (available_at) where state = 'pending';

    create table app.idempotency_records (
      id uuid primary key default extensions.gen_random_uuid(),
      {STD},
      actor_user_id uuid not null,
      route text not null,
      idempotency_key text not null check (char_length(idempotency_key) between 8 and 200),
      request_hash text not null,
      status_code integer,
      response_body jsonb,
      resource_type text,
      resource_id uuid,
      created_at timestamptz not null default now(),
      expires_at timestamptz not null default now() + interval '7 days',
      unique (org_id, actor_user_id, route, idempotency_key)
    );
    create index idempotency_expiry on app.idempotency_records (expires_at);

    create table app.background_jobs (
      id uuid primary key default extensions.gen_random_uuid(),
      {STD},
      job_type text not null check (job_type ~ '^[a-z_]+(\\.[a-z_]+)+$'),
      target_type text not null,
      target_id uuid not null,
      state text not null default 'queued'
        check (state in ('queued','processing','completed','failed','cancelled','needs_input')),
      attempts integer not null default 0 check (attempts >= 0),
      max_attempts integer not null default 3 check (max_attempts between 1 and 20),
      last_error_code text,
      result jsonb not null default '{{}}'::jsonb,  -- non-sensitive summaries only
      locked_by text,
      locked_until timestamptz,
      queued_at timestamptz not null default now(),
      started_at timestamptz,
      finished_at timestamptz,
      created_by uuid,
      row_version integer not null default 1,
      updated_at timestamptz not null default now()
    );
    create index background_jobs_target on app.background_jobs (target_type, target_id);
    create index background_jobs_queue on app.background_jobs (state, queued_at) where state in ('queued','processing');
    -- At most one live job of a type per target (retries reuse it).
    create unique index background_jobs_one_live on app.background_jobs (job_type, target_id)
      where state in ('queued','processing');
    {_touch("background_jobs")}
    """)

    # ------------------------------------------------------------------ foundation records
    op.execute(f"""
    create table app.data_sources (
      id uuid primary key default extensions.gen_random_uuid(),
      {STD},
      name text not null check (char_length(name) between 1 and 300),
      owner text,
      reference text,               -- URL or document reference
      licence_terms text,
      permitted_uses text[] not null default '{{}}',
      access_status text not null default 'unknown' check (access_status in ('available','restricted','pending',
                                                                             'unavailable','unknown')),
      version_label text,
      checksum text,
      last_checked_on date,
      {AUDIT_COLS}
    );
    {_touch("data_sources")}

    create table app.consent_records (
      id uuid primary key default extensions.gen_random_uuid(),
      {STD},
      subject_type text not null check (subject_type in ('caregiver_contact','user','media_subject','other')),
      subject_ref uuid,
      purpose text not null check (purpose in ('operational_contact','operational_records','model_training',
                                               'research','publication')),
      notice_version text not null,
      granted_at timestamptz,
      withdrawn_at timestamptz,
      method text not null check (method in ('verbal_recorded','written','in_app','partner_agreement','other')),
      recorded_by uuid,
      check (withdrawn_at is null or granted_at is null or withdrawn_at >= granted_at),
      {AUDIT_COLS}
    );
    {_touch("consent_records")}

    create table app.sharing_agreements (
      id uuid primary key default extensions.gen_random_uuid(),
      org_a uuid not null references app.organisations(id),
      org_b uuid not null references app.organisations(id),
      resource_scopes text[] not null,
      purpose text not null,
      effective_from date not null,
      effective_to date,
      state text not null default 'draft' check (state in ('draft','approved','expired','revoked')),
      approved_by_a uuid,
      approved_by_b uuid,
      check (org_a <> org_b),
      check (effective_to is null or effective_to >= effective_from),
      {AUDIT_COLS}
    );
    {_touch("sharing_agreements")}

    create table app.privacy_requests (
      id uuid primary key default extensions.gen_random_uuid(),
      {STD},
      subject_description text not null,
      request_type text not null check (request_type in ('access','correction','deletion','restriction',
                                                         'training_exclusion')),
      scope text,
      review_state text not null default 'received' check (review_state in ('received','in_review','approved',
                                                                            'rejected','executed')),
      execution_log jsonb not null default '[]'::jsonb,
      {AUDIT_COLS}
    );
    {_touch("privacy_requests")}

    create table app.data_quality_issues (
      id uuid primary key default extensions.gen_random_uuid(),
      {STD},
      resource_type text not null,
      resource_id uuid not null,
      rule text not null,
      rule_version text not null default '1',
      severity text not null check (severity in ('info','warning','blocking')),
      explanation text not null,
      state text not null default 'open' check (state in ('open','resolved','dismissed')),
      resolved_by uuid,
      resolution_note text,
      resolved_at timestamptz,
      {AUDIT_COLS}
    );
    create index dq_resource on app.data_quality_issues (resource_type, resource_id);
    {_touch("data_quality_issues")}
    """)

    # ------------------------------------------------------------------ geography & teams
    op.execute(f"""
    create table app.areas (
      id uuid primary key default extensions.gen_random_uuid(),
      {STD},
      code text not null check (char_length(code) between 1 and 64),
      name text not null check (char_length(name) between 1 and 200),
      kind text not null default 'ward' check (kind in ('district','zone','ward','locality','other')),
      parent_area_id uuid references app.areas(id),
      boundary extensions.geometry(MultiPolygon, 4326),
      boundary_source text,
      boundary_version text,
      effective_from date not null default current_date,
      effective_to date,
      unique (org_id, code, effective_from),
      unique (id, org_id),
      check (effective_to is null or effective_to > effective_from),
      {AUDIT_COLS}
    );
    create index areas_boundary on app.areas using gist (boundary);
    {_touch("areas")}

    create table app.teams (
      id uuid primary key default extensions.gen_random_uuid(),
      {STD},
      name text not null,
      skills text[] not null default '{{}}',
      access_notes text,
      active boolean not null default true,
      unique (id, org_id),
      {AUDIT_COLS}
    );
    {_touch("teams")}

    create table app.team_members (
      id uuid primary key default extensions.gen_random_uuid(),
      {STD},
      team_id uuid not null,
      membership_id uuid not null,
      valid_from date not null default current_date,
      valid_to date,
      foreign key (team_id, org_id) references app.teams(id, org_id),
      foreign key (membership_id, org_id) references app.memberships(id, org_id),
      {AUDIT_COLS}
    );
    {_touch("team_members")}
    """)

    # ------------------------------------------------------------------ animals
    op.execute(f"""
    create table app.animals (
      id uuid primary key default extensions.gen_random_uuid(),
      {STD},
      reference_code text not null check (reference_code ~ '^PG-[0-9A-HJKMNP-TV-Z]{{4}}-[0-9A-HJKMNP-TV-Z]{{4}}$'),
      species text not null default 'dog' check (species in ('dog','cat','other','unknown')),
      nickname text check (char_length(nickname) <= 80),
      sex text not null default 'unknown' check (sex in ('female','male','unknown')),
      sterilisation_status text not null default 'unknown'
        check (sterilisation_status in ('sterilised','not_sterilised','unknown')),
      age_band text not null default 'unknown' check (age_band in ('puppy','young','adult','senior','unknown')),
      coat_description text check (char_length(coat_description) <= 300),
      identifying_marks text check (char_length(identifying_marks) <= 500),
      breed_note text check (char_length(breed_note) <= 120),  -- optional, untrusted unless known
      ownership_category text not null default 'unknown'
        check (ownership_category in ('owned','community','unowned','shelter','unknown')),
      profile_state text not null default 'provisional'
        check (profile_state in ('provisional','reviewed','active','disputed','merged_alias','archived')),
      merged_into_id uuid,
      home_area_id uuid,
      last_observed_at timestamptz,
      archived_reason text,
      source_type text not null default 'field_entry'
        check (source_type in ('field_entry','import','partner_record','sync')),
      source_reference text,
      client_operation_id uuid,
      unique (org_id, reference_code),
      unique (id, org_id),
      unique (org_id, client_operation_id),
      foreign key (merged_into_id, org_id) references app.animals(id, org_id),
      foreign key (home_area_id, org_id) references app.areas(id, org_id),
      check ((profile_state = 'merged_alias') = (merged_into_id is not null)),
      check (merged_into_id is null or merged_into_id <> id),
      {AUDIT_COLS}
    );
    create index animals_org_state on app.animals (org_id, profile_state);
    create index animals_org_area on app.animals (org_id, home_area_id);
    create index animals_org_last_seen on app.animals (org_id, last_observed_at desc nulls last);
    create index animals_search_trgm on app.animals using gin (
      (coalesce(nickname,'') || ' ' || reference_code || ' ' || coalesce(coat_description,'') || ' ' ||
       coalesce(identifying_marks,'')) extensions.gin_trgm_ops);
    {_touch("animals")}

    create table app.animal_caregivers (
      id uuid primary key default extensions.gen_random_uuid(),
      {STD},
      animal_id uuid not null,
      relationship text not null check (relationship in ('owner','feeder','caretaker','other')),
      contact_name text check (char_length(contact_name) <= 120),
      contact_phone text check (contact_phone ~ '^\\+?[0-9 ()-]{{6,20}}$'),
      contact_notes text check (char_length(contact_notes) <= 500),
      linked_user_id uuid,
      consent_record_id uuid references app.consent_records(id),
      valid_from date not null default current_date,
      valid_to date,
      foreign key (animal_id, org_id) references app.animals(id, org_id),
      {AUDIT_COLS}
    );
    create index caregivers_animal on app.animal_caregivers (animal_id);
    {_touch("animal_caregivers")}

    create table app.animal_observations (
      id uuid primary key default extensions.gen_random_uuid(),
      {STD},
      animal_id uuid,                       -- null until identity is resolved
      reported_animal_reference text,       -- identity as originally reported, preserved after merges
      observer_user_id uuid not null,
      observed_at timestamptz,
      observed_on date,
      time_precision text not null check (time_precision in ('exact','day','month','unknown')),
      location extensions.geography(Point, 4326),
      location_approx extensions.geography(Point, 4326),
      location_accuracy_m numeric check (location_accuracy_m is null or location_accuracy_m >= 0),
      location_method text not null default 'unknown'
        check (location_method in ('gps','map_pick','area_only','described','unknown')),
      area_id uuid,
      notes text check (char_length(notes) <= 1000),
      source_type text not null default 'field_entry' check (source_type in ('field_entry','import','sync')),
      field_task_id uuid,
      client_operation_id uuid,
      unique (org_id, client_operation_id),
      unique (id, org_id),
      foreign key (animal_id, org_id) references app.animals(id, org_id),
      foreign key (area_id, org_id) references app.areas(id, org_id),
      check (time_precision = 'unknown' or observed_at is not null or observed_on is not null),
      check ((location is null) = (location_approx is null)),
      {AUDIT_COLS}
    );
    create index observations_animal on app.animal_observations (animal_id, observed_on desc);
    create index observations_org_time on app.animal_observations (org_id, created_at desc);
    create index observations_location on app.animal_observations using gist (location);
    {_touch("animal_observations")}
    """)

    # ------------------------------------------------------------------ media
    op.execute(f"""
    create table app.media_assets (
      id uuid primary key default extensions.gen_random_uuid(),
      {STD},
      bucket text not null,
      object_key text not null,
      purpose text not null check (purpose in ('animal_photo','vaccination_evidence','document')),
      declared_mime text not null,
      detected_mime text,
      declared_bytes bigint not null check (declared_bytes > 0 and declared_bytes <= 15728640),
      byte_size bigint check (byte_size is null or byte_size > 0),
      sha256 text check (sha256 ~ '^[0-9a-f]{{64}}$'),
      width integer check (width is null or width > 0),
      height integer check (height is null or height > 0),
      state text not null default 'pending_upload'
        check (state in ('pending_upload','uploaded','validating','approved','rejected','deleted')),
      rejection_code text,
      source_rights text not null default 'organisation'
        check (source_rights in ('own_photo','organisation','partner','unknown')),
      consent_scope text not null default 'operational' check (consent_scope in ('operational',
                                                                                'operational_and_training')),
      uploader_user_id uuid not null,
      derivatives jsonb not null default '{{}}'::jsonb,
      retention_until date,
      uploaded_at timestamptz,
      validated_at timestamptz,
      unique (org_id, object_key),
      unique (id, org_id),
      {AUDIT_COLS}
    );
    create index media_state on app.media_assets (state, created_at);
    create index media_sha on app.media_assets (org_id, sha256);
    {_touch("media_assets")}

    create table app.observation_media (
      id uuid primary key default extensions.gen_random_uuid(),
      {STD},
      observation_id uuid not null,
      media_id uuid not null,
      subject_bbox jsonb,             -- {{x,y,w,h}} in original-image pixel coordinates (after EXIF orientation)
      subject_count integer check (subject_count is null or subject_count >= 0),
      crop_version text,
      capture_session_id uuid,
      unique (observation_id, media_id),
      foreign key (observation_id, org_id) references app.animal_observations(id, org_id),
      foreign key (media_id, org_id) references app.media_assets(id, org_id),
      {AUDIT_COLS}
    );
    {_touch("observation_media")}

    create table app.image_quality_results (
      id uuid primary key default extensions.gen_random_uuid(),
      {STD},
      media_id uuid not null,
      region_key text not null default 'full',
      pipeline_version text not null,
      sharpness double precision,
      brightness double precision,
      contrast double precision,
      width integer,
      height integer,
      warnings text[] not null default '{{}}',
      decision text not null check (decision in ('ok','warn','reject')),
      override_reason text,
      overridden_by uuid,
      foreign key (media_id, org_id) references app.media_assets(id, org_id),
      unique (media_id, region_key, pipeline_version),
      {AUDIT_COLS}
    );
    {_touch("image_quality_results")}
    """)

    # ------------------------------------------------------------------ vaccination ledger
    op.execute(f"""
    create table app.vaccine_products (
      id uuid primary key default extensions.gen_random_uuid(),
      {STD},
      name text not null check (char_length(name) between 1 and 200),
      manufacturer text,
      species text[] not null default '{{dog}}',
      form text,
      unit text not null default 'dose' check (unit in ('dose','vial','ml')),
      review_state text not null default 'unreviewed' check (review_state in ('unreviewed','reviewed')),
      active boolean not null default true,
      unique (org_id, name),
      unique (id, org_id),
      {AUDIT_COLS}
    );
    {_touch("vaccine_products")}

    create table app.vaccine_lots (
      id uuid primary key default extensions.gen_random_uuid(),
      {STD},
      product_id uuid not null,
      lot_number text not null check (lot_number ~ '^[A-Za-z0-9][A-Za-z0-9./ -]{{0,39}}$'),
      expiry_date date,
      supplier text,
      received_on date,
      unique (org_id, product_id, lot_number),
      unique (id, org_id),
      foreign key (product_id, org_id) references app.vaccine_products(id, org_id),
      {AUDIT_COLS}
    );
    {_touch("vaccine_lots")}

    create table app.animal_vaccination_events (
      id uuid primary key default extensions.gen_random_uuid(),
      {STD},
      animal_id uuid not null,
      original_animal_id uuid not null,   -- animal the evidence was first recorded against (kept across merges)
      administered_on date,
      administered_at timestamptz,
      date_precision text not null check (date_precision in ('exact_time','day','month','year','unknown')),
      product_id uuid,
      product_text text check (char_length(product_text) <= 200),
      lot_id uuid,
      lot_text text check (char_length(lot_text) <= 40),
      administered_by_name text check (char_length(administered_by_name) <= 200),
      administered_by_registration text check (char_length(administered_by_registration) <= 100),
      administered_by_user_id uuid,
      area_id uuid,
      location extensions.geography(Point, 4326),
      source_type text not null check (source_type in ('field_entry','certificate_upload','import',
                                                       'partner_record','sync')),
      source_reference text,
      submitter_note text check (char_length(submitter_note) <= 1000),
      state text not null default 'submitted'
        check (state in ('draft','submitted','verified','rejected','needs_correction','superseded')),
      supersedes_event_id uuid,
      superseded_by_event_id uuid,
      has_conflict boolean not null default false,
      next_review_on date,
      next_review_source text,
      submitted_by uuid,
      submitted_at timestamptz,
      verified_by uuid,
      verified_at timestamptz,
      client_operation_id uuid,
      unique (org_id, client_operation_id),
      unique (id, org_id),
      foreign key (animal_id, org_id) references app.animals(id, org_id),
      foreign key (original_animal_id, org_id) references app.animals(id, org_id),
      foreign key (product_id, org_id) references app.vaccine_products(id, org_id),
      foreign key (lot_id, org_id) references app.vaccine_lots(id, org_id),
      foreign key (area_id, org_id) references app.areas(id, org_id),
      foreign key (supersedes_event_id, org_id) references app.animal_vaccination_events(id, org_id),
      check ((date_precision = 'unknown') = (administered_on is null)),
      check (date_precision <> 'exact_time' or administered_at is not null),
      check (date_precision <> 'month' or extract(day from administered_on) = 1),
      check (date_precision <> 'year' or (extract(day from administered_on) = 1
                                           and extract(month from administered_on) = 1)),
      check (state = 'draft' or (submitted_by is not null and submitted_at is not null)),
      check ((state = 'verified') = (verified_by is not null and verified_at is not null)),
      check ((next_review_on is null) = (next_review_source is null)),
      check (product_id is null or product_text is null),
      check (lot_id is null or lot_text is null),
      {AUDIT_COLS}
    );
    create index vacc_animal on app.animal_vaccination_events (animal_id, administered_on desc nulls last);
    create index vacc_org_state on app.animal_vaccination_events (org_id, state, submitted_at);
    {_touch("animal_vaccination_events")}

    -- Administration dates cannot be in the future (relative to the database clock, one-day tolerance for
    -- timezones). Implemented as a trigger because CHECK constraints must be immutable.
    create or replace function app.vacc_date_guard() returns trigger language plpgsql set search_path = '' as $$
    begin
      if new.administered_on is not null and new.administered_on > (now() at time zone 'utc')::date + 1 then
        raise exception 'administration date is in the future' using errcode = 'check_violation',
          constraint = 'vacc_not_future';
      end if;
      return new;
    end $$;
    create trigger vacc_date_guard before insert or update of administered_on on app.animal_vaccination_events
      for each row execute function app.vacc_date_guard();

    create table app.vaccination_evidence (
      id uuid primary key default extensions.gen_random_uuid(),
      {STD},
      event_id uuid not null,
      media_id uuid not null,
      unique (event_id, media_id),
      foreign key (event_id, org_id) references app.animal_vaccination_events(id, org_id),
      foreign key (media_id, org_id) references app.media_assets(id, org_id),
      {AUDIT_COLS}
    );
    {_touch("vaccination_evidence")}

    create table app.vaccination_reviews (
      id uuid primary key default extensions.gen_random_uuid(),
      {STD},
      event_id uuid not null,
      reviewer_user_id uuid not null,
      reviewer_scope text not null default 'veterinary_review',
      outcome text not null check (outcome in ('verified','rejected','needs_correction')),
      reason text check (char_length(reason) <= 2000),
      event_row_version integer not null,
      evidence_snapshot jsonb not null,
      created_at timestamptz not null default now(),
      is_demo boolean not null default false,
      foreign key (event_id, org_id) references app.animal_vaccination_events(id, org_id),
      check (outcome = 'verified' or char_length(coalesce(reason, '')) >= 3)
    );
    create index reviews_event on app.vaccination_reviews (event_id, created_at);

    create or replace function app.review_guard() returns trigger language plpgsql set search_path = '' as $$
    declare v_submitter uuid;
    begin
      if tg_op <> 'INSERT' then
        raise exception 'vaccination_reviews is append-only' using errcode = 'insufficient_privilege';
      end if;
      select submitted_by into v_submitter from app.animal_vaccination_events where id = new.event_id;
      if v_submitter is not null and v_submitter = new.reviewer_user_id then
        raise exception 'a submitter cannot review their own vaccination record'
          using errcode = 'check_violation', constraint = 'review_not_self';
      end if;
      return new;
    end $$;
    create trigger review_guard before insert or update or delete on app.vaccination_reviews
      for each row execute function app.review_guard();
    """)

    # ------------------------------------------------------------------ merges, campaigns, tasks, sync
    op.execute(f"""
    create table app.animal_merge_operations (
      id uuid primary key default extensions.gen_random_uuid(),
      {STD},
      source_animal_id uuid not null,
      target_animal_id uuid not null,
      state text not null default 'proposed' check (state in ('proposed','executed','reversed','rejected')),
      reason text not null check (char_length(reason) >= 3),
      proposed_by uuid not null,
      decided_by uuid,
      executed_at timestamptz,
      manifest jsonb not null default '{{}}'::jsonb,  -- ids of every relationship moved, for reversal
      reversed_by uuid,
      reversed_at timestamptz,
      reversal_reason text,
      foreign key (source_animal_id, org_id) references app.animals(id, org_id),
      foreign key (target_animal_id, org_id) references app.animals(id, org_id),
      check (source_animal_id <> target_animal_id),
      check (state <> 'reversed' or (reversed_by is not null and reversal_reason is not null)),
      {AUDIT_COLS}
    );
    create index merges_source on app.animal_merge_operations (source_animal_id);
    create index merges_target on app.animal_merge_operations (target_animal_id);
    {_touch("animal_merge_operations")}

    create table app.campaigns (
      id uuid primary key default extensions.gen_random_uuid(),
      {STD},
      name text not null check (char_length(name) between 1 and 200),
      purpose text,
      activity text not null default 'vaccination' check (activity in ('vaccination','survey','mixed','other')),
      starts_on date,
      ends_on date,
      coordinator_membership_id uuid,
      state text not null default 'draft' check (state in ('draft','approved','active','closed')),
      resources jsonb not null default '{{}}'::jsonb,
      unique (id, org_id),
      check (ends_on is null or starts_on is null or ends_on >= starts_on),
      foreign key (coordinator_membership_id, org_id) references app.memberships(id, org_id),
      {AUDIT_COLS}
    );
    {_touch("campaigns")}

    create table app.campaign_areas (
      id uuid primary key default extensions.gen_random_uuid(),
      {STD},
      campaign_id uuid not null,
      area_id uuid not null,
      unique (campaign_id, area_id),
      foreign key (campaign_id, org_id) references app.campaigns(id, org_id),
      foreign key (area_id, org_id) references app.areas(id, org_id),
      {AUDIT_COLS}
    );
    {_touch("campaign_areas")}

    create table app.field_tasks (
      id uuid primary key default extensions.gen_random_uuid(),
      {STD},
      campaign_id uuid,
      task_type text not null check (task_type in ('vaccination_round','survey','animal_followup',
                                                   'evidence_correction','identity_review','other')),
      title text not null check (char_length(title) between 1 and 200),
      instructions text check (char_length(instructions) <= 2000),
      area_id uuid,
      animal_id uuid,
      location_approx extensions.geography(Point, 4326),
      assignee_membership_id uuid,
      team_id uuid,
      planned_start timestamptz,
      planned_end timestamptz,
      due_on date,
      priority text not null default 'normal' check (priority in ('low','normal','high')),
      priority_rationale text,
      state text not null default 'unassigned'
        check (state in ('unassigned','assigned','in_progress','completed','blocked','cancelled')),
      outcome_note text check (char_length(outcome_note) <= 1000),
      blocked_reason text,
      cancelled_reason text,
      completed_at timestamptz,
      source_event_type text,
      source_event_id uuid,
      client_operation_id uuid,
      unique (org_id, client_operation_id),
      unique (id, org_id),
      foreign key (campaign_id, org_id) references app.campaigns(id, org_id),
      foreign key (area_id, org_id) references app.areas(id, org_id),
      foreign key (animal_id, org_id) references app.animals(id, org_id),
      foreign key (assignee_membership_id, org_id) references app.memberships(id, org_id),
      foreign key (team_id, org_id) references app.teams(id, org_id),
      check (state <> 'blocked' or char_length(coalesce(blocked_reason,'')) >= 3),
      check (state <> 'cancelled' or char_length(coalesce(cancelled_reason,'')) >= 3),
      check (state not in ('assigned','in_progress') or assignee_membership_id is not null or team_id is not null),
      check ((state = 'completed') = (completed_at is not null)),
      check (planned_end is null or planned_start is null or planned_end >= planned_start),
      {AUDIT_COLS}
    );
    create index tasks_assignee on app.field_tasks (assignee_membership_id, state);
    create index tasks_org_state on app.field_tasks (org_id, state, due_on);
    create index tasks_animal on app.field_tasks (animal_id);
    {_touch("field_tasks")}

    create view app.animal_followup_tasks with (security_invoker = true) as
      select * from app.field_tasks where task_type in ('animal_followup','evidence_correction','identity_review');

    create table app.sync_operations (
      id uuid primary key default extensions.gen_random_uuid(),
      {STD},
      operation_id uuid not null,
      device_id text not null check (char_length(device_id) between 8 and 64),
      actor_user_id uuid not null,
      operation_type text not null,
      target_type text,
      target_id uuid,
      base_row_version integer,
      state text not null check (state in ('received','accepted','conflict','rejected')),
      result_code text,
      result_detail jsonb not null default '{{}}'::jsonb,  -- ids and field names only
      client_created_at timestamptz,
      received_at timestamptz not null default now(),
      resolved_at timestamptz,
      resolved_by uuid,
      unique (org_id, operation_id),
      {AUDIT_COLS}
    );
    create index sync_actor on app.sync_operations (actor_user_id, received_at desc);
    {_touch("sync_operations")}
    """)

    # ------------------------------------------------------------------ worker context
    op.execute("""
    create or replace function app.set_worker_context(p_job uuid) returns uuid
    language plpgsql volatile security definer set search_path = '' as $$
    declare v_org uuid;
    begin
      if session_user <> 'pawguard_worker' then
        raise exception 'worker context is only available to the worker role' using errcode = 'insufficient_privilege';
      end if;
      select org_id into v_org from app.background_jobs where id = p_job and state = 'processing';
      if v_org is null then
        raise exception 'job is not claimed' using errcode = 'insufficient_privilege';
      end if;
      perform set_config('pawguard.user_id', '', true);
      perform set_config('pawguard.org_id', v_org::text, true);
      perform set_config('pawguard.actor_kind', 'worker', true);
      perform set_config('pawguard.job_id', p_job::text, true);
      return v_org;
    end $$;

    create or replace function app.current_org_id() returns uuid
    language plpgsql stable security definer set search_path = '' as $$
    declare
      v_org uuid := nullif(current_setting('pawguard.org_id', true), '')::uuid;
      v_user uuid := nullif(current_setting('pawguard.user_id', true), '')::uuid;
      v_kind text := current_setting('pawguard.actor_kind', true);
      v_job uuid := nullif(current_setting('pawguard.job_id', true), '')::uuid;
    begin
      if v_org is null then
        return null;
      end if;
      if v_kind = 'user' and v_user is not null then
        if exists (select 1 from app.memberships m
                   where m.user_id = v_user and m.org_id = v_org and m.status = 'active'
                     and m.valid_from <= now() and (m.valid_until is null or m.valid_until > now())) then
          return v_org;
        end if;
      elsif v_kind = 'worker' and session_user = 'pawguard_worker' and v_job is not null then
        if exists (select 1 from app.background_jobs j where j.id = v_job and j.org_id = v_org
                   and j.state = 'processing') then
          return v_org;
        end if;
      end if;
      return null;
    end $$;
    revoke all on function app.set_worker_context(uuid) from public;
    grant execute on function app.set_worker_context(uuid) to pawguard_worker;

    -- Short, non-enumerable reference codes: PG-XXXX-XXXX (Crockford base32, 40 random bits).
    create or replace function app.new_reference_code() returns text language plpgsql volatile
    set search_path = '' as $$
    declare
      alphabet constant text := '0123456789ABCDEFGHJKMNPQRSTVWXYZ';
      b bytea := extensions.gen_random_bytes(8);
      s text := '';
    begin
      for i in 0..7 loop
        s := s || substr(alphabet, (get_byte(b, i) % 32) + 1, 1);
      end loop;
      return 'PG-' || substr(s, 1, 4) || '-' || substr(s, 5, 4);
    end $$;
    grant execute on function app.new_reference_code() to pawguard_api, pawguard_worker;
    """)

    # ------------------------------------------------------------------ RLS
    for t in TENANT_TABLES:
        op.execute(f"""
        alter table app.{t} enable row level security;
        alter table app.{t} force row level security;
        create policy {t}_tenant on app.{t} for all
          using (org_id = (select app.current_org_id()))
          with check (org_id = (select app.current_org_id()));
        """)
    op.execute("""
    -- Caregiver contact details need an explicit capability on top of tenancy.
    create policy caregivers_capability on app.animal_caregivers as restrictive for select
      using ((select app.has_capability('caregiver.read')));
    create policy caregivers_write_capability on app.animal_caregivers as restrictive for insert
      with check ((select app.has_capability('caregiver.write')));

    -- The dispatcher (worker role, no job context) moves identifier-only rows across tenants.
    create policy outbox_dispatcher on app.outbox_events for all to pawguard_worker using (true) with check (true);
    create policy jobs_dispatcher on app.background_jobs for all to pawguard_worker using (true) with check (true);

    alter table app.sharing_agreements enable row level security;
    alter table app.sharing_agreements force row level security;
    create policy sharing_parties on app.sharing_agreements for select
      using ((select app.current_org_id()) in (org_a, org_b));
    """)

    # ------------------------------------------------------------------ grants (no DELETE on evidence)
    op.execute("""
    grant select, insert, update on
      app.outbox_events, app.background_jobs, app.data_sources, app.consent_records, app.privacy_requests,
      app.data_quality_issues, app.areas, app.teams, app.team_members, app.animals, app.animal_caregivers,
      app.animal_observations, app.media_assets, app.observation_media, app.image_quality_results,
      app.vaccine_products, app.vaccine_lots, app.animal_vaccination_events, app.vaccination_evidence,
      app.animal_merge_operations, app.campaigns, app.campaign_areas, app.field_tasks, app.sync_operations
      to pawguard_api;
    grant select, insert, update, delete on app.idempotency_records to pawguard_api;
    grant select, insert on app.vaccination_reviews to pawguard_api;
    grant select on app.sharing_agreements, app.animal_followup_tasks to pawguard_api;
    grant delete on app.campaign_areas, app.team_members to pawguard_api;

    grant select, insert, update on app.outbox_events, app.background_jobs, app.image_quality_results,
      app.data_quality_issues to pawguard_worker;
    grant select, update on app.media_assets, app.animals, app.animal_observations, app.observation_media
      to pawguard_worker;
    grant select on app.animal_vaccination_events, app.areas, app.memberships, app.user_profiles
      to pawguard_worker;
    grant delete on app.idempotency_records to pawguard_worker;
    grant select on app.idempotency_records to pawguard_worker;
    """)
    # Worker needs to read idempotency rows for expiry cleanup under its job context.


def downgrade() -> None:
    op.execute("""
    drop view if exists app.animal_followup_tasks;
    drop table if exists app.sync_operations, app.field_tasks, app.campaign_areas, app.campaigns,
      app.animal_merge_operations, app.vaccination_reviews, app.vaccination_evidence,
      app.animal_vaccination_events, app.vaccine_lots, app.vaccine_products, app.image_quality_results,
      app.observation_media, app.media_assets, app.animal_observations, app.animal_caregivers, app.animals,
      app.team_members, app.teams, app.areas, app.data_quality_issues, app.privacy_requests,
      app.sharing_agreements, app.consent_records, app.data_sources, app.background_jobs,
      app.idempotency_records, app.outbox_events cascade;
    drop function if exists app.set_worker_context(uuid), app.new_reference_code(), app.vacc_date_guard(),
      app.review_guard();
    """)
