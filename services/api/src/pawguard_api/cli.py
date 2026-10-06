"""Administrative CLI (``pawguard-admin``). Uses the OWNER database connection — operators only.

Commands:
  bootstrap-admin   Create the first organisation administrator (documented provisioning path).
  seed-demo         Load fictional demo tenants and accounts (development/test with demo mode only).
  create-test-db    Create/recreate the database used by the automated tests and migrate it.
"""

import getpass
import os
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import typer
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, make_url

from pawguard_api.capabilities import ROLE_TEMPLATES, Role
from pawguard_api.integrations.supabase_admin import SupabaseAuthAdmin
from pawguard_api.settings import get_settings

app = typer.Typer(no_args_is_help=True, add_completion=False)
API_DIR = Path(__file__).resolve().parents[2]


def _owner_url(database: str | None = None) -> str:
    s = get_settings()
    if not s.migrate_database_url:
        raise typer.BadParameter("PAWGUARD_MIGRATE_DATABASE_URL is required for administrative commands")
    url = make_url(s.migrate_database_url.replace("postgresql://", "postgresql+psycopg://", 1))
    if database:
        url = url.set(database=database)
    return url.render_as_string(hide_password=False)


@contextmanager
def owner_conn(database: str | None = None) -> Iterator[Connection]:
    engine = create_engine(_owner_url(database))
    try:
        with engine.begin() as conn:
            conn.execute(text("set search_path = app, extensions, public"))
            yield conn
    finally:
        engine.dispose()


@app.command("bootstrap-admin")
def bootstrap_admin(
    email: str = typer.Option(..., help="Email of the first administrator"),
    org_name: str = typer.Option(..., help="Organisation name"),
    org_type: str = typer.Option("animal_welfare_ngo"),
    region_code: str = typer.Option(None, help="ISO 3166-2 code, e.g. IN-TN"),
    timezone: str = typer.Option("Asia/Kolkata"),
    password_env: str = typer.Option(None, help="Read the initial password from this environment variable "
                                                "instead of prompting"),
) -> None:
    """Create an organisation and its first administrator. Refuses if the organisation already has one.

    The administrator receives member-management and professional-approval capabilities but NOT veterinary
    review: professional authority must be granted to a person by a different approver.
    """
    password = os.environ.get(password_env) if password_env else getpass.getpass("Initial password: ")
    if not password or len(password) < 12:
        raise typer.BadParameter("Initial password must be at least 12 characters")
    s = get_settings()
    user_id = SupabaseAuthAdmin(s).ensure_user(email, password)
    caps = sorted(c.value for c in ROLE_TEMPLATES[Role.ORG_ADMIN])
    with owner_conn() as c:
        org_id = c.execute(text("select id from app.organisations where name = :n"), {"n": org_name}).scalar()
        if org_id and c.execute(text("select 1 from app.memberships where org_id = :o and role = 'org_admin' "
                                     "and status = 'active'"), {"o": org_id}).first():
            typer.echo("This organisation already has an active administrator; use the app to add more.")
            raise typer.Exit(1)
        if not org_id:
            org_id = c.execute(text(
                "insert into app.organisations (name, org_type, region_code, timezone, activation_state) "
                "values (:n, :t, :r, :tz, 'active') returning id"),
                {"n": org_name, "t": org_type, "r": region_code, "tz": timezone}).scalar()
        c.execute(text("insert into app.user_profiles (user_id) values (:u) on conflict do nothing"), {"u": user_id})
        mid = c.execute(text(
            "insert into app.memberships (org_id, user_id, role, capabilities, status, approved_at) "
            "values (:o, :u, 'org_admin', :caps, 'active', now()) returning id"),
            {"o": org_id, "u": user_id, "caps": caps}).scalar()
        c.execute(text(
            "insert into app.audit_events (org_id, actor_kind, action, target_type, target_id, reason, change_summary) "
            "values (:o, 'cli', 'membership.bootstrapped', 'membership', :m, 'bootstrap-admin command', "
            "jsonb_build_object('role', 'org_admin'))"), {"o": org_id, "m": mid})
    typer.echo(f"Created administrator membership in organisation {org_id}.")


