"""WhatsApp through Twilio (trial template) with delivery tracking.

- Deliveries record the provider, the masked recipient, Twilio's own status (queued → sent → delivered → read, or
  undelivered/failed), when it last changed, Twilio's error code and the text Twilio says it sent.
- Status only moves forward: a late or duplicate "sent" callback never moves a delivered/read message back.
- New kind 'demo_reminder': a demo-only reminder scheduled a few minutes ahead for a fictional pet, without touching
  vaccination records or due dates. Staff may queue 'test' and 'demo_reminder' rows for their own organisation.
- The claim function also returns whether the person still has each channel switched on (opt-out at send time).
- No blind resend: `send_started_at` is set just before the request to Twilio and cleared once the outcome is known.
  A row reclaimed with it still set (worker stopped, or a timeout) is not sent again.

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-07
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
    alter table app.notification_deliveries
      add column provider text check (provider is null or provider in ('smtp','webpush','meta','twilio')),
      add column recipient_masked text check (char_length(recipient_masked) <= 40),
      add column provider_status text check (provider_status is null or provider_status in
        ('accepted','queued','sending','sent','delivered','read','undelivered','failed','canceled','scheduled')),
      add column provider_status_at timestamptz,
      add column provider_error_code text check (char_length(provider_error_code) <= 20),
      add column provider_body text check (char_length(provider_body) <= 1000),
      add column send_started_at timestamptz;
    create index deliveries_provider_sid on app.notification_deliveries (provider_message_id)
      where provider_message_id is not null;
    alter table app.notification_deliveries drop constraint notification_deliveries_kind_check;
    alter table app.notification_deliveries add constraint notification_deliveries_kind_check
      check (kind in ('vaccination_reminder','test','verify_email','lost_message','demo_reminder'));
    drop policy deliveries_self_insert on app.notification_deliveries;
    create policy deliveries_self_insert on app.notification_deliveries for insert
      with check (org_id = (select app.current_org_id()) and user_id = (select app.current_user_id())
                  and kind in ('test','verify_email','demo_reminder'));

    -- Before sending: record which provider and (masked) recipient this attempt uses.
    create or replace function app.set_delivery_provider(p_id uuid, p_provider text, p_recipient_masked text)
    returns void language sql volatile security definer set search_path = '' as $$
      update app.notification_deliveries set provider = p_provider, recipient_masked = left(p_recipient_masked, 40),
             send_started_at = now()
       where id = p_id;
    $$;

    -- The request definitely did not create a message (refused or never reached Twilio): a retry is safe.
    create or replace function app.clear_delivery_send(p_id uuid)
    returns void language sql volatile security definer set search_path = '' as $$
      update app.notification_deliveries set send_started_at = null where id = p_id;
    $$;

    -- Staff cancel a scheduled demo reminder of their own organisation before it is sent.
    create or replace function app.cancel_demo_delivery(p_id uuid)
    returns boolean language plpgsql volatile security definer set search_path = '' as $$
    declare n integer;
    begin
      update app.notification_deliveries set state = 'skipped', last_error = 'Cancelled before sending',
             updated_at = now()
       where id = p_id and org_id = app.current_org_id() and kind = 'demo_reminder'
         and state in ('queued','deferred');
      get diagnostics n = row_count;
      return n > 0;
    end $$;

    -- After the API accepted the message: Twilio's SID, first status and the text it sent.
    create or replace function app.set_provider_result(p_id uuid, p_sid text, p_status text, p_body text)
    returns void language sql volatile security definer set search_path = '' as $$
      update app.notification_deliveries
         set provider_message_id = left(p_sid, 200), provider_status = p_status, provider_status_at = now(),
             provider_body = left(p_body, 1000), send_started_at = null
       where id = p_id;
    $$;

    -- Status callbacks and polling: forward-only. Ranks: queued/accepted/scheduled 1, sending 2, sent 3,
    -- delivered 4, read 5; undelivered/failed/canceled are final unless already delivered/read.
    create or replace function app.record_twilio_status(p_sid text, p_status text, p_error text)
    returns integer language plpgsql volatile security definer set search_path = '' as $$
    declare n integer;
    begin
      update app.notification_deliveries d
         set provider_status = p_status, provider_status_at = now(),
             provider_error_code = coalesce(left(p_error, 20), d.provider_error_code),
             state = case when p_status in ('undelivered','failed') then 'failed' else d.state end,
             last_error = case when p_status in ('undelivered','failed')
                               then left('Twilio ' || p_status || coalesce(' (error ' || p_error || ')', ''), 300)
                               else d.last_error end
       where d.provider = 'twilio' and d.provider_message_id = p_sid
         and (case p_status when 'read' then 5 when 'delivered' then 4 when 'sent' then 3 when 'sending' then 2
                            when 'undelivered' then 4 when 'failed' then 4 when 'canceled' then 4 else 1 end)
           > (case coalesce(d.provider_status, '') when 'read' then 5 when 'delivered' then 4 when 'sent' then 3
                when 'sending' then 2 when 'undelivered' then 6 when 'failed' then 6 when 'canceled' then 6
                when '' then 0 else 1 end);
      get diagnostics n = row_count;
      return n;
    end $$;

    -- Messages to check with Twilio when callbacks can't reach us (bounded: last 2 hours, at most p_limit).
    create or replace function app.twilio_status_to_check(p_limit integer)
    returns table (id uuid, sid text) language sql stable security definer set search_path = '' as $$
      select d.id, d.provider_message_id from app.notification_deliveries d
       where d.provider = 'twilio' and d.state = 'sent' and d.provider_message_id is not null
         and coalesce(d.provider_status, '') not in ('delivered','read','undelivered','failed','canceled')
         and d.sent_at > now() - interval '2 hours'
         and (d.provider_status_at is null or d.provider_status_at < now() - interval '45 seconds')
       order by d.sent_at limit greatest(1, least(p_limit, 20));
    $$;

    revoke all on function app.set_delivery_provider(uuid, text, text), app.set_provider_result(uuid, text, text, text),
      app.record_twilio_status(text, text, text), app.twilio_status_to_check(integer), app.clear_delivery_send(uuid),
      app.cancel_demo_delivery(uuid) from public;
    grant execute on function app.set_delivery_provider(uuid, text, text), app.set_provider_result(uuid, text, text, text),
      app.record_twilio_status(text, text, text), app.twilio_status_to_check(integer), app.clear_delivery_send(uuid)
      to pawguard_worker;
    grant execute on function app.record_twilio_status(text, text, text), app.cancel_demo_delivery(uuid) to pawguard_api;

    -- Claim: also return whether each channel is still switched on (checked again at send time).
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
        'vaccine', r.vaccine_name, 'due_on', r.due_on, 'reminder_kind', r.kind, 'reminder_state', r.state,
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
      left join app.notification_preferences p on p.user_id = u.user_id;
    end $$;
    """)


def downgrade() -> None:
    op.execute("""
    drop function if exists app.set_delivery_provider(uuid, text, text), app.set_provider_result(uuid, text, text, text),
      app.record_twilio_status(text, text, text), app.twilio_status_to_check(integer), app.clear_delivery_send(uuid),
      app.cancel_demo_delivery(uuid);
    delete from app.notification_deliveries where kind = 'demo_reminder';
    alter table app.notification_deliveries drop constraint notification_deliveries_kind_check;
    alter table app.notification_deliveries add constraint notification_deliveries_kind_check
      check (kind in ('vaccination_reminder','test','verify_email','lost_message'));
    drop policy deliveries_self_insert on app.notification_deliveries;
    create policy deliveries_self_insert on app.notification_deliveries for insert
      with check (org_id = (select app.current_org_id()) and user_id = (select app.current_user_id())
                  and kind in ('test','verify_email'));
    alter table app.notification_deliveries drop column if exists provider, drop column if exists recipient_masked,
      drop column if exists provider_status, drop column if exists provider_status_at,
      drop column if exists provider_error_code, drop column if exists provider_body,
      drop column if exists send_started_at;
    """)
