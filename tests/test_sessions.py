"""Real session storage, login/logout, CSRF and shared HTML/JSON guards."""

from datetime import UTC, datetime, timedelta
from typing import Annotated

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from fieldops.auth import COOKIE, current_user, digest, require_csrf
from fieldops.main import create_app
from fieldops.models import Intervention, Notification, NotificationOutbox, PersonaSession, User
from fieldops.permissions import inbox_scope, intervention_scope, require_role
from fieldops.seed import persona_id

pytestmark = pytest.mark.integration


@pytest.fixture
def client(pg_settings):
    settings = pg_settings.model_copy(
        update={
            "demo_mode": True,
            "session_secret_file": None,
            "session_secret": None,
            "operator_secret": None,
        }
    )
    from pydantic import SecretStr

    settings.session_secret = SecretStr("synthetic-session-signing-key-only-32-chars")
    settings.operator_secret = SecretStr("synthetic-operator-secret-only-32-chars")
    app = create_app(settings)

    # Test-only adapters exercise the exact guards future JSON/HTML services must call.
    @app.post("/qa/dispatcher/json")
    @app.post("/qa/dispatcher/html")
    def dispatcher(user: Annotated[User, Depends(require_csrf)]):
        require_role(user, "dispatcher")
        return {"ok": True}

    @app.get("/qa/operator")
    def operator(user: Annotated[User, Depends(current_user)]):
        require_role(user, "operator")
        return {"ok": True}

    @app.get("/qa/jobs/json")
    @app.get("/qa/jobs/html")
    def jobs(user: Annotated[User, Depends(current_user)]):
        with Session(app.state.engine) as db:
            return [
                str(value)
                for value in db.scalars(intervention_scope(select(Intervention.id), user))
            ]

    @app.get("/qa/inbox")
    def inbox(user: Annotated[User, Depends(current_user)]):
        with Session(app.state.engine) as db:
            return [str(value) for value in db.scalars(inbox_scope(select(Notification.id), user))]

    with TestClient(app) as value:
        yield value


def login(client, persona="demo-manager", **extra):
    csrf = client.get("/auth/csrf").json()["csrf_token"]
    response = client.post(
        "/auth/login",
        headers={"X-CSRF-Token": csrf},
        json={"persona_id": str(persona_id(persona)), **extra},
    )
    return response


def test_session_cookie_logout_revokes_replay(client):
    response = login(client)
    assert response.status_code == 200
    header = response.headers["set-cookie"].lower()
    assert "httponly" in header and "samesite=lax" in header and "max-age=28800" in header
    cookie = client.cookies.get(COOKIE)
    csrf = response.json()["csrf_token"]
    assert client.get("/auth/session").json()["persona"]["role"] == "dispatcher"
    assert client.get("/session").status_code == 200
    assert client.post("/auth/logout").status_code == 403
    assert client.post("/auth/logout", headers={"X-CSRF-Token": csrf}).status_code == 204
    client.cookies.set(COOKIE, cookie)
    assert client.get("/auth/session").status_code == 401
    assert client.get("/session").status_code == 401


@pytest.mark.parametrize("route", ["/qa/dispatcher/json", "/qa/dispatcher/html"])
def test_direct_role_and_csrf_denial(client, route):
    assert client.post(route).status_code == 401
    csrf = login(client, "demo-technician-a").json()["csrf_token"]
    assert client.post(route, headers={"X-CSRF-Token": csrf}).status_code == 403
    csrf = login(client).json()["csrf_token"]
    assert client.post(route).status_code == 403
    assert client.post(route, headers={"X-CSRF-Token": "wrong"}).status_code == 403
    assert client.post(route, headers={"X-CSRF-Token": csrf}).status_code == 200


