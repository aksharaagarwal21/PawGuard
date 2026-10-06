"""Phase 7: assisted identification plumbing through the real job pipeline, storage and the exported ONNX model.

Images are the repository's synthetic fixture: these tests check plumbing, isolation and states — not accuracy
(accuracy evidence lives in docs/EVALUATION.md)."""

import io
import json
from pathlib import Path

import pytest
from PIL import Image, ImageEnhance
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from test_media import _upload

pytestmark = pytest.mark.storage
REPO = Path(__file__).resolve().parents[3]
MANIFEST = REPO / "data/manifests/models/dinov2_small_arcface_head-v1.json"  # adopted model (Phase 7)
FIXTURE = REPO / "tests/fixtures/synthetic-animal.jpg"
BOX = {"x": 10, "y": 10, "w": 300, "h": 220}


def _jpeg(brightness: float = 1.0) -> bytes:
    img = Image.open(FIXTURE).convert("RGB")
    if brightness != 1.0:
        img = ImageEnhance.Brightness(img).enhance(brightness)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return buf.getvalue()


def _job(owner_engine, target_id: str, job_type: str) -> str:
    from pawguard_worker import identity, jobs, media

    with owner_engine.connect() as c:
        job_id = c.execute(text("select id from app.background_jobs where target_id = :t and job_type = :jt "
                                "order by queued_at desc limit 1"), {"t": target_id, "jt": job_type}).scalar_one()
    handler = {"media.validate": media.validate, "identity.enrol": identity.enrol,
               "identity.search": identity.search}[job_type]
    term = {"media.validate": media.reject, "identity.search": identity.search_failed}.get(job_type)
    return jobs.run(str(job_id), handler, on_terminal=term)


@pytest.fixture
def preview_model(owner_engine):
    """Register the exported identity model as *staged + research preview* in the test database."""
    if not MANIFEST.is_file():
        pytest.skip("identity model not exported (pawid identity-export)")
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if not (REPO / "models" / m["artifact_path"]).is_file():
        pytest.skip("identity model weights not present")
    with owner_engine.begin() as c:
        c.execute(text("update app.model_versions set research_preview = false, index_wanted = false "
                       "where task = 'identity_embedding'"))
        mid = c.execute(text("""
            insert into app.model_versions (task, name, family, version_label, artifact_path, sha256, size_bytes,
              licence, source_url, preprocessing, output_spec, thresholds, embedding_dim, evaluation_report,
              release_gate, research_preview, index_wanted)
            values ('identity_embedding', :n, :f, :v, :p, :sha, :size, :lic, :src, cast(:pre as jsonb),
              cast(:out as jsonb), cast(:thr as jsonb), 384, :rep, cast(:gate as jsonb), true, true)
            on conflict (task, name, version_label) do update set research_preview = true, index_wanted = true,
              state = 'staged'
            returning id"""),
            {"n": m["name"], "f": m["family"], "v": m["version_label"], "p": m["artifact_path"], "sha": m["sha256"],
             "size": m["size_bytes"], "lic": m["licence"], "src": m["source_url"],
             "pre": json.dumps(m["preprocessing"]), "out": json.dumps(m["output_spec"]),
             "thr": json.dumps(m["thresholds"]), "rep": m["evaluation_report"],
             "gate": json.dumps(m["release_gate"])}).scalar_one()
    yield mid
    with owner_engine.begin() as c:
        c.execute(text("update app.model_versions set research_preview = false, index_wanted = false "
                       "where task = 'identity_embedding'"))


@pytest.fixture
def demo_orgs(world, make_token):
    org = world.org(demo=True)
    vol = make_token(world.member(org, "field_volunteer"))
    other = world.org(demo=True)
    other_vol = make_token(world.member(other, "field_volunteer"))
    real = world.org()
    real_vol = make_token(world.member(real, "field_volunteer"))
    return {"org": org, "vol": vol, "other": other, "other_vol": other_vol, "real": real, "real_vol": real_vol}


def _approved_photo(client, auth, owner_engine, org, token, brightness=1.0) -> str:
    m = _upload(client, auth, {"org": org, "vol": token}, _jpeg(brightness))
    assert _job(owner_engine, m["id"], "media.validate") == "completed"
    return m["id"]


def _enrolled_animal(client, auth, owner_engine, org, token) -> tuple[str, str]:
    h = auth(token, org)
    photo = _approved_photo(client, auth, owner_engine, org, token)
    a = client.post("/api/v1/animals", headers=h, json={"species": "dog", "nickname": "Gallery dog"}).json()
    obs = client.post("/api/v1/observations", headers=h, json={
        "animal_id": a["id"], "observed_on": None, "time_precision": "unknown", "media_ids": [photo],
        "subjects": [{"media_id": photo, "source": "detector", "box": BOX, "dog_count": 1}]})
    assert obs.status_code == 201, obs.text
    with owner_engine.connect() as c:
        om = c.execute(text("select id from app.observation_media where media_id = :m"), {"m": photo}).scalar_one()
    assert _job(owner_engine, str(om), "identity.enrol") == "completed"
    return a["id"], photo


def test_unavailable_without_a_model_and_research_only_outside_demo(client, auth, demo_orgs, owner_engine):
    with owner_engine.begin() as c:
        c.execute(text("update app.model_versions set research_preview = false where task = 'identity_embedding'"))
    h = auth(demo_orgs["real_vol"], demo_orgs["real"])
    st = client.get("/api/v1/identity/status", headers=h).json()
    assert st["mode"] == "unavailable" and st["reason"] == "no_model"
    photo = _approved_photo(client, auth, owner_engine, demo_orgs["real"], demo_orgs["real_vol"])
    s = client.post("/api/v1/identity/searches", headers=h, json={"media_id": photo}).json()
    assert s["mode"] == "unavailable" and s["state"] == "unavailable" and s["candidates"] == []


