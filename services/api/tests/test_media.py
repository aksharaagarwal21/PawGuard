"""Private media pipeline against the real local Storage service and the worker's validation code."""

import io
import uuid

import httpx
import pytest
from PIL import Image
from sqlalchemy import text

pytestmark = pytest.mark.storage


def _jpeg_with_orientation(w: int = 400, h: int = 200, orientation: int = 6) -> bytes:
    img = Image.new("RGB", (w, h), (180, 120, 60))
    exif = Image.Exif()
    exif[0x0112] = orientation  # rotate 90° on display
    exif[0x8825] = {2: (13.0, 5.0, 0.0)}  # a GPS block that must not survive
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif)
    return buf.getvalue()


@pytest.fixture
def media_org(world, make_token):
    org = world.org()
    vol = world.member(org, "field_volunteer")
    other_org = world.org()
    outsider = world.member(other_org, "veterinary_reviewer")
    return {"org": org, "vol": make_token(vol), "other_org": other_org, "outsider": make_token(outsider)}


def _upload(client, auth, s, data: bytes, mime: str = "image/jpeg", declared: int | None = None,
            purpose: str = "animal_photo") -> dict:
    h = auth(s["vol"], s["org"])
    intent = client.post("/api/v1/media/upload-intents", headers=h,
                         json={"purpose": purpose, "content_type": mime, "byte_size": declared or len(data)})
    assert intent.status_code == 201, intent.text
    body = intent.json()
    put = httpx.put(body["upload_url"], content=data, headers=body["headers"], timeout=20)
    assert put.status_code == 200, put.text
    done = client.post(f"/api/v1/media/{body['media_id']}/complete", headers=h)
    assert done.status_code == 200, done.text
    return done.json()


def _run_job(owner_engine, media_id: str, job_type: str = "media.validate") -> str:
    from pawguard_worker import analysis, jobs, media

    with owner_engine.connect() as c:
        job_id = c.execute(text("select id from app.background_jobs where target_id = :m and job_type = :t "
                                "order by queued_at desc limit 1"), {"m": media_id, "t": job_type}).scalar_one()
    if job_type == "media.analyse":
        return jobs.run(str(job_id), analysis.analyse)
    return jobs.run(str(job_id), media.validate, on_terminal=media.reject)


def test_valid_photo_is_normalised_stripped_and_served_privately(client, auth, media_org, owner_engine):
    s = media_org
    m = _upload(client, auth, s, _jpeg_with_orientation())
    assert m["state"] == "uploaded" and m["job_state"] == "queued"
    # Not viewable before validation
    assert client.get(f"/api/v1/media/{m['id']}/url", headers=auth(s["vol"], s["org"])).status_code == 409
    assert _run_job(owner_engine, m["id"]) == "completed"
    assert _run_job(owner_engine, m["id"]) == "skipped"  # duplicate delivery is a no-op
    info = client.get(f"/api/v1/media/{m['id']}", headers=auth(s["vol"], s["org"])).json()
    assert info["state"] == "approved" and (info["width"], info["height"]) == (200, 400)  # EXIF rotation applied
    link = client.get(f"/api/v1/media/{m['id']}/url?variant=display", headers=auth(s["vol"], s["org"])).json()
    img_bytes = httpx.get(link["url"], timeout=20).content
    out = Image.open(io.BytesIO(img_bytes))
    assert out.format == "JPEG" and out.size == (200, 400)
    assert not out.getexif()  # no EXIF (orientation, GPS) in what is served
    with owner_engine.connect() as c:
        key = c.execute(text("select object_key from app.media_assets where id = :m"), {"m": m["id"]}).scalar()
    from pawguard_api.integrations.storage import get_storage

    assert get_storage().info(key) is None  # quarantined original (with GPS EXIF) removed
    # Other organisations cannot see it or its status
    ho = auth(s["outsider"], s["other_org"])
    assert client.get(f"/api/v1/media/{m['id']}", headers=ho).status_code == 404
    assert client.get(f"/api/v1/media/{m['id']}/url", headers=ho).status_code == 404


def test_disguised_file_is_rejected_from_bytes(client, auth, media_org, owner_engine):
    m = _upload(client, auth, media_org, b"<html>not an image</html>" * 20)
    assert _run_job(owner_engine, m["id"]) == "failed"
    info = client.get(f"/api/v1/media/{m['id']}", headers=auth(media_org["vol"], media_org["org"])).json()
    assert info["state"] == "rejected" and info["rejection_code"] == "decode_failed"


def test_png_declared_as_jpeg_is_a_type_mismatch(client, auth, media_org, owner_engine):
    buf = io.BytesIO()
    Image.new("RGB", (100, 100)).save(buf, format="PNG")
    m = _upload(client, auth, media_org, buf.getvalue(), mime="image/jpeg")
    _run_job(owner_engine, m["id"])
    info = client.get(f"/api/v1/media/{m['id']}", headers=auth(media_org["vol"], media_org["org"])).json()
    assert info["rejection_code"] == "type_mismatch"


def test_decompression_bomb_is_refused(client, auth, media_org, owner_engine):
    buf = io.BytesIO()
    Image.new("1", (9000, 9000)).save(buf, format="PNG", optimize=True)  # tiny file, 81 MP
    m = _upload(client, auth, media_org, buf.getvalue(), mime="image/png")
    _run_job(owner_engine, m["id"])
    info = client.get(f"/api/v1/media/{m['id']}", headers=auth(media_org["vol"], media_org["org"])).json()
    assert info["state"] == "rejected" and info["rejection_code"] == "too_many_pixels"


def test_declared_size_mismatch_is_rejected_at_completion(client, auth, media_org):
    data = _jpeg_with_orientation()
    m = _upload(client, auth, media_org, data, declared=len(data) + 10)
    assert m["state"] == "rejected" and m["rejection_code"] == "declared_metadata_mismatch"


def test_pdf_evidence_only_for_evidence_purposes(client, auth, media_org):
    h = auth(media_org["vol"], media_org["org"])
    r = client.post("/api/v1/media/upload-intents", headers=h,
                    json={"purpose": "animal_photo", "content_type": "application/pdf", "byte_size": 1000})
    assert r.status_code == 422
    r = client.post("/api/v1/media/upload-intents", headers=h,
                    json={"purpose": "vaccination_evidence", "content_type": "image/gif", "byte_size": 1000})
    assert r.status_code == 422
    r = client.post("/api/v1/media/upload-intents", headers=h,
                    json={"purpose": "vaccination_evidence", "content_type": "image/jpeg", "byte_size": 16 * 1024 * 1024})
    assert r.status_code == 422


def test_unfinished_upload_cannot_be_completed_or_attached(client, auth, media_org):
    h = auth(media_org["vol"], media_org["org"])
    intent = client.post("/api/v1/media/upload-intents", headers=h,
                         json={"purpose": "animal_photo", "content_type": "image/jpeg", "byte_size": 1234}).json()
    r = client.post(f"/api/v1/media/{intent['media_id']}/complete", headers=h)
    assert r.status_code == 409 and r.json()["error"]["code"] == "upload_incomplete"
    r = client.post("/api/v1/observations", headers=h,
                    json={"time_precision": "unknown", "media_ids": [intent["media_id"]]})
    assert r.status_code == 422 and r.json()["error"]["fields"][0]["code"] == "media_not_ready"
    assert client.delete(f"/api/v1/media/{intent['media_id']}", headers=h).status_code == 204
    assert client.get(f"/api/v1/media/{uuid.uuid4()}", headers=h).status_code == 404
