"""Phase 5: photo analysis (OpenCV quality + YOLOX detection) through the real job pipeline and storage."""

import io
import json
from pathlib import Path

import pytest
from PIL import Image
from sqlalchemy import text
from test_media import _run_job, _upload, media_org  # noqa: F401 - shared fixture/helpers

pytestmark = pytest.mark.storage
REPO = Path(__file__).resolve().parents[3]
MANIFEST = REPO / "data/manifests/models/yolox_s-coco-0.1.1rc0.json"
COCO = REPO / "data/manifests/coco-val2017-dog-sample-v1.json"
COCO_DIR = REPO / "data/raw/coco/val2017_sample"


@pytest.fixture
def active_detector(owner_engine):
    """Register the verified detector as active in the *test* database (registry is per database)."""
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if not (REPO / "models" / m["artifact_path"]).is_file():
        pytest.skip("detector weights not downloaded (see docs/ML_PLAN.md)")
    with owner_engine.begin() as c:
        c.execute(text("update app.model_versions set state = 'retired' where task = 'dog_detection'"))
        c.execute(text("""
            insert into app.model_versions (task, name, family, version_label, artifact_path, sha256, size_bytes,
              licence, source_url, preprocessing, output_spec, thresholds, evaluation_report, state, activated_at)
            values ('dog_detection', :n, :f, :v, :p, :sha, :size, :lic, :src, cast(:pre as jsonb), '{}',
              cast(:thr as jsonb), :rep, 'active', now())
            on conflict (task, name, version_label) do update set state = 'active'"""),
                  {"n": m["name"], "f": m["family"], "v": m["version_label"], "p": m["artifact_path"],
                   "sha": m["sha256"], "size": m["size_bytes"], "lic": m["licence"], "src": m["source_url"],
                   "pre": json.dumps(m["preprocessing"]), "thr": json.dumps(m["thresholds"]),
                   "rep": m["evaluation_report"]})
    yield
    with owner_engine.begin() as c:
        c.execute(text("update app.model_versions set state = 'retired' where task = 'dog_detection'"))


def _coco_dog_image() -> bytes:
    if not COCO.is_file():
        pytest.skip("COCO sample not built (pawid coco-sample)")
    entries = json.loads(COCO.read_text(encoding="utf-8"))["images"]
    single = next(e for e in entries if e["split"] == "verification" and len(e["dog_boxes_xywh"]) == 1)
    return (COCO_DIR / single["file_name"]).read_bytes()


def test_real_photo_gets_detected_dog_boxes_in_image_coordinates(client, auth, media_org, owner_engine,  # noqa: F811
                                                                 active_detector):
    m = _upload(client, auth, media_org, _coco_dog_image())
    assert _run_job(owner_engine, m["id"]) == "completed"
    h = auth(media_org["vol"], media_org["org"])
    assert client.get(f"/api/v1/media/{m['id']}/analysis", headers=h).json()["state"] == "pending"
    assert _run_job(owner_engine, m["id"], "media.analyse") == "completed"
    a = client.get(f"/api/v1/media/{m['id']}/analysis", headers=h).json()
    assert a["state"] == "completed" and len(a["dogs"]) >= 1
    assert a["model_name"] == "yolox_s_coco" and a["pipeline_version"]
    for d in a["dogs"]:
        assert d["x"] >= 0 and d["x"] + d["w"] <= a["image_width"] + 1
        assert d["y"] >= 0 and d["y"] + d["h"] <= a["image_height"] + 1
    assert {q["region"] for q in a["quality"]} >= {"full", "top_dog"}
    # Another organisation cannot read the analysis
    assert client.get(f"/api/v1/media/{m['id']}/analysis",
                      headers=auth(media_org["outsider"], media_org["other_org"])).status_code == 404


def test_no_active_model_means_unavailable_not_fabricated(client, auth, media_org, owner_engine):  # noqa: F811
    with owner_engine.begin() as c:
        c.execute(text("update app.model_versions set state = 'retired' where task = 'dog_detection'"))
    m = _upload(client, auth, media_org, _coco_dog_image())
    _run_job(owner_engine, m["id"])
    _run_job(owner_engine, m["id"], "media.analyse")
    a = client.get(f"/api/v1/media/{m['id']}/analysis", headers=auth(media_org["vol"], media_org["org"])).json()
    assert a["state"] == "unavailable" and a["dogs"] == [] and a["model_name"] is None
    assert a["quality"]  # OpenCV measurements still run


def test_warned_photo_needs_a_reason_and_boxes_must_fit(client, auth, media_org, owner_engine,  # noqa: F811
                                                       active_detector):
    buf = io.BytesIO()
    Image.new("RGB", (800, 600), (3, 3, 3)).save(buf, format="JPEG")  # almost black frame
    m = _upload(client, auth, media_org, buf.getvalue())
    _run_job(owner_engine, m["id"])
    _run_job(owner_engine, m["id"], "media.analyse")
    h = auth(media_org["vol"], media_org["org"])
    a = client.get(f"/api/v1/media/{m['id']}/analysis", headers=h).json()
    assert a["state"] == "no_animal"
    assert "very_dark" in next(q for q in a["quality"] if q["region"] == "full")["warnings"]
    base = {"time_precision": "unknown", "media_ids": [m["id"]]}
    r = client.post("/api/v1/observations", headers=h, json=base)
    assert r.status_code == 422 and r.json()["error"]["fields"][0]["field"] == "quality_override_reason"
    r = client.post("/api/v1/observations", headers=h, json={
        **base, "quality_override_reason": "Only photo taken at night",
        "subjects": [{"media_id": m["id"], "source": "detector", "box": {"x": 700, "y": 10, "w": 200, "h": 50}}]})
    assert r.status_code == 422 and r.json()["error"]["fields"][0]["code"] == "box_out_of_bounds"
    r = client.post("/api/v1/observations", headers=h, json={
        **base, "quality_override_reason": "Only photo taken at night",
        "subjects": [{"media_id": m["id"], "source": "none", "dog_count": 0}]})
    assert r.status_code == 201
    with owner_engine.connect() as c:
        reason = c.execute(text("select override_reason from app.image_quality_results where media_id = :m "
                                "and decision = 'warn' limit 1"), {"m": m["id"]}).scalar()
    assert reason == "Only photo taken at night"