@app.command("seed-demo")
def seed_demo() -> None:
    """Load fictional demo data. Idempotent: re-running updates the same rows (deterministic IDs)."""
    s = get_settings()
    if s.env not in ("development", "test") or not s.demo_mode:
        typer.echo("Refusing: seed-demo only runs with PAWGUARD_ENV=development|test and PAWGUARD_DEMO_MODE=true.")
        raise typer.Exit(2)
    from pawguard_api.seed.runner import run_seed

    with owner_conn() as c:
        summary = run_seed(c, SupabaseAuthAdmin(s))
    for k, v in summary.items():
        typer.echo(f"  {k}: {v}")


def ensure_test_database(name: str, recreate: bool = False) -> None:
    """Create (or recreate) the automated-test database and migrate it to head.

    The test database lives beside the Supabase database but has no Supabase ``auth`` schema, so a minimal
    ``auth.sessions`` table is created first; migration 0001 then installs the real session-liveness check
    against it and tests insert session rows directly.
    """
    if not name.replace("_", "").isalnum() or name in ("postgres", "template0", "template1"):
        raise ValueError("invalid test database name")
    s = get_settings()
    base = make_url(s.migrate_database_url.replace("postgresql://", "postgresql+psycopg://", 1))  # type: ignore[union-attr]
    admin_url = base.set(database="postgres").render_as_string(hide_password=False)
    engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with engine.connect() as c:
        exists = c.execute(text("select 1 from pg_database where datname = :n"), {"n": name}).first()
        if exists and recreate:
            c.execute(text(f'drop database "{name}" with (force)'))
            exists = None
        if not exists:
            c.execute(text(f'create database "{name}"'))
    engine.dispose()
    test_url = base.set(database=name).render_as_string(hide_password=False)
    engine = create_engine(test_url)
    with engine.begin() as c:
        c.execute(text("create schema if not exists auth"))
        c.execute(text("create table if not exists auth.sessions (id uuid primary key, user_id uuid not null, "
                       "not_after timestamptz)"))
    engine.dispose()
    env = dict(os.environ, PAWGUARD_MIGRATE_DATABASE_URL=test_url)
    proc = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=API_DIR, env=env,
                          capture_output=True, text=True)
    if proc.returncode != 0:
        # Alembic output can include SQL; it never includes role passwords (verifiers are pre-hashed).
        raise RuntimeError(f"migrating the test database failed:\n{proc.stderr[-4000:]}")


@app.command("create-test-db")
def create_test_db(recreate: bool = typer.Option(True, help="Drop and recreate if it exists")) -> None:
    """Create the test database (name from PAWGUARD_TEST_DATABASE_NAME) and run all migrations on it."""
    name = os.environ.get("PAWGUARD_TEST_DATABASE_NAME", "pawguard_test")
    ensure_test_database(name, recreate=recreate)
    typer.echo(f"Test database '{name}' is at the latest migration.")


@app.command("demo-reset")
def demo_reset(yes: bool = typer.Option(False, "--yes", help="Actually delete; without it, only report"),
               keep_media: bool = typer.Option(False, help="Do not delete demo photos from storage")) -> None:
    """Return the DEMO organisations to their seeded state. Non-demo organisations are never touched: their row
    counts are checked inside the same transaction and any difference rolls the whole reset back."""
    s = get_settings()
    if s.env not in ("development", "test") or not s.demo_mode:
        typer.echo("Refusing: demo-reset only runs with PAWGUARD_ENV=development|test and PAWGUARD_DEMO_MODE=true.")
        raise typer.Exit(2)
    from pawguard_api.seed.reset import demo_media_keys, reset_demo_rows, tenant_tables

    if not yes:
        with owner_conn() as c:
            demo = [str(x) for x in c.execute(text("select id from app.organisations where is_demo")).scalars()]
            for t in tenant_tables(c):
                n = c.execute(text(f"select count(*) from app.{t} where org_id = any(cast(:d as uuid[]))"),  # noqa: S608
                              {"d": demo}).scalar_one()
                if n:
                    typer.echo(f"  would delete {n:6d} from {t}")
            typer.echo(f"  would remove {len(demo_media_keys(c, demo))} demo storage objects")
        typer.echo("Dry run. Re-run with --yes to reset the demo organisations.")
        return
    with owner_conn() as c:
        summary = reset_demo_rows(c)
    typer.echo(f"deleted {sum(summary['deleted'].values())} demo rows from {len(summary['deleted'])} tables; "
               f"non-demo rows untouched: {summary.get('non_demo_rows', 0)}")
    if summary["media_keys"] and not keep_media:
        from pawguard_api.integrations.storage import get_storage

        keys = summary["media_keys"]
        for i in range(0, len(keys), 100):
            get_storage().remove(keys[i:i + 100])
        typer.echo(f"removed {len(keys)} demo storage objects")
    seed_demo()
    typer.echo("demo organisations re-seeded")


