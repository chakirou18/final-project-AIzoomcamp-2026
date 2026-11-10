"""T07 real PostgreSQL locks, durable control results and direct HTTP authority checks."""

import time
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from uuid import uuid4

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError
from sqlalchemy import event, func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from test_t06_postgresql import MANAGER, A, login
from test_t06_postgresql import queue as queue

from fieldops.control_schemas import PauseRequest, ResumeRequest
from fieldops.main import create_app
from fieldops.models import (
    Base,
    Notification,
    WorkerControlAudit,
    WorkerResumeAction,
)
from fieldops.policy import DomainError
from fieldops.schemas import InterventionCreate, Transition
from fieldops.seed import persona_id
from fieldops.services.controls import ControlService
from fieldops.settings import Settings
from fieldops.worker import OutboxWorker

OPERATOR = persona_id("demo-operator")
OPERATOR_SECRET = "synthetic-t07-operator-credential-only"
RECOVERY_SECRET = "synthetic-t07-recovery-credential-only"


@pytest.fixture
def ops(queue):
    worker, service, settings = queue
    settings = settings.model_copy(
        update={
            "operator_secret": SecretStr(OPERATOR_SECRET),
            "recovery_secret": SecretStr(RECOVERY_SECRET),
        }
    )
    with TestClient(create_app(settings)) as client:
        yield worker, service, ControlService(worker.engine), client, settings


def operator(client):
    csrf = client.get("/auth/csrf").json()["csrf_token"]
    response = client.post(
        "/auth/login",
        json={
            "persona_id": str(OPERATOR),
            "operator_secret": OPERATOR_SECRET,
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200
    return {"X-CSRF-Token": response.json()["csrf_token"]}


def resume_command(generation=1, **extra):
    return ResumeRequest(
        incident_id=uuid4(), expected_generation=generation, idempotency_key=uuid4(), **extra
    )


def counts(engine):
    with Session(engine) as db:
        return tuple(
            db.scalar(select(func.count()).select_from(model))
            for model in (
                Notification,
                WorkerControlAudit,
                WorkerResumeAction,
            )
        )


@pytest.mark.parametrize(
    "data",
    [
        {"expected_generation": -1},
        {"expected_generation": True},
        {"expected_generation": "0"},
        {"expected_generation": 0, "duration_seconds": 601},
        {"expected_generation": 0, "duration_seconds": 0},
        {"expected_generation": 0, "target": "shell"},
    ],
)
def test_pause_contract_rejects_unbounded_commands(data):
    with pytest.raises(ValidationError):
        PauseRequest.model_validate(data)


@pytest.mark.integration
def test_dashboard_real_counts_and_failed_oldest(ops):
    worker, service, control, _, _ = ops
    jobs = [
        service.create(MANAGER, InterventionCreate(title="Counts", site="Demo", technician_id=A))
        for _ in range(4)
    ]
    service.create(MANAGER, InterventionCreate(title="Open", site="Demo"))
    cancelled = service.create(MANAGER, InterventionCreate(title="Cancelled", site="Demo"))
    service.transition(
        MANAGER, cancelled.id, Transition(expected_version=1, target_status="cancelled")
    )
    service.transition(A, jobs[0].id, Transition(expected_version=1, target_status="in_progress"))
    service.transition(
        A, jobs[0].id, Transition(expected_version=2, target_status="completed", resolution="Done")
    )
    service.transition(A, jobs[1].id, Transition(expected_version=1, target_status="in_progress"))
    claims = worker.claim()
    assert len(claims) == 4 and worker.deliver(claims[0])
    assert worker.fail(claims[3])
    with worker.engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE notification_outbox SET status='failed', attempts=5, "
                "lease_token=NULL, lease_until=NULL, "
                "created_at=clock_timestamp()-interval '90 seconds' "
                "WHERE id=:id"
            ),
            {"id": claims[2].event_id},
        )
    data = control.dashboard(OPERATOR)
    assert data.interventions == {
        "open": 1,
        "assigned": 2,
        "in_progress": 1,
        "completed": 1,
        "cancelled": 1,
    }
    assert data.unfinished == 4 and data.assigned == 2 and data.pending_interventions == 1
    assert data.notifications == {"pending": 1, "processing": 1, "failed": 1, "delivered": 1}
    assert (
        data.undelivered == 3 and 90 <= data.oldest_undelivered_age_seconds < 100 and data.delayed
    )


