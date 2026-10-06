def test_live(client):
    assert client.get("/health/live").json() == {"status": "ok"}


def test_ready_reports_components_without_config_values(client):
    r = client.get("/health/ready")
    body = r.json()
    assert set(body["components"]) >= {"database", "auth_keys", "storage", "job_broker"}
    assert body["components"]["database"]["ok"] is True
    assert "postgresql" not in r.text and "sb_secret" not in r.text


def test_unknown_route_uses_error_shape(client):
    r = client.get("/api/v1/does-not-exist")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"


def test_demo_endpoints_hidden_when_demo_mode_off(client):
    assert client.get("/api/v1/demo/accounts").status_code == 404
