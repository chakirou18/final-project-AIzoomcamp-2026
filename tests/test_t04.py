"""Lifecycle matrix and real PostgreSQL transaction/security evidence."""

from concurrent.futures import ThreadPoolExecutor
from itertools import product
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from fieldops.main import create_app
from fieldops.models import Intervention, NotificationOutbox
from fieldops.policy import DomainError, check_transition
from fieldops.schemas import (
    Assignment,
    InterventionCreate,
    InterventionEdit,
    InterventionFilters,
    Pagination,
    Status,
    Transition,
)
from fieldops.seed import persona_id
from fieldops.services.interventions import InterventionService

MANAGER = persona_id("demo-manager")
A = persona_id("demo-technician-a")
B = persona_id("demo-technician-b")
ALLOWED = {
    ("open", "assigned"),
    ("open", "cancelled"),
    ("assigned", "in_progress"),
    ("assigned", "cancelled"),
    ("in_progress", "completed"),
    ("in_progress", "cancelled"),
}


@pytest.mark.parametrize("source,target", list(product(Status, repeat=2)))
def test_complete_policy_matrix(source, target):
    if (source, target) in ALLOWED:
        check_transition(source, target)
    else:
        with pytest.raises(DomainError) as failure:
            check_transition(source, target)
        assert failure.value.status_code == 409


@pytest.fixture
def domain(pg_engine):
    return InterventionService(pg_engine)


def create(domain, **extra):
    return domain.create(MANAGER, InterventionCreate(title="Synthetic T04", site="Demo", **extra))


@pytest.mark.integration
@pytest.mark.parametrize(
    "source,target", list(product(Status, ["in_progress", "completed", "cancelled"]))
)
def test_database_transition_matrix(domain, source, target):
    job = create(domain, technician_id=None if source == "open" else A)
    if source in {"in_progress", "completed"}:
        job = domain.transition(
            A, job.id, Transition(expected_version=job.row_version, target_status="in_progress")
        )
    if source in {"completed", "cancelled"}:
        job = domain.transition(
            A if source == "completed" else MANAGER,
            job.id,
            Transition(
                expected_version=job.row_version,
                target_status=source,
                resolution="Fixed" if source == "completed" else None,
            ),
        )
    payload = Transition(
        expected_version=job.row_version,
        target_status=target,
        resolution="Fixed" if target == "completed" else None,
    )
    actor = MANAGER if target == "cancelled" else A
    if (source, target) in ALLOWED:
        assert domain.transition(actor, job.id, payload).status == target
    else:
        with pytest.raises(Exception) as failure:
            domain.transition(actor, job.id, payload)
        # Unassigned jobs deny technician scope before evaluating lifecycle state.
        assert failure.value.status_code == (403 if source == "open" and actor == A else 409)
        assert domain.detail(MANAGER, job.id) == job


@pytest.mark.integration
@pytest.mark.parametrize("priority", ["low", "medium", "high", "urgent"])
def test_lifecycle_and_history(domain, priority):
    job = create(domain, priority=priority, technician_id=A)
    assert (job.status, job.row_version, job.assignment_version) == ("assigned", 1, 1)
    assert domain.assign(MANAGER, job.id, Assignment(expected_version=1, technician_id=A)) == job
    job = domain.assign(MANAGER, job.id, Assignment(expected_version=1, technician_id=B))
    assert job.assignment_version == 2 and job.row_version == 2
    with pytest.raises(Exception) as failure:
        domain.detail(A, job.id)
    assert failure.value.status_code == 403
    job = domain.transition(B, job.id, Transition(expected_version=2, target_status="in_progress"))
    job = domain.transition(
        B, job.id, Transition(expected_version=3, target_status="completed", resolution="Fixed")
    )
    assert job.created_at <= job.started_at <= job.closed_at == job.updated_at
    assert job.resolution == "Fixed" and job.priority == priority
    history = domain.list_history(MANAGER, job.id, Pagination()).items
    assert [h.event_type for h in history] == [
        "transitioned",
        "transitioned",
        "assigned",
        "assigned",
        "created",
    ]
    with Session(domain.engine) as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(NotificationOutbox)
                .where(NotificationOutbox.intervention_id == job.id)
            )
            == 2
        )
    with pytest.raises(DomainError):
        domain.edit(MANAGER, job.id, InterventionEdit(expected_version=4, title="Denied"))