models_app = typer.Typer(no_args_is_help=True, help="Model registry (staged → active → retired).")
app.add_typer(models_app, name="models")
REPO = Path(__file__).resolve().parents[4]


def _model_dir() -> Path:
    d = Path(get_settings().model_dir)
    return d if d.is_absolute() else REPO / d


@models_app.command("register")
def models_register(
    manifest: Path = typer.Argument(..., help="Model manifest JSON (data/manifests/models/*.json)"),
) -> None:
    """Register an artefact as *staged* after verifying its checksum and size on disk."""
    import hashlib
    import json

    m = json.loads(manifest.read_text(encoding="utf-8"))
    path = _model_dir() / m["artifact_path"]
    if not path.is_file():
        raise typer.BadParameter(f"artefact not found: {path}")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != m["sha256"] or path.stat().st_size != m["size_bytes"]:
        raise typer.BadParameter("artefact checksum/size does not match the manifest")
    with owner_conn() as c:
        row = c.execute(text("""
            insert into app.model_versions (task, name, family, version_label, artifact_path, sha256, size_bytes,
              licence, source_url, preprocessing, output_spec, thresholds, embedding_dim, notes, release_gate)
            values (:task, :name, :family, :ver, :path, :sha, :size, :lic, :src, cast(:pre as jsonb),
              cast(:out as jsonb), cast(:thr as jsonb), :dim, :notes, cast(:gate as jsonb))
            on conflict (task, name, version_label) do nothing returning id"""),
            {"task": m["task"], "name": m["name"], "family": m["family"], "ver": m["version_label"],
             "path": m["artifact_path"], "sha": m["sha256"], "size": m["size_bytes"], "lic": m["licence"],
             "src": m["source_url"], "pre": json.dumps(m["preprocessing"]),
             "out": json.dumps(m.get("output_spec", {})), "thr": json.dumps(m.get("thresholds", {})),
             "dim": m.get("embedding_dim") or (m.get("output_spec") or {}).get("dim"), "notes": m.get("notes"),
             "gate": json.dumps(m.get("release_gate") or {})}).scalar()
    typer.echo(f"registered (staged): {row}" if row else "already registered")


@models_app.command("activate")
def models_activate(
    name: str, version_label: str, reason: str = typer.Option(..., help="Why this model is promoted"),
) -> None:
    """Promote a staged model. Requires its evaluation report to exist; retires the previously active model for
    the task (kept for rollback)."""
    import json

    with owner_conn() as c:
        m = c.execute(text("select * from app.model_versions where name = :n and version_label = :v"),
                      {"n": name, "v": version_label}).one_or_none()
        if m is None:
            raise typer.BadParameter("unknown model")
        manifest = next((p for p in (REPO / "data/manifests/models").glob("*.json")
                         if json.loads(p.read_text(encoding="utf-8")).get("name") == name
                         and json.loads(p.read_text(encoding="utf-8")).get("version_label") == version_label), None)
        report = json.loads(manifest.read_text(encoding="utf-8")).get("evaluation_report") if manifest else None
        if not report or not (REPO / report).is_file():
            raise typer.BadParameter("an evaluation report must exist before activation")
        if m.task == "identity_embedding":
            if not (m.release_gate or {}).get("passed"):
                raise typer.BadParameter("identity models can be activated only after their release gate passed "
                                         "(docs/ML_PLAN.md); use research-preview for demo organisations")
            done, eligible = _index_coverage(c, m.id)
            if eligible and done / eligible < 0.9:
                raise typer.BadParameter(f"gallery index incomplete ({done}/{eligible}); run `models reindex` "
                                         "and wait for the jobs before switching")
        c.execute(text("update app.model_versions set state = 'retired', retired_at = now() "
                       "where task = :t and state = 'active'"), {"t": m.task})
        c.execute(text("update app.model_versions set state = 'active', activated_at = now(), evaluation_report = :r, "
                       "research_preview = false, index_wanted = true where id = :id"), {"r": report, "id": m.id})
        c.execute(text("insert into app.audit_events (actor_kind, action, target_type, target_id, reason, "
                       "change_summary) values ('cli', 'model.activated', 'model_version', :id, :reason, "
                       "jsonb_build_object('task', cast(:t as text)))"), {"id": m.id, "reason": reason, "t": m.task})
    typer.echo(f"activated {name} {version_label}")