@pytest.mark.integration
def test_empty_age_and_fresh_paused_stale_and_missing_heartbeat(ops):
    worker, _, control, client, _ = ops
    data = control.dashboard(OPERATOR)
    assert data.undelivered == 0 and data.oldest_undelivered_age_seconds == 0
    assert data.worker.heartbeat_state == "missing"
    worker.run_once()
    assert control.status().heartbeat_state == "fresh"
    control.pause(OPERATOR, PauseRequest(expected_generation=0))
    worker.run_once()
    state = control.status()
    assert (
        state.paused
        and state.heartbeat_state == "fresh"
        and state.last_instance_id == worker.instance_id
    )
    with worker.engine.begin() as connection:
        connection.execute(
            text("UPDATE worker_heartbeats SET last_seen=clock_timestamp()-interval '16 seconds'")
        )
    assert control.status().heartbeat_state == "stale"
    assert client.get("/health/ready").status_code == 200  # Readiness is not worker health.


@pytest.mark.integration
def test_pause_blocks_claim_and_previously_claimed_delivery(ops):
    worker, service, control, _, _ = ops
    job = service.create(MANAGER, InterventionCreate(title="Pause", site="Demo", technician_id=A))
    claim = worker.claim()[0]
    state = control.pause(OPERATOR, PauseRequest(expected_generation=0))
    assert state.paused and state.generation == 1 and state.effective_at < state.expires_at
    assert (state.expires_at - state.effective_at).total_seconds() == 600
    assert worker.claim() == [] and not worker.deliver(claim)
    assert counts(worker.engine) == (0, 1, 0)
    worker.run_once()
    result = control.resume(resume_command())
    assert result.success
    assert worker.deliver(claim)
    with Session(worker.engine) as db:
        assert db.scalar(select(Notification.intervention_id)) == job.id


@pytest.mark.integration
def test_pause_ack_waits_for_real_delivery_transaction(ops):
    worker, service, control, _, _ = ops
    service.create(
        MANAGER, InterventionCreate(title="Active transaction", site="Demo", technician_id=A)
    )
    claim = worker.claim()[0]
    entered, release = Event(), Event()

    def hold(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO notifications"):
            entered.set()
            assert release.wait(5)

    event.listen(worker.engine, "before_cursor_execute", hold)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            delivery = pool.submit(worker.deliver, claim)
            assert entered.wait(3)
            pausing = pool.submit(control.pause, OPERATOR, PauseRequest(expected_generation=0))
            deadline = time.monotonic() + 1.5
            waiting = False
            while time.monotonic() < deadline:
                with worker.engine.connect() as connection:
                    waiting = connection.scalar(
                        text(
                            "SELECT EXISTS(SELECT 1 FROM pg_stat_activity "
                            "WHERE datname=current_database() AND wait_event_type='Lock' "
                            "AND query LIKE '%worker_control%')"
                        )
                    )
                if waiting:
                    break
            assert waiting and not pausing.done()
            release.set()
            assert delivery.result(timeout=3)
            state = pausing.result(timeout=3)
            with Session(worker.engine) as db:
                assert db.scalar(select(Notification.delivered_at)) <= state.effective_at
    finally:
        release.set()
        event.remove(worker.engine, "before_cursor_execute", hold)


@pytest.mark.integration
def test_concurrent_replay_atomic_result_and_wrong_key_binding(ops):
    worker, _, control, _, _ = ops
    control.pause(OPERATOR, PauseRequest(expected_generation=0))
    command = resume_command()
    barrier = Barrier(2)

    def invoke():
        barrier.wait()
        return control.resume(command)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: invoke(), range(2)))
    assert results[0] == results[1] and results[0].success
    assert counts(worker.engine) == (0, 2, 1)
    changed = command.model_copy(update={"incident_id": uuid4()})
    with pytest.raises(DomainError) as error:
        control.resume(changed)
    assert error.value.code == "idempotency_conflict"
    wrong = control.resume(resume_command(99))
    assert not wrong.success and wrong.outcome == "generation_mismatch"
    assert control.resume(resume_command()).outcome == "not_paused"


