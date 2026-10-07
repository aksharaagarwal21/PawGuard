"""Signed vaccination credentials (ADR 0010, 0011).

- `clinic_signing_keys`: one active Ed25519 key per organisation; the private key is stored sealed (AES-GCM under a
  master key that is never in the database). Row-level security with no policies: the API reaches it only through
  the functions below (its own organisation's sealed key for signing; public keys for the trust list).
- `vaccination_credentials`: the signed QR text for a verified vaccination; one active credential per record. Written
  only through functions that check the record is verified and belongs to the caller's organisation.
- `signing_list_versions`: version numbers of the trust list and the revocation list, bumped by triggers in the same
  transaction as the key or revocation change.

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-07
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
    -- A verified record that a vet later corrects becomes 'superseded' and keeps who verified it (history); records
    -- that were never verified still cannot carry a verifier.
    alter table app.animal_vaccination_events drop constraint animal_vaccination_events_check5;
    alter table app.animal_vaccination_events add constraint animal_vaccination_events_verifier_check check (
      (state <> 'verified' or (verified_by is not null and verified_at is not null))
      and (state in ('verified','superseded') or (verified_by is null and verified_at is null)));

    create table app.signing_list_versions (
      name text primary key check (name in ('trust','revocation')),
      version bigint not null default 1,
      updated_at timestamptz not null default now()
    );
    insert into app.signing_list_versions (name) values ('trust'), ('revocation');
    alter table app.signing_list_versions enable row level security;
    alter table app.signing_list_versions force row level security;

    create or replace function app.bump_signing_list(p_name text) returns void
    language sql volatile security definer set search_path = '' as $$
      insert into app.signing_list_versions as v (name, version) values (p_name, 2)
      on conflict (name) do update set version = v.version + 1, updated_at = now();
    $$;
    revoke all on function app.bump_signing_list(text) from public;

    create table app.clinic_signing_keys (
      id uuid primary key default extensions.gen_random_uuid(),
      org_id uuid not null references app.organisations(id),
      kid text not null unique check (kid ~ '^[0-9a-f]{16}$'),
      public_key bytea not null check (octet_length(public_key) = 32),
      private_key_sealed bytea not null check (octet_length(private_key_sealed) between 40 and 200),
      status text not null default 'active' check (status in ('active','retired','revoked')),
      created_at timestamptz not null default now(),
      retired_at timestamptz,
      revoked_at timestamptz,
      revoke_reason text check (char_length(revoke_reason) <= 300),
      created_by uuid
    );
    create unique index clinic_signing_keys_one_active on app.clinic_signing_keys (org_id) where status = 'active';
    alter table app.clinic_signing_keys enable row level security;
    alter table app.clinic_signing_keys force row level security;
    revoke all on app.clinic_signing_keys from public;

    create or replace function app.signing_keys_changed() returns trigger
    language plpgsql security definer set search_path = '' as $$
    begin
      perform app.bump_signing_list('trust');
      return null;
    end $$;
    create trigger clinic_signing_keys_version after insert or update on app.clinic_signing_keys
      for each statement execute function app.signing_keys_changed();

    create table app.vaccination_credentials (
      id uuid primary key,
      org_id uuid not null references app.organisations(id),
      event_id uuid not null references app.animal_vaccination_events(id),
      animal_id uuid not null references app.animals(id),
      kid text not null references app.clinic_signing_keys(kid),
      qr_text text not null check (char_length(qr_text) <= 2000 and qr_text like 'PG1:%'),
      issued_at timestamptz not null,
      state text not null default 'active' check (state in ('active','revoked')),
      revoked_at timestamptz,
      revoke_reason text check (char_length(revoke_reason) <= 300),
      replaced_by uuid references app.vaccination_credentials(id) deferrable initially deferred,
      is_demo boolean not null default false,
      created_by uuid
    );
    create unique index credentials_one_active on app.vaccination_credentials (event_id) where state = 'active';
    create index credentials_animal on app.vaccination_credentials (animal_id, state);
    alter table app.vaccination_credentials enable row level security;
    alter table app.vaccination_credentials force row level security;
    create policy credentials_tenant on app.vaccination_credentials for select
      using (org_id = (select app.current_org_id()));
    grant select on app.vaccination_credentials to pawguard_api;

    create or replace function app.credentials_changed() returns trigger
    language plpgsql security definer set search_path = '' as $$
    begin
      if new.state = 'revoked' and old.state is distinct from 'revoked' then
        perform app.bump_signing_list('revocation');
      end if;
      return null;
    end $$;
    create trigger vaccination_credentials_revocation after update on app.vaccination_credentials
      for each row execute function app.credentials_changed();

    -- The API may act only for its own organisation; an operator session (the migration owner, which may bypass
    -- row-level security) runs the key commands and the demo seed for any organisation.
    create or replace function app.signing_org_ok(p_org uuid) returns boolean
    language sql stable security definer set search_path = '' as $$
      select p_org = app.current_org_id()
          or coalesce((select r.rolsuper or r.rolbypassrls from pg_catalog.pg_roles r where r.rolname = session_user),
                      false);
    $$;

    -- A new key for the caller's own (active) organisation; becomes active only if none is active.
    create or replace function app.add_signing_key(p_org uuid, p_kid text, p_public bytea, p_sealed bytea,
                                                   p_actor uuid) returns boolean
    language plpgsql volatile security definer set search_path = '' as $$
    declare n integer;
    begin
      if not app.signing_org_ok(p_org) then
        raise exception 'signing key: wrong organisation' using errcode = '42501';
      end if;
      insert into app.clinic_signing_keys (org_id, kid, public_key, private_key_sealed, created_by)
      select p_org, p_kid, p_public, p_sealed, p_actor
       where exists (select 1 from app.organisations o where o.id = p_org and o.activation_state = 'active')
         and not exists (select 1 from app.clinic_signing_keys k where k.org_id = p_org and k.status = 'active');
      get diagnostics n = row_count;
      return n > 0;
    end $$;

    -- The sealed active key of the caller's own organisation (decrypted only in the API process).
    create or replace function app.signing_key_for_issue(p_org uuid)
    returns table (kid text, sealed bytea) language sql stable security definer set search_path = '' as $$
      select k.kid, k.private_key_sealed from app.clinic_signing_keys k
       where k.org_id = p_org and app.signing_org_ok(p_org) and k.status = 'active';
    $$;

    -- Public keys for the trust list (all organisations; retired keys stay so older certificates still verify).
    create or replace function app.trust_keys()
    returns table (kid text, org_id uuid, org_name text, public_key bytea, valid_from timestamptz,
                   valid_to timestamptz, status text, is_demo boolean)
    language sql stable security definer set search_path = '' as $$
      select k.kid, k.org_id, o.name, k.public_key, k.created_at, coalesce(k.retired_at, k.revoked_at), k.status,
             o.is_demo
        from app.clinic_signing_keys k join app.organisations o on o.id = k.org_id
       order by k.created_at;
    $$;

    create or replace function app.revoked_credentials()
    returns table (id uuid) language sql stable security definer set search_path = '' as $$
      select c.id from app.vaccination_credentials c where c.state = 'revoked' order by c.revoked_at;
    $$;

    create or replace function app.signing_list_version(p_name text) returns bigint
    language sql stable security definer set search_path = '' as $$
      select coalesce((select version from app.signing_list_versions where name = p_name), 1);
    $$;

    -- Store a credential: the record must be verified and belong to the caller's organisation. Owner-entered
    -- records that no vet has verified can never get one.
    create or replace function app.store_credential(p_id uuid, p_event uuid, p_kid text, p_qr text,
                                                    p_issued_at timestamptz, p_actor uuid) returns void
    language plpgsql volatile security definer set search_path = '' as $$
    declare e record;
    begin
      select v.id, v.org_id, v.animal_id, v.state, v.is_demo into e
        from app.animal_vaccination_events v where v.id = p_event for update;
      if e.id is null or not app.signing_org_ok(e.org_id) then
        raise exception 'credential: record not in this organisation' using errcode = '42501';
      end if;
      if e.state <> 'verified' then
        raise exception 'credential: record is not verified' using errcode = '22023';
      end if;
      if not exists (select 1 from app.clinic_signing_keys k where k.kid = p_kid and k.org_id = e.org_id
                                                             and k.status = 'active') then
        raise exception 'credential: key is not the active key of this organisation' using errcode = '42501';
      end if;
      insert into app.vaccination_credentials (id, org_id, event_id, animal_id, kid, qr_text, issued_at, is_demo,
                                               created_by)
      values (p_id, e.org_id, p_event, e.animal_id, p_kid, p_qr, p_issued_at, e.is_demo, p_actor);
    end $$;

    -- Revoke (cancel or replace) credentials of the caller's organisation.
    create or replace function app.revoke_credential(p_id uuid, p_reason text, p_replaced_by uuid) returns boolean
    language plpgsql volatile security definer set search_path = '' as $$
    declare n integer;
    begin
      update app.vaccination_credentials
         set state = 'revoked', revoked_at = now(), revoke_reason = left(p_reason, 300), replaced_by = p_replaced_by
       where id = p_id and state = 'active' and app.signing_org_ok(org_id);
      get diagnostics n = row_count;
      return n > 0;
    end $$;

    -- Pet photo for comparison on the verify page (active credentials only; no owner or location data).
    create or replace function app.credential_photo_key(p_id uuid) returns text
    language sql stable security definer set search_path = '' as $$
      select (select m.derivatives->>'thumb' from app.observation_media om
                join app.animal_observations o on o.id = om.observation_id
                join app.media_assets m on m.id = om.media_id
               where o.animal_id = c.animal_id and m.state = 'approved' order by o.created_at limit 1)
        from app.vaccination_credentials c
        join app.animals a on a.id = c.animal_id
       where c.id = p_id and c.state = 'active' and a.profile_state not in ('archived','merged_alias');
    $$;


    -- Demo mode only (checked in the API): sample certificates from DEMO organisations — never real ones.
    create or replace function app.demo_sample_certificates()
    returns table (genuine text, cancelled text) language sql stable security definer set search_path = '' as $$
      select (select c.qr_text from app.vaccination_credentials c
                join app.animals a on a.id = c.animal_id
                join app.animal_vaccination_events e on e.id = c.event_id
                join app.vaccine_products p on p.id = e.product_id
               where c.is_demo and c.state = 'active' and a.nickname = 'Bruno' and p.name ilike '%rabies%'
               order by c.issued_at desc limit 1),
             (select c.qr_text from app.vaccination_credentials c
               where c.is_demo and c.state = 'revoked' order by c.revoked_at desc limit 1);
    $$;

    revoke all on function app.add_signing_key(uuid, text, bytea, bytea, uuid), app.signing_key_for_issue(uuid),
      app.trust_keys(), app.revoked_credentials(), app.signing_list_version(text),
      app.store_credential(uuid, uuid, text, text, timestamptz, uuid), app.revoke_credential(uuid, text, uuid),
      app.credential_photo_key(uuid), app.signing_keys_changed(), app.credentials_changed(),
      app.signing_org_ok(uuid), app.demo_sample_certificates() from public;
    grant execute on function app.add_signing_key(uuid, text, bytea, bytea, uuid), app.signing_key_for_issue(uuid),
      app.trust_keys(), app.revoked_credentials(), app.signing_list_version(text),
      app.store_credential(uuid, uuid, text, text, timestamptz, uuid), app.revoke_credential(uuid, text, uuid),
      app.credential_photo_key(uuid), app.demo_sample_certificates() to pawguard_api;
    """)


def downgrade() -> None:
    op.execute("""
    alter table app.animal_vaccination_events drop constraint if exists animal_vaccination_events_verifier_check;
    update app.animal_vaccination_events set verified_by = null, verified_at = null where state = 'superseded';
    alter table app.animal_vaccination_events add constraint animal_vaccination_events_check5
      check ((state = 'verified') = ((verified_by is not null) and (verified_at is not null)));
    drop function if exists app.add_signing_key(uuid, text, bytea, bytea, uuid), app.signing_key_for_issue(uuid),
      app.trust_keys(), app.revoked_credentials(), app.signing_list_version(text),
      app.store_credential(uuid, uuid, text, text, timestamptz, uuid), app.revoke_credential(uuid, text, uuid),
      app.credential_photo_key(uuid), app.signing_org_ok(uuid), app.demo_sample_certificates();
    drop table if exists app.vaccination_credentials;
    drop table if exists app.clinic_signing_keys;
    drop function if exists app.signing_keys_changed(), app.credentials_changed();
    drop table if exists app.signing_list_versions;
    drop function if exists app.bump_signing_list(text);
    """)
