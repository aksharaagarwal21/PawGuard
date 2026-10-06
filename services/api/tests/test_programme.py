"""Programme views: export scope, honest registry measures, map precision."""

from datetime import date

from test_prevention import _animal, _vacc, org_setup  # noqa: F401 - reuse fixture and helpers


def test_export_is_scoped_audited_and_declares_data_mode(client, auth, org_setup):  # noqa: F811
    a, b = org_setup(), org_setup()
    mine = _animal(client, auth, a, nickname="ExportMine")
    _animal(client, auth, b, nickname="ExportTheirs")
    # Field volunteers cannot export
    assert client.get("/api/v1/exports/animals.csv", headers=auth(a["tokens"]["volunteer"], a["org"])).status_code == 403
    r = client.get("/api/v1/exports/animals.csv", headers=auth(a["tokens"]["coordinator"], a["org"]))
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    lines = r.text.splitlines()
    assert lines[0].startswith("# data_mode: live")
    assert "ExportMine" in r.text and "ExportTheirs" not in r.text
    assert mine["reference_code"] in r.text
    assert "contact" not in lines[1] and "lat" not in lines[1] and "notes" not in lines[1]
    audit = client.get("/api/v1/audit", headers=auth(a["tokens"]["admin"], a["org"])).json()
    assert any(e["action"] == "export.animals_csv" for e in audit)


def test_summary_is_labelled_registry_not_coverage(client, auth, org_setup):  # noqa: F811
    s = org_setup()
    animal = _animal(client, auth, s)
    ev = _vacc(client, auth, s, animal["id"]).json()
    client.post(f"/api/v1/vaccination-events/{ev['id']}/reviews", headers=auth(s["tokens"]["vet"], s["org"]),
                json={"outcome": "verified", "row_version": ev["row_version"]})
    _animal(client, auth, s, nickname="Unvaccinated?")
    body = client.get("/api/v1/programme/summary", headers=auth(s["tokens"]["volunteer"], s["org"])).json()
    assert "not population vaccination coverage" in body["note"]
    assert body["totals"]["registered_animals"] == 2
    assert body["totals"]["animals_with_verified_record"] == 1
    assert "coverage" not in {k for a in body["areas"] for k in a}  # no coverage field exists


def test_map_points_are_approximate_without_capability(client, auth, org_setup):  # noqa: F811
    s = org_setup()
    _animal(client, auth, s, first_observation={"observed_on": str(date.today()), "time_precision": "day",
                                                "location": {"lat": 13.08271, "lon": 80.27068, "method": "gps"}})
    vol = client.get("/api/v1/map/layers", headers=auth(s["tokens"]["volunteer"], s["org"])).json()
    vet = client.get("/api/v1/map/layers", headers=auth(s["tokens"]["vet"], s["org"])).json()
    assert vol["precision"] == "approximate" and vet["precision"] == "exact"
    vlon, vlat = vol["sightings"]["features"][0]["geometry"]["coordinates"]
    elon, elat = vet["sightings"]["features"][0]["geometry"]["coordinates"]
    assert (elat, elon) == (13.08271, 80.27068)  # GeoJSON order is [lon, lat]
    assert (vlat, vlon) != (elat, elon) and abs(vlat - elat) <= 0.005 and abs(vlon - elon) <= 0.005