@pytest.mark.integration
def test_rate_limit_new_generation_and_old_replay_do_not_resume_new_pause(ops):
    worker, _, control, _, _ = ops
    control.pause(OPERATOR, PauseRequest(expected_generation=0))
    command = resume_command()
    recorded = control.resume(command)
    with pytest.raises(DomainError) as error:
        control.pause(OPERATOR, PauseRequest(expected_generation=1))
    assert error.value.status_code == 429
    with worker.engine.begin() as connection:
        connection.execute(
            text("UPDATE worker_control SET last_pause_at=clock_timestamp()-interval '11 seconds'")
        )
    control.pause(OPERATOR, PauseRequest(expected_generation=1))
    assert control.resume(command) == recorded
    assert control.status().paused and control.status().generation == 2
    assert not control.resume(resume_command(1)).success


@pytest.mark.integration
def test_real_short_expiration_is_audited_external_recovery(ops):
    worker, _, control, _, _ = ops
    control.pause(OPERATOR, PauseRequest(expected_generation=0, duration_seconds=1))
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        worker.run_once()
        if not control.status().paused:
            break
        time.sleep(0.02)
    assert not control.status().paused
    assert control.resume(resume_command()).outcome == "not_paused"
    with Session(worker.engine) as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(WorkerControlAudit)
                .where(
                    WorkerControlAudit.event_type == "auto_expired",
                    WorkerControlAudit.outcome == "externally_recovered",
                )
            )
            == 1
        )


@pytest.mark.integration
@pytest.mark.parametrize(
    "operation,table",
    [
        ("pause", "worker_control_audit"),
        ("resume", "worker_resume_actions"),
        ("resume", "worker_control_audit"),
    ],
)
@pytest.mark.parametrize("phase", ["statement", "commit"])
def test_control_and_result_rollback_on_real_postgresql_failure(ops, operation, table, phase):
    worker, _, control, _, _ = ops
    if operation == "resume":
        control.pause(OPERATOR, PauseRequest(expected_generation=0))
    before = control.status()
    previous_counts = counts(worker.engine)
    with worker.engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE FUNCTION reject_t07() RETURNS trigger LANGUAGE plpgsql AS $$ "
            "BEGIN RAISE EXCEPTION 'injected'; END $$"
        )
        if phase == "statement":
            trigger = f"CREATE TRIGGER reject_t07 BEFORE INSERT ON {table} "
        else:
            trigger = (
                f"CREATE CONSTRAINT TRIGGER reject_t07 AFTER INSERT ON {table} "
                "DEFERRABLE INITIALLY DEFERRED "
            )
        connection.exec_driver_sql(trigger + "FOR EACH ROW EXECUTE FUNCTION reject_t07()")
    with pytest.raises(DBAPIError):
        if operation == "pause":
            control.pause(OPERATOR, PauseRequest(expected_generation=0))
        else:
            control.resume(resume_command())
    assert control.status() == before and counts(worker.engine) == previous_counts


@pytest.mark.integration
@pytest.mark.parametrize(
    "credential", [None, "invalid", OPERATOR_SECRET, "synthetic-webhook-credential-only-32"]
)
def test_internal_auth_cannot_be_replaced_by_operator_or_webhook(ops, credential):
    worker, _, control, client, _ = ops
    operator(client)
    headers = {"Authorization": "Bearer " + credential} if credential else {}
    assert client.get("/internal/worker/status", headers=headers).status_code == 401
    assert (
        client.post(
            "/internal/worker/resume",
            headers=headers,
            json=resume_command().model_dump(mode="json"),
        ).status_code
        == 401
    )
    assert not control.status().paused and counts(worker.engine) == (0, 0, 0)