@pytest.mark.integration
@pytest.mark.parametrize("state", ["open", "assigned", "in_progress"])
def test_cancellation(domain, state):
    job = create(domain, technician_id=A if state != "open" else None)
    if state == "in_progress":
        job = domain.transition(A, job.id, Transition(expected_version=1, target_status=state))
    job = domain.transition(
        MANAGER, job.id, Transition(expected_version=job.row_version, target_status="cancelled")
    )
    assert job.closed_at == job.updated_at and job.status == "cancelled"
    with pytest.raises(DomainError):
        domain.transition(
            MANAGER, job.id, Transition(expected_version=job.row_version, target_status="cancelled")
        )


@pytest.mark.integration
@pytest.mark.parametrize("table", ["notification_outbox", "intervention_history"])
def test_assignment_failure_rolls_back(domain, table):
    job = create(domain)

    def reject(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO " + table):
            raise RuntimeError("Injected transaction failure")

    event.listen(domain.engine, "before_cursor_execute", reject)
    try:
        with pytest.raises(RuntimeError):
            domain.assign(MANAGER, job.id, Assignment(expected_version=1, technician_id=A))
    finally:
        event.remove(domain.engine, "before_cursor_execute", reject)
    assert domain.detail(MANAGER, job.id) == job
    assert domain.list_history(MANAGER, job.id, Pagination()).total == 1
    with Session(domain.engine) as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(NotificationOutbox)
                .where(NotificationOutbox.intervention_id == job.id)
            )
            == 0
        )
    assert (
        domain.assign(MANAGER, job.id, Assignment(expected_version=1, technician_id=A)).row_version
        == 2
    )


@pytest.mark.integration
def test_concurrent_updates_and_stale_noop(domain):
    job = create(domain)
    barrier = Barrier(2)

    def assign(technician):
        barrier.wait(timeout=10)
        try:
            return domain.assign(
                MANAGER, job.id, Assignment(expected_version=1, technician_id=technician)
            )
        except DomainError as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(assign, [A, B]))
    assert sum(isinstance(result, DomainError) for result in results) == 1
    loser = next(result for result in results if isinstance(result, DomainError))
    assert loser.code == "stale_version"
    winner = domain.detail(MANAGER, job.id)
    with pytest.raises(DomainError, match="stale_version"):
        domain.assign(
            MANAGER, job.id, Assignment(expected_version=1, technician_id=winner.technician_id)
        )
    assert domain.list_history(MANAGER, job.id, Pagination()).total == 2