def test_login_requires_csrf_and_operator_secret(client):
    operator = str(persona_id("demo-operator"))
    assert client.post("/auth/login", json={"persona_id": operator}).status_code == 403
    assert login(client, "demo-operator").status_code == 403
    assert login(client, "demo-operator", operator_secret="wrong").status_code == 403
    assert all(item["role"] != "operator" for item in client.get("/auth/personas").json())
    response = login(
        client, "demo-operator", operator_secret="synthetic-operator-secret-only-32-chars"
    )
    assert response.status_code == 200
    assert client.get("/qa/operator").status_code == 200
    assert (
        client.post(
            "/qa/dispatcher/json", headers={"X-CSRF-Token": response.json()["csrf_token"]}
        ).status_code
        == 403
    )
    client.app.state.settings.operator_secret = None
    assert (
        login(
            client, "demo-operator", operator_secret="synthetic-operator-secret-only-32-chars"
        ).status_code
        == 403
    )


def test_expired_inactive_tampered_and_rotated_sessions(client):
    assert login(client).status_code == 200
    first = client.cookies.get(COOKIE)
    assert login(client, "demo-technician-a").status_code == 200
    second = client.cookies.get(COOKIE)
    client.cookies.clear()
    client.cookies.set(COOKIE, first)
    assert client.get("/auth/session").status_code == 401
    client.cookies.clear()
    client.cookies.set(COOKIE, second + "tampered")
    assert client.get("/auth/session").status_code == 401
    client.cookies.clear()
    client.cookies.set(COOKIE, second)
    assert client.get("/auth/session").status_code == 200
    token_digest = digest(second.partition(".")[0])
    with Session(client.app.state.engine) as db, db.begin():
        record = db.get(PersonaSession, token_digest)
        # Preserve the expiry constraint while expiring this exact test session.
        record.created_at = datetime.now(UTC) - timedelta(hours=2)
        record.expires_at = datetime.now(UTC) - timedelta(hours=1)
    assert client.get("/auth/session").status_code == 401
    # Even an incorrectly extended expiry cannot bypass the absolute eight-hour age cap.
    with Session(client.app.state.engine) as db, db.begin():
        record = db.get(PersonaSession, token_digest)
        record.created_at = datetime.now(UTC) - timedelta(hours=1)
        record.expires_at = datetime.now(UTC) + timedelta(hours=1)
    assert client.get("/auth/session").status_code == 200
    with Session(client.app.state.engine) as db, db.begin():
        record = db.get(PersonaSession, token_digest)
        record.created_at = datetime.now(UTC) - timedelta(hours=10)
        record.expires_at = datetime.now(UTC) + timedelta(hours=1)
    assert client.get("/auth/session").status_code == 401
    assert login(client, "demo-technician-b").status_code == 200
    with Session(client.app.state.engine) as db, db.begin():
        db.get(User, persona_id("demo-technician-b")).active = False
    try:
        assert client.get("/auth/session").status_code == 401
        assert login(client, "demo-technician-b").status_code == 403
    finally:
        with Session(client.app.state.engine) as db, db.begin():
            db.get(User, persona_id("demo-technician-b")).active = True


def test_html_login_logout_and_sanitized_validation(client):
    csrf = client.get("/auth/csrf").json()["csrf_token"]
    values = {"persona_id": str(persona_id("demo-manager")), "csrf_token": csrf}
    assert client.post("/session/login", data={**values, "csrf_token": "wrong"}).status_code == 403
    response = client.post("/session/login", data=values, follow_redirects=False)
    assert response.status_code == 303
    csrf = client.get("/auth/session").json()["csrf_token"]
    assert client.post("/session/logout", data={}).status_code == 422
    assert client.post("/session/logout", data={"csrf_token": "wrong"}).status_code == 403
    assert (
        client.post(
            "/session/logout", data={"csrf_token": csrf}, follow_redirects=False
        ).status_code
        == 303
    )
    assert client.get("/session").status_code == 401
    sentinel = "SYNTHETIC_INVALID_SECRET_SENTINEL"
    response = client.post("/auth/login", json={"persona_id": sentinel})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert sentinel not in response.text


def test_nonlocal_secure_cookie_and_demo_disabled(client):
    client.app.state.settings.environment = "production"
    response = client.get("/auth/csrf")
    assert "secure" in response.headers["set-cookie"].lower()
    client.app.state.settings.demo_mode = False
    assert client.get("/auth/csrf").status_code == 404
    assert client.get("/auth/personas").status_code == 404


