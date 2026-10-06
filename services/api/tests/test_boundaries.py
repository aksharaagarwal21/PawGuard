"""Phase 9 boundary audit: restricted matching cannot be reached by real organisations, by any route."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError


@pytest.mark.parametrize("column, value", [("is_demo", "true"), ("activation_state", "'active'")])
def test_api_role_cannot_change_demo_flag_or_activation(world, api_engine_for_tests, column, value):
    org = world.org()
    admin = world.member(org, "org_admin")
    with api_engine_for_tests.connect() as c, pytest.raises(DBAPIError, match="permission denied"):
        with c.begin():
            c.execute(text("select app.set_request_context(:u, :o)"), {"u": admin, "o": org})
            c.execute(text(f"update app.organisations set {column} = {value} where id = :o"), {"o": org})


def test_api_role_cannot_touch_the_model_registry_or_embeddings(world, api_engine_for_tests):
    org = world.org(demo=True)
    user = world.member(org, "programme_coordinator")
    statements = [
        "update app.model_versions set state = 'active', research_preview = false",
        "update app.model_versions set release_gate = '{\"passed\": true}'::jsonb",
        "select count(*) from app.animal_embeddings",
    ]
    for sql in statements:
        with api_engine_for_tests.connect() as c, pytest.raises(DBAPIError, match="permission denied"):
            with c.begin():
                c.execute(text("select app.set_request_context(:u, :o)"), {"u": user, "o": org})
                c.execute(text(sql))


def test_no_http_route_can_change_models_or_demo_status(client):
    """The OpenAPI surface has no write operation on models, releases, previews or organisations."""
    spec = client.get("/openapi.json").json()
    writes = [(p, m) for p, ops in spec["paths"].items() for m in ops if m in ("post", "put", "patch", "delete")]
    segments = {"models", "model-versions", "organisations", "research-preview", "release-gate", "identity-models"}
    risky = [w for w in writes if segments & set(w[0].strip("/").split("/"))]
    assert risky == [], risky
