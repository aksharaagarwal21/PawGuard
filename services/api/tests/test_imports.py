"""Partner CSV imports: immutable raw file, dry-run report, approved apply, idempotency, rollback."""

import base64
from datetime import date, timedelta

from test_prevention import org_setup  # noqa: F401 - reuse fixture


def _b64(s: str) -> str:
    return base64.b64encode(s.encode("utf-8")).decode()


ANIMALS = """source_row_id,nickname,species,sex,sterilisation_status,age_band,ownership_category,area_code,last_seen_date,latitude,longitude,coat_description
P-1, Kaalu ,Dog,F,yes,adult,street,W1,2026-09-01,13.05,80.25,Black with tan
P-2,மணி,canine,M,intact,pup,stray,ZZ,2026-09-02,,,Brown
P-3,,dog,?,maybe,old,community,W1,2099-01-01,,,White
P-3,Dup,dog,F,no,adult,owned,W1,2026-09-03,,,Grey
P-4,Out,dog,F,no,adult,owned,W1,2026-09-04,123,80,Grey
"""


def test_dry_run_reports_and_apply_creates_only_good_rows(client, auth, org_setup):  # noqa: F811
    s = org_setup()
    hc = auth(s["tokens"]["coordinator"], s["org"])
    assert client.post("/api/v1/imports", headers=auth(s["tokens"]["volunteer"], s["org"]),
                       json={"import_type": "animals_csv", "source_label": "Partner shelter export",
                             "content_base64": _b64(ANIMALS)}).status_code == 403
    r = client.post("/api/v1/imports", headers=hc, json={"import_type": "animals_csv", "filename": "a.csv",
                                                        "source_label": "Partner shelter export",
                                                        "content_base64": _b64(ANIMALS)})
    assert r.status_code == 201, r.text
    job = r.json()
    rows = {x["row"]: x for x in job["report"]["rows"]}
    assert rows[2]["status"] == "valid" and rows[2]["clean"]["sex"] == "female"
    assert rows[2]["clean"]["sterilisation_status"] == "sterilised" and rows[2]["clean"]["nickname"] == "Kaalu"
    assert rows[3]["status"] == "warning" and rows[3]["clean"]["nickname"] == "மணி"  # local script preserved
    assert {i["code"] for i in rows[3]["issues"]} == {"unknown_area"}
    assert rows[4]["status"] == "rejected"  # future date
    assert {i["code"] for i in rows[4]["issues"]} >= {"date_in_future", "unmapped_value"}
    assert rows[4]["clean"]["sex"] == "unknown" and rows[4]["clean"]["sterilisation_status"] == "unknown"
    assert rows[5]["status"] == "rejected" and rows[5]["issues"][0]["code"] == "duplicate_in_file"
    assert rows[6]["status"] == "rejected"  # latitude out of range
    # Same file again is refused (raw file is immutable and identified by checksum)
    again = client.post("/api/v1/imports", headers=hc, json={"import_type": "animals_csv", "source_label": "again",
                                                            "content_base64": _b64(ANIMALS)})
    assert again.status_code == 409
    # Nothing exists yet
    assert client.get("/api/v1/animals?q=Kaalu", headers=hc).json()["total_matching"] == 0
    applied = client.post(f"/api/v1/imports/{job['id']}/apply", headers=hc,
                          json={"row_version": job["row_version"], "include_warning_rows": True}).json()
    assert applied["state"] == "applied" and len(applied["created_record_ids"]["animals"]) == 2
    kaalu = client.get("/api/v1/animals?q=Kaalu", headers=hc).json()["items"][0]
    assert kaalu["profile_state"] == "provisional"
    # A second file containing an already imported row skips it (idempotent by source row)
    second = client.post("/api/v1/imports", headers=hc, json={
        "import_type": "animals_csv", "source_label": "Partner shelter export (resend)",
        "content_base64": _b64("source_row_id,nickname,area_code\nP-1,Kaalu,W1\n")}).json()
    assert second["report"]["rows"][0]["status"] == "skip"
    # Roll back archives (never deletes) the untouched imported records
    rb = client.post(f"/api/v1/imports/{job['id']}/rollback", headers=hc, json={"reason": "Wrong partner file"})
    assert rb.status_code == 200 and rb.json()["state"] == "rolled_back"
    assert client.get(f"/api/v1/animals/{kaalu['id']}", headers=hc).json()["profile_state"] == "archived"