@models_app.command("retire")
def models_retire(name: str, version_label: str, reason: str = typer.Option(...)) -> None:
    """Retire a model (rollback: activate the previous version again)."""
    with owner_conn() as c:
        mid = c.execute(text("update app.model_versions set state = 'retired', retired_at = now() "
                             "where name = :n and version_label = :v returning id"),
                        {"n": name, "v": version_label}).scalar()
        if mid:
            c.execute(text("insert into app.audit_events (actor_kind, action, target_type, target_id, reason) "
                           "values ('cli', 'model.retired', 'model_version', :id, :reason)"),
                      {"id": mid, "reason": reason})
    typer.echo("retired" if mid else "not found")


def _queue_reindex(c: Connection, model_id: str) -> int:
    """Queue gallery enrolment for every eligible photo (all organisations) not yet embedded for this model."""
    rows = c.execute(text("""
        select om.id, om.org_id from app.observation_media om
          join app.animal_observations o on o.id = om.observation_id
          join app.media_assets m on m.id = om.media_id
          join app.animals a on a.id = o.animal_id
         where jsonb_typeof(om.subject_bbox) = 'object' and m.state = 'approved' and a.profile_state <> 'archived'
           and not exists (select 1 from app.animal_embeddings e
                            where e.observation_media_id = om.id and e.model_version_id = :mv)"""),
        {"mv": model_id}).all()
    for r in rows:
        job = c.execute(text("""insert into app.background_jobs (org_id, job_type, target_type, target_id, max_attempts)
                                values (:o, 'identity.enrol', 'observation_media', :id, 2)
                                on conflict do nothing returning id"""), {"o": r.org_id, "id": r.id}).scalar()
        if job:
            c.execute(text("""insert into app.outbox_events (org_id, event_type, aggregate_type, aggregate_id, payload)
                              values (:o, 'job.queued', 'background_job', :j, '{"job_type": "identity.enrol"}')"""),
                      {"o": r.org_id, "j": job})
    return len(rows)


def _index_coverage(c: Connection, model_id: str) -> tuple[int, int]:
    """(eligible photos embedded for this model, eligible photos) across all organisations."""
    return c.execute(text("""
        with elig as (
          select om.id from app.observation_media om
            join app.animal_observations o on o.id = om.observation_id
            join app.media_assets m on m.id = om.media_id
            join app.animals a on a.id = o.animal_id
           where jsonb_typeof(om.subject_bbox) = 'object' and m.state = 'approved' and a.profile_state <> 'archived')
        select (select count(*) from elig where exists (select 1 from app.animal_embeddings e
                  where e.observation_media_id = elig.id and e.model_version_id = :mv and e.state = 'active')),
               (select count(*) from elig)"""), {"mv": model_id}).one()


@models_app.command("reindex")
def models_reindex(name: str, version_label: str) -> None:
    """Maintain a gallery index for an identity model and queue embeddings for every eligible photo. Do this
    before switching models: queries keep using the current model until the new collection is complete."""
    with owner_conn() as c:
        mid = c.execute(text("update app.model_versions set index_wanted = true where name = :n and "
                             "version_label = :v and task = 'identity_embedding' returning id"),
                        {"n": name, "v": version_label}).scalar()
        if mid is None:
            raise typer.BadParameter("unknown identity model")
        n = _queue_reindex(c, mid)
        done, eligible = _index_coverage(c, mid)
    typer.echo(f"queued {n} photo(s); currently embedded {done}/{eligible}")


