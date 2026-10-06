"""Foundation: extensions, private app schema, runtime roles, request-context functions, access tables.

Revision ID: 0001
Revises:
Create Date: 2026-10-05
"""
import base64
import hashlib
import hmac
import os
import secrets
from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CAPABILITIES = [
    "animal.read", "animal.write", "animal.merge", "animal.location.exact", "caregiver.read", "caregiver.write",
    "observation.write", "media.upload", "identity.search", "identity.decide", "vaccination.submit",
    "vaccination.review", "task.work", "task.manage", "campaign.manage", "survey.write", "report.aggregate",
    "member.manage", "professional.approve", "audit.read", "system.view", "data.import", "model.manage",
]
ROLES = ["resident", "field_volunteer", "veterinary_reviewer", "programme_coordinator", "org_admin",
         "content_reviewer"]


def _q(values: list[str]) -> str:
    return ", ".join("'" + v.replace("'", "''") + "'" for v in values)


def _scram_verifier(password: str, iterations: int = 4096) -> str:
    """SCRAM-SHA-256 verifier (RFC 5802/7677, PostgreSQL format) computed client-side, so the plaintext
    password is never sent to the server, written to server logs or echoed in error messages."""
    salt = secrets.token_bytes(16)
    salted = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    client_key = hmac.new(salted, b"Client Key", hashlib.sha256).digest()
    stored_key = hashlib.sha256(client_key).digest()
    server_key = hmac.new(salted, b"Server Key", hashlib.sha256).digest()
    b64 = lambda b: base64.b64encode(b).decode()  # noqa: E731
    return f"SCRAM-SHA-256${iterations}:{b64(salt)}${b64(stored_key)}:{b64(server_key)}"


def _role_sql(role: str, env_var: str) -> str:
    password = os.environ.get(env_var)
    if not password:
        raise RuntimeError(f"{env_var} must be set when running migrations (password for role {role}).")
    verifier = _scram_verifier(password)
    # Existing roles: only rotate the password, then assert the attributes are still least-privilege.
    return f"""
    do $$ begin
      if not exists (select 1 from pg_roles where rolname = '{role}') then
        create role {role} login nosuperuser nocreatedb nocreaterole noinherit nobypassrls
          password '{verifier}';
      else
        alter role {role} with login password '{verifier}';
      end if;
      if exists (select 1 from pg_roles where rolname = '{role}'
                 and (rolsuper or rolbypassrls or rolcreaterole or rolcreatedb)) then
        raise exception 'role {role} has elevated attributes; refusing to continue';
      end if;
    end $$;
    """