@pytest.mark.integration
def test_operator_demo_csrf_agent_separation_and_live_openapi(ops):
    _, _, control, client, _ = ops
    assert client.get("/api/v1/dashboard").status_code == 401
    for key in ("demo-manager", "demo-technician-a"):
        headers = login(client, key)
        assert client.get("/app/dashboard").status_code == 403
        assert (
            client.post(
                "/demo/worker/pause", json={"expected_generation": 0}, headers=headers
            ).status_code
            == 403
        )
    headers = operator(client)
    assert client.get("/api/v1/dashboard").status_code == 200
    assert client.post("/demo/worker/pause", json={"expected_generation": 0}).status_code == 403
    assert (
        client.post(
            "/demo/worker/pause", json={"expected_generation": 0}, headers=headers
        ).status_code
        == 200
    )
    recovery = {"Authorization": "Bearer " + RECOVERY_SECRET}
    response = client.post(
        "/internal/worker/resume", json=resume_command().model_dump(mode="json"), headers=recovery
    )
    assert response.status_code == 200 and not control.status().paused
    result = response.json()
    conflict = client.post(
        "/internal/worker/resume",
        headers=recovery,
        json={
            "idempotency_key": result["idempotency_key"],
            "incident_id": str(uuid4()),
            "expected_generation": 1,
        },
    )
    assert (
        conflict.status_code == 409 and conflict.json()["error"]["code"] == "idempotency_conflict"
    )
    client.app.state.settings.demo_mode = False
    assert (
        client.post(
            "/demo/worker/pause", json={"expected_generation": 1}, headers=headers
        ).status_code
        == 404
    )
    assert (
        client.get("/internal/alerts", headers=recovery).status_code == 404
    )  # Future T10 receiver absent.
    schema = client.get("/openapi.json").json()
    conflicts = schema["paths"]["/internal/worker/resume"]["post"]["responses"]["409"]
    assert len(conflicts["content"]["application/json"]["schema"]["anyOf"]) == 2
    assert schema["paths"]["/internal/worker/resume"]["post"]["security"] == [
        {"RecoveryBearer": []}
    ]
    assert schema["paths"]["/demo/worker/pause"]["post"]["security"] == [
        {"PersonaSession": [], "CSRFToken": []}
    ]


@pytest.mark.integration
def test_migration_reapply_retains_business_data_and_worker_restart_identity(ops):
    worker, service, control, _, settings = ops
    job = service.create(MANAGER, InterventionCreate(title="Survives migration", site="Demo"))
    worker.run_once()
    first = worker.instance_id
    restarted = OutboxWorker(worker.engine)
    restarted.run_once()
    assert restarted.instance_id != first and control.status().fresh_instances == 2
    config = Config("alembic.ini")
    config.attributes["settings"] = settings
    command.downgrade(config, "0002_t03_review")
    command.upgrade(config, "head")
    assert service.detail(MANAGER, job.id).title == "Survives migration"
    with worker.engine.connect() as connection:
        assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []


@pytest.mark.integration
def test_database_rejects_extended_pause_and_audit_rewrites(ops):
    worker, _, control, _, _ = ops
    control.pause(OPERATOR, PauseRequest(expected_generation=0))
    with pytest.raises(DBAPIError), worker.engine.begin() as connection:
        connection.execute(
            text("UPDATE worker_control SET expires_at=effective_at+interval '601 seconds'")
        )
    control.resume(resume_command())
    for table in ("worker_control_audit", "worker_resume_actions"):
        with pytest.raises(DBAPIError), worker.engine.begin() as connection:
            connection.execute(text(f"DELETE FROM {table}"))


