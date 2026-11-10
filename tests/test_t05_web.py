"""Real PostgreSQL HTML adapters: permissions, validation and persisted workflows."""

import re
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from fieldops.bootstrap import migrate, seed
from fieldops.database import create_database_engine
from fieldops.main import create_app
from fieldops.models import Notification, NotificationOutbox, PersonaSession
from fieldops.policy import DomainError
from fieldops.schemas import Assignment, InterventionCreate, InterventionFilters
from fieldops.seed import persona_id
from fieldops.services.interventions import InterventionService
from fieldops.web import payload
from fieldops.worker import OutboxWorker

MANAGER = persona_id("demo-manager")
A = persona_id("demo-technician-a")
B = persona_id("demo-technician-b")


def csrf(response):
    return re.search(r'name="csrf_token" value="([^"]+)"', response.text)[1]


def login(client, identity="demo-manager"):
    page = client.get("/app/login")
    assert page.status_code == 200
    response = client.post(
        "/app/login",
        data={"csrf_token": csrf(page), "persona_id": str(persona_id(identity))},
        follow_redirects=False,
    )
    assert response.status_code == 303
    return csrf(client.get("/app/interventions"))


@pytest.fixture
def web(pg_settings):
    # Isolate the queue from previous regression fixtures; never drain application events.
    name = "fieldops_t05_" + uuid4().hex + "_test"
    base = create_database_engine(pg_settings)
    try:
        with base.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.exec_driver_sql(f'CREATE DATABASE "{name}"')
    finally:
        base.dispose()
    settings = pg_settings.model_copy(
        update={
            "db_name": name,
            "demo_mode": True,
            "session_secret_file": None,
            "session_secret": SecretStr("synthetic-t05-test-signing-key-only"),
        }
    )
    migrate(settings)
    seed(settings)
    with TestClient(create_app(settings)) as client:
        yield client, InterventionService(client.app.state.engine)


@pytest.mark.parametrize("value", ["0", "-1", "1.0", "abc", "1" * 19])
def test_html_version_rejects_invalid_strings(value):
    with pytest.raises((DomainError, ValidationError)) as error:
        payload(Assignment, {"expected_version": value, "technician_id": str(A)})
    if isinstance(error.value, DomainError):
        assert error.value.status_code == 422
    else:
        assert error.value.errors()[0]["loc"] == ("expected_version",)


