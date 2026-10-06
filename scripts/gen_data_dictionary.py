"""Generate docs/DATA_DICTIONARY.md from the migrated database (owner connection, read-only queries).

Usage: uv run python scripts/gen_data_dictionary.py
The narrative sections at the top are maintained in this script; tables/columns/constraints/policies come from
the live catalog so the document cannot drift from the schema.
"""

from collections import defaultdict
from pathlib import Path

from sqlalchemy import create_engine, text

from pawguard_api.settings import get_settings

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "DATA_DICTIONARY.md"

INTRO = """# Data dictionary

Generated from the database by `scripts/gen_data_dictionary.py` (do not edit the generated sections by hand).
Schema `app` holds all business data; it is not exposed through PostgREST. Every table has row-level security
enabled **and forced**; tenant tables use the policy `org_id = app.current_org_id()` (ADR 0003).

## Conventions

- Primary keys are UUIDs. User-facing animal references are separate random codes (`PG-XXXX-XXXX`).
- `timestamptz` for instants, `date` + an explicit precision column for calendar dates that may be partial.
- `unknown` is an explicit enumerated value; `NULL` means "not recorded" (never "no").
- Mutable rows carry `row_version` (incremented by trigger) for optimistic concurrency; `is_demo` marks fixtures.
- Exact coordinates (`geography(Point,4326)`) are returned only to members with `animal.location.exact`;
  `location_approx` is snapped to a ~500 m grid.

## Vocabulary notes

| Field | Meaning |
|---|---|
| `animals.profile_state` | Identity-record review state; says nothing about health or vaccination |
| `animal_vaccination_events.state` | `submitted` = awaiting veterinary review; `verified` = evidence accepted that a vaccine was recorded as given (not a statement that the animal cannot transmit disease) |
| `date_precision` | `exact_time` / `day` / `month` (stored as 1st of month) / `year` (stored as 1 Jan) / `unknown` (date NULL) |
| `media_assets.state` | `pending_upload` → `uploaded` → `validating` → `approved`/`rejected`; only approved files are shown |
| `field_tasks.task_type` | `animal_followup`, `evidence_correction`, `identity_review` form the view `animal_followup_tasks` (ADR 0007) |
"""


def main() -> None:
    s = get_settings()
    url = (s.migrate_database_url or "").replace("postgresql://", "postgresql+psycopg://", 1)
    engine = create_engine(url)
    with engine.connect() as c:
        tables = c.execute(text("""select c.relname, obj_description(c.oid) as comment, c.relrowsecurity,
                                   c.relforcerowsecurity from pg_class c where c.relnamespace = 'app'::regnamespace
                                   and c.relkind = 'r' order by c.relname""")).all()
        cols = c.execute(text("""select table_name, column_name, data_type, udt_name, is_nullable, column_default
                                 from information_schema.columns where table_schema = 'app'
                                 order by table_name, ordinal_position""")).all()
        checks = c.execute(text("""select conrelid::regclass::text as tbl, conname, pg_get_constraintdef(oid) as definition,
                                   contype from pg_constraint where connamespace = 'app'::regnamespace
                                   and contype in ('c','f','u') order by 1, 2""")).all()
        policies = c.execute(text("""select tablename, policyname, cmd, permissive, roles from pg_policies
                                     where schemaname = 'app' order by 1, 2""")).all()
        fks = c.execute(text("""select conrelid::regclass::text as src, confrelid::regclass::text as dst
                                from pg_constraint where connamespace = 'app'::regnamespace and contype = 'f'""")).all()
        version = c.execute(text("select version_num from public.alembic_version")).scalar()
    by_table = defaultdict(list)
    for r in cols:
        by_table[r.table_name].append(r)
    cons = defaultdict(list)
    for r in checks:
        cons[r.tbl.removeprefix("app.")].append(r)
    pols = defaultdict(list)
    for r in policies:
        pols[r.tablename].append(r)

    core = {"organisations", "memberships", "animals", "animal_observations", "media_assets", "observation_media",
            "animal_vaccination_events", "vaccination_reviews", "vaccination_evidence", "vaccine_products",
            "vaccine_lots", "field_tasks", "campaigns", "areas", "animal_merge_operations", "animal_caregivers",
            "professional_approvals"}
    edges = sorted({(r.src.removeprefix("app."), r.dst.removeprefix("app.")) for r in fks
                    if r.src.removeprefix("app.") in core and r.dst.removeprefix("app.") in core and r.src != r.dst})
    lines = [INTRO, f"\n_Schema revision: `{version}`._\n", "\n## ER diagram (core Prevention tables)\n",
             "```mermaid", "erDiagram"]
    lines += [f"  {dst} ||--o{{ {src} : \"\"" for src, dst in edges]
    lines += ["```", "", "## Tables", ""]
    for t in tables:
        rls = "RLS enabled + forced" if t.relrowsecurity and t.relforcerowsecurity else "**RLS NOT FORCED**"
        lines += [f"### `app.{t.relname}`", "", f"{rls}.", ""]
        lines += ["| Column | Type | Null | Default |", "|---|---|---|---|"]
        for col in by_table[t.relname]:
            typ = col.udt_name if col.data_type == "USER-DEFINED" else col.data_type
            default = (col.column_default or "").replace("|", "\\|")
            if len(default) > 50:
                default = default[:47] + "…"
            lines.append(f"| `{col.column_name}` | {typ} | {'yes' if col.is_nullable == 'YES' else 'no'} | {default} |")
        rules = [r for r in cons[t.relname] if r.contype in ("c", "u")]
        if rules:
            lines += ["", "<details><summary>Constraints</summary>", ""]
            for r in rules:
                definition = r.definition.replace("|", "¦")
                lines.append(f"- `{r.conname}`: `{definition}`")
            lines += ["", "</details>"]
        if pols[t.relname]:
            lines += ["", "Policies: " + "; ".join(
                f"`{p.policyname}` ({p.cmd.lower()}, {'permissive' if p.permissive == 'PERMISSIVE' else 'restrictive'}"
                f"{', roles ' + ','.join(p.roles) if p.roles and p.roles != ['public'] else ''})" for p in pols[t.relname])]
        lines.append("")
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {OUT.relative_to(ROOT)} ({len(tables)} tables)")


if __name__ == "__main__":
    main()
