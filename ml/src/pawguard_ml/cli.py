"""`pawid` — reproducible data/ML commands. Every command records its inputs (manifests, checksums, seeds) in the
artefacts it writes. Paths default to the repository layout; large data lives under data/raw (gitignored)."""

import json
from pathlib import Path

import typer

app = typer.Typer(no_args_is_help=True, add_completion=False)
ROOT = Path(__file__).resolve().parents[3]


@app.command("coco-sample")
def coco_sample(
    zip_path: Path = typer.Option(ROOT / "data/raw/coco/annotations_trainval2017.zip"),
    out_dir: Path = typer.Option(ROOT / "data/raw/coco/val2017_sample"),
    manifest: Path = typer.Option(ROOT / "data/manifests/coco-val2017-dog-sample-v1.json"),
    n_pos: int = 60,
    n_neg: int = 25,
) -> None:
    """Build the licence-filtered COCO dog sample (downloads ~85 images from images.cocodataset.org)."""
    from pawguard_ml.coco_sample import build

    typer.echo(json.dumps(build(zip_path, out_dir, manifest, n_pos=n_pos, n_neg=n_neg), indent=2))


@app.command("detector-verify")
def detector_verify(
    model: Path = typer.Option(ROOT / "models/yolox/yolox_s.onnx"),
    manifest: Path = typer.Option(ROOT / "data/manifests/coco-val2017-dog-sample-v1.json"),
    img_dir: Path = typer.Option(ROOT / "data/raw/coco/val2017_sample"),
) -> None:
    """Compare preprocessing conventions on the verification subset only."""
    from pawguard_ml.detector_eval import verify_preprocessing

    typer.echo(json.dumps(verify_preprocessing(model, manifest, img_dir), indent=2))


@app.command("detector-eval")
def detector_eval(
    legacy: bool = typer.Option(..., help="Preprocessing convention established by detector-verify"),
    model: Path = typer.Option(ROOT / "models/yolox/yolox_s.onnx"),
    manifest: Path = typer.Option(ROOT / "data/manifests/coco-val2017-dog-sample-v1.json"),
    img_dir: Path = typer.Option(ROOT / "data/raw/coco/val2017_sample"),
    report: Path = typer.Option(ROOT / "docs/evidence/detector-eval-yolox_s-coco-v1.json"),
) -> None:
    """Evaluate the detector on the evaluation subset and write a report."""
    from pawguard_ml.detector_eval import evaluate

    typer.echo(json.dumps(evaluate(model, manifest, img_dir, legacy, report), indent=2, default=float))


@app.command("dataset-prepare")
def dataset_prepare(
    name: str = typer.Option("dogfacenet-224"),
    version: str = typer.Option("1"),
    root: Path = typer.Option(ROOT / "data/raw/dogfacenet/after_4_bis"),
    seed: int = typer.Option(20261006),
    purpose: str = typer.Option("research_benchmark"),
    modality: str = typer.Option("face"),
    rights: str = typer.Option("Zenodo record 12578449, CC-BY-4.0 (G. Mougeot); web-collected pet photos, "
                               "third-party photo rights not documented; research evaluation only"),
    source: str = typer.Option("https://zenodo.org/records/12578449 (DogFaceNet_224resized.zip, "
                               "md5 010c207e202bb499039452aa7363b015)"),
) -> None:
    """Ingest -> validate -> duplicate graph -> label-conflict exclusion -> grouped open-set split -> leakage
    check. Writes data/manifests/datasets/<name>-v<version>.json (paths, hashes, labels, flags, roles; no images)."""
    from pawguard_ml import datasets as ds

    samples = ds.ingest(root, root.parent)
    dup = ds.duplicate_groups(samples)
    conflicts = ds.flag_label_conflicts(samples)
    split_stats = ds.split(samples, seed)
    leak = ds.leakage_checks(samples)
    excluded: dict[str, int] = {}
    for s in samples:
        if s.split == "excluded":
            excluded[s.exclusion] = excluded.get(s.exclusion, 0) + 1
    flags: dict[str, int] = {}
    for s in samples:
        for f in s.flags:
            flags[f] = flags.get(f, 0) + 1
    meta = {"name": name, "version": version, "purpose": purpose, "modality": modality, "rights": rights,
            "source": source, "seed": seed, "near_duplicate_phash_threshold": ds.PHASH_NEAR_DUP,
            "counts": {"identities": len({s.identity for s in samples}), "images": len(samples),
                       "duplicates": dup, "label_conflict_samples": conflicts, "excluded_by_reason": excluded,
                       "flags": flags, "split": split_stats},
            "leakage_check": leak,
            "limitations": ["No capture-session or site metadata in the source; near-duplicate groups are only a "
                            "proxy for sessions",
                            "Aligned face crops: results do not transfer to full-body field photos",
                            "Asserted labels not reviewed by knowledgeable annotators yet"]}
    out = ROOT / f"data/manifests/datasets/{name}-v{version}.json"
    sha = ds.write_manifest(samples, meta, out)
    typer.echo(json.dumps({"manifest": out.relative_to(ROOT).as_posix(), "sha256": sha, **meta["counts"],
                           "leakage_check": leak}, indent=2))


