"""Pet vaccination tracking and reminders (pet owners, clinics as organisations).

- New capability `pet.own` (held by the `resident` role used for pet owners). Owners never get registry-wide
  `animal.read`; owner endpoints only return pets linked to the owner through `animal_caregivers`
  (relationship 'owner', linked_user_id). Caregiver row security now also lets an owner read — and create — only
  their own owner link.
- `animals.date_of_birth`; vaccine products can carry a *demo* schedule template (interval + label, never a medical
  schedule); vaccination events gain sources `owner_entry` (unverified, goes to the workbench) and `clinic_record`
  (entered by an authorised vet at the clinic).
- `vaccination_reminders`: one row per (animal, due date, kind); pending rows are cancelled and recreated in the
  same transaction when the due date changes. In-app only — nothing is sent.
- `demo_clock`: per-organisation day offset for demonstrations (demo organisations only; stored dates untouched).
- `pet_cards`: random, revocable tokens for the public vaccination card; `app.public_card(token)` returns only
  what the public card shows.

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-06
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CAPABILITIES = [
    "animal.read", "animal.write", "animal.merge", "animal.location.exact", "caregiver.read", "caregiver.write",
    "observation.write", "media.upload", "identity.search", "identity.decide", "vaccination.submit",
    "vaccination.review", "task.work", "task.manage", "campaign.manage", "survey.write", "report.aggregate",
    "member.manage", "professional.approve", "audit.read", "system.view", "data.import", "model.manage",
    "pet.own",
]


def upgrade() -> None:
    caps = ", ".join(f"'{c}'" for c in CAPABILITIES)
    op.execute(f"""
    alter table app.memberships drop constraint memberships_capabilities_check;
    alter table app.memberships add constraint memberships_capabilities_check
      check (capabilities <@ array[{caps}]::text[]);

    alter table app.animals add column date_of_birth date check (date_of_birth is null or date_of_birth <= current_date);

    alter table app.vaccine_products
      add column template_interval_days integer check (template_interval_days is null or template_interval_days between 7 and 1100),
      add column template_label text check (char_length(template_label) <= 120);

    alter table app.animal_vaccination_events drop constraint animal_vaccination_events_source_type_check;
    alter table app.animal_vaccination_events add constraint animal_vaccination_events_source_type_check
      check (source_type in ('field_entry','certificate_upload','import','partner_record','sync','owner_entry',
                             'clinic_record'));

    -- Owners: read their own owner links; create an owner link only for themselves.
    drop policy caregivers_capability on app.animal_caregivers;
    create policy caregivers_capability on app.animal_caregivers as restrictive for select
      using ((select app.has_capability('caregiver.read')) or linked_user_id = (select app.current_user_id()));
    drop policy caregivers_write_capability on app.animal_caregivers;
    create policy caregivers_write_capability on app.animal_caregivers as restrictive for insert
      with check ((select app.has_capability('caregiver.write'))
                  or (relationship = 'owner' and linked_user_id = (select app.current_user_id())
                      and (select app.has_capability('pet.own'))));

    create table app.vaccination_reminders (
      id uuid primary key default extensions.gen_random_uuid(),
      org_id uuid not null references app.organisations(id),
      animal_id uuid not null,
      owner_user_id uuid not null,
      source_event_id uuid not null,
      vaccine_name text not null,
      due_on date not null,
      kind text not null check (kind in ('due_in_14','due_in_7','due_in_1','overdue')),
      show_on date not null,
      state text not null default 'pending' check (state in ('pending','done','cancelled')),
      snoozed_until date,
      done_event_id uuid,
      is_demo boolean not null default false,
      created_at timestamptz not null default now(),
      updated_at timestamptz not null default now(),
      row_version integer not null default 1,
      unique (id, org_id),
      foreign key (animal_id, org_id) references app.animals(id, org_id),
      foreign key (source_event_id, org_id) references app.animal_vaccination_events(id, org_id)
    );
    -- Idempotency: one live reminder per animal, vaccine due date and kind.
    create unique index reminders_one_live on app.vaccination_reminders (animal_id, vaccine_name, due_on, kind)
      where state <> 'cancelled';
    create index reminders_owner on app.vaccination_reminders (owner_user_id, state, show_on);
    create trigger vaccination_reminders_touch before update on app.vaccination_reminders
      for each row execute function app.touch_row();
    alter table app.vaccination_reminders enable row level security;
    alter table app.vaccination_reminders force row level security;
    create policy reminders_tenant on app.vaccination_reminders for all
      using (org_id = (select app.current_org_id())) with check (org_id = (select app.current_org_id()));
    create trigger vaccination_reminders_demo_flag before insert on app.vaccination_reminders
      for each row execute function app.inherit_demo_flag();
    grant select, insert, update on app.vaccination_reminders to pawguard_api, pawguard_worker;

    create table app.demo_clock (
      org_id uuid primary key references app.organisations(id),
      offset_days integer not null default 0 check (offset_days between -60 and 400),
      set_by uuid,
      updated_at timestamptz not null default now()
    );
    alter table app.demo_clock enable row level security;
    alter table app.demo_clock force row level security;
    create policy demo_clock_tenant on app.demo_clock for all
      using (org_id = (select app.current_org_id()))
      with check (org_id = (select app.current_org_id())
                  and exists (select 1 from app.organisations o where o.id = org_id and o.is_demo));
    grant select, insert, update on app.demo_clock to pawguard_api, pawguard_worker;

    create table app.pet_cards (
      id uuid primary key default extensions.gen_random_uuid(),
      org_id uuid not null references app.organisations(id),
      animal_id uuid not null,
      token text not null unique check (char_length(token) >= 32),
      created_by uuid not null,
      created_at timestamptz not null default now(),
      revoked_at timestamptz,
      foreign key (animal_id, org_id) references app.animals(id, org_id)
    );
    create unique index pet_cards_one_live on app.pet_cards (animal_id) where revoked_at is null;
    alter table app.pet_cards enable row level security;
    alter table app.pet_cards force row level security;
    create policy pet_cards_tenant on app.pet_cards for all
      using (org_id = (select app.current_org_id())) with check (org_id = (select app.current_org_id()));
    grant select, insert, update on app.pet_cards to pawguard_api;

    -- Public card: only pet name, species, photo key, verified vaccinations (product, date, next due), clinic name,
    -- and the organisation's demo-clock offset. Nothing about owners or locations. Revoked tokens return no rows.
    create or replace function app.public_card(p_token text)
    returns table (animal_name text, species text, photo_key text, clinic_name text, is_demo boolean,
                   timezone text, offset_days integer, vaccine text, administered_on date, next_due_on date,
                   next_due_source text)
    language sql stable security definer set search_path = '' as $$
      select coalesce(a.nickname, a.reference_code), a.species,
             (select m.derivatives->>'thumb' from app.observation_media om
                join app.animal_observations o on o.id = om.observation_id
                join app.media_assets m on m.id = om.media_id
               where o.animal_id = a.id and m.state = 'approved' order by o.created_at limit 1),
             org.name, a.is_demo, org.timezone, coalesce(dc.offset_days, 0),
             coalesce(p.name, e.product_text), e.administered_on, e.next_review_on, e.next_review_source
        from app.pet_cards c
        join app.animals a on a.id = c.animal_id
        join app.organisations org on org.id = c.org_id
        left join app.demo_clock dc on dc.org_id = c.org_id
        left join app.animal_vaccination_events e on e.animal_id = a.id and e.state = 'verified'
        left join app.vaccine_products p on p.id = e.product_id
       where c.token = p_token and c.revoked_at is null and a.profile_state not in ('archived','merged_alias')
    $$;
    revoke all on function app.public_card(text) from public;
    grant execute on function app.public_card(text) to pawguard_api;
    """)


def downgrade() -> None:
    op.execute("""
    drop function if exists app.public_card(text);
    drop table if exists app.pet_cards, app.demo_clock, app.vaccination_reminders;
    alter table app.vaccine_products drop column if exists template_interval_days, drop column if exists template_label;
    alter table app.animals drop column if exists date_of_birth;
    """)
