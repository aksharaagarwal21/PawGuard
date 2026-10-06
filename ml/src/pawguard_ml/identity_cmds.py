"""`pawid` identity commands: fetch the pinned backbone, embed, select on validation, evaluate once on test.

Pre-registered decision rule (written before any identity result was computed): among frozen-backbone
configurations, choose the one with the highest **validation** coverage@3 at the threshold where validation
FPIR ≤ 0.10 (tie-break: MRR). The test split is evaluated once, with configurations fixed in the selection file;
re-running the test command refuses unless explicitly acknowledged.
"""

import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import typer

from pawguard_ml import retrieval as rv

ROOT = Path(__file__).resolve().parents[3]
DATASET = ROOT / "data/manifests/datasets/dogfacenet-224-v1.json"
DATA_ROOT = ROOT / "data/raw/dogfacenet"
EVID = ROOT / "docs/evidence"
SELECTION = EVID / "identity-val-selection-dinov2s-v1.json"


def _model_dir() -> Path:
    from pawguard_ml.identity import MODEL_REVISION

    return ROOT / "models/dinov2-small" / MODEL_REVISION


def _cache_dir() -> Path:
    return ROOT / "data/derived/embeddings/dinov2-small"


def load_manifest(path: Path = DATASET) -> tuple[dict, str]:
    raw = path.read_bytes()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def split_rows(m: dict, split: str) -> list[dict]:
    order = {"gallery": 0, "query": 1, "unknown_query": 2, "training": 3, "": 3}
    rows = [s for s in m["samples"] if s["split"] == split]
    return sorted(rows, key=lambda s: (order.get(s["role"], 3), s["key"]))


_BACKBONE = None


def backbone():
    global _BACKBONE
    if _BACKBONE is None:
        import torch

        from pawguard_ml.identity import Backbone

        torch.set_num_threads(max(1, (torch.get_num_threads() or 2)))
        _BACKBONE = Backbone(_model_dir())
    return _BACKBONE


def embeddings(m: dict, sha: str, split: str, resize_mode: str, mask: str = "none", flip: bool = False) -> dict:
    from pawguard_ml.identity import cached_embeddings

    rows = split_rows(m, split)
    emb = cached_embeddings(_cache_dir(), sha, backbone, DATA_ROOT, [r["key"] for r in rows], resize_mode, mask,
                            flip, tag=f"{m['name']}-v{m['version']}-{split}")
    emb["rows"] = rows
    return emb


def to_split(emb: dict, vecs: np.ndarray) -> rv.SplitData:
    rows = emb["rows"]
    roles = np.array([r["role"] for r in rows])
    ids = np.array([r["identity"] for r in rows])
    ok = ~np.isin(np.array(emb["keys"]), np.array(emb["failed"], dtype=str)) if emb["failed"] else np.ones(len(rows), bool)
    g, q, u = (roles == "gallery") & ok, (roles == "query") & ok, (roles == "unknown_query") & ok
    return rv.SplitData(ids[g], vecs[g], ids[q], vecs[q], ids[u], vecs[u])


def _pooled(emb: dict, pooling: str) -> np.ndarray:
    from pawguard_worker.vision.embed import pool

    return pool(emb["cls"], emb["patch_mean"], pooling)


def _round(d: dict) -> dict:
    return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in d.items()}