@app.command("annotate-export")
def annotate_export(
    manifest: Path = typer.Option(ROOT / "data/manifests/datasets/dogfacenet-224-v1.json"),
    out_dir: Path = typer.Option(ROOT / "data/annotation/dogfacenet-224-v1"),
    limit: int = typer.Option(60, help="Max conflict groups in this batch"),
) -> None:
    """Export label-conflict groups for two independent annotators: an offline HTML contact sheet (images
    referenced from the local raw folder, never uploaded) and a decisions CSV template."""
    import csv
    import html

    m = json.loads(manifest.read_text(encoding="utf-8"))
    raw_root = ROOT / "data/raw/dogfacenet"
    groups: dict[str, list[dict]] = {}
    for s in m["samples"]:
        if "cross_identity_duplicate" in s["flags"]:
            groups.setdefault(s["dup_group"], []).append(s)
    out_dir.mkdir(parents=True, exist_ok=True)
    rows, parts = [], []
    for gi, (_g, members) in enumerate(sorted(groups.items())[:limit]):
        figs = []
        for x in members:
            src = (raw_root / x["key"]).as_uri()
            cap = html.escape(x["identity"] + " / " + x["key"].split("/")[-1])
            figs.append(f'<figure><img src="{src}" width="160" alt="sample {cap}"><figcaption>{cap}</figcaption></figure>')
        idents = html.escape(", ".join(sorted({x["identity"] for x in members})))
        parts.append(f"<section><h2>Group {gi + 1} ({len(members)} images; identities {idents})</h2>"
                     f"<div>{''.join(figs)}</div></section>")
        rows += [{"sample_key": x["key"], "group": gi + 1, "asserted_identity": x["identity"],
                  "task": "identity_group", "annotator": "", "outcome": "", "proposed_label": "", "note": ""}
                 for x in members]
    head = ("<!doctype html><meta charset='utf-8'><title>Label conflicts</title>"
            "<style>body{font-family:sans-serif}figure{display:inline-block;margin:4px}div{display:flex;"
            "flex-wrap:wrap}</style><h1>Label-conflict review (research dataset; local only)</h1>"
            "<p>Each group contains near-identical images filed under different identities. For each image decide: "
            "same animal as the group's majority (agree), a different animal (disagree), or cannot tell. Two "
            "annotators work independently; disagreements go to adjudication.</p>")
    (out_dir / "review.html").write_text(head + "".join(parts), encoding="utf-8")
    with (out_dir / "decisions_template.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ["sample_key"])
        w.writeheader()
        w.writerows(rows)
    typer.echo(f"exported {min(limit, len(groups))} of {len(groups)} conflict groups to {out_dir}")


@app.command("annotate-import")
def annotate_import(
    decisions: list[Path] = typer.Argument(..., help="Completed decision CSVs, one per annotator"),
    out: Path = typer.Option(ROOT / "data/annotation/dogfacenet-224-v1/adjudication.json"),
) -> None:
    """Combine independent annotators: agreement -> 'agreed'; any disagreement or 'cannot_tell' -> 'pending'
    adjudication. Labels in a manifest change only through a new dataset version."""
    import csv

    by_sample: dict[str, list[dict]] = {}
    for path in decisions:
        with path.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if not row.get("annotator") or not row.get("outcome"):
                    raise typer.BadParameter(f"{path}: every row needs annotator and outcome")
                by_sample.setdefault(row["sample_key"], []).append(row)
    result = {}
    for key, rows in by_sample.items():
        outcomes = {r["outcome"] for r in rows}
        annotators = {r["annotator"] for r in rows}
        agreed = len(annotators) >= 2 and len(outcomes) == 1 and "cannot_tell" not in outcomes
        result[key] = {"state": "agreed" if agreed else "pending", "outcomes": sorted(outcomes),
                       "annotators": sorted(annotators)}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    typer.echo(json.dumps({s: sum(1 for v in result.values() if v["state"] == s) for s in ("agreed", "pending")}))


@app.command("dataset-register")
def dataset_register(manifest: Path = typer.Argument(...)) -> None:
    """Record a prepared dataset version (and its samples) in the database for lineage. Operator command."""
    import hashlib

    from sqlalchemy import create_engine, text

    from pawguard_api.settings import get_settings

    raw = manifest.read_bytes()
    m = json.loads(raw)
    url = (get_settings().migrate_database_url or "").replace("postgresql://", "postgresql+psycopg://", 1)
    rel = manifest.resolve().relative_to(ROOT).as_posix()
    with create_engine(url).begin() as c:
        dv = c.execute(text("""
            insert into app.dataset_versions (name, version, purpose, source_reference, rights_summary, consent_scope,
              modality, manifest_path, manifest_sha256, split_manifest_path, split_sha256, counts, status, frozen_at)
            values (:n, :v, :p, :src, :r, 'research_only', :mod, :path, :sha, :path, :sha, cast(:counts as jsonb),
              'frozen', now())
            on conflict (name, version) do nothing returning id"""),
            {"n": m["name"], "v": m["version"], "p": m["purpose"], "src": m["source"], "r": m["rights"],
             "mod": m["modality"], "path": rel, "sha": hashlib.sha256(raw).hexdigest(),
             "counts": json.dumps(m["counts"])}).scalar()
        if dv is None:
            typer.echo("already registered (versions are immutable; prepare a new version to change it)")
            return
        c.execute(text("""
            insert into app.dataset_samples (dataset_version_id, sample_key, source_sha256, phash, identity_label,
              modality, quality_flags, dup_group, split, split_role, exclusion_reason, transform_version)
            select :dv, x.key, x.sha256, x.phash, x.identity, :mod, x.flags, x.dup_group, x.split,
                   nullif(x.role, ''), nullif(x.exclusion, ''), :tv
            from jsonb_to_recordset(cast(:samples as jsonb)) as x(key text, sha256 text, phash text, identity text,
                 flags text[], dup_group text, split text, role text, exclusion text)"""),
                  {"dv": dv, "mod": m["modality"], "tv": m["transform_version"], "samples": json.dumps(m["samples"])})
    typer.echo(f"registered dataset {m['name']} v{m['version']} ({len(m['samples'])} samples), frozen")


from pawguard_ml import identity_cmds  # noqa: E402 - registers identity commands on the same app

identity_cmds.register(app)
