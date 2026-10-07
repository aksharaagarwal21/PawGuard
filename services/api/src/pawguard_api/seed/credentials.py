"""Demo signed certificates (labelled demo): keys for the demo organisations, a certificate for every verified demo
record, and one replaced (cancelled) certificate for Bruno's rabies record so the verifier can show "replaced".
The altered sample is produced on request from Bruno's genuine certificate (see credentials.tampered_copy)."""

from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection

from pawguard_api.domain import credentials
from pawguard_api.integrations.cose import SigningUnavailable


def seed_credentials(c: Connection) -> dict[str, Any]:
    orgs = c.execute(text("select id from app.organisations where is_demo and activation_state = 'active' "
                          "order by name")).scalars().all()
    issued = 0
    try:
        for org in orgs:
            c.execute(text("select app.set_request_context(null, :o)"), {"o": org})
            actor = credentials.Actor(org, None)
            credentials.ensure_key(c, actor)
            issued += credentials.backfill(c, actor)
        bruno = c.execute(text("""
            select e.id, e.org_id from app.animal_vaccination_events e
              join app.animals a on a.id = e.animal_id
              join app.vaccine_products p on p.id = e.product_id
             where a.is_demo and a.nickname = 'Bruno' and e.state = 'verified' and p.name ilike '%rabies%'
             order by e.administered_on desc limit 1""")).first()
        replaced = 0
        has_sample = c.execute(text("select 1 from app.vaccination_credentials where is_demo and state = 'revoked'"
                                    " limit 1")).scalar()
        if bruno and not has_sample:
            c.execute(text("select app.set_request_context(null, :o)"), {"o": bruno.org_id})
            credentials.issue_replacing(c, credentials.Actor(bruno.org_id, None), bruno.id)
            replaced = 1
    except SigningUnavailable:
        return {"signed_certificates": "skipped (signing keys not configured — run `pawguard-admin keys init`)"}
    return {"signed_certificates": issued, "replaced_sample": replaced}