@pytest.mark.integration
def test_direct_http_permissions_validation_and_pagination(pg_settings):
    settings = pg_settings.model_copy(
        update={
            "demo_mode": True,
            "session_secret_file": None,
            "session_secret": SecretStr("synthetic-t04-test-signing-key-only-32"),
        }
    )
    with TestClient(create_app(settings)) as client:
        path = "/api/v1/interventions"
        assert client.get(path).status_code == 401

        def login(persona):
            token = client.get("/auth/csrf").json()["csrf_token"]
            response = client.post(
                "/auth/login", headers={"X-CSRF-Token": token}, json={"persona_id": str(persona)}
            )
            assert response.status_code == 200
            return {"X-CSRF-Token": response.json()["csrf_token"]}

        headers = login(MANAGER)
        assert client.post(path, json={"title": "x", "site": "y"}).status_code == 403
        for bad in [{"priority": "critical"}, {"title": " "}, {"status": "completed"}]:
            assert (
                client.post(
                    path, headers=headers, json={"title": "x", "site": "y", **bad}
                ).status_code
                == 422
            )
        response = client.post(
            path,
            headers=headers,
            json={"title": "HTTP synthetic", "site": "Demo", "technician_id": str(A)},
        )
        assert response.status_code == 201
        job = response.json()
        url = path + "/" + job["id"]
        assert (
            client.patch(
                url, headers=headers, json={"expected_version": 1, "title": "Changed"}
            ).status_code
            == 200
        )

        assert (
            client.patch(
                url, headers=headers, json={"expected_version": 1, "title": "Stale"}
            ).status_code
            == 409
        )
        assert client.get(path + "?page_size=101").status_code == 422
        assert client.get(path + "?page=" + "9" * 30).json()["items"] == []
        assert client.delete(url + "/history", headers=headers).status_code == 405
        headers = login(B)
        assert client.get(url).status_code == 403
        assert client.get(url + "/history").status_code == 403
        assert (
            client.post(path, headers=headers, json={"title": "x", "site": "y"}).status_code == 403
        )
        assert client.get(path + "?technician_id=" + str(A)).json()["items"] == []
        headers = login(A)
        assert client.get(url).status_code == 200
        assert client.get("/api/v1/technicians").status_code == 403
        assert (
            client.post(
                url + "/transitions",
                headers=headers,
                json={"expected_version": 2, "target_status": "completed", "resolution": "Fixed"},
            ).status_code
            == 409
        )
        assert (
            client.post(
                url + "/transitions",
                headers=headers,
                json={"expected_version": 2, "target_status": "in_progress"},
            ).status_code
            == 200
        )
        assert (
            client.post(
                url + "/transitions",
                headers=headers,
                json={"expected_version": 3, "target_status": "completed", "resolution": " "},
            ).status_code
            == 422
        )
        assert (
            client.post(
                url + "/transitions",
                headers=headers,
                json={"expected_version": 3, "target_status": "completed", "resolution": "Fixed"},
            ).status_code
            == 200
        )


@pytest.mark.integration
def test_create_assignment_failure_is_atomic(domain):
    with Session(domain.engine) as db:
        before = db.scalar(select(func.count()).select_from(Intervention))

    def reject(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO notification_outbox"):
            raise RuntimeError("Injected create failure")

    event.listen(domain.engine, "before_cursor_execute", reject)
    try:
        with pytest.raises(RuntimeError):
            create(domain, technician_id=A)
    finally:
        event.remove(domain.engine, "before_cursor_execute", reject)
    with Session(domain.engine) as db:
        assert db.scalar(select(func.count()).select_from(Intervention)) == before


@pytest.mark.integration
def test_filters_order_and_pages(domain):
    jobs = [create(domain, technician_id=B, priority="urgent") for _ in range(3)]
    filters = InterventionFilters(
        technician_id=B, status="assigned", priority="urgent", page_size=2
    )
    page = domain.list(MANAGER, filters)
    assert [job.id for job in page.items] == [jobs[2].id, jobs[1].id]
    second = domain.list(MANAGER, filters.model_copy(update={"page": 2}))
    assert second.items[0].id == jobs[0].id and second.total == page.total
    assert not domain.list(A, filters).items
    assert all(job.technician_id == B for job in domain.list(B, filters).items)


@pytest.mark.integration
@pytest.mark.parametrize("actor", [A, B, persona_id("demo-operator")])
def test_nonmanager_mutations_denied(domain, actor):
    job = create(domain, technician_id=A)
    commands = [
        lambda: domain.create(actor, InterventionCreate(title="x", site="y")),
        lambda: domain.edit(actor, job.id, InterventionEdit(expected_version=1, title="Denied")),
        lambda: domain.assign(actor, job.id, Assignment(expected_version=1, technician_id=B)),
        lambda: domain.transition(
            actor, job.id, Transition(expected_version=1, target_status="cancelled")
        ),
    ]
    for command in commands:
        with pytest.raises(Exception) as failure:
            command()
        assert failure.value.status_code == 403
    assert domain.detail(MANAGER, job.id) == job


@pytest.mark.integration
def test_invalid_assignee_and_manager_start_denied(domain):
    job = create(domain)
    with pytest.raises(DomainError) as failure:
        domain.assign(MANAGER, job.id, Assignment(expected_version=1, technician_id=MANAGER))
    assert failure.value.status_code == 422
    with pytest.raises(Exception) as failure:
        domain.transition(
            MANAGER, job.id, Transition(expected_version=1, target_status="in_progress")
        )
    assert failure.value.status_code == 403
    assert domain.detail(MANAGER, job.id) == job
