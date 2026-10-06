"""Outbound notifications on free providers: email (SMTP), Web Push and WhatsApp (Cloud API test number).

- `notification_preferences` (one row per person, opt-in per channel, own row only).
- `push_subscriptions` (browser endpoints; own rows only).
- `notification_deliveries`: the send queue. One row per (reminder kind, channel) — the unique `dedupe_key` makes
  scanning idempotent, so a reminder is never sent twice on the same channel. Owners see their own rows; clinic
  staff with `animal.read` see their clinic's rows.
- `provider_status`: last known state per provider (ok, not configured, token expired, rate limited, daily cap
  reached) so staff see "token expired — renew" instead of silent failures.
- Workers never read these tables directly: they use narrow security-definer functions (queue due reminders,
  claim a batch, finish one, set provider status, count recent sends).

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-07
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
    create table app.notification_preferences (
      user_id uuid primary key,
      email_enabled boolean not null default false,
      email_address text check (email_address is null or (char_length(email_address) <= 254
                                and email_address ~ '^[^@[:space:]]+@[^@[:space:]]+\\.[^@[:space:]]+$')),
      push_enabled boolean not null default false,
      whatsapp_enabled boolean not null default false,
      whatsapp_number text check (whatsapp_number is null or whatsapp_number ~ '^\\+[1-9][0-9]{7,14}$'),
      updated_at timestamptz not null default now()
    );
    alter table app.notification_preferences enable row level security;
    alter table app.notification_preferences force row level security;
    create policy prefs_own on app.notification_preferences for all
      using (user_id = (select app.current_user_id())) with check (user_id = (select app.current_user_id()));
    grant select, insert, update on app.notification_preferences to pawguard_api;

    create table app.push_subscriptions (
      id uuid primary key default extensions.gen_random_uuid(),
      user_id uuid not null,
      endpoint text not null unique check (char_length(endpoint) <= 1000 and endpoint like 'https://%'),
      p256dh text not null check (char_length(p256dh) <= 200),
      auth text not null check (char_length(auth) <= 100),
      user_agent text check (char_length(user_agent) <= 300),
      created_at timestamptz not null default now(),
      last_success_at timestamptz,
      revoked_at timestamptz
    );
    create index push_subscriptions_user on app.push_subscriptions (user_id) where revoked_at is null;
    alter table app.push_subscriptions enable row level security;
    alter table app.push_subscriptions force row level security;
    create policy push_own on app.push_subscriptions for all
      using (user_id = (select app.current_user_id())) with check (user_id = (select app.current_user_id()));
    grant select, insert, update, delete on app.push_subscriptions to pawguard_api;

    create table app.notification_deliveries (
      id uuid primary key default extensions.gen_random_uuid(),
      org_id uuid not null references app.organisations(id),
      user_id uuid not null,
      channel text not null check (channel in ('email','push','whatsapp')),
      kind text not null check (kind in ('vaccination_reminder','test')),
      reminder_id uuid,
      dedupe_key text not null unique check (char_length(dedupe_key) <= 200),
      state text not null default 'queued'
        check (state in ('queued','sending','sent','deferred','failed','skipped')),
      attempts integer not null default 0,
      last_error text check (char_length(last_error) <= 300),
      provider_message_id text check (char_length(provider_message_id) <= 200),
      available_at timestamptz not null default now(),
      locked_until timestamptz,
      sent_at timestamptz,
      is_demo boolean not null default false,
      created_at timestamptz not null default now(),
      updated_at timestamptz not null default now(),
      row_version integer not null default 1
    );
    create index deliveries_ready on app.notification_deliveries (available_at) where state in ('queued','deferred');
    create index deliveries_org on app.notification_deliveries (org_id, created_at desc);
    create trigger notification_deliveries_touch before update on app.notification_deliveries
      for each row execute function app.touch_row();
    create trigger notification_deliveries_demo_flag before insert on app.notification_deliveries
      for each row execute function app.inherit_demo_flag();
    alter table app.notification_deliveries enable row level security;
    alter table app.notification_deliveries force row level security;
    create policy deliveries_read on app.notification_deliveries for select
      using (org_id = (select app.current_org_id())
             and ((select app.has_capability('animal.read')) or user_id = (select app.current_user_id())));
    -- People may queue only a test message to themselves; reminder deliveries are created by the scanner.
    create policy deliveries_test_insert on app.notification_deliveries for insert
      with check (org_id = (select app.current_org_id()) and user_id = (select app.current_user_id())
                  and kind = 'test');
    grant select, insert on app.notification_deliveries to pawguard_api;

    create table app.provider_status (
      provider text primary key check (provider in ('email','push','whatsapp','llm')),
      state text not null check (state in ('ok','not_configured','token_expired','rate_limited','cap_reached','error')),
      detail text check (char_length(detail) <= 300),
      updated_at timestamptz not null default now()
    );
    grant select on app.provider_status to pawguard_api, pawguard_worker;

    -- Queue the reminder each owner should see today (latest kind per pet/vaccine/due date; not snoozed), once per
    -- enabled channel. "Today" is the organisation's calendar date plus any demo offset. Idempotent.
    create or replace function app.queue_due_notifications() returns integer
    language plpgsql volatile security definer set search_path = '' as $$
    declare n integer;
    begin
      with today as (
        select o.id as org_id, ((now() at time zone o.timezone)::date + coalesce(dc.offset_days, 0)) as d
        from app.organisations o left join app.demo_clock dc on dc.org_id = o.id
        where o.activation_state = 'active'
      ), visible as (
        select distinct on (r.animal_id, r.vaccine_name, r.due_on) r.id, r.org_id, r.owner_user_id
        from app.vaccination_reminders r
        join today t on t.org_id = r.org_id
        join app.animals a on a.id = r.animal_id and a.profile_state not in ('archived','merged_alias')
        where r.state = 'pending' and r.show_on <= t.d and (r.snoozed_until is null or r.snoozed_until <= t.d)
        order by r.animal_id, r.vaccine_name, r.due_on, r.show_on desc
      )
      insert into app.notification_deliveries (org_id, user_id, channel, kind, reminder_id, dedupe_key)
      select v.org_id, v.owner_user_id, ch.channel, 'vaccination_reminder', v.id, v.id::text || ':' || ch.channel
      from visible v
      join app.notification_preferences p on p.user_id = v.owner_user_id
      cross join lateral (values ('email', p.email_enabled), ('push', p.push_enabled),
                                 ('whatsapp', p.whatsapp_enabled)) as ch(channel, enabled)
      where ch.enabled
      on conflict (dedupe_key) do nothing;
      get diagnostics n = row_count;
      return n;
    end $$;

    -- Claim a batch for sending (SKIP LOCKED; stuck 'sending' rows are reclaimed after their lock expires). Returns
    -- everything the sender needs as JSON: the message facts (no free text from users) and the recipient details.
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
        'pet', coalesce(a.nickname, a.reference_code), 'vaccine', r.vaccine_name, 'due_on', r.due_on,
        'reminder_kind', r.kind, 'reminder_state', r.state,
        'email_address', p.email_address, 'whatsapp_number', p.whatsapp_number,
        'push', coalesce((select jsonb_agg(jsonb_build_object('endpoint', s.endpoint, 'p256dh', s.p256dh,
                                                              'auth', s.auth))
                          from app.push_subscriptions s where s.user_id = u.user_id and s.revoked_at is null),
                         '[]'::jsonb))
      from u
      join app.organisations o on o.id = u.org_id
      left join app.demo_clock dc on dc.org_id = u.org_id
      left join app.vaccination_reminders r on r.id = u.reminder_id
      left join app.animals a on a.id = r.animal_id
      left join app.notification_preferences p on p.user_id = u.user_id;
    end $$;

    create or replace function app.finish_notification_delivery(p_id uuid, p_state text, p_error text,
                                                                p_provider_id text, p_retry_seconds integer)
    returns void language sql volatile security definer set search_path = '' as $$
      update app.notification_deliveries
         set state = p_state, last_error = left(p_error, 300), provider_message_id = left(p_provider_id, 200),
             sent_at = case when p_state = 'sent' then now() else sent_at end, locked_until = null,
             available_at = case when p_retry_seconds is not null then now() + make_interval(secs => p_retry_seconds)
                                 else available_at end
       where id = p_id and state = 'sending';
    $$;

    create or replace function app.set_provider_status(p_provider text, p_state text, p_detail text)
    returns void language sql volatile security definer set search_path = '' as $$
      insert into app.provider_status (provider, state, detail, updated_at) values (p_provider, p_state, left(p_detail, 300), now())
      on conflict (provider) do update set state = excluded.state, detail = excluded.detail, updated_at = now();
    $$;

    create or replace function app.notifications_sent_last_day(p_channel text) returns integer
    language sql stable security definer set search_path = '' as $$
      select count(*)::integer from app.notification_deliveries
       where channel = p_channel and state = 'sent' and sent_at > now() - interval '24 hours';
    $$;

    create or replace function app.notifications_ready() returns boolean
    language sql stable security definer set search_path = '' as $$
      select exists (select 1 from app.notification_deliveries
                      where (state in ('queued','deferred') and available_at <= now())
                         or (state = 'sending' and locked_until < now()));
    $$;

    create or replace function app.revoke_push_endpoint(p_endpoint text) returns void
    language sql volatile security definer set search_path = '' as $$
      update app.push_subscriptions set revoked_at = now() where endpoint = p_endpoint and revoked_at is null;
    $$;

    create or replace function app.mark_push_success(p_endpoint text) returns void
    language sql volatile security definer set search_path = '' as $$
      update app.push_subscriptions set last_success_at = now() where endpoint = p_endpoint;
    $$;

    revoke all on function app.queue_due_notifications(), app.claim_notification_deliveries(integer),
      app.finish_notification_delivery(uuid, text, text, text, integer), app.set_provider_status(text, text, text),
      app.notifications_sent_last_day(text), app.notifications_ready(), app.revoke_push_endpoint(text),
      app.mark_push_success(text) from public;
    grant execute on function app.queue_due_notifications(), app.claim_notification_deliveries(integer),
      app.finish_notification_delivery(uuid, text, text, text, integer), app.set_provider_status(text, text, text),
      app.notifications_sent_last_day(text), app.notifications_ready(), app.revoke_push_endpoint(text),
      app.mark_push_success(text) to pawguard_worker;
    -- The API may trigger a scan (demo "send due reminders now"); it is idempotent and creates no free text.
    grant execute on function app.queue_due_notifications() to pawguard_api;
    """)


def downgrade() -> None:
    op.execute("""
    drop function if exists app.queue_due_notifications(), app.claim_notification_deliveries(integer),
      app.finish_notification_delivery(uuid, text, text, text, integer), app.set_provider_status(text, text, text),
      app.notifications_sent_last_day(text), app.notifications_ready(), app.revoke_push_endpoint(text),
      app.mark_push_success(text);
    drop table if exists app.provider_status, app.notification_deliveries, app.push_subscriptions,
      app.notification_preferences;
    """)
