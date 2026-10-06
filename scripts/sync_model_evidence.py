"""Copy the measured PawID evaluation (numbers + charts, no dog photos) into the web app's Model evidence page.

    uv run python scripts/sync_model_evidence.py

Reads ml/eval/dogfacenet/results.json and writes apps/web/src/content/pawid-evaluation.json (a subset: metrics with
CIs and counts, threshold, model, split hash, seed, commit, caveat) and copies the two chart PNGs to
apps/web/public/model-evidence/. Nothing is computed or rounded here; the page formats the stored values.
"""

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "ml/eval/dogfacenet"
r = json.loads((SRC / "results.json").read_text(encoding="utf-8"))
if r.get("smoke_test"):
    raise SystemExit("results.json is a smoke test; run the full evaluation first")
out = {k: r[k] for k in ("title", "caveat", "created_at", "seed", "commit", "command", "model", "dataset",
                         "selection_on_validation", "test", "metric_definitions", "timing")}
out["source"] = "ml/eval/dogfacenet/results.json"
dest = ROOT / "apps/web/src/content/pawid-evaluation.json"
dest.parent.mkdir(parents=True, exist_ok=True)
dest.write_bytes((json.dumps(out, indent=1, ensure_ascii=False) + "\n").encode("utf-8"))
charts = ROOT / "apps/web/public/model-evidence"
charts.mkdir(parents=True, exist_ok=True)
for name in ("chart_top1_top3.png", "chart_threshold_tradeoff.png"):
    shutil.copyfile(SRC / name, charts / name)
print(f"wrote {dest.relative_to(ROOT).as_posix()} and 2 charts")
