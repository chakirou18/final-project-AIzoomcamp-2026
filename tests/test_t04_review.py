"""Independent T04 audit: real HTTP, commit-time failures and authorization races."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from itertools import product
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import event, func, select, text
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.orm import Session

from fieldops.auth import COOKIE
from fieldops.bootstrap import migrate, seed
from fieldops.database import create_database_engine
from fieldops.main import create_app
from fieldops.models import Intervention, InterventionHistory, NotificationOutbox, User
from fieldops.schemas import (
    Assignment,
    InterventionCreate,
    InterventionEdit,
    Pagination,
    Transition,
)
from fieldops.seed import persona_id
from fieldops.services.interventions import InterventionService

pytestmark = pytest.mark.integration
MANAGER = persona_id("demo-manager")
A = persona_id("demo-technician-a")
B = persona_id("demo-technician-b")


@pytest.fixture(scope="module")
def audit_settings(pg_settings):
    # No application DB is downgraded or cleared; this DB is retained for inspection.
    name = "fieldops_t04_review_" + uuid4().hex + "_test"
    engine = create_database_engine(pg_settings)
    try:
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            conn.exec_driver_sql(f'CREATE DATABASE "{name}"')
    finally:
        engine.dispose()
    settings = pg_settings.model_copy(
        update={
            "db_name": name,
            "demo_mode": True,
            "session_secret_file": None,
            "session_secret": SecretStr("synthetic-t04-review-signing-key-32-chars"),
            "operator_secret": SecretStr("synthetic-t04-review-operator-key-32-chars"),
        }
    )
    migrate(settings)
    seed(settings)
    return settings


@pytest.fixture
def domain(audit_settings):
    engine = create_database_engine(audit_settings)
    try:
        yield InterventionService(engine)
    finally:
        engine.dispose()


def login(client, key):
    csrf = client.get("/auth/csrf").json()["csrf_token"]
    payload = {"persona_id": str(persona_id(key))}
    if key == "demo-operator":
        payload["operator_secret"] = "synthetic-t04-review-operator-key-32-chars"
    response = client.post("/auth/login", headers={"X-CSRF-Token": csrf}, json=payload)
    assert response.status_code == 200
    return {"X-CSRF-Token": response.json()["csrf_token"]}


@pytest.fixture
def clients(audit_settings):
    with ExitStack() as stack:
        result = {}
        for role in ("manager", "technician-a", "technician-b", "operator"):
            client = stack.enter_context(TestClient(create_app(audit_settings)))
            result[role] = (client, login(client, "demo-" + role))
        yield result


def create(domain, assignee=None):
    return domain.create(
        MANAGER,
        InterventionCreate(
            title="Synthetic audit",
            site="Audit site",
            technician_id=assignee,
        ),
    )


def state_job(domain, state):
    job = create(domain, None if state == "open" else A)
    if state in {"in_progress", "completed"}:
        job = domain.transition(
            A, job.id, Transition(expected_version=job.row_version, target_status="in_progress")
        )
    if state in {"completed", "cancelled"}:
        job = domain.transition(
            A if state == "completed" else MANAGER,
            job.id,
            Transition(
                expected_version=job.row_version,
                target_status=state,
                resolution="Synthetic repair" if state == "completed" else None,
            ),
        )
    return job


@pytest.mark.parametrize(
    "source,target",
    list(product(["open", "assigned", "in_progress", "completed", "cancelled"], repeat=2)),
)
def test_http_full_transition_matrix(domain, clients, source, target):
    job = state_job(domain, source)
    role = "manager" if target == "cancelled" else "technician-a"
    client, headers = clients[role]
    payload = {"expected_version": job.row_version, "target_status": target}
    if target == "completed":
        payload["resolution"] = "Synthetic repair"
    response = client.post(
        f"/api/v1/interventions/{job.id}/transitions", headers=headers, json=payload
    )
    allowed = {
        ("open", "cancelled"),
        ("assigned", "in_progress"),
        ("assigned", "cancelled"),
        ("in_progress", "completed"),
        ("in_progress", "cancelled"),
    }
    expected = (
        422
        if target in {"open", "assigned"}
        else 200
        if (source, target) in allowed
        else 403
        if source == "open" and role == "technician-a"
        else 409
    )
    assert response.status_code == expected, response.text
    if expected == 200:
        result = response.json()
        assert result["status"] == target and result["row_version"] == job.row_version + 1
    else:
        assert set(response.json()) == {"error"}
        assert domain.detail(MANAGER, job.id) == job


def counts(domain):
    with Session(domain.engine) as db:
        return tuple(
            db.scalar(select(func.count()).select_from(model))
            for model in (Intervention, InterventionHistory, NotificationOutbox)
        )


@pytest.mark.parametrize(
    "operation,table",
    [
        ("create", "intervention_history"),
        ("create_assigned", "intervention_history"),
        ("create_assigned", "notification_outbox"),
        ("assign", "intervention_history"),
        ("assign", "notification_outbox"),
        ("edit", "intervention_history"),
        ("transition", "intervention_history"),
    ],
)
def test_database_commit_failure_rolls_back_every_row(domain, operation, table):
    job = create(domain, A if operation == "transition" else None)
    before = counts(domain)
    # PostgreSQL itself rejects COMMIT after ORM flush succeeded. No persistence mocks.
    with domain.engine.begin() as conn:
        conn.exec_driver_sql("""CREATE FUNCTION t04_audit_reject() RETURNS trigger
            LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'synthetic audit rejection'; END $$""")
        conn.exec_driver_sql(f"""CREATE CONSTRAINT TRIGGER t04_audit_reject
            AFTER INSERT ON {table} DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION t04_audit_reject()""")
    try:
        with pytest.raises(DBAPIError) as failure:
            if operation.startswith("create"):
                create(domain, A if operation == "create_assigned" else None)
            elif operation == "assign":
                domain.assign(MANAGER, job.id, Assignment(expected_version=1, technician_id=A))
            elif operation == "edit":
                domain.edit(MANAGER, job.id, InterventionEdit(expected_version=1, title="Changed"))
            else:
                domain.transition(
                    A, job.id, Transition(expected_version=1, target_status="in_progress")
                )
        assert failure.value.orig.sqlstate == "P0001"
    finally:
        with domain.engine.begin() as conn:
            conn.exec_driver_sql(f"DROP TRIGGER t04_audit_reject ON {table}")
            conn.exec_driver_sql("DROP FUNCTION t04_audit_reject()")
    assert counts(domain) == before
    assert domain.detail(MANAGER, job.id) == job


def test_history_scope_locked_until_history_read_finishes(domain):
    job = create(domain, A)
    probed = []

    def probe(conn, cursor, statement, parameters, context, executemany):
        if not probed and "FROM interventions " in statement and statement.startswith("SELECT"):
            probed.append(True)
            with domain.engine.connect() as other, other.begin():
                other.execute(text("SET LOCAL lock_timeout='100ms'"))
                with pytest.raises(OperationalError) as failure:
                    other.execute(
                        text("UPDATE interventions SET technician_id=:tech WHERE id=:id"),
                        {"tech": B, "id": job.id},
                    )
                assert failure.value.orig.sqlstate == "55P03"

    event.listen(domain.engine, "after_cursor_execute", probe)
    try:
        assert domain.list_history(A, job.id, Pagination()).total == 2
    finally:
        event.remove(domain.engine, "after_cursor_execute", probe)
    assert probed


def test_assignment_outbox_timestamp_reflects_operation(domain):
    job = create(domain)
    job = domain.assign(MANAGER, job.id, Assignment(expected_version=1, technician_id=A))
    with Session(domain.engine) as db:
        outbox = db.scalar(
            select(NotificationOutbox).where(NotificationOutbox.intervention_id == job.id)
        )
        assert job.created_at <= job.updated_at == outbox.created_at == outbox.available_at


def test_concurrent_http_assignment_and_checked_noop(domain, audit_settings):
    job = create(domain)
    with (
        TestClient(create_app(audit_settings)) as one,
        TestClient(create_app(audit_settings)) as two,
    ):
        headers = [login(one, "demo-manager"), login(two, "demo-manager")]
        barrier = Barrier(2)
        url = f"/api/v1/interventions/{job.id}/assignment"

        def assign(index):
            barrier.wait(timeout=10)
            return [one, two][index].post(
                url,
                headers=headers[index],
                json={
                    "expected_version": 1,
                    "technician_id": str([A, B][index]),
                },
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            responses = list(executor.map(assign, [0, 1]))
        assert sorted(response.status_code for response in responses) == [200, 409]
        conflict = next(response for response in responses if response.status_code == 409)
        assert conflict.json()["error"]["code"] == "stale_version"
        winner = next(response.json() for response in responses if response.status_code == 200)
        before = counts(domain)
        repeat = {"expected_version": 2, "technician_id": winner["technician_id"]}
        assert one.post(url, headers=headers[0], json=repeat).json() == winner
        assert counts(domain) == before
        repeat["expected_version"] = 1
        assert one.post(url, headers=headers[0], json=repeat).status_code == 409
        assert counts(domain) == before
    with Session(domain.engine) as db:
        events = db.scalars(
            select(NotificationOutbox).where(NotificationOutbox.intervention_id == job.id)
        ).all()
        assert len(events) == 1
        assert events[0].recipient_id == UUID(winner["technician_id"])
        assert events[0].assignment_version == 1 and events[0].status == "pending"
    assert domain.list_history(MANAGER, job.id, Pagination()).total == 2


@pytest.mark.parametrize("role", ["technician-a", "technician-b", "operator"])
def test_real_http_denied_mutations(domain, clients, role):
    job = create(domain, A)
    client, headers = clients[role]
    url = f"/api/v1/interventions/{job.id}"
    for method, path, payload in [
        ("POST", "/api/v1/interventions", {"title": "x", "site": "y"}),
        ("PATCH", url, {"expected_version": 1, "title": "Denied"}),
        ("POST", url + "/assignment", {"expected_version": 1, "technician_id": str(B)}),
        ("POST", url + "/transitions", {"expected_version": 1, "target_status": "cancelled"}),
    ]:
        response = client.request(method, path, headers=headers, json=payload)
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "forbidden"
    assert domain.detail(MANAGER, job.id) == job


@pytest.mark.parametrize("invalid", ["missing", "tampered", "revoked"])
def test_invalid_sessions_on_business_routes(domain, audit_settings, invalid):
    job = create(domain, A)
    with TestClient(create_app(audit_settings)) as client:
        headers = login(client, "demo-manager")
        saved = client.cookies.get(COOKIE)
        if invalid == "revoked":
            assert client.post("/auth/logout", headers=headers).status_code == 204
            cookie = saved
        else:
            cookie = saved + "bad" if invalid == "tampered" else None
        client.cookies.clear()
        request_headers = {**headers, **({"Cookie": f"{COOKIE}={cookie}"} if cookie else {})}
        for method, url, payload in [
            ("GET", "/api/v1/interventions", None),
            ("GET", f"/api/v1/interventions/{job.id}/history", None),
            (
                "POST",
                f"/api/v1/interventions/{job.id}/assignment",
                {"expected_version": 1, "technician_id": str(B)},
            ),
        ]:
            response = client.request(method, url, headers=request_headers, json=payload)
            assert response.status_code == 401
            assert response.json()["error"]["code"] == "unauthenticated"
    assert domain.detail(MANAGER, job.id) == job


@pytest.mark.parametrize("state", ["open", "assigned", "in_progress", "completed", "cancelled"])
@pytest.mark.parametrize("operation", ["edit", "assignment"])
def test_http_edit_and_assignment_eligibility(domain, clients, state, operation):
    job = state_job(domain, state)
    client, headers = clients["manager"]
    url = f"/api/v1/interventions/{job.id}"
    before = counts(domain)
    if operation == "edit":
        response = client.patch(
            url,
            headers=headers,
            json={
                "expected_version": job.row_version,
                "description": "Edited synthetic description",
            },
        )
    else:
        response = client.post(
            url + "/assignment",
            headers=headers,
            json={
                "expected_version": job.row_version,
                "technician_id": str(B),
            },
        )
    assert response.status_code == (200 if state in {"open", "assigned"} else 409)
    if response.status_code == 409:
        assert domain.detail(MANAGER, job.id) == job and counts(domain) == before


@pytest.mark.parametrize("field,length", [("title", 160), ("site", 250), ("description", 4000)])
def test_http_field_limit_boundary(domain, clients, field, length):
    client, headers = clients["manager"]
    payload = {"title": "Synthetic", "site": "Demo", field: "x" * length}
    valid = client.post("/api/v1/interventions", headers=headers, json=payload)
    assert valid.status_code == 201 and valid.json()[field] == "x" * length
    before = counts(domain)
    payload[field] += "x"
    invalid = client.post("/api/v1/interventions", headers=headers, json=payload)
    assert invalid.status_code == 422 and invalid.json()["error"]["fields"]
    assert counts(domain) == before


def test_csrf_wrong_role_cross_scope_and_missing_id(domain, clients):
    job = create(domain, A)
    manager, manager_headers = clients["manager"]
    technician, tech_headers = clients["technician-a"]
    other, other_headers = clients["technician-b"]
    operator, _ = clients["operator"]
    url = f"/api/v1/interventions/{job.id}"
    before = counts(domain)
    for headers in ({}, {"X-CSRF-Token": "invalid"}, tech_headers):
        for method, path, payload in [
            ("POST", "/api/v1/interventions", {"title": "x", "site": "y"}),
            ("PATCH", url, {"expected_version": 1, "title": "Denied"}),
            ("POST", url + "/assignment", {"expected_version": 1, "technician_id": str(B)}),
            ("POST", url + "/transitions", {"expected_version": 1, "target_status": "cancelled"}),
        ]:
            response = manager.request(method, path, headers=headers, json=payload)
            assert response.status_code == 403
            assert response.json()["error"]["code"] == "csrf_failed"
    for suffix in ("", "/history"):
        assert other.get(url + suffix).status_code == 403
        assert operator.get(url + suffix).status_code == 403
    assert (
        other.post(
            url + "/transitions",
            headers=other_headers,
            json={
                "expected_version": 1,
                "target_status": "in_progress",
            },
        ).status_code
        == 403
    )
    assert (
        manager.post(
            url + "/transitions",
            headers=manager_headers,
            json={
                "expected_version": 1,
                "target_status": "in_progress",
            },
        ).status_code
        == 403
    )
    assert operator.get("/api/v1/interventions").status_code == 403
    assert len(manager.get("/api/v1/technicians").json()) == 2
    assert manager.get("/api/v1/interventions/" + str(uuid4())).status_code == 404
    assert manager.get("/api/v1/interventions/bad-uuid").status_code == 422
    assert technician.get(url).headers["cache-control"] == "no-store"
    assert counts(domain) == before and domain.detail(MANAGER, job.id) == job


def test_inactive_unknown_and_nontechnician_assignees(domain, clients):
    inactive = uuid4()
    with Session(domain.engine) as db, db.begin():
        db.add(
            User(
                id=inactive,
                persona_key="audit-" + inactive.hex,
                display_name="Synthetic inactive",
                role="technician",
                active=False,
            )
        )
    job = create(domain)
    manager, headers = clients["manager"]
    before = counts(domain)
    for assignee in (inactive, uuid4(), MANAGER):
        response = manager.post(
            f"/api/v1/interventions/{job.id}/assignment",
            headers=headers,
            json={"expected_version": 1, "technician_id": str(assignee)},
        )
        assert response.status_code == 422
        assert "technician_id" in response.json()["error"]["fields"]
    assert counts(domain) == before and domain.detail(MANAGER, job.id) == job


@pytest.mark.parametrize("state", ["open", "assigned", "in_progress"])
def test_cancel_preserves_assignment_start_and_history(domain, state):
    job = state_job(domain, state)
    result = domain.transition(
        MANAGER, job.id, Transition(expected_version=job.row_version, target_status="cancelled")
    )
    assert result.technician_id == job.technician_id
    assert result.started_at == job.started_at
    assert result.assignment_version == job.assignment_version
    assert result.closed_at == result.updated_at >= job.updated_at
    history = domain.list_history(MANAGER, job.id, Pagination()).items[0]
    assert history.actor_id == MANAGER and history.created_at == result.closed_at
    assert history.changed_fields["status"] == {"old": state, "new": "cancelled"}
    assert history.changed_fields["row_version"] == {
        "old": job.row_version,
        "new": result.row_version,
    }


def test_resolution_boundaries_and_edit_history(domain, clients):
    job = create(domain, A)
    manager, headers = clients["manager"]
    technician, tech_headers = clients["technician-a"]
    url = f"/api/v1/interventions/{job.id}"
    assert (
        manager.patch(
            url,
            headers=headers,
            json={
                "expected_version": 1,
                "description": "Explicit edit",
            },
        ).status_code
        == 200
    )
    history = domain.list_history(MANAGER, job.id, Pagination()).items[0]
    assert history.event_type == "edited" and history.actor_id == MANAGER
    assert history.changed_fields["description"] == {"old": "", "new": "Explicit edit"}
    assert (
        technician.post(
            url + "/transitions",
            headers=tech_headers,
            json={
                "expected_version": 2,
                "target_status": "in_progress",
            },
        ).status_code
        == 200
    )
    before = counts(domain)
    for resolution in (None, "", " \t\n", "x" * 4001):
        response = technician.post(
            url + "/transitions",
            headers=tech_headers,
            json={
                "expected_version": 3,
                "target_status": "completed",
                "resolution": resolution,
            },
        )
        assert response.status_code == 422
    assert counts(domain) == before
    result = technician.post(
        url + "/transitions",
        headers=tech_headers,
        json={
            "expected_version": 3,
            "target_status": "completed",
            "resolution": "x" * 4000,
        },
    )
    assert result.status_code == 200 and len(result.json()["resolution"]) == 4000