def test_vaccination_import_creates_submitted_records_only(client, auth, org_setup):  # noqa: F811
    s = org_setup()
    hc = auth(s["tokens"]["coordinator"], s["org"])
    a = client.post("/api/v1/animals", headers=hc, json={"species": "dog", "nickname": "ImportTarget"}).json()
    d = (date.today() - timedelta(days=20)).strftime("%d/%m/%Y")
    csv_text = (f"source_row_id,animal_reference,administered_on,date_precision,product_name,lot_number\n"
                f"V-1,{a['reference_code']},{d},day,Test vaccine,L-001\n"
                f"V-2,PG-0000-0000,{d},day,Test vaccine,L-001\n"
                f"V-3,{a['reference_code']},{d},day,Unknown Brand,bad$lot\n")
    job = client.post("/api/v1/imports", headers=hc, json={"import_type": "vaccinations_csv", "source_label": "Clinic",
                                                          "date_format": "DD/MM/YYYY",
                                                          "content_base64": _b64(csv_text)}).json()
    st = [r["status"] for r in job["report"]["rows"]]
    assert st == ["valid", "rejected", "rejected"]
    assert job["report"]["rows"][0]["clean"]["lot_id"]  # matched to the known lot
    applied = client.post(f"/api/v1/imports/{job['id']}/apply", headers=hc,
                          json={"row_version": job["row_version"]}).json()
    eid = applied["created_record_ids"]["vaccination_events"][0]
    ev = client.get(f"/api/v1/vaccination-events/{eid}", headers=hc).json()
    assert ev["state"] == "submitted" and ev["source_type"] == "partner_record"
    assert client.post(f"/api/v1/imports/{job['id']}/rollback", headers=hc,
                       json={"reason": "nope"}).status_code == 409  # vaccination imports are corrected by review


def test_rollback_refused_once_an_imported_record_was_used(client, auth, org_setup):  # noqa: F811
    s = org_setup()
    hc = auth(s["tokens"]["coordinator"], s["org"])
    job = client.post("/api/v1/imports", headers=hc, json={
        "import_type": "animals_csv", "source_label": "Partner list",
        "content_base64": _b64("source_row_id,nickname\nR-1,Used later\nR-2,Untouched\n")}).json()
    applied = client.post(f"/api/v1/imports/{job['id']}/apply", headers=hc,
                          json={"row_version": job["row_version"]}).json()
    assert len(applied["created_record_ids"]["animals"]) == 2
    used = client.get("/api/v1/animals?q=Used later", headers=hc).json()["items"][0]
    r = client.patch(f"/api/v1/animals/{used['id']}", headers=hc,
                     json={"row_version": used["row_version"], "identifying_marks": "Notched left ear"})
    assert r.status_code == 200, r.text
    rb = client.post(f"/api/v1/imports/{applied['id']}/rollback", headers=hc, json={"reason": "Wrong file"})
    assert rb.status_code == 409 and rb.json()["error"]["code"] == "records_in_use"
    # Nothing was archived by the refused rollback
    assert client.get("/api/v1/animals?q=Untouched", headers=hc).json()["items"][0]["profile_state"] == "provisional"
    # A different person without animal.merge cannot roll back at all
    hv = auth(s["tokens"]["volunteer"], s["org"])
    assert client.post(f"/api/v1/imports/{applied['id']}/rollback", headers=hv,
                       json={"reason": "x" * 10}).status_code == 403
