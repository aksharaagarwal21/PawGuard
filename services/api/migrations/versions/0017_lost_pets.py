"""Lost pets and private finder ↔ owner messages (no phone masking, no accounts needed for finders).

- `lost_reports`: an owner marks a pet lost (last seen date, area in words, a note) and later found.
- `lost_threads` / `lost_messages`: a finder who scans the pet's QR tag can write to the owner. The finder gets a
  private conversation link (random token; only its SHA-256 hash is stored) to read replies. The owner's name, phone and
  email are never shown; the finder shares a contact only if they choose to.
- Public access goes only through narrow security-definer functions with limits (per pet per day, per conversation
  per day, lengths). Owners use normal row security through their clinic membership.
- New finder messages notify the owner on their chosen channels (delivery kind 'lost_message'; the notification never
  contains the message text).

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-07
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
    create table app.lost_reports (
      id uuid primary key default extensions.gen_random_uuid(),
      org_id uuid not null references app.organisations(id),
      animal_id uuid not null,
      owner_user_id uuid not null,
      state text not null default 'open' check (state in ('open','found','cancelled')),
      last_seen_on date,
      area_text text check (char_length(area_text) <= 120),
      note text check (char_length(note) <= 300),
      created_at timestamptz not null default now(),
      closed_at timestamptz,
      is_demo boolean not null default false,
      foreign key (animal_id, org_id) references app.animals(id, org_id)
    );
    create unique index lost_reports_one_open on app.lost_reports (animal_id) where state = 'open';

    create table app.lost_threads (
      id uuid primary key default extensions.gen_random_uuid(),
      org_id uuid not null references app.organisations(id),
      animal_id uuid not null,
      report_id uuid not null references app.lost_reports(id),
      finder_token_hash text not null unique check (char_length(finder_token_hash) = 64),
      finder_contact text check (char_length(finder_contact) <= 120),
      created_at timestamptz not null default now(),
      last_message_at timestamptz not null default now(),
      is_demo boolean not null default false
    );
    create table app.lost_messages (
      id uuid primary key default extensions.gen_random_uuid(),
      org_id uuid not null references app.organisations(id),
      thread_id uuid not null references app.lost_threads(id),
      sender text not null check (sender in ('finder','owner')),
      body text not null check (char_length(body) between 1 and 500),
      created_at timestamptz not null default now(),
      read_by_owner_at timestamptz,
      is_demo boolean not null default false
    );
    create index lost_messages_thread on app.lost_messages (thread_id, created_at);

    alter table app.notification_deliveries add column animal_id uuid;
    alter table app.notification_deliveries drop constraint notification_deliveries_kind_check;
    alter table app.notification_deliveries add constraint notification_deliveries_kind_check
      check (kind in ('vaccination_reminder','test','verify_email','lost_message'));
    """)
    for t in ("lost_reports", "lost_threads", "lost_messages"):
        op.execute(f"""
        create trigger {t}_demo_flag before insert on app.{t} for each row execute function app.inherit_demo_flag();
        alter table app.{t} enable row level security;
        alter table app.{t} force row level security;
        create policy {t}_tenant on app.{t} for all
          using (org_id = (select app.current_org_id())) with check (org_id = (select app.current_org_id()));
        grant select, insert, update on app.{t} to pawguard_api;
        """)
    op.execute("""
    -- Public card: is this pet reported lost? (Shown on the QR card page.)
    create or replace function app.public_lost_status(p_card_token text)
    returns table (lost boolean, last_seen_on date, area_text text)
    language sql stable security definer set search_path = '' as $$
      select (r.id is not null), r.last_seen_on, r.area_text
        from app.pet_cards c
        left join app.lost_reports r on r.animal_id = c.animal_id and r.state = 'open'
       where c.token = p_card_token and c.revoked_at is null;
    $$;

    -- Finder writes first: needs a live card and an open lost report. Limits: 20 new conversations per pet per day.
    create or replace function app.finder_start_thread(p_card_token text, p_token_hash text, p_body text,
                                                       p_contact text)
    returns uuid language plpgsql volatile security definer set search_path = '' as $$
    declare v_card record; v_report record; v_thread uuid; v_count integer;
    begin
      select c.org_id, c.animal_id into v_card from app.pet_cards c
       where c.token = p_card_token and c.revoked_at is null;
      if v_card is null then return null; end if;
      select r.id, r.owner_user_id into v_report from app.lost_reports r
       where r.animal_id = v_card.animal_id and r.state = 'open';
      if v_report is null then return null; end if;
      select count(*) into v_count from app.lost_threads
       where animal_id = v_card.animal_id and created_at > now() - interval '1 day';
      if v_count >= 20 then raise exception 'too many conversations today' using errcode = 'P0001'; end if;
      insert into app.lost_threads (org_id, animal_id, report_id, finder_token_hash, finder_contact)
      values (v_card.org_id, v_card.animal_id, v_report.id, p_token_hash, nullif(left(p_contact, 120), ''))
      returning id into v_thread;
      insert into app.lost_messages (org_id, thread_id, sender, body)
      values (v_card.org_id, v_thread, 'finder', left(p_body, 500));
      perform app.queue_lost_message_notice(v_card.org_id, v_report.owner_user_id, v_card.animal_id, v_thread);
      return v_thread;
    end $$;

    -- The finder's private conversation view (by token hash): pet basics and the messages, nothing about the owner.
    create or replace function app.finder_thread(p_token_hash text) returns jsonb
    language sql stable security definer set search_path = '' as $$
      select jsonb_build_object(
        'pet_name', coalesce(a.nickname, a.reference_code), 'species', a.species, 'clinic', o.name,
        'is_demo', a.is_demo, 'open', r.state = 'open', 'found', r.state = 'found',
        'messages', coalesce((select jsonb_agg(jsonb_build_object('sender', m.sender, 'body', m.body,
                                                                  'created_at', m.created_at) order by m.created_at)
                              from app.lost_messages m where m.thread_id = t.id), '[]'::jsonb))
        from app.lost_threads t
        join app.animals a on a.id = t.animal_id
        join app.organisations o on o.id = t.org_id
        join app.lost_reports r on r.id = t.report_id
       where t.finder_token_hash = p_token_hash;
    $$;

    -- Finder replies: open report only; at most 30 finder messages per conversation per day.
    create or replace function app.finder_post(p_token_hash text, p_body text) returns boolean
    language plpgsql volatile security definer set search_path = '' as $$
    declare v_t record; v_count integer;
    begin
      select t.id, t.org_id, t.animal_id, r.owner_user_id, r.state into v_t
        from app.lost_threads t join app.lost_reports r on r.id = t.report_id
       where t.finder_token_hash = p_token_hash;
      if v_t is null or v_t.state <> 'open' then return false; end if;
      select count(*) into v_count from app.lost_messages
       where thread_id = v_t.id and sender = 'finder' and created_at > now() - interval '1 day';
      if v_count >= 30 then raise exception 'too many messages today' using errcode = 'P0001'; end if;
      insert into app.lost_messages (org_id, thread_id, sender, body) values (v_t.org_id, v_t.id, 'finder', left(p_body, 500));
      update app.lost_threads set last_message_at = now() where id = v_t.id;
      perform app.queue_lost_message_notice(v_t.org_id, v_t.owner_user_id, v_t.animal_id, v_t.id);
      return true;
    end $$;

    -- Tell the owner on their chosen channels (at most one notice per conversation per hour; no message text).
    create or replace function app.queue_lost_message_notice(p_org uuid, p_owner uuid, p_animal uuid, p_thread uuid)
    returns void language sql volatile security definer set search_path = '' as $$
      insert into app.notification_deliveries (org_id, user_id, channel, kind, animal_id, dedupe_key)
      select p_org, p_owner, ch.channel, 'lost_message', p_animal,
             'lost:' || p_thread || ':' || ch.channel || ':' || to_char(now(), 'YYYYMMDDHH24')
        from app.notification_preferences p
        cross join lateral (values ('email', p.email_enabled and p.email_verified_at is not null),
                                   ('push', p.push_enabled), ('whatsapp', p.whatsapp_enabled)) as ch(channel, enabled)
       where p.user_id = p_owner and ch.enabled
      on conflict (dedupe_key) do nothing;
    $$;

    revoke all on function app.public_lost_status(text), app.finder_start_thread(text, text, text, text),
      app.finder_thread(text), app.finder_post(text, text), app.queue_lost_message_notice(uuid, uuid, uuid, uuid)
      from public;
    grant execute on function app.public_lost_status(text), app.finder_start_thread(text, text, text, text),
      app.finder_thread(text), app.finder_post(text, text) to pawguard_api;

    -- The sender needs the pet's name for lost-message notices too.
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
        'attempts', u.attempts, 'is_demo', u.is_demo, 'clinic', o.name,
        'today', ((now() at time zone o.timezone)::date + coalesce(dc.offset_days, 0)),
        'pet', coalesce(a.nickname, a.reference_code, a2.nickname, a2.reference_code),
        'vaccine', r.vaccine_name, 'due_on', r.due_on, 'reminder_kind', r.kind, 'reminder_state', r.state,
        'email_address', p.email_address, 'email_verified', p.email_verified_at is not null,
        'whatsapp_number', p.whatsapp_number,
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
      left join app.notification_preferences p on p.user_id = u.user_id;
    end $$;
    """)


def downgrade() -> None:
    op.execute("""
    drop function if exists app.public_lost_status(text), app.finder_start_thread(text, text, text, text),
      app.finder_thread(text), app.finder_post(text, text), app.queue_lost_message_notice(uuid, uuid, uuid, uuid);
    drop table if exists app.lost_messages, app.lost_threads, app.lost_reports;
    alter table app.notification_deliveries drop column if exists animal_id;
    """)