@models_app.command("research-preview")
def models_research_preview(name: str, version_label: str, reason: str = typer.Option(...),
                            off: bool = typer.Option(False, help="Turn the preview off")) -> None:
    """Let a *staged* identity model run in DEMO organisations only, labelled as research. Real organisations keep
    the manual path until a model passes the release gate and is activated."""
    with owner_conn() as c:
        if not off:
            c.execute(text("update app.model_versions set research_preview = false where task = 'identity_embedding'"))
        mid = c.execute(text("""update app.model_versions set research_preview = :on, index_wanted = index_wanted or :on
                                where name = :n and version_label = :v and task = 'identity_embedding'
                                  and state = 'staged' returning id"""),
                        {"on": not off, "n": name, "v": version_label}).scalar()
        if mid is None:
            raise typer.BadParameter("unknown staged identity model")
        c.execute(text("insert into app.audit_events (actor_kind, action, target_type, target_id, reason) "
                       "values ('cli', :a, 'model_version', :id, :reason)"),
                  {"a": "model.research_preview_off" if off else "model.research_preview_on", "id": mid,
                   "reason": reason})
        n = 0 if off else _queue_reindex(c, mid)
    typer.echo(f"research preview {'off' if off else 'on (demo organisations only)'}; queued {n} photo(s)")


runs_app = typer.Typer(no_args_is_help=True, help="Training / evaluation run lineage.")
app.add_typer(runs_app, name="runs")


@runs_app.command("register")
def runs_register(report: Path = typer.Argument(..., help="docs/evidence/*.json written by pawid"),
                  kind: str = typer.Option(..., help="evaluation | training | export"),
                  task: str = typer.Option("identity_embedding"),
                  decision: str = typer.Option("", help="What was decided from this run")) -> None:
    """Record a run's lineage (dataset/split/code/environment hashes, config, metrics) in ``training_runs``."""
    import hashlib
    import json

    raw = report.read_bytes()
    r = json.loads(raw)
    lin = r.get("lineage", {})
    ds_sha = lin.get("dataset_manifest_sha256") or (r.get("dataset") or {}).get("sha256") \
        or (r.get("dataset") or {}).get("manifest_sha256")
    rel = report.resolve().relative_to(REPO).as_posix()
    with owner_conn() as c:
        dv = c.execute(text("select id from app.dataset_versions where manifest_sha256 = :s"), {"s": ds_sha}).scalar()
        rid = c.execute(text("""
            insert into app.training_runs (task, run_label, kind, dataset_version_id, dataset_manifest_sha256,
              split_sha256, code_commit, code_sha256, environment_lock_sha256, seed, config, metrics, resources,
              artifacts, report_path, decision)
            values (:t, :label, :k, :dv, :ds, :split, :commit, :code, :env, :seed, cast(:cfg as jsonb),
              cast(:met as jsonb), cast(:res as jsonb), cast(:art as jsonb), :path, :dec)
            on conflict (run_label) do nothing returning id"""),
            {"t": task, "label": f"{report.stem}:{hashlib.sha256(raw).hexdigest()[:12]}", "k": kind, "dv": dv,
             "ds": ds_sha, "split": lin.get("split_sha256") or ds_sha, "commit": lin.get("code_commit"),
             "code": lin.get("code_sha256"), "env": lin.get("environment_lock_sha256"),
             "seed": (r.get("runs") or [{}])[0].get("config", {}).get("seed") if r.get("runs") else None,
             "cfg": json.dumps(r.get("selected") or r.get("selected_preprocessing") or {}),
             "met": json.dumps(r.get("selected_val_with_ci") or r.get("best_val_with_ci") or r.get("results") or {}),
             "res": json.dumps(r.get("resources") or {}), "art": json.dumps(r.get("head_artifact") or {}),
             "path": rel, "dec": decision or None}).scalar()
    typer.echo(f"recorded run {rid}" if rid else "already recorded")


@models_app.command("list")
def models_list() -> None:
    with owner_conn() as c:
        for r in c.execute(text("select task, name, version_label, state, registered_at from app.model_versions "
                                "order by task, registered_at")):
            typer.echo(f"{r.task:20} {r.name:22} {r.version_label:18} {r.state:8} {r.registered_at:%Y-%m-%d}")


if __name__ == "__main__":
    app()