@pytest.mark.integration
def test_manager_technician_persistent_html_journey(web):
    client, service = web
    token = login(client)
    title = "HTML journey " + uuid4().hex
    response = client.post(
        "/app/interventions/new",
        data={
            "csrf_token": token,
            "title": title,
            "site": "Synthetic site",
            "priority": "high",
            "description": "<script>alert('not executable')</script>",
            "technician_id": "",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    url = response.headers["location"].split("?")[0]
    identifier = UUID(url.rsplit("/", 1)[1])
    page = client.get(url)
    assert "&lt;script&gt;" in page.text
    assert "<script>alert" not in page.text
    response = client.post(
        url + "/edit",
        data={
            "csrf_token": token,
            "title": title + " edited",
            "description": "Edited",
            "site": "Updated site",
            "priority": "urgent",
            "expected_version": "1",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    response = client.post(
        url + "/assignment",
        data={
            "csrf_token": token,
            "technician_id": str(A),
            "expected_version": "2",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    with Session(service.engine) as db:
        event = db.scalar(
            select(NotificationOutbox).where(NotificationOutbox.intervention_id == identifier)
        )
        event_id = event.id
        assert event.status == "pending"
    worker = OutboxWorker(service.engine)
    claims = worker.claim()
    for claim in claims:
        worker.deliver(claim)
    token = login(client, "demo-technician-a")
    inbox = client.get("/app/inbox?page_size=100")
    assert str(identifier) in inbox.text
    with Session(service.engine) as db:
        item = db.scalar(select(Notification).where(Notification.outbox_id == event_id))
        notification_id = item.id
    read_url = f"/app/inbox/{notification_id}/read"
    for _ in range(2):
        assert (
            client.post(read_url, data={"csrf_token": token}, follow_redirects=False).status_code
            == 303
        )
    assert (
        client.post(
            url + "/transition",
            data={
                "csrf_token": token,
                "expected_version": "3",
                "target_status": "in_progress",
            },
            follow_redirects=False,
        ).status_code
        == 303
    )
    response = client.post(
        url + "/transition",
        data={
            "csrf_token": token,
            "expected_version": "4",
            "target_status": "completed",
            "resolution": "Repaired and verified",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    login(client)
    assert "Repaired and verified" in client.get(url).text
    job = service.detail(MANAGER, identifier)
    assert job.status == "completed" and job.started_at and job.closed_at


@pytest.mark.integration
@pytest.mark.parametrize(
    "case", ["validation", "csrf", "stale", "role", "cross", "expired", "invalid"]
)
def test_html_negative_security_and_conflicts(web, case):
    client, service = web
    job = service.create(
        MANAGER, InterventionCreate(title="Negative", site="Demo", technician_id=A)
    )
    url = f"/app/interventions/{job.id}"
    token = login(client)
    if case == "validation":
        response = client.post(
            "/app/interventions/new",
            data={
                "csrf_token": token,
                "title": "",
                "site": "Kept site",
                "priority": "invalid",
            },
        )
        assert response.status_code == 422
        assert 'role="alert"' in response.text and 'value="Kept site"' in response.text
        assert 'aria-invalid="true"' in response.text
    elif case == "csrf":
        assert (
            client.post(
                url + "/assignment",
                data={
                    "technician_id": str(B),
                    "expected_version": "1",
                },
            ).status_code
            == 403
        )
    elif case == "stale":
        service.assign(MANAGER, job.id, Assignment(technician_id=B, expected_version=1))
        response = client.post(
            url + "/edit",
            data={
                "csrf_token": token,
                "expected_version": "1",
                "title": "Unsaved title",
            },
        )
        assert response.status_code == 409
        assert "Reload the latest version" in response.text
        assert 'value="Unsaved title"' in response.text
    elif case in {"role", "cross"}:
        token = login(client, "demo-technician-b")
        path = "/app/interventions/new" if case == "role" else url
        assert client.get(path).status_code == 403
        assert (
            client.post(
                url + "/transition",
                data={
                    "csrf_token": token,
                    "expected_version": "1",
                    "target_status": "in_progress",
                },
            ).status_code
            == 403
        )
    elif case == "expired":
        with Session(service.engine) as db, db.begin():
            records = db.scalars(
                select(PersonaSession).where(
                    PersonaSession.user_id == MANAGER, PersonaSession.revoked_at.is_(None)
                )
            )
            for record in records:
                record.created_at = func.now() - timedelta(hours=2)
                record.expires_at = func.now() - timedelta(seconds=1)
        assert client.get(url).status_code == 401
    else:
        client.cookies.clear()
        client.cookies.set("fieldops_session", "invalid")
        assert client.get(url).status_code == 401
    assert service.detail(MANAGER, job.id).status == "assigned"


@pytest.mark.integration
def test_historical_notification_has_no_job_link_or_detail_access(web):
    client, service = web
    job = service.create(
        MANAGER, InterventionCreate(title="Private reassigned", site="Demo", technician_id=A)
    )
    worker = OutboxWorker(service.engine)
    for claim in worker.claim():
        worker.deliver(claim)
    service.assign(MANAGER, job.id, Assignment(expected_version=1, technician_id=B))
    login(client, "demo-technician-a")
    page = client.get("/app/inbox?page_size=100")
    assert "Historical assignment" in page.text
    assert f'href="/app/interventions/{job.id}"' not in page.text
    denied = client.get(f"/app/interventions/{job.id}")
    assert denied.status_code == 403 and "Private reassigned" not in denied.text


@pytest.mark.integration
def test_html_filters_pagination_logout_and_local_assets(web):
    client, service = web
    token = login(client)
    for _ in range(2):
        service.create(MANAGER, InterventionCreate(title="Filter", site="Demo", priority="urgent"))
    page = client.get("/app/interventions?priority=urgent&page_size=1")
    assert page.status_code == 200 and "Next" in page.text
    assert "priority=urgent&amp;page_size=1&amp;page=2" in page.text
    assert client.get("/app/interventions?priority=nonsense").status_code == 422
    assert client.get("/app/interventions?page=1&page=2").status_code == 422
    for path in ["/static/vendor/bootstrap-5.3.8.min.css", "/static/vendor/htmx-2.0.8.min.js"]:
        assert client.get(path).status_code == 200
    assert page.headers["cache-control"] == "no-store"
    assert "frame-ancestors 'none'" in page.headers["content-security-policy"]
    assert (
        client.post("/app/logout", data={"csrf_token": token}, follow_redirects=False).status_code
        == 303
    )
    assert client.get("/app/interventions").status_code == 401


@pytest.mark.integration
@pytest.mark.parametrize("case", ["duplicate", "oversized", "extra", "unknown", "wrong_inbox_role"])
def test_html_parser_and_direct_access_boundaries(web, case):
    client, service = web
    token = login(client)
    if case == "duplicate":
        response = client.post(
            "/app/interventions/new",
            content="title=A&title=B",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert response.status_code == 422
    elif case == "oversized":
        response = client.post(
            "/app/interventions/new",
            content="title=" + "A" * 65537,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert response.status_code == 422
    elif case == "extra":
        response = client.post(
            "/app/interventions/new",
            data={
                "csrf_token": token,
                "title": "Blocked",
                "site": "Demo",
                "status": "completed",
            },
        )
        assert response.status_code == 422
    elif case == "unknown":
        assert client.get(f"/app/interventions/{uuid4()}").status_code == 404
    else:
        assert client.get("/app/inbox").status_code == 403
    assert not service.list(MANAGER, InterventionFilters()).items


@pytest.mark.integration
def test_completion_errors_reassignment_stale_commands_and_read_scope(web):
    client, service = web
    job = service.create(
        MANAGER, InterventionCreate(title="Complete", site="Demo", technician_id=A)
    )
    worker = OutboxWorker(service.engine)
    for claim in worker.claim():
        worker.deliver(claim)
    with Session(service.engine) as db:
        notification_id = db.scalar(select(Notification.id))
    token = login(client, "demo-technician-b")
    assert (
        client.post(f"/app/inbox/{notification_id}/read", data={"csrf_token": token}).status_code
        == 403
    )
    token = login(client, "demo-technician-a")
    url = f"/app/interventions/{job.id}"
    assert (
        client.post(
            url + "/transition",
            data={
                "csrf_token": token,
                "expected_version": "1",
                "target_status": "in_progress",
            },
            follow_redirects=False,
        ).status_code
        == 303
    )
    response = client.post(
        url + "/transition",
        data={
            "csrf_token": token,
            "expected_version": "2",
            "target_status": "completed",
            "resolution": " ",
        },
    )
    assert response.status_code == 422 and 'role="alert"' in response.text
    response = client.post(
        url + "/transition",
        data={
            "csrf_token": token,
            "expected_version": "1",
            "target_status": "completed",
            "resolution": "Keep this proposed resolution",
        },
    )
    assert response.status_code == 409
    assert "Keep this proposed resolution" in response.text
    assert f'href="{url}">Reload the latest version' in response.text
    assert service.detail(MANAGER, job.id).status == "in_progress"


@pytest.mark.integration
def test_manager_cancellation_and_paginated_history(web):
    client, service = web
    token = login(client)
    job = service.create(MANAGER, InterventionCreate(title="Cancel", site="Demo", technician_id=A))
    url = f"/app/interventions/{job.id}"
    page = client.get(url + "?notice=updated&page=1&page_size=1")
    assert page.status_code == 200 and "Next" in page.text
    assert (
        client.post(
            url + "/transition",
            data={
                "csrf_token": token,
                "expected_version": "1",
                "target_status": "cancelled",
            },
            follow_redirects=False,
        ).status_code
        == 303
    )
    job = service.detail(MANAGER, job.id)
    assert job.status == "cancelled" and job.closed_at
    assert "Confirm cancellation" not in client.get(url).text
