"""Independent HTML authorization audit with exact persisted-state comparisons."""

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_t05_web import MANAGER, A, B, login
from test_t05_web import web as web

from fieldops.models import InterventionHistory, NotificationOutbox
from fieldops.schemas import InterventionCreate

pytestmark = pytest.mark.integration


def snapshot(service, identifier):
    with Session(service.engine) as db:
        return (
            service.detail(MANAGER, identifier).model_dump(mode="json"),
            db.scalar(select(func.count()).select_from(InterventionHistory)),
            db.scalar(select(func.count()).select_from(NotificationOutbox)),
        )


@pytest.mark.parametrize(
    "persona,operation",
    [
        ("demo-technician-a", "create"),
        ("demo-technician-a", "edit"),
        ("demo-technician-a", "assignment"),
        ("demo-technician-a", "cancel"),
        ("demo-technician-b", "edit"),
        ("demo-technician-b", "assignment"),
        ("demo-technician-b", "start"),
        ("demo-technician-b", "complete"),
        ("demo-technician-b", "cancel"),
        ("demo-manager", "start"),
        ("demo-manager", "complete"),
    ],
)
def test_direct_html_denials_preserve_job_history_and_outbox(web, persona, operation):
    client, service = web
    job = service.create(
        MANAGER, InterventionCreate(title="Audit private job", site="Synthetic", technician_id=A)
    )
    before = snapshot(service, job.id)
    token = login(client, persona)
    url = f"/app/interventions/{job.id}"
    data = {"csrf_token": token, "expected_version": "1"}
    if operation == "create":
        url = "/app/interventions/new"
        data = {"csrf_token": token, "title": "Denied", "site": "Synthetic"}
    elif operation == "edit":
        url += "/edit"
        data["priority"] = "urgent"
    elif operation == "assignment":
        url += "/assignment"
        data["technician_id"] = str(B)
    else:
        url += "/transition"
        data["target_status"] = {
            "start": "in_progress",
            "complete": "completed",
            "cancel": "cancelled",
        }[operation]
        if operation == "complete":
            data["resolution"] = "Denied completion"
    response = client.post(url, data=data)
    assert response.status_code == 403
    assert response.headers["content-type"].startswith("text/html")
    assert snapshot(service, job.id) == before


@pytest.mark.parametrize("token_state", ["missing", "wrong", "other_session"])
def test_csrf_cannot_mutate_or_leak_session_material(web, token_state):
    client, service = web
    job = service.create(MANAGER, InterventionCreate(title="CSRF unchanged", site="Demo"))
    before = snapshot(service, job.id)
    first = login(client)
    current = login(client)
    supplied = {"missing": "", "wrong": "invalid", "other_session": first}[token_state]
    response = client.post(
        f"/app/interventions/{job.id}/edit",
        data={
            "csrf_token": supplied,
            "expected_version": "1",
            "title": "Not saved",
        },
    )
    assert response.status_code == 403
    # Boolean assertions avoid serializing live runtime tokens into JUnit failure reports.
    assert all(value not in response.text for value in (first, current))
    assert snapshot(service, job.id) == before


def test_unauthenticated_html_mutations_and_unknown_reference_are_safe(web):
    client, service = web
    job = service.create(
        MANAGER, InterventionCreate(title="Private title", site="Demo", technician_id=A)
    )
    before = snapshot(service, job.id)
    response = client.post(
        f"/app/interventions/{job.id}/transition",
        data={
            "expected_version": "1",
            "target_status": "in_progress",
        },
    )
    assert response.status_code == 401 and "Private title" not in response.text
    assert snapshot(service, job.id) == before