@pytest.mark.integration
def test_stale_or_repeated_pause_cannot_extend_generation_deadline(ops):
    worker, _, control, _, _ = ops
    initial = control.pause(OPERATOR, PauseRequest(expected_generation=0))
    for generation, code in [(0, "generation_mismatch"), (1, "already_paused")]:
        with pytest.raises(DomainError) as error:
            control.pause(OPERATOR, PauseRequest(expected_generation=generation))
        assert error.value.code == code
        current = control.status()
        assert current.generation == initial.generation and current.expires_at == initial.expires_at
    assert counts(worker.engine) == (0, 3, 0)


@pytest.mark.integration
def test_agent_bearer_never_grants_operator_or_browser_permissions(ops):
    _, _, control, client, _ = ops
    headers = {"Authorization": "Bearer " + RECOVERY_SECRET}
    assert client.get("/internal/worker/status", headers=headers).status_code == 200
    assert client.get("/api/v1/dashboard", headers=headers).status_code == 401
    assert (
        client.post(
            "/demo/worker/pause", json={"expected_generation": 0}, headers=headers
        ).status_code
        == 401
    )
    assert not control.status().paused


@pytest.mark.integration
def test_control_connection_loss_rolls_back_and_recovers(ops):
    worker, _, control, _, _ = ops
    armed = [True]

    def terminate(connection, cursor, statement, parameters, context, executemany):
        if armed[0] and "FROM worker_control" in statement and "FOR UPDATE" in statement:
            armed[0] = False
            pid = connection.exec_driver_sql("SELECT pg_backend_pid()").scalar_one()
            with worker.engine.connect() as killer:
                killer.execute(text("SELECT pg_terminate_backend(:pid)"), {"pid": pid})

    event.listen(worker.engine, "before_cursor_execute", terminate)
    try:
        with pytest.raises(DBAPIError):
            control.pause(OPERATOR, PauseRequest(expected_generation=0))
    finally:
        event.remove(worker.engine, "before_cursor_execute", terminate)
    assert not control.status().paused and counts(worker.engine) == (0, 0, 0)
    assert control.pause(OPERATOR, PauseRequest(expected_generation=0)).paused


@pytest.mark.parametrize("generation", [0, -1, True, "1"])
def test_resume_contract_requires_positive_strict_generation(generation):
    with pytest.raises(ValidationError):
        ResumeRequest(incident_id=uuid4(), idempotency_key=uuid4(), expected_generation=generation)


@pytest.mark.parametrize(
    "operator,recovery",
    [
        ("same-synthetic-key-32-characters-long", "same-synthetic-key-32-characters-long"),
        (OPERATOR_SECRET, "weak"),
        (None, ""),
    ],
)
def test_credentials_fail_closed_on_reuse_or_weak_recovery(operator, recovery):
    with pytest.raises(ValidationError):
        Settings(
            db_password=SecretStr("synthetic-only"),
            operator_secret=operator,
            recovery_secret=recovery,
        )


@pytest.mark.parametrize("name", ["operator", "recovery"])
def test_control_file_and_explicit_empty_inline_source_are_ambiguous(tmp_path, name):
    path = tmp_path / "synthetic-control"
    path.write_text("synthetic-file-key-at-least-32-characters", encoding="utf-8")
    with pytest.raises(ValidationError, match="Configure only one control credential source"):
        Settings(
            db_password=SecretStr("synthetic-only"),
            **{
                name + "_secret": "",
                name + "_secret_file": path,
            },
        )


@pytest.mark.integration
def test_expiry_reconciles_without_manufacturing_worker_heartbeat(ops):
    _, _, control, _, _ = ops
    control.pause(OPERATOR, PauseRequest(expected_generation=0, duration_seconds=1))
    deadline = time.monotonic() + 3
    while control.status().paused and time.monotonic() < deadline:
        time.sleep(0.02)
    state = control.status()
    assert not state.paused and state.heartbeat_state == "missing" and state.generation == 1
    assert control.dashboard(OPERATOR).worker.heartbeat_state == "missing"
