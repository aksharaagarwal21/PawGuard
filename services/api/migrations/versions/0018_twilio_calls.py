"""Optional phone-call reminders via a Twilio trial (verified numbers only), with a keypad reply.

- Opt-in per person (`call_enabled`, `call_number`); channel 'call' for deliveries and provider status.
- The keypad reply is stored on the delivery (`reply`): 1 = "I'll book a visit", 2 = remind me again in 3 days
  (snoozes that reminder). Recorded through one security-definer function called by the signature-checked webhook.

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-07
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
    alter table app.notification_preferences
      add column call_enabled boolean not null default false,
      add column call_number text check (call_number is null or call_number ~ '^\\+[1-9][0-9]{7,14}$');
    alter table app.notification_deliveries add column reply text check (reply is null or reply in ('1','2'));
    alter table app.notification_deliveries drop constraint notification_deliveries_channel_check;
    alter table app.notification_deliveries add constraint notification_deliveries_channel_check
      check (channel in ('email','push','whatsapp','call'));
    alter table app.provider_status drop constraint provider_status_provider_check;
    alter table app.provider_status add constraint provider_status_provider_check
      check (provider in ('email','push','whatsapp','llm','call'));

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
        ('push', p.push_enabled), ('whatsapp', p.whatsapp_enabled),
        ('call', p.call_enabled and p.call_number is not null)) as ch(channel, enabled)
      where ch.enabled
      on conflict (dedupe_key) do nothing;
      get diagnostics n = row_count;
      return n;
    end $fn$;

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
        'whatsapp_number', p.whatsapp_number, 'call_number', p.call_number,
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

    -- Keypad reply from the call webhook. 2 = remind again in 3 days (snoozes that reminder group).
    create or replace function app.record_call_reply(p_delivery uuid, p_digit text) returns boolean
    language plpgsql volatile security definer set search_path = '' as $$
    declare v record;
    begin
      if p_digit not in ('1','2') then return false; end if;
      update app.notification_deliveries set reply = p_digit
       where id = p_delivery and channel = 'call' and state = 'sent'
       returning reminder_id, org_id into v;
      if v is null then return false; end if;
      if p_digit = '2' and v.reminder_id is not null then
        update app.vaccination_reminders r set snoozed_until = (
                 select (now() at time zone o.timezone)::date + coalesce(dc.offset_days, 0) + 3
                   from app.organisations o left join app.demo_clock dc on dc.org_id = o.id where o.id = v.org_id)
         from app.vaccination_reminders x
         where x.id = v.reminder_id and r.animal_id = x.animal_id and r.vaccine_name = x.vaccine_name
           and r.due_on = x.due_on and r.state = 'pending';
      end if;
      return true;
    end $$;
    revoke all on function app.record_call_reply(uuid, text) from public;
    grant execute on function app.record_call_reply(uuid, text) to pawguard_api;
    """)


def downgrade() -> None:
    op.execute("""
    drop function if exists app.record_call_reply(uuid, text);
    alter table app.notification_preferences drop column if exists call_enabled, drop column if exists call_number;
    alter table app.notification_deliveries drop column if exists reply;
    """)
