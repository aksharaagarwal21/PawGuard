"""'This pet bit someone' instant check: bite reports, 10-day observation, daily check-ins, private share links.

- `observation_periods`: one per pet and bite date (a second report of the same bite joins it). Length comes from a
  policy note (10 days for dogs and cats, WHO FAQ 2018 — pending clinical review). Status moves to completed /
  completed_with_gaps / change_reported when the period ends; it never says "safe" or "rabies-free".
- `bite_reports`: what the reporter said (date, optional time, person or animal bitten, coarse area, note), an
  optional contact sealed with the master key (AES-GCM; only with consent), consent flags, status, duplicate link.
- `observation_checkins`: one state per day per source (owner-reported or vet-recorded). A missing day is shown as
  "No update" by the application — never filled in.
- `share_links`: the reporter's private tracking link and doctor links (random token; only its SHA-256 hash is
  stored), expiry, revocation, and an access log.
- Public access only through the security-definer functions below, with limits (per client per hour, per pet per day,
  per report). Owners and clinic staff use normal row security through their clinic membership.
- Owners are told on their chosen channels (delivery kind 'bite_alert', message without reporter details).

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-07
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
    alter table app.organisations add column contact_phone text
      check (contact_phone is null or contact_phone ~ '^\\+?[0-9 ()-]{6,20}$');

    create table app.observation_periods (
      id uuid primary key default extensions.gen_random_uuid(),
      org_id uuid not null references app.organisations(id),
      animal_id uuid not null,
      bite_date date not null,
      length_days integer not null default 10 check (length_days between 1 and 30),
      policy_note text not null default 'Observe the biting dog or cat for 10 days (WHO, 2018) - pending clinical review'
        check (char_length(policy_note) <= 200),
      status text not null default 'active'
        check (status in ('active','completed','completed_with_gaps','change_reported')),
      closed_at timestamptz,
      close_notified boolean not null default false,
      is_demo boolean not null default false,
      created_at timestamptz not null default now(),
      foreign key (animal_id, org_id) references app.animals(id, org_id),
      unique (animal_id, bite_date)
    );

    create table app.bite_reports (
      id uuid primary key default extensions.gen_random_uuid(),
      org_id uuid not null references app.organisations(id),
      animal_id uuid not null,
      period_id uuid not null references app.observation_periods(id),
      reference text not null unique check (reference ~ '^BR-[A-Z0-9]{4}-[A-Z0-9]{4}$'),
      bite_date date not null,
      bite_time text check (bite_time is null or bite_time ~ '^([01][0-9]|2[0-3]):[0-5][0-9]$'),
      bitten text not null check (bitten in ('person','animal')),
      area text check (char_length(area) <= 80),
      note text check (char_length(note) <= 500),
      contact_sealed bytea check (octet_length(contact_sealed) <= 600),
      contact_kind text check (contact_kind is null or contact_kind = 'email'),
      consent_updates boolean not null default false,
      consent_share_with_owner boolean not null default false,
      status text not null default 'under_observation'
        check (status in ('open','under_observation','closed','disputed','withdrawn')),
      duplicate_of uuid references app.bite_reports(id),
      dispute_reason text check (char_length(dispute_reason) <= 500),
      disputed_at timestamptz,
      client_hash text check (char_length(client_hash) <= 64),
      is_demo boolean not null default false,
      created_at timestamptz not null default now(),
      foreign key (animal_id, org_id) references app.animals(id, org_id)
    );
    create index bite_reports_animal on app.bite_reports (animal_id, created_at);
    create index bite_reports_client on app.bite_reports (client_hash, created_at);

    create table app.observation_checkins (
      id uuid primary key default extensions.gen_random_uuid(),
      org_id uuid not null references app.organisations(id),
      period_id uuid not null references app.observation_periods(id),
      day_number integer not null check (day_number between 1 and 30),
      checkin_date date not null,
      state text not null check (state in ('normal','not_eating','unusual_behaviour','missing','died','other')),
      note text check (char_length(note) <= 300),
      source text not null check (source in ('owner','vet')),
      recorded_by uuid,
      created_at timestamptz not null default now(),
      updated_at timestamptz not null default now(),
      unique (period_id, day_number, source)
    );

    create table app.share_links (
      id uuid primary key default extensions.gen_random_uuid(),
      org_id uuid not null references app.organisations(id),
      report_id uuid not null references app.bite_reports(id),
      purpose text not null check (purpose in ('reporter','doctor')),
      token_hash text not null unique check (char_length(token_hash) = 64),
      expires_at timestamptz not null,
      revoked_at timestamptz,
      created_at timestamptz not null default now()
    );
    create table app.share_link_access (
      id uuid primary key default extensions.gen_random_uuid(),
      link_id uuid not null references app.share_links(id),
      accessed_at timestamptz not null default now()
    );

    alter table app.observation_periods enable row level security;
    alter table app.observation_periods force row level security;
    alter table app.bite_reports enable row level security;
    alter table app.bite_reports force row level security;
    alter table app.observation_checkins enable row level security;
    alter table app.observation_checkins force row level security;
    alter table app.share_links enable row level security;
    alter table app.share_links force row level security;
    alter table app.share_link_access enable row level security;
    alter table app.share_link_access force row level security;
    create policy observation_periods_tenant on app.observation_periods for all
      using (org_id = (select app.current_org_id())) with check (org_id = (select app.current_org_id()));
    create policy bite_reports_tenant on app.bite_reports for all
      using (org_id = (select app.current_org_id())) with check (org_id = (select app.current_org_id()));
    create policy observation_checkins_tenant on app.observation_checkins for all
      using (org_id = (select app.current_org_id())) with check (org_id = (select app.current_org_id()));
    grant select, update on app.observation_periods to pawguard_api;
    grant select, update (status, dispute_reason, disputed_at) on app.bite_reports to pawguard_api;
    grant select, insert, update on app.observation_checkins to pawguard_api;
    -- share_links / share_link_access: functions only.

    -- Notifications: owner alerts about a bite (no reporter details), linked to the observation period.
    alter table app.notification_deliveries add column observation_period_id uuid
      references app.observation_periods(id);
    alter table app.notification_deliveries drop constraint notification_deliveries_kind_check;
    alter table app.notification_deliveries add constraint notification_deliveries_kind_check
      check (kind in ('vaccination_reminder','test','verify_email','lost_message','demo_reminder','bite_alert',
                      'bite_closed'));

    create or replace function app.queue_bite_notice(p_period uuid, p_kind text)
    returns integer language plpgsql volatile security definer set search_path = '' as $$
    declare n integer;
    begin
      insert into app.notification_deliveries (org_id, user_id, channel, kind, animal_id, observation_period_id,
                                               dedupe_key, is_demo)
      select op.org_id, c.linked_user_id, ch.channel, p_kind, op.animal_id, op.id,
             p_kind || ':' || op.id || ':' || c.linked_user_id || ':' || ch.channel, op.is_demo
        from app.observation_periods op
        join app.animal_caregivers c on c.animal_id = op.animal_id and c.relationship = 'owner'
             and c.linked_user_id is not null and (c.valid_to is null or c.valid_to > current_date)
        join app.notification_preferences p on p.user_id = c.linked_user_id
        cross join lateral (values ('email', p.email_enabled and p.email_verified_at is not null),
                                   ('push', p.push_enabled), ('whatsapp', p.whatsapp_enabled)) as ch(channel, enabled)
       where op.id = p_period and ch.enabled
      on conflict (dedupe_key) do nothing;
      get diagnostics n = row_count;
      return n;
    end $$;

    -- Public bite mode (from the collar QR): pet basics, clinic contact and the latest verified rabies record with
    -- its signed certificate. Nothing about the owner or any location. Unknown/revoked card: no rows.
    create or replace function app.public_bite_pet(p_card_token text) returns jsonb
    language sql stable security definer set search_path = '' as $$
      select jsonb_build_object(
        'pet_name', coalesce(a.nickname, a.reference_code), 'species', a.species, 'sex', a.sex,
        'clinic_name', o.name, 'clinic_email', o.contact_email, 'clinic_phone', o.contact_phone, 'is_demo', a.is_demo,
        'rabies', (select jsonb_build_object('vaccine', coalesce(p.name, e.product_text), 'given_on', e.administered_on,
                                             'next_due_on', e.next_review_on,
                                             'certificate', (select cr.qr_text from app.vaccination_credentials cr
                                                              where cr.event_id = e.id and cr.state = 'active'))
                     from app.animal_vaccination_events e
                     left join app.vaccine_products p on p.id = e.product_id
                    where e.animal_id = a.id and e.state = 'verified'
                      and coalesce(p.name, e.product_text) ilike '%rabies%'
                    order by e.administered_on desc nulls last limit 1))
        from app.pet_cards c
        join app.animals a on a.id = c.animal_id
        join app.organisations o on o.id = c.org_id
       where c.token = p_card_token and c.revoked_at is null and a.profile_state not in ('archived','merged_alias');
    $$;

    -- Create a report from the public card. Limits: 3 per client per hour, 5 per pet per day; bite date within the
    -- last 30 days and not in the future (organisation's local date). A second report of the same pet and day joins
    -- the existing observation period and is marked as a possible duplicate. The reporter link expires 60 days after
    -- the bite. The owner is told on their channels (once per period).
    create or replace function app.public_create_bite_report(
      p_card_token text, p_reference text, p_bite_date date, p_bite_time text, p_bitten text, p_area text,
      p_note text, p_contact_sealed bytea, p_contact_kind text, p_consent_updates boolean, p_consent_share boolean,
      p_client_hash text, p_reporter_hash text) returns jsonb
    language plpgsql volatile security definer set search_path = '' as $$
    declare v_card record; v_today date; v_period uuid; v_first uuid; v_report uuid; v_new_period boolean := false;
    begin
      select c.animal_id, c.org_id, a.is_demo, o.timezone into v_card
        from app.pet_cards c join app.animals a on a.id = c.animal_id join app.organisations o on o.id = c.org_id
       where c.token = p_card_token and c.revoked_at is null and a.profile_state not in ('archived','merged_alias');
      if v_card is null then return jsonb_build_object('error', 'not_found'); end if;
      v_today := (now() at time zone v_card.timezone)::date;
      if p_bite_date > v_today or p_bite_date < v_today - 30 then
        return jsonb_build_object('error', 'bad_date');
      end if;
      if (select count(*) from app.bite_reports where client_hash = p_client_hash
            and created_at > now() - interval '1 hour') >= 3
         or (select count(*) from app.bite_reports where animal_id = v_card.animal_id
            and created_at > now() - interval '1 day') >= 5 then
        return jsonb_build_object('error', 'rate_limited');
      end if;
      select id into v_period from app.observation_periods where animal_id = v_card.animal_id and bite_date = p_bite_date;
      if v_period is null then
        insert into app.observation_periods (org_id, animal_id, bite_date, is_demo)
        values (v_card.org_id, v_card.animal_id, p_bite_date, v_card.is_demo) returning id into v_period;
        v_new_period := true;
      end if;
      select id into v_first from app.bite_reports where period_id = v_period order by created_at limit 1;
      insert into app.bite_reports (org_id, animal_id, period_id, reference, bite_date, bite_time, bitten, area, note,
                                    contact_sealed, contact_kind, consent_updates, consent_share_with_owner,
                                    duplicate_of, client_hash, is_demo)
      values (v_card.org_id, v_card.animal_id, v_period, p_reference, p_bite_date, nullif(p_bite_time, ''), p_bitten,
              nullif(left(p_area, 80), ''), nullif(left(p_note, 500), ''), p_contact_sealed, p_contact_kind,
              coalesce(p_consent_updates, false), coalesce(p_consent_share, false), v_first, p_client_hash,
              v_card.is_demo)
      returning id into v_report;
      insert into app.share_links (org_id, report_id, purpose, token_hash, expires_at)
      values (v_card.org_id, v_report, 'reporter', p_reporter_hash, (p_bite_date + 60)::timestamptz);
      if v_new_period then perform app.queue_bite_notice(v_period, 'bite_alert'); end if;
      return jsonb_build_object('report_id', v_report, 'period_id', v_period, 'duplicate', v_first is not null);
    end $$;

    -- Read a share link (reporter or doctor): logs the access; expired or revoked links return nothing.
    create or replace function app.share_view(p_token_hash text) returns jsonb
    language plpgsql volatile security definer set search_path = '' as $$
    declare v_link record; v_out jsonb;
    begin
      select l.* into v_link from app.share_links l
       where l.token_hash = p_token_hash and l.revoked_at is null and l.expires_at > now();
      if v_link is null then return null; end if;
      insert into app.share_link_access (link_id) values (v_link.id);
      select jsonb_build_object(
        'purpose', v_link.purpose, 'expires_at', v_link.expires_at,
        'reference', r.reference, 'bite_date', r.bite_date, 'bite_time', r.bite_time, 'bitten', r.bitten,
        'report_status', r.status, 'timezone', o.timezone, 'is_demo', r.is_demo,
        'pet_name', coalesce(a.nickname, a.reference_code), 'species', a.species,
        'clinic_name', o.name, 'clinic_email', o.contact_email, 'clinic_phone', o.contact_phone,
        'period', jsonb_build_object('bite_date', op.bite_date, 'length_days', op.length_days, 'status', op.status,
                                     'policy_note', op.policy_note),
        'checkins', coalesce((select jsonb_agg(jsonb_build_object('day', ch.day_number, 'date', ch.checkin_date,
                                                                 'state', ch.state, 'source', ch.source)
                                               order by ch.day_number, ch.source)
                              from app.observation_checkins ch where ch.period_id = op.id), '[]'::jsonb),
        'rabies', (select jsonb_build_object('vaccine', coalesce(p.name, e.product_text), 'given_on', e.administered_on,
                                             'next_due_on', e.next_review_on,
                                             'certificate', (select cr.qr_text from app.vaccination_credentials cr
                                                              where cr.event_id = e.id and cr.state = 'active'))
                     from app.animal_vaccination_events e
                     left join app.vaccine_products p on p.id = e.product_id
                    where e.animal_id = a.id and e.state = 'verified'
                      and coalesce(p.name, e.product_text) ilike '%rabies%'
                    order by e.administered_on desc nulls last limit 1),
        'doctor_links', case when v_link.purpose = 'reporter' then
             coalesce((select jsonb_agg(jsonb_build_object('id', d.id, 'expires_at', d.expires_at,
                                                           'created_at', d.created_at,
                                                           'views', (select count(*) from app.share_link_access x
                                                                      where x.link_id = d.id)) order by d.created_at)
                       from app.share_links d where d.report_id = r.id and d.purpose = 'doctor'
                         and d.revoked_at is null and d.expires_at > now()), '[]'::jsonb) end)
        into v_out
        from app.bite_reports r
        join app.observation_periods op on op.id = r.period_id
        join app.animals a on a.id = r.animal_id
        join app.organisations o on o.id = r.org_id
       where r.id = v_link.report_id;
      return v_out;
    end $$;

    -- The reporter makes a doctor link (30 days; at most 5 live per report).
    create or replace function app.share_create_doctor_link(p_reporter_hash text, p_doctor_hash text) returns boolean
    language plpgsql volatile security definer set search_path = '' as $$
    declare v_link record;
    begin
      select l.* into v_link from app.share_links l where l.token_hash = p_reporter_hash and l.purpose = 'reporter'
         and l.revoked_at is null and l.expires_at > now();
      if v_link is null then return false; end if;
      if (select count(*) from app.share_links where report_id = v_link.report_id and purpose = 'doctor'
            and revoked_at is null and expires_at > now()) >= 5 then return false; end if;
      insert into app.share_links (org_id, report_id, purpose, token_hash, expires_at)
      values (v_link.org_id, v_link.report_id, 'doctor', p_doctor_hash, now() + interval '30 days');
      return true;
    end $$;

    -- The reporter revokes all doctor links of their report.
    create or replace function app.share_revoke_doctor_links(p_reporter_hash text) returns integer
    language plpgsql volatile security definer set search_path = '' as $$
    declare v_link record; n integer;
    begin
      select l.* into v_link from app.share_links l where l.token_hash = p_reporter_hash and l.purpose = 'reporter'
         and l.revoked_at is null and l.expires_at > now();
      if v_link is null then return 0; end if;
      update app.share_links set revoked_at = now()
       where report_id = v_link.report_id and purpose = 'doctor' and revoked_at is null;
      get diagnostics n = row_count;
      return n;
    end $$;

    -- Reporter contacts (sealed) for update emails: only reports that consented to updates.
    create or replace function app.bite_update_contacts(p_period uuid)
    returns table (reference text, contact_sealed bytea) language sql stable security definer set search_path = '' as $$
      select r.reference, r.contact_sealed from app.bite_reports r
       where r.period_id = p_period and r.consent_updates and r.contact_sealed is not null
         and r.status <> 'withdrawn';
    $$;

    -- End observation periods whose last day has passed (organisation's local date). Outcome from the check-ins:
    -- any change reported → change_reported; any day without an owner or vet update → completed_with_gaps;
    -- otherwise completed. Returns the periods closed now (for notices).
    create or replace function app.close_due_observations() returns table (period_id uuid, status text)
    language plpgsql volatile security definer set search_path = '' as $$
    begin
      return query
      with due as (
        select op.id, op.length_days from app.observation_periods op
        join app.organisations o on o.id = op.org_id
        left join app.demo_clock dc on dc.org_id = op.org_id
        where op.status = 'active'
          and ((now() at time zone o.timezone)::date + coalesce(dc.offset_days, 0)) > op.bite_date + op.length_days
      ), outcome as (
        select d.id,
               case when exists (select 1 from app.observation_checkins c where c.period_id = d.id
                                   and c.state <> 'normal') then 'change_reported'
                    when (select count(distinct c.day_number) from app.observation_checkins c
                           where c.period_id = d.id) < d.length_days then 'completed_with_gaps'
                    else 'completed' end as status
          from due d
      )
      update app.observation_periods op set status = outcome.status, closed_at = now()
        from outcome where op.id = outcome.id
      returning op.id, op.status;
    end $$;

    revoke all on function app.queue_bite_notice(uuid, text), app.public_bite_pet(text),
      app.public_create_bite_report(text, text, date, text, text, text, text, bytea, text, boolean, boolean, text, text),
      app.share_view(text), app.share_create_doctor_link(text, text), app.share_revoke_doctor_links(text),
      app.bite_update_contacts(uuid), app.close_due_observations() from public;
    grant execute on function app.queue_bite_notice(uuid, text), app.public_bite_pet(text),
      app.public_create_bite_report(text, text, date, text, text, text, text, bytea, text, boolean, boolean, text, text),
      app.share_view(text), app.share_create_doctor_link(text, text), app.share_revoke_doctor_links(text),
      app.bite_update_contacts(uuid), app.close_due_observations() to pawguard_api;
    grant execute on function app.queue_bite_notice(uuid, text), app.bite_update_contacts(uuid),
      app.close_due_observations() to pawguard_worker;

    -- The sender needs the bite date and the pet's sex (for "him"/"her") for bite notices.
    create or replace function app.claim_notification_deliveries(p_limit integer) returns setof jsonb
    language plpgsql volatile security definer set search_path = '' as $$
    begin
      return query
      with c as (
        select d.id from app.notification_deliveries d
        where (d.state in ('queued','deferred') and d.available_at <= now())
           or (d.state = 'sending' and d.locked_until < now())
        order by d.available_at limit greatest(1, least(p_limit, 100)) for update skip locked
      ), u as (
        update app.notification_deliveries d set state = 'sending', attempts = d.attempts + 1,
               locked_until = now() + interval '5 minutes'
        from c where d.id = c.id
        returning d.*
      )
      select jsonb_build_object(
        'id', u.id, 'org_id', u.org_id, 'user_id', u.user_id, 'channel', u.channel, 'kind', u.kind,
        'attempts', u.attempts, 'is_demo', u.is_demo, 'org_is_demo', o.is_demo, 'clinic', o.name,
        'provider_message_id', u.provider_message_id, 'send_started', u.send_started_at is not null,
        'today', ((now() at time zone o.timezone)::date + coalesce(dc.offset_days, 0)),
        'pet', coalesce(a.nickname, a.reference_code, a2.nickname, a2.reference_code),
        'pet_sex', coalesce(a.sex, a2.sex),
        'vaccine', r.vaccine_name, 'due_on', r.due_on, 'reminder_kind', r.kind, 'reminder_state', r.state,
        'bite_date', op.bite_date, 'observation_days', op.length_days, 'observation_status', op.status,
        'email_address', p.email_address, 'email_verified', p.email_verified_at is not null,
        'whatsapp_number', p.whatsapp_number, 'call_number', p.call_number,
        'email_enabled', coalesce(p.email_enabled, false), 'push_enabled', coalesce(p.push_enabled, false),
        'whatsapp_enabled', coalesce(p.whatsapp_enabled, false), 'call_enabled', coalesce(p.call_enabled, false),
        'push', coalesce((select jsonb_agg(jsonb_build_object('endpoint', s.endpoint, 'p256dh', s.p256dh,
                                                              'auth', s.auth))
                          from app.push_subscriptions s where s.user_id = u.user_id and s.revoked_at is null),
                         '[]'::jsonb))
      from u
      join app.organisations o on o.id = u.org_id
      left join app.demo_clock dc on dc.org_id = u.org_id
      left join app.vaccination_reminders r on r.id = u.reminder_id
      left join app.animals a on a.id = r.animal_id
      left join app.animals a2 on a2.id = u.animal_id
      left join app.observation_periods op on op.id = u.observation_period_id
      left join app.notification_preferences p on p.user_id = u.user_id;
    end $$;
    """)


def downgrade() -> None:
    op.execute("""
    drop function if exists app.queue_bite_notice(uuid, text), app.public_bite_pet(text),
      app.public_create_bite_report(text, text, date, text, text, text, text, bytea, text, boolean, boolean, text, text),
      app.share_view(text), app.share_create_doctor_link(text, text), app.share_revoke_doctor_links(text),
      app.bite_update_contacts(uuid), app.close_due_observations();
    delete from app.notification_deliveries where kind in ('bite_alert','bite_closed');
    alter table app.notification_deliveries drop column if exists observation_period_id;
    alter table app.notification_deliveries drop constraint notification_deliveries_kind_check;
    alter table app.notification_deliveries add constraint notification_deliveries_kind_check
      check (kind in ('vaccination_reminder','test','verify_email','lost_message','demo_reminder'));
    drop table if exists app.share_link_access, app.share_links, app.observation_checkins, app.bite_reports,
      app.observation_periods;
    alter table app.organisations drop column if exists contact_phone;
    """)