def test_research_preview_runs_only_in_demo_organisations(client, auth, demo_orgs, preview_model):
    real = client.get("/api/v1/identity/status", headers=auth(demo_orgs["real_vol"], demo_orgs["real"])).json()
    assert real["mode"] == "unavailable" and real["reason"] == "research_only"
    demo = client.get("/api/v1/identity/status", headers=auth(demo_orgs["vol"], demo_orgs["org"])).json()
    assert demo["mode"] == "research_preview" and demo["release_gate_passed"] is False


def test_search_suggests_enrolled_animal_and_records_decision(client, auth, demo_orgs, owner_engine, preview_model):
    org, tok = demo_orgs["org"], demo_orgs["vol"]
    h = auth(tok, org)
    animal_id, _ = _enrolled_animal(client, auth, owner_engine, org, tok)
    with owner_engine.connect() as c:
        assert c.execute(text("select count(*) from app.animal_embeddings where animal_id = :a"),
                         {"a": animal_id}).scalar_one() == 1
    query = _approved_photo(client, auth, owner_engine, org, tok, brightness=1.1)
    created = client.post("/api/v1/identity/searches", headers=h, json={"media_id": query, "box": BOX})
    assert created.status_code == 201 and created.json()["state"] == "pending"
    sid = created.json()["id"]
    assert client.post(f"/api/v1/identity/searches/{sid}/decision", headers=h,
                       json={"decision": "not_sure"}).status_code == 409  # still running
    assert _job(owner_engine, sid, "identity.search") == "completed"
    res = client.get(f"/api/v1/identity/searches/{sid}", headers=h).json()
    assert res["state"] == "completed" and res["mode"] == "research_preview"
    top = res["candidates"][0]
    assert top["rank"] == 1 and top["animal"]["id"] == animal_id and top["photos"][0]["url"]
    assert "score" not in json.dumps(res)  # similarity is never exposed as a number
    # Decisions: the animal must be usable; latest decision counts; feedback reflects it
    assert client.post(f"/api/v1/identity/searches/{sid}/decision", headers=h,
                       json={"decision": "same_animal"}).status_code == 422
    d = client.post(f"/api/v1/identity/searches/{sid}/decision", headers=h,
                    json={"decision": "same_animal", "animal_id": animal_id})
    assert d.status_code == 200 and d.json()["decision"] == "same_animal"
    fb = client.get("/api/v1/identity/feedback", headers=h).json()
    assert fb["chose_top1"] == 1 and fb["decisions"] == 1
    # Another organisation sees neither the search nor the animal as a candidate
    oh = auth(demo_orgs["other_vol"], demo_orgs["other"])
    assert client.get(f"/api/v1/identity/searches/{sid}", headers=oh).status_code == 404
    oq = _approved_photo(client, auth, owner_engine, demo_orgs["other"], demo_orgs["other_vol"], brightness=1.1)
    os_ = client.post("/api/v1/identity/searches", headers=oh, json={"media_id": oq, "box": BOX}).json()
    assert _job(owner_engine, os_["id"], "identity.search") == "completed"
    other_res = client.get(f"/api/v1/identity/searches/{os_['id']}", headers=oh).json()
    assert other_res["state"] == "no_candidate" and other_res["gallery_animals"] == 0
    # Choosing an animal from another organisation is refused
    assert client.post(f"/api/v1/identity/searches/{os_['id']}/decision", headers=oh,
                       json={"decision": "same_animal", "animal_id": animal_id}).status_code == 422


def test_archived_animals_are_never_suggested_and_incomplete_index_is_reported(client, auth, demo_orgs,
                                                                               owner_engine, preview_model):
    org, tok = demo_orgs["org"], demo_orgs["vol"]
    h = auth(tok, org)
    animal_id, _ = _enrolled_animal(client, auth, owner_engine, org, tok)
    with owner_engine.begin() as c:
        c.execute(text("update app.animals set profile_state = 'archived', archived_reason = 'test' where id = :a"),
                  {"a": animal_id})
    q = _approved_photo(client, auth, owner_engine, org, tok, brightness=0.9)
    sid = client.post("/api/v1/identity/searches", headers=h, json={"media_id": q, "box": BOX}).json()["id"]
    _job(owner_engine, sid, "identity.search")
    assert all(c["animal"]["id"] != animal_id
               for c in client.get(f"/api/v1/identity/searches/{sid}", headers=h).json()["candidates"])
    # A linked photo whose enrolment has not run yet makes the index incomplete → stale_index, not silent misses
    b = client.post("/api/v1/animals", headers=h, json={"species": "dog", "nickname": "Not yet indexed"}).json()
    p = _approved_photo(client, auth, owner_engine, org, tok, brightness=0.8)
    client.post("/api/v1/observations", headers=h, json={
        "animal_id": b["id"], "time_precision": "unknown", "media_ids": [p],
        "subjects": [{"media_id": p, "source": "detector", "box": BOX, "dog_count": 1}]})
    sid2 = client.post("/api/v1/identity/searches", headers=h, json={"media_id": q, "box": BOX}).json()["id"]
    _job(owner_engine, sid2, "identity.search")
    assert client.get(f"/api/v1/identity/searches/{sid2}", headers=h).json()["state"] == "stale_index"


def test_identity_model_cannot_be_activated_without_a_passed_release_gate(owner_engine, preview_model):
    with pytest.raises(DBAPIError), owner_engine.begin() as c:
        c.execute(text("update app.model_versions set state = 'active', research_preview = false where id = :id"),
                  {"id": preview_model})
