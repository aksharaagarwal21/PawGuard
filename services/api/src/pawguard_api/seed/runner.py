"""Demo seed runner. Runs as the owner (bypasses RLS) and must only ever be called by ``seed-demo``."""

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from pawguard_api.capabilities import ROLE_TEMPLATES, Role
from pawguard_api.integrations.supabase_admin import SupabaseAuthAdmin
from pawguard_api.seed.accounts import ACCOUNTS, DEMO_PASSWORD, ORGS, demo_id
from pawguard_api.seed.domain import seed_domain


def seed_accounts(c: Connection, auth: SupabaseAuthAdmin) -> dict[str, UUID]:
    for org in ORGS:
        c.execute(text("""
            insert into app.organisations (id, name, org_type, region_code, timezone, activation_state, is_demo)
            values (:id, :name, :t, :r, 'Asia/Kolkata', 'active', true)
            on conflict (id) do update set name = excluded.name, org_type = excluded.org_type,
              region_code = excluded.region_code, activation_state = 'active', is_demo = true
        """), {"id": demo_id("org", org.key), "name": org.name, "t": org.org_type, "r": org.region_code})

    user_ids: dict[str, UUID] = {}
    admin_of = {org: acc for acc in ACCOUNTS for (org, role) in acc.memberships if role == "org_admin"}
    for acc in ACCOUNTS:
        uid = auth.ensure_user(acc.email, DEMO_PASSWORD, display_name=acc.preferred_name)
        user_ids[acc.key] = uid
        c.execute(text("""
            insert into app.user_profiles (user_id, preferred_name, locale, is_demo) values (:u, :n, :l, true)
            on conflict (user_id) do update set preferred_name = excluded.preferred_name,
              locale = excluded.locale, is_demo = true
        """), {"u": uid, "n": acc.preferred_name, "l": acc.locale})

    for acc in ACCOUNTS:
        for org_key, role in acc.memberships:
            org_id = demo_id("org", org_key)
            mid = demo_id("membership", f"{acc.key}:{org_key}")
            caps = sorted(c_.value for c_ in ROLE_TEMPLATES[Role(role)])
            approver = user_ids[admin_of[org_key].key] if acc.key != admin_of[org_key].key else None
            c.execute(text("""
                insert into app.memberships (id, org_id, user_id, role, capabilities, status, approved_by,
                                             approved_at, is_demo)
                values (:id, :o, :u, :r, :caps, 'active', :ap, now(), true)
                on conflict (id) do update set role = excluded.role, capabilities = excluded.capabilities,
                  status = 'active', revoked_at = null, revoked_by = null, revocation_reason = null
            """), {"id": mid, "o": org_id, "u": user_ids[acc.key], "r": role, "caps": caps, "ap": approver})
            if org_key in acc.vet_approval_in:
                c.execute(text("""
                    insert into app.professional_approvals (id, org_id, membership_id, user_id, scope,
                      evidence_reference, reviewer_user_id, review_state, decided_at, decision_reason, is_demo)
                    values (:id, :o, :m, :u, 'veterinary_review',
                      'DEMO: fictional registration reference — not a real professional record',
                      :rv, 'approved', now(), 'Demo fixture', true)
                    on conflict (id) do update set review_state = 'approved', valid_until = null
                """), {"id": demo_id("approval", f"{acc.key}:{org_key}"), "o": org_id, "m": mid,
                       "u": user_ids[acc.key], "rv": user_ids[admin_of[org_key].key]})
    return user_ids


def run_seed(c: Connection, auth: SupabaseAuthAdmin) -> dict[str, object]:
    users = seed_accounts(c, auth)
    summary: dict[str, object] = {"organisations": len(ORGS), "accounts": len(users)}
    summary.update(seed_domain(c, users))
    from pawguard_api.seed.credentials import seed_credentials

    summary.update(seed_credentials(c))
    return summary
