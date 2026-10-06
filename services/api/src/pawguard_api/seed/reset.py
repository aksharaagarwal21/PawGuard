"""Reset the DEMO organisations to their seeded state without touching anything else.

Only rows whose ``org_id`` belongs to an organisation flagged ``is_demo`` are deleted. Accounts, memberships,
professional approvals and global research/model records are kept (the seed recreates any demo fixtures that are
missing). Row counts outside the demo organisations are measured before and after inside the same transaction; if
any differs, everything is rolled back. Refused in production.
"""

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection

# Kept for every organisation: who people are and what they may do, plus global research lineage.
KEEP = {"memberships", "professional_approvals", "dataset_versions"}


def tenant_tables(c: Connection) -> list[str]:
    rows = c.execute(text("""
        select c.table_name from information_schema.columns c
        join information_schema.tables t on t.table_schema = c.table_schema and t.table_name = c.table_name
             and t.table_type = 'BASE TABLE'
        where c.table_schema = 'app' and c.column_name = 'org_id' order by 1""")).scalars().all()
    return [r for r in rows if r not in KEEP]


def _non_demo_counts(c: Connection, tables: list[str], demo: list[Any]) -> dict[str, int]:
    return {t: c.execute(text(f"select count(*) from app.{t} where org_id is null or "  # noqa: S608 - names from catalog
                              "not (org_id = any(cast(:d as uuid[])))"), {"d": demo}).scalar_one() for t in tables}


def demo_media_keys(c: Connection, demo: list[Any]) -> list[str]:
    keys: list[str] = []
    for r in c.execute(text("select object_key, derivatives from app.media_assets where org_id = any(cast(:d as uuid[]))"),
                       {"d": demo}):
        keys.append(r.object_key)
        keys.extend(v for v in (r.derivatives or {}).values() if isinstance(v, str))
    return sorted(set(keys))


def reset_demo_rows(c: Connection) -> dict[str, Any]:
    """Delete demo-organisation operational rows in the caller's transaction (owner connection required)."""
    demo = [str(x) for x in c.execute(text("select id from app.organisations where is_demo")).scalars().all()]
    if not demo:
        return {"demo_organisations": 0, "deleted": {}, "media_keys": []}
    tables = tenant_tables(c)
    before = _non_demo_counts(c, tables, demo)
    keys = demo_media_keys(c, demo)
    # Append-only guards (audit, reviews) and foreign keys are suspended only for this transaction; every delete is
    # restricted to demo organisations, and composite foreign keys keep references inside one organisation.
    c.execute(text("set local session_replication_role = replica"))
    deleted = {}
    for t in tables:
        n = c.execute(text(f"delete from app.{t} where org_id = any(cast(:d as uuid[]))"), {"d": demo}).rowcount  # noqa: S608
        if n:
            deleted[t] = n
    c.execute(text("set local session_replication_role = origin"))
    after = _non_demo_counts(c, tables, demo)
    if before != after:
        changed = {t: (before[t], after[t]) for t in tables if before[t] != after[t]}
        raise RuntimeError(f"non-demo data changed during reset; rolled back: {changed}")
    c.execute(text("insert into app.audit_events (actor_kind, action, target_type, change_summary) "
                   "values ('cli', 'demo.reset', 'organisation', cast(:s as jsonb))"),
              {"s": json.dumps({"organisations": len(demo), "rows": sum(deleted.values())})})
    return {"demo_organisations": len(demo), "deleted": deleted, "media_keys": keys, "non_demo_rows": sum(after.values())}