def test_invalid_signing_configuration_fails_closed(client):
    assert login(client).status_code == 200
    client.app.state.settings.session_secret = None
    assert client.get("/auth/session").status_code == 503
    response = client.get("/auth/csrf")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "session_configuration_unavailable"


def test_session_tokens_are_not_cached(client):
    response = login(client)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert client.get("/auth/session").headers["cache-control"] == "no-store"


def test_http_cross_user_scope_and_historical_inbox(client):
    with Session(client.app.state.engine) as db, db.begin():
        a, b = persona_id("demo-technician-a"), persona_id("demo-technician-b")
        job = Intervention(
            title="Audit Synthetic",
            site="Synthetic",
            technician_id=a,
            assignment_version=1,
            status="assigned",
        )
        db.add(job)
        db.flush()
        event = NotificationOutbox(intervention_id=job.id, recipient_id=a, assignment_version=1)
        db.add(event)
        db.flush()
        item = Notification(
            outbox_id=event.id, intervention_id=job.id, recipient_id=a, assignment_version=1
        )
        db.add(item)
        db.flush()
        job_id, item_id = job.id, item.id
    assert login(client, "demo-technician-b").status_code == 200
    for route in ["/qa/jobs/json", "/qa/jobs/html"]:
        response = client.get(route)
        assert response.status_code == 200 and str(job_id) not in response.json()
    assert str(item_id) not in client.get("/qa/inbox").json()
    assert login(client, "demo-technician-a").status_code == 200
    assert str(job_id) in client.get("/qa/jobs/json").json()
    assert str(item_id) in client.get("/qa/inbox").json()
    with Session(client.app.state.engine) as db, db.begin():
        job = db.get(Intervention, job_id)
        job.technician_id = b
        job.assignment_version = 2
    assert str(job_id) not in client.get("/qa/jobs/html").json()
    assert str(item_id) in client.get("/qa/inbox").json()
    assert login(client).status_code == 200
    assert client.get("/qa/inbox").status_code == 403


def test_html_operator_gate_and_json_escalation_fields(client):
    csrf = client.get("/auth/csrf").json()["csrf_token"]
    values = {"persona_id": str(persona_id("demo-operator")), "csrf_token": csrf}
    assert client.post("/session/login", data=values).status_code == 403
    assert (
        client.post("/session/login", data={**values, "operator_secret": "wrong"}).status_code
        == 403
    )
    response = client.post(
        "/auth/login",
        json={"persona_id": str(persona_id("demo-manager")), "role": "operator"},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 422
    assert client.get("/qa/operator").status_code == 401
    response = client.post(
        "/session/login",
        data={**values, "operator_secret": "synthetic-operator-secret-only-32-chars"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert client.get("/qa/operator").status_code == 200


@pytest.mark.parametrize(
    "body",
    [
        "persona_id=a&persona_id=b&csrf_token=x",
        "csrf_token=" + ("x" * 4097),
    ],
)
def test_malformed_html_login_is_bounded(client, body):
    response = client.post(
        "/session/login",
        content=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_signed_but_unregistered_token_does_not_authenticate(client):
    import hashlib
    import hmac

    token = "operator:" + str(persona_id("demo-operator"))
    signature = hmac.new(
        b"synthetic-session-signing-key-only-32-chars", token.encode(), hashlib.sha256
    ).hexdigest()
    client.cookies.clear()
    client.cookies.set(COOKIE, token + "." + signature)
    assert client.get("/auth/session").status_code == 401
    assert client.get("/qa/operator").status_code == 401


def test_local_https_also_sets_secure_cookie(client):
    response = client.get("https://testserver/auth/csrf")
    assert response.status_code == 200
    from http.cookies import SimpleCookie

    cookies = SimpleCookie()
    cookies.load(response.headers["set-cookie"])
    assert cookies["fieldops_login_csrf"]["secure"]
