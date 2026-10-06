"""Confirm an email address before sending reminders to it (double opt-in).

Anyone can type an address on the Notifications page, and demo accounts are public, so reminders are sent only to
addresses whose owner clicked the link in a short confirmation email. The token is generated when that email is
sent; only its SHA-256 hash is stored, and it expires after 48 hours. Changing the address clears the confirmation.

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-07
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
    alter table app.notification_preferences
      add column email_verified_at timestamptz,
      add column email_verify_hash text check (email_verify_hash is null or char_length(email_verify_hash) = 64),
      add column email_verify_sent_at timestamptz;

    alter table app.notification_deliveries drop constraint notification_deliveries_kind_check;
    alter table app.notification_deliveries add constraint notification_deliveries_kind_check
      check (kind in ('vaccination_reminder','test','verify_email'));
    drop policy deliveries_test_insert on app.notification_deliveries;
    create policy deliveries_self_insert on app.notification_deliveries for insert
      with check (org_id = (select app.current_org_id()) and user_id = (select app.current_user_id())
                  and kind in ('test','verify_email'));

    -- Called by the worker when it sends the confirmation email: returns a fresh random token, stores its hash.
    create or replace function app.issue_email_verification(p_user uuid) returns text
    language plpgsql volatile security definer set search_path = '' as $$
    declare v_token text;
    begin
      v_token := translate(encode(extensions.gen_random_bytes(32), 'base64'), '+/=', '-_');
      update app.notification_preferences
         set email_verify_hash = encode(extensions.digest(v_token, 'sha256'), 'hex'), email_verify_sent_at = now()
       where user_id = p_user and email_address is not null;
      if not found then
        return null;
      end if;
      return v_token;
    end $$;

    -- Called by the public confirmation page: true when the token matches an unexpired request.
    create or replace function app.confirm_email(p_token text) returns boolean
    language plpgsql volatile security definer set search_path = '' as $$
    begin
      update app.notification_preferences
         set email_verified_at = now(), email_verify_hash = null
       where email_verify_hash = encode(extensions.digest(p_token, 'sha256'), 'hex')
         and email_verify_sent_at > now() - interval '48 hours';
      return found;
    end $$;

    revoke all on function app.issue_email_verification(uuid), app.confirm_email(text) from public;
    grant execute on function app.issue_email_verification(uuid) to pawguard_worker;
    grant execute on function app.confirm_email(text) to pawguard_api;

    -- Scan: email reminders only for confirmed addresses (unless the server sends demo mail to a team inbox), so a
    -- reminder that appears before confirmation is queued after it rather than skipped for good.
    drop function app.queue_due_notifications();
    create or replace function app.queue_due_notifications(p_email_needs_confirmation boolean default true)
    returns integer language plpgsql volatile security definer set search_path = '' as $fn$
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
      cross join lateral (values
        ('email', p.email_enabled and (not p_email_needs_confirmation or p.email_verified_at is not null)),
        ('push', p.push_enabled), ('whatsapp', p.whatsapp_enabled)) as ch(channel, enabled)
      where ch.enabled
      on conflict (dedupe_key) do nothing;
      get diagnostics n = row_count;
      return n;
    end $fn$;
    revoke all on function app.queue_due_notifications(boolean) from public;
    grant execute on function app.queue_due_notifications(boolean) to pawguard_worker, pawguard_api;

    -- The sender needs to know whether the address is confirmed.
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
      left join app.notification_preferences p on p.user_id = u.user_id;
    end $$;
    """)


def downgrade() -> None:
    op.execute("""
    drop function if exists app.issue_email_verification(uuid), app.confirm_email(text),
      app.queue_due_notifications(boolean);
    drop policy if exists deliveries_self_insert on app.notification_deliveries;
    create policy deliveries_test_insert on app.notification_deliveries for insert
      with check (org_id = (select app.current_org_id()) and user_id = (select app.current_user_id())
                  and kind = 'test');
    alter table app.notification_deliveries drop constraint notification_deliveries_kind_check;
    alter table app.notification_deliveries add constraint notification_deliveries_kind_check
      check (kind in ('vaccination_reminder','test'));
    alter table app.notification_preferences drop column if exists email_verified_at,
      drop column if exists email_verify_hash, drop column if exists email_verify_sent_at;
    """)
