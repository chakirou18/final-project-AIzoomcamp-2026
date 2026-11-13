"""Public-demo boundary: access code, private-path blocking, limits, headers, fail-closed config."""

import base64

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from fieldops.main import create_app
from fieldops.public_demo import SlidingWindow, blocked
from fieldops.settings import Settings

CODE = "synthetic-public-demo-access-code-test-only"
SESSION = "synthetic-public-demo-session-key-test-only-000"


def settings(**overrides):
    values = dict(
        environment="public-demo",
        demo_mode=True,
        public_demo=True,
        public_demo_access_code=SecretStr(CODE),
        db_password=SecretStr("synthetic-test-only"),
        session_secret=SecretStr(SESSION),
        telemetry_enabled=False,
    )
    values.update(overrides)
    return Settings(**values)


def basic(code=CODE, user="demo"):
    return {"Authorization": "Basic " + base64.b64encode(f"{user}:{code}".encode()).decode()}


@pytest.fixture
def client():
    with TestClient(create_app(settings())) as test_client:
        yield test_client


def test_health_probe_needs_no_access_code_and_carries_security_headers(client):
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]


@pytest.mark.parametrize("path", ["/static/app.css", "/app/login", "/api/v1/interventions", "/"])
def test_every_application_path_requires_the_access_code(client, path):
    response = client.get(path, follow_redirects=False)
    assert response.status_code == 401
    assert response.headers["www-authenticate"].startswith("Basic ")
    assert response.json()["error"]["code"] == "unauthenticated"


@pytest.mark.parametrize(
    "headers",
    [
        basic("wrong-code-wrong-code-wrong"),
        basic(user="admin"),
        {"Authorization": "Bearer " + CODE},
        {"Authorization": "Basic not-base64!"},
        {"Authorization": "Basic " + "A" * 600},
    ],
)
def test_wrong_or_malformed_credentials_are_rejected(client, headers):
    assert client.get("/static/app.css", headers=headers).status_code == 401


def test_valid_access_code_reaches_public_application_paths(client):
    response = client.get("/static/app.css", headers=basic())
    assert response.status_code == 200


@pytest.mark.parametrize(
    "path",
    [
        "/metrics",
        "/internal/worker/status",
        "/internal/oncall/evidence",
        "/demo/worker/pause",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/contracts/openapi.json",
        "/api/v1/incidents",
        "/api/v1/incidents/00000000-0000-0000-0000-000000000000/authorize",
        "/api/v1/dashboard",
        "/app/operator",
        "/app/dashboard",
        "/app/worker/pause",
    ],
)
def test_private_surfaces_are_hidden_even_with_the_access_code(client, path):
    assert client.get(path, headers=basic()).status_code == 404
    assert client.post(path, headers=basic(), json={}).status_code == 404


def test_repeated_failures_lock_out_the_client_even_with_a_later_valid_code(client):
    for _ in range(10):
        assert client.get("/static/app.css", headers=basic("x" * 24)).status_code == 401
    locked = client.get("/static/app.css", headers=basic())
    assert locked.status_code == 429 and locked.headers["retry-after"] == "600"


def test_lockout_is_per_cloudflare_client_address(client):
    attacker = {"CF-Connecting-IP": "198.51.100.7"}
    for _ in range(10):
        client.get("/static/app.css", headers={**basic("y" * 24), **attacker})
    assert client.get("/static/app.css", headers={**basic(), **attacker}).status_code == 429
    other = {"CF-Connecting-IP": "203.0.113.9"}
    assert client.get("/static/app.css", headers={**basic(), **other}).status_code == 200


def test_request_rate_limit_answers_429():
    with TestClient(create_app(settings(public_demo_requests_per_minute=10))) as client:
        assert [client.get("/health/live").status_code for _ in range(15)] == [200] * 15
        codes = [client.get("/static/app.css", headers=basic()).status_code for _ in range(12)]
        assert codes[:10] == [200] * 10 and codes[10:] == [429, 429]


def test_public_demo_is_a_no_op_when_disabled():
    plain = settings(public_demo=False, environment="local")
    with TestClient(create_app(plain)) as client:
        response = client.get("/static/app.css")
        assert response.status_code == 200
        assert "x-frame-options" not in response.headers


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"environment": "local"}, "non-local environment"),
        ({"demo_mode": False}, "synthetic demo personas"),
        ({"public_demo_access_code": None}, "access code"),
        ({"public_demo_access_code": SecretStr("short")}, "access code"),
        ({"operator_secret": SecretStr("o" * 40)}, "operator, recovery or agent"),
        ({"recovery_secret": SecretStr("r" * 40)}, "operator, recovery or agent"),
    ],
)
def test_public_demo_configuration_fails_closed(overrides, message):
    with pytest.raises(ValueError, match=message):
        settings(**overrides)


def test_access_code_file_is_supported(tmp_path):
    path = tmp_path / "access_code"
    path.write_text(CODE + "\n", encoding="utf-8")
    loaded = settings(public_demo_access_code=None, public_demo_access_code_file=path)
    assert loaded.public_demo_access_code.get_secret_value() == CODE


def test_sliding_window_and_path_rules():
    window = SlidingWindow(2, 10, max_keys=2)
    assert not window.hit("a", 0) and not window.hit("a", 1) and window.hit("a", 2)
    assert not window.hit("a", 11)  # old events expire
    window.hit("b", 12)
    window.hit("c", 13)  # evicts the stalest key instead of growing
    assert len(window.events) == 2
    assert blocked("/internal/x") and blocked("/metrics") and blocked("/app/operator/login")
    assert not blocked("/app/interventions") and not blocked("/api/v1/notifications")
