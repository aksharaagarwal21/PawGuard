"""Prepare the DEMO organisations for a demonstration.

Pet vaccination reminders: as the demo pet owner, through the normal owner API, it uploads the synthetic test
certificate (tests/fixtures/synthetic-certificate.jpg — a generated drawing, not a real record) and submits one
owner-entered vaccination for Bruno, so the clinic vet has one owner upload awaiting verification.

Photo lookup:
Through the normal API (as the demo volunteer) it uploads one licence-filtered COCO dog photo from the local sample,
waits for validation and detection, records it as a sighting of the first registered demo animal with the detected
dog chosen as the subject, and waits until the research-preview gallery has indexed it. The same file can then be
used on the capture page to show a "possible match".

This prepares a *demonstration of the workflow*, not evidence of accuracy (the lookup uses the same photo).
Only runs in development/test with demo mode on. Requires the API (:8000), worker and dispatcher to be running.

    uv run python scripts/demo_prepare.py
"""

import json
import os
import sys
import time
from pathlib import Path

import httpx

from pawguard_api.settings import get_settings

ROOT = Path(__file__).resolve().parents[1]
RIVERSIDE = "04e6d089-3750-505d-a6de-3813a6458fcb"
EMAIL, PASSWORD = "volunteer.priya@example.org", "PawGuard-demo-2026"  # published fictional demo account
OWNER_EMAIL, LOTUS = "owner.neha@example.org", "4bc42f9a-53c3-559d-8c05-7c4472f7da4a"  # fictional pet owner / clinic


def env(name: str, default: str | None = None) -> str:
    """Value from the environment, else from the repository's .env (web-side settings are not in API settings)."""
    if os.environ.get(name):
        return os.environ[name]
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{name}="):
            return line.split("=", 1)[1].strip().strip('"')
    if default is None:
        sys.exit(f"{name} is not set")
    return default


def coco_dog() -> Path:
    m = json.loads((ROOT / "data/manifests/coco-val2017-dog-sample-v1.json").read_text(encoding="utf-8"))
    e = next(i for i in m["images"] if i["split"] == "verification" and len(i["dog_boxes_xywh"]) == 1)
    return ROOT / "data/raw/coco/val2017_sample" / e["file_name"]


def wait(fn, what: str, timeout: float = 120):
    end = time.time() + timeout
    while time.time() < end:
        v = fn()
        if v:
            return v
        time.sleep(1.5)
    sys.exit(f"Timed out waiting for {what}. Are the worker and dispatcher running?")


def sign_in(s, email: str) -> str:
    r = httpx.post(f"{s.supabase_url}/auth/v1/token?grant_type=password",
                   headers={"apikey": env("PAWGUARD_SUPABASE_PUBLISHABLE_KEY")},
                   json={"email": email, "password": PASSWORD}, timeout=20)
    r.raise_for_status()
    return r.json()["access_token"]


def upload(api: httpx.Client, s, path: Path, purpose: str, mime: str) -> str:
    data = path.read_bytes()
    intent = api.post("/api/v1/media/upload-intents", json={"purpose": purpose, "content_type": mime,
                                                             "byte_size": len(data)})
    intent.raise_for_status()
    i = intent.json()
    url = i["upload_url"]
    if url.startswith("/"):  # same-origin storage links (public-link mode): go to local Supabase directly
        url = s.supabase_url.rstrip("/") + url
    httpx.put(url, content=data, headers=i["headers"], timeout=30).raise_for_status()
    api.post(f"/api/v1/media/{i['media_id']}/complete").raise_for_status()
    return i["media_id"]