def upgrade() -> None:
    op.execute("create schema if not exists extensions")
    for ext in ("pgcrypto", "postgis", "vector", "citext", "btree_gist", "pg_trgm"):
        op.execute(f'create extension if not exists "{ext}" with schema extensions')

    # exec_driver_sql: the verifier contains ':' which SQLAlchemy's text() would parse as bind parameters.
    bind = op.get_bind()
    bind.exec_driver_sql(_role_sql("pawguard_api", "PAWGUARD_DB_API_PASSWORD"))
    bind.exec_driver_sql(_role_sql("pawguard_worker", "PAWGUARD_DB_WORKER_PASSWORD"))

    op.execute("create schema if not exists app")
    op.execute("revoke all on schema app from public")
    op.execute("grant usage on schema app to pawguard_api, pawguard_worker")
    op.execute("grant usage on schema extensions to pawguard_api, pawguard_worker")
    op.execute("""
      do $$ begin
        execute format('alter role pawguard_api in database %I set search_path = app, extensions', current_database());
        execute format('alter role pawguard_worker in database %I set search_path = app, extensions', current_database());
        execute format('alter role pawguard_api in database %I set statement_timeout = %L', current_database(), '15s');
      end $$;
    """)
    # Defence in depth: Supabase's PostgREST roles get nothing in the app schema.
    op.execute("""
      do $$ begin
        if exists (select 1 from pg_roles where rolname = 'anon') then
          revoke all on schema app from anon, authenticated, service_role;
        end if;
      end $$;
    """)

    # ---------- shared helpers ----------
    op.execute("""
    create or replace function app.touch_row() returns trigger language plpgsql set search_path = '' as $$
    begin
      new.updated_at := now();
      new.row_version := old.row_version + 1;
      return new;
    end $$;
    """)

    # ---------- organisations ----------
    op.execute(f"""
    create table app.organisations (
      id uuid primary key default extensions.gen_random_uuid(),
      name text not null check (char_length(name) between 1 and 200),
      org_type text not null check (org_type in ('animal_welfare_ngo','municipal_programme','veterinary_service',
                                                 'health_facility','community_group','other')),
      region_code text check (region_code ~ '^[A-Z]{{2}}(-[A-Z0-9]{{1,3}})?$'),
      contact_email text check (contact_email is null or contact_email ~ '^[^@\\s]+@[^@\\s]+$'),
      timezone text not null default 'Asia/Kolkata',
      activation_state text not null default 'pending'
        check (activation_state in ('pending','active','suspended','closed')),
      is_demo boolean not null default false,
      created_at timestamptz not null default now(),
      created_by uuid,
      updated_at timestamptz not null default now(),
      row_version integer not null default 1
    );
    create trigger organisations_touch before update on app.organisations
      for each row execute function app.touch_row();

    create table app.user_profiles (
      user_id uuid primary key,
      preferred_name text check (char_length(preferred_name) <= 120),
      locale text not null default 'en' check (locale in ('en','ta','hi')),
      accessibility_prefs jsonb not null default '{{}}'::jsonb,
      is_demo boolean not null default false,
      created_at timestamptz not null default now(),
      updated_at timestamptz not null default now(),
      row_version integer not null default 1
    );
    create trigger user_profiles_touch before update on app.user_profiles
      for each row execute function app.touch_row();

    create table app.memberships (
      id uuid primary key default extensions.gen_random_uuid(),
      org_id uuid not null references app.organisations(id),
      user_id uuid not null,
      role text not null check (role in ({_q(ROLES)})),
      capabilities text[] not null default '{{}}' check (capabilities <@ array[{_q(CAPABILITIES)}]::text[]),
      status text not null default 'active' check (status in ('invited','active','suspended','revoked')),
      valid_from timestamptz not null default now(),
      valid_until timestamptz,
      approved_by uuid,
      approved_at timestamptz,
      revoked_by uuid,
      revoked_at timestamptz,
      revocation_reason text,
      is_demo boolean not null default false,
      created_at timestamptz not null default now(),
      created_by uuid,
      updated_at timestamptz not null default now(),
      row_version integer not null default 1,
      unique (id, org_id),
      check (valid_until is null or valid_until > valid_from),
      check ((status = 'revoked') = (revoked_at is not null))
    );
    create unique index memberships_one_current_per_user_org on app.memberships (org_id, user_id)
      where status in ('invited','active','suspended');
    create index memberships_user_idx on app.memberships (user_id) where status = 'active';
    create trigger memberships_touch before update on app.memberships
      for each row execute function app.touch_row();

    create table app.professional_approvals (
      id uuid primary key default extensions.gen_random_uuid(),
      org_id uuid not null references app.organisations(id),
      membership_id uuid not null,
      user_id uuid not null,
      scope text not null check (scope in ('veterinary_review','clinical_care','content_review_clinical',
                                           'content_review_veterinary')),
      evidence_reference text not null check (char_length(evidence_reference) between 1 and 500),
      reviewer_user_id uuid not null,
      review_state text not null default 'pending'
        check (review_state in ('pending','approved','rejected','revoked')),
      valid_from timestamptz not null default now(),
      valid_until timestamptz,
      decided_at timestamptz,
      decision_reason text,
      is_demo boolean not null default false,
      created_at timestamptz not null default now(),
      created_by uuid,
      updated_at timestamptz not null default now(),
      row_version integer not null default 1,
      foreign key (membership_id, org_id) references app.memberships(id, org_id),
      -- No one approves their own professional authority.
      check (reviewer_user_id <> user_id),
      check (valid_until is null or valid_until > valid_from)
    );
    create index professional_approvals_lookup on app.professional_approvals (org_id, user_id, scope)
      where review_state = 'approved';
    create trigger professional_approvals_touch before update on app.professional_approvals
      for each row execute function app.touch_row();

    create table app.audit_events (
      id uuid primary key default extensions.gen_random_uuid(),
      occurred_at timestamptz not null default now(),
      org_id uuid references app.organisations(id),
      actor_user_id uuid,
      actor_kind text not null check (actor_kind in ('user','worker','system','cli')),
      action text not null check (action ~ '^[a-z_]+(\\.[a-z_]+)+$'),
      target_type text,
      target_id uuid,
      request_id text,
      reason text check (char_length(reason) <= 2000),
      change_summary jsonb not null default '{{}}'::jsonb
    );
    create index audit_events_org_time on app.audit_events (org_id, occurred_at desc);
    create index audit_events_target on app.audit_events (target_type, target_id);

    create or replace function app.audit_immutable() returns trigger language plpgsql set search_path = '' as $$
    begin
      raise exception 'audit_events is append-only' using errcode = 'insufficient_privilege';
    end $$;
    create trigger audit_events_no_update before update or delete on app.audit_events
      for each row execute function app.audit_immutable();
    """)

    # ---------- request context (ADR 0003) ----------
    op.execute("""
    create or replace function app.set_request_context(p_user uuid, p_org uuid) returns void
    language sql volatile set search_path = '' as $$
      select set_config('pawguard.user_id', coalesce(p_user::text, ''), true),
             set_config('pawguard.org_id', coalesce(p_org::text, ''), true),
             set_config('pawguard.actor_kind', 'user', true),
             set_config('pawguard.job_id', '', true);
    $$;

    create or replace function app.current_user_id() returns uuid
    language sql stable set search_path = '' as $$
      select nullif(current_setting('pawguard.user_id', true), '')::uuid;
    $$;

    -- Returns the context organisation only while the context user still holds an active membership in it.
    -- (The worker branch is added with background_jobs in a later revision.)
    create or replace function app.current_org_id() returns uuid
    language plpgsql stable security definer set search_path = '' as $$
    declare
      v_org uuid := nullif(current_setting('pawguard.org_id', true), '')::uuid;
      v_user uuid := nullif(current_setting('pawguard.user_id', true), '')::uuid;
    begin
      if v_org is null or v_user is null or current_setting('pawguard.actor_kind', true) <> 'user' then
        return null;
      end if;
      if exists (select 1 from app.memberships m
                 where m.user_id = v_user and m.org_id = v_org and m.status = 'active'
                   and m.valid_from <= now() and (m.valid_until is null or m.valid_until > now())) then
        return v_org;
      end if;
      return null;
    end $$;

    create or replace function app.has_capability(p_cap text) returns boolean
    language sql stable security definer set search_path = '' as $$
      select exists (
        select 1 from app.memberships m
        where m.user_id = nullif(current_setting('pawguard.user_id', true), '')::uuid
          and m.org_id = nullif(current_setting('pawguard.org_id', true), '')::uuid
          and current_setting('pawguard.actor_kind', true) = 'user'
          and m.status = 'active' and m.valid_from <= now()
          and (m.valid_until is null or m.valid_until > now())
          and p_cap = any (m.capabilities));
    $$;

    create or replace function app.has_professional_scope(p_scope text) returns boolean
    language sql stable security definer set search_path = '' as $$
      select exists (
        select 1 from app.professional_approvals pa
        where pa.user_id = nullif(current_setting('pawguard.user_id', true), '')::uuid
          and pa.org_id = nullif(current_setting('pawguard.org_id', true), '')::uuid
          and current_setting('pawguard.actor_kind', true) = 'user'
          and pa.scope = p_scope and pa.review_state = 'approved'
          and pa.valid_from <= now() and (pa.valid_until is null or pa.valid_until > now()));
    $$;

    -- Organisations the context user actively belongs to (for the organisation picker).
    create or replace function app.user_org_ids() returns setof uuid
    language sql stable security definer set search_path = '' as $$
      select m.org_id from app.memberships m
      where m.user_id = nullif(current_setting('pawguard.user_id', true), '')::uuid
        and m.status = 'active' and m.valid_from <= now()
        and (m.valid_until is null or m.valid_until > now());
    $$;
    """)

    # Server-side session liveness (sign-out / revocation before token expiry). Only on Supabase.
    op.execute("""
    do $$ begin
      if to_regclass('auth.sessions') is not null then
        execute $f$
          create or replace function app.session_is_active(p_session uuid, p_user uuid) returns boolean
          language sql stable security definer set search_path = '' as $b$
            select exists (select 1 from auth.sessions s
                           where s.id = p_session and s.user_id = p_user
                             and (s.not_after is null or s.not_after > now()));
          $b$;
        $f$;
      else
        execute $f$
          create or replace function app.session_is_active(p_session uuid, p_user uuid) returns boolean
          language sql stable set search_path = '' as $b$ select null::boolean; $b$;
        $f$;
      end if;
    end $$;
    """)

    for fn in ("set_request_context(uuid, uuid)", "current_user_id()", "current_org_id()",
               "has_capability(text)", "has_professional_scope(text)", "user_org_ids()",
               "session_is_active(uuid, uuid)"):
        op.execute(f"revoke all on function app.{fn} from public")
        op.execute(f"grant execute on function app.{fn} to pawguard_api, pawguard_worker")

    # ---------- RLS ----------
    op.execute("""
    alter table app.organisations enable row level security;
    alter table app.organisations force row level security;
    create policy organisations_select on app.organisations for select
      using (id in (select app.user_org_ids()));
    create policy organisations_update on app.organisations for update
      using (id = (select app.current_org_id()) and (select app.has_capability('member.manage')))
      with check (id = (select app.current_org_id()));

    alter table app.user_profiles enable row level security;
    alter table app.user_profiles force row level security;
    create policy user_profiles_select on app.user_profiles for select
      using (user_id = (select app.current_user_id())
             or exists (select 1 from app.memberships m
                        where m.user_id = user_profiles.user_id and m.org_id = (select app.current_org_id())));
    create policy user_profiles_insert on app.user_profiles for insert
      with check (user_id = (select app.current_user_id()));
    create policy user_profiles_update on app.user_profiles for update
      using (user_id = (select app.current_user_id())) with check (user_id = (select app.current_user_id()));

    alter table app.memberships enable row level security;
    alter table app.memberships force row level security;
    create policy memberships_select on app.memberships for select
      using (user_id = (select app.current_user_id()) or org_id = (select app.current_org_id()));
    create policy memberships_insert on app.memberships for insert
      with check (org_id = (select app.current_org_id()) and (select app.has_capability('member.manage')));
    create policy memberships_update on app.memberships for update
      using (org_id = (select app.current_org_id()) and (select app.has_capability('member.manage')))
      with check (org_id = (select app.current_org_id()));

    alter table app.professional_approvals enable row level security;
    alter table app.professional_approvals force row level security;
    create policy professional_approvals_select on app.professional_approvals for select
      using (org_id = (select app.current_org_id()) or user_id = (select app.current_user_id()));
    create policy professional_approvals_write on app.professional_approvals for insert
      with check (org_id = (select app.current_org_id()) and (select app.has_capability('professional.approve'))
                  and reviewer_user_id = (select app.current_user_id()));
    create policy professional_approvals_update on app.professional_approvals for update
      using (org_id = (select app.current_org_id()) and (select app.has_capability('professional.approve')))
      with check (org_id = (select app.current_org_id()));

    alter table app.audit_events enable row level security;
    alter table app.audit_events force row level security;
    create policy audit_events_select on app.audit_events for select
      using (org_id = (select app.current_org_id()) and (select app.has_capability('audit.read')));
    create policy audit_events_insert on app.audit_events for insert
      with check ((org_id = (select app.current_org_id()))
                  or (org_id is null and actor_user_id = (select app.current_user_id())));
    """)

    op.execute("""
    grant select, update on app.organisations to pawguard_api;
    grant select, insert, update on app.user_profiles to pawguard_api;
    grant select, insert, update on app.memberships to pawguard_api;
    grant select, insert, update on app.professional_approvals to pawguard_api;
    grant select, insert on app.audit_events to pawguard_api, pawguard_worker;
    grant select on app.organisations to pawguard_worker;
    """)


def downgrade() -> None:
    op.execute("drop schema if exists app cascade")
    # Roles are cluster-wide and may own objects in other databases; they are dropped manually if needed.