def register(app: typer.Typer) -> None:
    @app.command("model-fetch")
    def model_fetch() -> None:
        """Download the pinned DINOv2-S files (safetensors + configs only) and verify them against the Hub."""
        from pawguard_ml.hf_fetch import fetch
        from pawguard_ml.identity import MODEL_REPO, MODEL_REVISION

        res = fetch(MODEL_REPO, MODEL_REVISION, ["config.json", "preprocessor_config.json", "model.safetensors",
                                                 "README.md"], _model_dir())
        out = ROOT / "data/manifests/models/dinov2-small-source.json"
        out.write_text(json.dumps(res, indent=2) + "\n", encoding="utf-8")
        typer.echo(json.dumps(res, indent=2))

    @app.command("embed")
    def embed(split: str = typer.Option("val"), resize_mode: str = typer.Option("resize224"),
              mask: str = typer.Option("none"), flip: bool = typer.Option(False)) -> None:
        """Compute (or reuse cached) frozen-backbone embeddings for one split of the frozen dataset."""
        m, sha = load_manifest()
        t0 = time.perf_counter()
        emb = embeddings(m, sha, split, resize_mode, mask, flip)
        typer.echo(json.dumps({"split": split, "images": len(emb["keys"]), "failed": len(emb["failed"]),
                               "cache": emb["cache"], "seconds": round(time.perf_counter() - t0, 1)}))

    @app.command("identity-select")
    def identity_select(fpir_target: float = typer.Option(0.10), reps: int = typer.Option(1000)) -> None:
        """Validation only: compare preprocessing × pooling × multi-image aggregation, pick by the pre-registered
        rule, then analyse gallery size, number of enrolled identities, background dependence and margins."""
        from pawguard_worker.vision.embed import POOLINGS, RESIZE_MODES

        m, sha = load_manifest()
        grid, embs = [], {}
        for rm in RESIZE_MODES:
            embs[rm] = embeddings(m, sha, "val", rm)
            for pooling in POOLINGS:
                d = to_split(embs[rm], _pooled(embs[rm], pooling))
                for agg in rv.AGGREGATIONS:
                    sc = rv.score(d, agg)
                    tau = rv.threshold_for_fpir(sc.u_top1, fpir_target)
                    grid.append({"resize_mode": rm, "pooling": pooling, "aggregation": agg, "tau": round(tau, 5),
                                 "metrics": _round(rv.metrics(sc, tau))})
        best = max(grid, key=lambda r: (r["metrics"]["coverage_at_3"], r["metrics"]["mrr"]))
        rm, pooling, agg, tau = best["resize_mode"], best["pooling"], best["aggregation"], best["tau"]
        d = to_split(embs[rm], _pooled(embs[rm], pooling))
        sc = rv.score(d, agg)
        gallery_size = []
        for cap in (1, 2, 3, None):
            for a in rv.AGGREGATIONS:
                s2 = rv.score(rv.cap_gallery(d, cap, seed=1), a)
                gallery_size.append({"max_gallery_images_per_identity": cap or "all", "aggregation": a,
                                     "metrics_at_selected_tau": _round(rv.metrics(s2, tau))})
        enrolled = []
        for frac in (0.25, 0.5, 1.0):
            d2 = rv.subsample_identities(d, frac, seed=1)
            s2 = rv.score(d2, agg)
            enrolled.append({"fraction_of_identities_enrolled": frac, "identities": len(np.unique(d2.gallery_ids)),
                             "metrics_at_selected_tau": _round(rv.metrics(s2, tau))})
        masking = []
        for mask in ("center_only", "border_only"):
            e = embeddings(m, sha, "val", rm, mask=mask)
            s2 = rv.score(to_split(e, _pooled(e, pooling)), agg)
            masking.append({"mask": mask, "metrics_at_selected_tau": _round(rv.metrics(s2, tau)),
                            "own_tau_fpir_0_10": round(rv.threshold_for_fpir(s2.u_top1, fpir_target), 5)})
        report = {
            "purpose": "Validation-only model selection for the frozen DINOv2-S baseline (research benchmark).",
            "decision_rule": "max validation coverage@3 at the threshold giving validation FPIR <= "
                             f"{fpir_target}; tie-break MRR",
            "dataset": {"manifest": DATASET.relative_to(ROOT).as_posix(), "sha256": sha, "split": "val",
                        "gallery_images": len(d.gallery_ids), "enrolled_identities": len(np.unique(d.gallery_ids)),
                        "queries": len(d.query_ids), "unknown_queries": len(d.unknown_ids),
                        "unknown_identities": len(np.unique(d.unknown_ids)),
                        "failed_to_process": len(embs[rm]["failed"])},
            "model": {"repo": "facebook/dinov2-small", "revision": _model_dir().name, "frozen": True},
            "grid": grid,
            "selected": {"resize_mode": rm, "pooling": pooling, "aggregation": agg, "tau": tau,
                         "candidate_list_size": 3, "fpir_target": fpir_target},
            "selected_val_with_ci": rv.bootstrap(sc, tau, reps=reps),
            "gallery_size_effect": gallery_size,
            "enrolled_identity_count_effect": enrolled,
            "background_dependence": masking,
            "margin_top1_vs_top2": rv.margin_analysis(sc, tau),
            "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        }
        SELECTION.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
        typer.echo(json.dumps({"selected": report["selected"], "val": report["selected_val_with_ci"]}, indent=1))

    @app.command("identity-train")
    def identity_train(fpir_target: float = typer.Option(0.10), min_gain: float = typer.Option(0.02),
                       reps: int = typer.Option(1000)) -> None:
        """Head-only adaptation experiments on frozen features, selected on validation. Adopted only if validation
        coverage@3 improves on the frozen baseline by at least `min_gain` (absolute); otherwise the baseline stays."""
        import platform

        import psutil
        import torch
        from safetensors.torch import save_file

        from pawguard_ml.adapt import HeadConfig, features, train_head

        sel = json.loads(SELECTION.read_text(encoding="utf-8"))["selected"]
        base_val = json.loads(SELECTION.read_text(encoding="utf-8"))["selected_val_with_ci"]
        m, sha = load_manifest()
        rm, agg = sel["resize_mode"], sel["aggregation"]
        tr = embeddings(m, sha, "train", rm)
        trf = embeddings(m, sha, "train", rm, flip=True)
        va = embeddings(m, sha, "val", rm)
        y = np.array([r["identity"] for r in tr["rows"]])
        x = features(tr["cls"], tr["patch_mean"])
        x_flip = features(trf["cls"], trf["patch_mean"])
        vf = features(va["cls"], va["patch_mean"])
        configs = [HeadConfig(objective="supcon"), HeadConfig(objective="supcon", hidden=768),
                   HeadConfig(objective="arcface"), HeadConfig(objective="supcon", flip_augment=True)]
        runs, heads = [], []
        for cfg in configs:
            xs, ys = (np.concatenate([x, x_flip]), np.concatenate([y, y])) if cfg.flip_augment else (x, y)
            res = train_head(xs, ys, vf, lambda vz: to_split(va, vz), agg, fpir_target, cfg)
            heads.append(res.pop("head"))
            runs.append(res)
            typer.echo(json.dumps({"config": res["config"]["objective"], "hidden": cfg.hidden, "flip": cfg.flip_augment,
                                   "best_epoch": res["best_epoch"], "val": res["val_best"]}))
        best_i = max(range(len(runs)), key=lambda i: (runs[i]["val_best"]["coverage_at_3"], runs[i]["val_best"]["mrr"]))
        head = heads[best_i]
        with torch.inference_mode():
            vz = head(torch.from_numpy(vf)).numpy()
        sc = rv.score(to_split(va, vz), agg)
        tau = rv.threshold_for_fpir(sc.u_top1, fpir_target)
        gain = runs[best_i]["val_best"]["coverage_at_3"] - base_val["coverage_at_3"]["value"]
        run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        run_dir = ROOT / "data/derived/runs" / f"identity-head-{run_id}"
        run_dir.mkdir(parents=True, exist_ok=True)
        save_file({k: v.contiguous() for k, v in head.state_dict().items()}, str(run_dir / "head.safetensors"))
        code = hashlib.sha256()
        for p in [*sorted((ROOT / "ml/src").rglob("*.py")), ROOT / "services/worker/src/pawguard_worker/vision/embed.py"]:
            code.update(p.read_bytes())
        report = {
            "run_id": run_id, "purpose": "Head-only adaptation on frozen DINOv2-S features (research benchmark)",
            "decision_rule": f"adopt only if validation coverage@3 gain >= {min_gain} over the frozen baseline",
            "baseline_val": base_val, "selected_preprocessing": sel,
            "runs": runs, "best_run": best_i, "best_val_with_ci": rv.bootstrap(sc, tau, reps=reps),
            "best_val_tau": round(tau, 5), "val_coverage_at_3_gain": round(gain, 4),
            "adopted": bool(gain >= min_gain),
            "head_artifact": {"path": run_dir.relative_to(ROOT).as_posix() + "/head.safetensors",
                              "sha256": hashlib.sha256((run_dir / "head.safetensors").read_bytes()).hexdigest()},
            "lineage": {"dataset_manifest_sha256": sha, "split_sha256": sha, "code_sha256": code.hexdigest(),
                        "code_commit": None, "code_commit_note": "no git commits exist yet; code hash recorded",
                        "environment_lock_sha256": hashlib.sha256((ROOT / "ml/uv.lock").read_bytes()).hexdigest(),
                        "python": platform.python_version(), "torch": torch.__version__,
                        "device": "cpu", "threads": torch.get_num_threads()},
            "resources": {"peak_rss_mb": round(psutil.Process().memory_info().peak_wset / 1e6, 1)
                          if hasattr(psutil.Process().memory_info(), "peak_wset")
                          else round(psutil.Process().memory_info().rss / 1e6, 1),
                          "train_seconds_total": round(sum(r["train_seconds"] for r in runs), 1)},
            "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        }
        (EVID / "identity-train-runs-v1.json").write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
        typer.echo(json.dumps({"best_run": best_i, "adopted": report["adopted"], "gain": report["val_coverage_at_3_gain"],
                               "best_val": report["best_val_with_ci"]}, indent=1))

    @app.command("identity-test")
    def identity_test(acknowledge_reuse: str = typer.Option("", help="Reason, required to re-run on test"),
                      reps: int = typer.Option(1000)) -> None:
        """Protected final evaluation on the test split with configurations and thresholds fixed on validation."""
        import torch
        from safetensors.torch import load_file

        from pawguard_ml.adapt import Head, features

        out = EVID / "identity-test-dinov2s-v1.json"
        if out.exists() and not acknowledge_reuse:
            raise typer.BadParameter("test report exists; re-running needs --acknowledge-reuse '<reason>'")
        sel = json.loads(SELECTION.read_text(encoding="utf-8"))["selected"]
        train_path = EVID / "identity-train-runs-v1.json"
        train = json.loads(train_path.read_text(encoding="utf-8")) if train_path.exists() else None
        m, sha = load_manifest()
        te = embeddings(m, sha, "test", sel["resize_mode"])
        results = {}
        d = to_split(te, _pooled(te, sel["pooling"]))
        sc = rv.score(d, sel["aggregation"])
        results["frozen_baseline"] = {"config": sel, "tau_from_val": sel["tau"],
                                      "metrics": rv.bootstrap(sc, sel["tau"], reps=reps),
                                      "margin_top1_vs_top2": rv.margin_analysis(sc, sel["tau"])}
        errors = _error_examples(d, sc, sel["tau"], sel["aggregation"])
        if train:
            best = train["runs"][train["best_run"]]["config"]
            head = Head(768, 384, best["hidden"])
            head.load_state_dict(load_file(str(ROOT / train["head_artifact"]["path"])))
            head.eval()
            with torch.inference_mode():
                hz = head(torch.from_numpy(features(te["cls"], te["patch_mean"]))).numpy()
            hsc = rv.score(to_split(te, hz), sel["aggregation"])
            results["adapted_head"] = {"config": best, "adopted_on_validation": train["adopted"],
                                       "tau_from_val": train["best_val_tau"],
                                       "metrics": rv.bootstrap(hsc, train["best_val_tau"], reps=reps)}
        query_rows = [r for r in te["rows"] if r["role"] == "query"]
        report = {
            "purpose": "Protected test evaluation, DogFaceNet 224 v1 (research benchmark: aligned face crops of pet "
                       "dogs, unreviewed labels). Not evidence of field performance on community dogs.",
            "dataset": {"manifest_sha256": sha, "split": "test", "gallery_images": len(d.gallery_ids),
                        "enrolled_identities": len(np.unique(d.gallery_ids)), "queries": len(d.query_ids),
                        "unknown_queries": len(d.unknown_ids), "unknown_identities": len(np.unique(d.unknown_ids)),
                        "failed_to_process": len(te["failed"])},
            "measured": "open-set identification against an enrolled gallery (not pairwise verification)",
            "results": results,
            "subgroups": {"available": ["grayscale flag"],
                          "grayscale_queries": sum("grayscale" in r["flags"] for r in query_rows),
                          "note": "No site, lighting, pose, occlusion or coat-colour metadata exists in this source; "
                                  "subgroup results cannot be reported."},
            "error_examples": errors,
            "reuse_acknowledgement": acknowledge_reuse or None,
            "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        }
        out.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
        _error_gallery(errors, ROOT / "data/derived/error-gallery/identity-test-v1.html")
        typer.echo(json.dumps({k: v["metrics"] for k, v in results.items()}, indent=1))

    @app.command("identity-export")
    def identity_export(n_parity: int = typer.Option(50), n_latency: int = typer.Option(100)) -> None:
        """Export the selected identity model to ONNX — the frozen backbone, plus the adapted head when validation
        adopted it — check numerical + retrieval parity against PyTorch on validation, measure single-image CPU
        latency and memory, and write the model manifest (status: research only)."""
        import platform

        import cv2
        import psutil
        import torch
        from safetensors.torch import load_file

        from pawguard_ml.adapt import Head, features
        from pawguard_worker.vision.embed import EmbedConfig, OnnxEmbedder, pool, preprocess
        from pawguard_worker.vision.yolox import sha256_file

        sel = json.loads(SELECTION.read_text(encoding="utf-8"))["selected"]
        train_path = EVID / "identity-train-runs-v1.json"
        train = json.loads(train_path.read_text(encoding="utf-8")) if train_path.exists() else None
        use_head = bool(train and train["adopted"])
        bb = backbone()
        if use_head:
            best = train["runs"][train["best_run"]]["config"]
            head = Head(768, 384, best["hidden"])
            head.load_state_dict(load_file(str(ROOT / train["head_artifact"]["path"])))
            head.eval()

            class Combined(torch.nn.Module):
                def __init__(self) -> None:
                    super().__init__()
                    self.bb, self.head = bb, head

                def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
                    c, p = self.bb(x)
                    f = torch.cat([torch.nn.functional.normalize(c, dim=-1),
                                   torch.nn.functional.normalize(p, dim=-1)], dim=-1)
                    return c, p, self.head(f)

            module, outputs = Combined().eval(), ["cls", "patch_mean", "embedding"]
            pooling, tau, name = "head", train["best_val_tau"], "dinov2_small_arcface_head"
        else:
            module, outputs = bb, ["cls", "patch_mean"]
            pooling, tau, name = sel["pooling"], sel["tau"], "dinov2_small_frozen"
        out = _model_dir() / f"{name}.onnx"
        torch.onnx.export(module, (torch.zeros(1, 3, 224, 224),), str(out), input_names=["pixel_values"],
                          output_names=outputs, opset_version=18, dynamo=False,
                          dynamic_axes={"pixel_values": {0: "n"}, **{o: {0: "n"} for o in outputs}})
        proc = psutil.Process()
        rss0 = proc.memory_info().rss
        emb = OnnxEmbedder(out, EmbedConfig(sel["resize_mode"], pooling), threads=2)
        rss_loaded = proc.memory_info().rss
        m, sha = load_manifest()
        va = embeddings(m, sha, "val", sel["resize_mode"])
        keys = va["keys"]
        got: dict[str, list] = {o: [] for o in outputs}
        for i in range(0, len(keys), 32):
            batch = np.concatenate([preprocess(cv2.imread(str(DATA_ROOT / k)), sel["resize_mode"])
                                    for k in keys[i:i + 32]])
            for o, v in zip(outputs, emb.session.run(outputs, {emb.input_name: batch}), strict=True):
                got[o].append(v)
        onnx_out = {o: np.concatenate(v) for o, v in got.items()}
        if use_head:
            with torch.inference_mode():
                tv = head(torch.from_numpy(features(va["cls"], va["patch_mean"]))).numpy()
            ov = pool(onnx_out["embedding"], onnx_out["embedding"], "cls")
        else:
            tv = pool(va["cls"], va["patch_mean"], pooling)
            ov = pool(onnx_out["cls"], onnx_out["patch_mean"], pooling)
        n = min(n_parity, len(keys))
        torch_sc = rv.score(to_split(va, tv), sel["aggregation"])
        onnx_sc = rv.score(to_split(va, ov), sel["aggregation"])
        parity = {"images": len(keys), "fixed_sample_n": n, "reference": "PyTorch backbone (cached) + head",
                  "max_abs_diff_cls_fixed_sample": float(np.abs(va["cls"][:n] - onnx_out["cls"][:n]).max()),
                  "max_abs_diff_patch_mean_fixed_sample": float(np.abs(va["patch_mean"][:n]
                                                                       - onnx_out["patch_mean"][:n]).max()),
                  "min_cosine_embedding_all": round(float((tv * ov).sum(1).min()), 6),
                  "rank_agreement_all_queries": round(float((torch_sc.rank == onnx_sc.rank).mean()), 4),
                  "torch_metrics": _round(rv.metrics(torch_sc, tau)),
                  "onnx_metrics": _round(rv.metrics(onnx_sc, tau))}
        lat = []
        for k in keys[:n_latency]:
            t0 = time.perf_counter()
            emb.embed(cv2.imread(str(DATA_ROOT / k)))
            lat.append((time.perf_counter() - t0) * 1000)
        rss_after = proc.memory_info().rss
        perf = {"single_image_ms_median": round(float(np.median(lat)), 1),
                "single_image_ms_p95": round(float(np.percentile(lat, 95)), 1), "n": len(lat), "threads": 2,
                "includes": "decode + preprocess + inference", "cpu": platform.processor() or platform.machine(),
                "rss_increase_mb_after_load": round((rss_loaded - rss0) / 1e6, 1),
                "rss_increase_mb_after_inference": round((rss_after - rss0) / 1e6, 1),
                "onnx_size_bytes": out.stat().st_size}
        source = json.loads((ROOT / "data/manifests/models/dinov2-small-source.json").read_text(encoding="utf-8"))
        manifest = {
            "task": "identity_embedding", "name": name, "family": "DINOv2 ViT-S/14",
            "version_label": f"{_model_dir().name[:8]}-{sel['resize_mode']}-{pooling}-v1",
            "artifact_path": f"dinov2-small/{_model_dir().name}/{name}.onnx",
            "sha256": sha256_file(out), "size_bytes": out.stat().st_size, "embedding_dim": 384,
            "licence": "Backbone: Apache-2.0 (facebook/dinov2-small). Head: trained by PawGuard on DogFaceNet "
                       "(CC-BY-4.0 record; research use) — research only.",
            "source_url": f"https://huggingface.co/facebook/dinov2-small/tree/{_model_dir().name}",
            "source_files": source["files"],
            "head": ({"objective": best["objective"], "hidden": best["hidden"],
                      "artifact": train["head_artifact"], "training_report": "docs/evidence/identity-train-runs-v1.json"}
                     if use_head else None),
            "preprocessing": {"resize_mode": sel["resize_mode"], "pooling": pooling, "crop_margin": 0.1,
                              "channel_order": "RGB", "scale": "1/255", "mean": [0.485, 0.456, 0.406],
                              "std": [0.229, 0.224, 0.225], "interpolation": "bicubic (cv2.INTER_CUBIC)",
                              "input_size": [224, 224], "patch": 14,
                              "verified_by": "pawid identity-export parity on the validation split"},
            "output_spec": {"outputs": outputs, "dim": 384,
                            "normalised": "L2 (head output)" if use_head else "L2 after pooling"},
            "thresholds": {"similarity_tau": tau, "candidate_list_size": 3, "aggregation": sel["aggregation"],
                           "chosen_on": "validation (FPIR <= 0.10)"},
            "evaluation_report": "docs/evidence/identity-test-dinov2s-v1.json",
            "release_gate": {"passed": False, "reason": "Evaluated only on a research face benchmark (DogFaceNet), "
                             "not on permissioned field photos of the target population (ML_PLAN release gate)."},
            "parity": parity, "performance": perf,
            "notes": "Research only. Exported with torch.onnx (TorchScript exporter, opset 18). Embeddings are for "
                     "candidate retrieval with human confirmation; never an identification on their own.",
        }
        mpath = ROOT / f"data/manifests/models/{name}-v1.json"
        mpath.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        typer.echo(json.dumps({"manifest": mpath.relative_to(ROOT).as_posix(), "parity": parity,
                               "performance": perf}, indent=1))

def _error_examples(d: rv.SplitData, sc: rv.Scored, tau: float, aggregation: str, n: int = 24) -> dict:
    labels, s = rv.identity_scores(d.query, d, aggregation)
    misses = [i for i in np.argsort(sc.true_score) if sc.rank[i] > 1][:n]
    _, su = rv.identity_scores(d.unknown, d, aggregation)
    false_pos = [i for i in np.argsort(-su.max(1)) if su[i].max() >= tau][:n]

    def top3(row: np.ndarray) -> list:
        return [{"identity": str(labels[k]), "score": round(float(row[k]), 4)} for k in np.argsort(-row)[:3]]

    return {"enrolled_misses": [{"query_index": int(i), "true_identity": str(d.query_ids[i]),
                                 "true_rank": int(sc.rank[i]), "top3": top3(s[i])} for i in misses],
            "unknown_false_suggestions": [{"unknown_index": int(i), "identity": str(d.unknown_ids[i]),
                                           "top3": top3(su[i])} for i in false_pos]}


def _error_gallery(errors: dict, path: Path) -> None:
    """Local-only HTML listing (identity labels and scores; no images are copied or uploaded)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for kind, items in errors.items():
        rows.append(f"<h2>{kind}</h2><table border=1><tr><th>#</th><th>truth</th><th>top-3</th></tr>")
        for e in items:
            truth = e.get("true_identity") or f"unknown {e.get('identity')}"
            cands = ", ".join(f"{c['identity']}: {c['score']}" for c in e["top3"])
            idx = e.get("query_index", e.get("unknown_index"))
            rows.append(f"<tr><td>{idx}</td><td>{truth}</td><td>{cands}</td></tr>")
        rows.append("</table>")
    path.write_text("<!doctype html><meta charset=utf-8><title>Identity errors (local, research)</title>"
                    + "".join(rows), encoding="utf-8")