def prepare_pets(s) -> None:
    api = httpx.Client(base_url=env("PAWGUARD_API_INTERNAL_URL", "http://127.0.0.1:8000"), timeout=30,
                       headers={"authorization": f"Bearer {sign_in(s, OWNER_EMAIL)}", "x-pawguard-org": LOTUS})
    pets = api.get("/api/v1/my/pets").json()
    bruno = next((p for p in pets if p["name"] == "Bruno"), None)
    if bruno is None:
        sys.exit("Demo pet Bruno not found; run `pawguard-admin demo-reset --yes` first.")
    if bruno["awaiting_verification"]:
        print("Pets: an owner upload is already awaiting verification.")
        return
    cert = upload(api, s, ROOT / "tests/fixtures/synthetic-certificate.jpg", "vaccination_evidence", "image/jpeg")
    r = api.post(f"/api/v1/my/pets/{bruno['id']}/vaccinations", json={
        "product_text": "Leptospirosis vaccine (from a previous clinic)",
        "administered_on": time.strftime("%Y-%m-%d", time.localtime(time.time() - 20 * 86400)),
        "given_by": "Previous clinic", "certificate_media_ids": [cert]})
    r.raise_for_status()
    print("Pets: owner upload for Bruno submitted; it is awaiting the clinic vet's verification.")


def main() -> None:
    s = get_settings()
    if s.env not in ("development", "test") or not s.demo_mode:
        sys.exit("Refusing: only for development/test with PAWGUARD_DEMO_MODE=true.")
    prepare_pets(s)
    photo = coco_dog()
    if not photo.is_file():
        sys.exit("COCO sample not found (run `cd ml && uv run pawid coco-sample`).")
    tok = httpx.post(f"{s.supabase_url}/auth/v1/token?grant_type=password",
                     headers={"apikey": env("PAWGUARD_SUPABASE_PUBLISHABLE_KEY")},
                     json={"email": EMAIL, "password": PASSWORD}, timeout=20).json()["access_token"]
    api = httpx.Client(base_url=env("PAWGUARD_API_INTERNAL_URL", "http://127.0.0.1:8000"), timeout=30,
                       headers={"authorization": f"Bearer {tok}", "x-pawguard-org": RIVERSIDE})
    status = api.get("/api/v1/identity/status").json()
    if status["mode"] != "research_preview":
        sys.exit(f"Identity mode is {status['mode']} ({status.get('reason')}); enable the research preview first "
                 "(see docs/RELEASE_REPORT_PREVENTION.md).")
    animal = api.get("/api/v1/animals", params={"limit": 1}).json()["items"][0]
    data = photo.read_bytes()
    intent = api.post("/api/v1/media/upload-intents", json={"purpose": "animal_photo", "content_type": "image/jpeg",
                                                             "byte_size": len(data)}).json()
    upload_url = intent["upload_url"]
    if upload_url.startswith("/"):  # same-origin storage links (public-link mode): go to local Supabase directly
        upload_url = s.supabase_url.rstrip("/") + upload_url
    httpx.put(upload_url, content=data, headers=intent["headers"], timeout=30).raise_for_status()
    mid = intent["media_id"]
    api.post(f"/api/v1/media/{mid}/complete").raise_for_status()
    wait(lambda: api.get(f"/api/v1/media/{mid}").json()["state"] == "approved", "photo validation")
    analysis = wait(lambda: (lambda a: a if a["state"] != "pending" else None)(
        api.get(f"/api/v1/media/{mid}/analysis").json()), "detection")
    if not analysis["dogs"]:
        sys.exit(f"No dog detected ({analysis['state']}); cannot choose a subject.")
    d = analysis["dogs"][0]
    reason = "Preparation photo" if any(q["warnings"] for q in analysis.get("quality", [])) else None
    r = api.post("/api/v1/observations", json={
        "animal_id": animal["id"], "observed_on": time.strftime("%Y-%m-%d"), "time_precision": "day",
        "media_ids": [mid], "subjects": [{"media_id": mid, "source": "detector",
                                          "box": {k: d[k] for k in ("x", "y", "w", "h")}, "dog_count": 1}],
        "quality_override_reason": reason, "notes": "Sighting from the sample photo set (licence-filtered COCO photo)."})
    r.raise_for_status()
    wait(lambda: api.get("/api/v1/identity/status").json().get("index_coverage") == 1, "gallery indexing")
    print(f"Ready. Enrolled a photo for {animal['reference_code']}. On the capture page, upload:\n  {photo}")


if __name__ == "__main__":
    main()
