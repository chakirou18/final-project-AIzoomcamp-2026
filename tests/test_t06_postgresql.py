"""Real PostgreSQL claims, leases, COMMIT failures, hard process crashes and inbox scope."""

import json
import os
import platform
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event, Thread
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import event, func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from fieldops.bootstrap import migrate, seed
from fieldops.database import create_database_engine
from fieldops.main import create_app
from fieldops.models import Notification, NotificationOutbox
from fieldops.schemas import Assignment, InterventionCreate
from fieldops.seed import persona_id
from fieldops.services.interventions import InterventionService
from fieldops.trace_context import TraceContext
from fieldops.worker import Claim, OutboxWorker

pytestmark = pytest.mark.integration
MANAGER = persona_id("demo-manager")
A = persona_id("demo-technician-a")
B = persona_id("demo-technician-b")
PARENT = "00-0123456789abcdef0123456789abcdef-0123456789abcdef-01"


@pytest.fixture
def queue(pg_settings):
    # Fresh DB per case: no draining, resetting or modifying an existing application queue.
    name = "fieldops_t06_" + uuid4().hex + "_test"
    base = create_database_engine(pg_settings)
    try:
        with base.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            conn.exec_driver_sql(f'CREATE DATABASE "{name}"')
    finally:
        base.dispose()
    settings = pg_settings.model_copy(
        update={
            "db_name": name,
            "demo_mode": True,
            "session_secret_file": None,
            "session_secret": SecretStr("synthetic-t06-session-signing-key-only"),
        }
    )
    migrate(settings)
    seed(settings)
    engine = create_database_engine(settings)
    try:
        yield OutboxWorker(engine), InterventionService(engine), settings
    finally:
        engine.dispose()  # Retain the database and its evidence; never DROP DATABASE.


def assignment(queue, context=None):
    worker, service, _ = queue
    job = service.create(
        MANAGER,
        InterventionCreate(title="Synthetic delivery", site="Demo site", technician_id=A),
        context,
    )
    with Session(worker.engine) as db:
        identifier = db.scalar(
            select(NotificationOutbox.id).where(NotificationOutbox.intervention_id == job.id)
        )
    return job, identifier


def snapshot(worker, identifier):
    with Session(worker.engine) as db:
        item = db.get(NotificationOutbox, identifier)
        notification = db.scalar(select(Notification).where(Notification.outbox_id == identifier))
        return {
            "status": item.status,
            "attempts": item.attempts,
            "token": item.lease_token,
            "lease_until": item.lease_until,
            "error": item.last_error,
            "available": item.available_at,
            "delivered": item.delivered_at,
            "inbox": notification.id if notification else None,
            "inbox_delivered": notification.delivered_at if notification else None,
        }


def expire(worker, identifier):
    with worker.engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE notification_outbox "
                "SET lease_until=clock_timestamp()-interval '1s' WHERE id=:id"
            ),
            {"id": identifier},
        )


def ready(worker, identifier):
    with worker.engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE notification_outbox "
                "SET available_at=clock_timestamp()-interval '1s' WHERE id=:id"
            ),
            {"id": identifier},
        )


@pytest.mark.parametrize(
    "context", [TraceContext.parse(PARENT, "fieldops=0123456789abcdef"), TraceContext()]
)
def test_normal_delivery_and_duplicate_completion(queue, context):
    worker, _, _ = queue
    job, identifier = assignment(queue, context)
    (claim,) = worker.claim()
    assert claim.context == context
    assert snapshot(worker, identifier)["attempts"] == 1
    assert worker.deliver(claim)
    assert not worker.deliver(claim) and not worker.fail(claim)
    state = snapshot(worker, identifier)
    assert state["status"] == "delivered" and state["inbox"]
    assert state["delivered"] == state["inbox_delivered"]
    assert state["token"] is state["lease_until"] is None
    with Session(worker.engine) as db:
        row = db.get(Notification, state["inbox"])
        assert (row.recipient_id, row.intervention_id, row.assignment_version) == (A, job.id, 1)
        assert row.read_at is None


def test_skip_locked_claims_other_rows(queue):
    worker, _, _ = queue
    _, locked = assignment(queue)
    _, unlocked = assignment(queue)
    with Session(worker.engine) as db, db.begin():
        db.scalar(
            select(NotificationOutbox).where(NotificationOutbox.id == locked).with_for_update()
        )
        claims = worker.claim()
        assert [claim.event_id for claim in claims] == [unlocked]
    assert [claim.event_id for claim in worker.claim()] == [locked]


def test_three_concurrent_workers_and_duplicate_insertion(queue):
    worker, _, _ = queue
    ids = {assignment(queue)[1] for _ in range(20)}
    barrier = Barrier(3)

    def claim_batch(_):
        barrier.wait(timeout=10)
        return OutboxWorker(worker.engine).claim()

    with ThreadPoolExecutor(max_workers=3) as pool:
        batches = list(pool.map(claim_batch, range(3)))
    claims = [claim for batch in batches for claim in batch]
    assert len(claims) == len({claim.event_id for claim in claims}) == 20
    assert {claim.event_id for claim in claims} == ids
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert all(pool.map(worker.deliver, claims))
        assert not any(pool.map(worker.deliver, claims * 2))
    for identifier in ids:
        assert snapshot(worker, identifier)["attempts"] == 1
    with Session(worker.engine) as db:
        assert db.scalar(select(func.count()).select_from(Notification)) == 20


def test_expiration_and_token_fencing(queue):
    worker, _, _ = queue
    _, identifier = assignment(queue)
    (first,) = worker.claim()
    assert not worker.deliver(Claim(identifier, uuid4(), TraceContext()))
    expire(worker, identifier)
    assert not worker.deliver(first) and not worker.fail(first)
    (second,) = worker.claim()
    assert first.token != second.token
    assert snapshot(worker, identifier)["attempts"] == 2
    assert not worker.deliver(first) and not worker.fail(first)
    assert worker.deliver(second)


@pytest.mark.parametrize("mode", ["expiry", "failure"])
def test_every_claim_consumes_five_attempt_limit(queue, mode):
    worker, _, _ = queue
    _, identifier = assignment(queue)
    for attempt in range(1, 6):
        (claim,) = worker.claim()
        state = snapshot(worker, identifier)
        assert state["attempts"] == attempt and state["token"] == claim.token
        if mode == "expiry":
            expire(worker, identifier)
        else:
            assert worker.fail(claim)
            if attempt < 5:
                assert not worker.claim()  # Backoff applies, not immediate tight-loop reclaim.
                assert snapshot(worker, identifier)["available"] > state["available"]
                ready(worker, identifier)
    assert worker.claim() == []
    assert worker.claim() == []
    state = snapshot(worker, identifier)
    assert state["status"] == "failed" and state["attempts"] == 5
    assert state["inbox"] is state["delivered"] is state["token"] is state["lease_until"] is None
    with Session(worker.engine) as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(NotificationOutbox)
                .where(NotificationOutbox.status.in_(["pending", "processing", "failed"]))
            )
            == 1
        )


def test_preexisting_inbox_is_reconciled_without_duplicate(queue):
    worker, _, _ = queue
    job, identifier = assignment(queue)
    with Session(worker.engine) as db, db.begin():
        db.add(
            Notification(
                outbox_id=identifier, recipient_id=A, intervention_id=job.id, assignment_version=1
            )
        )
    (claim,) = worker.claim()
    assert worker.deliver(claim)
    with Session(worker.engine) as db:
        assert db.scalar(select(func.count()).select_from(Notification)) == 1
    assert (
        snapshot(worker, identifier)["delivered"] == snapshot(worker, identifier)["inbox_delivered"]
    )


@pytest.mark.parametrize(
    "table,phase",
    [
        ("notifications", "BEFORE INSERT"),
        ("notifications", "AFTER INSERT"),
        ("notification_outbox", "AFTER UPDATE"),
    ],
)
def test_database_rejection_rolls_back_inbox_and_ack(queue, table, phase):
    worker, _, _ = queue
    _, identifier = assignment(queue)
    (claim,) = worker.claim()
    before = snapshot(worker, identifier)
    with worker.engine.begin() as conn:
        conn.exec_driver_sql("""CREATE FUNCTION t06_reject() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'synthetic delivery failure'; END $$""")
        if phase.startswith("AFTER"):
            conn.exec_driver_sql(f"""CREATE CONSTRAINT TRIGGER t06_reject {phase} ON {table}
                DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION t06_reject()""")
        else:
            conn.exec_driver_sql(
                f"CREATE TRIGGER t06_reject {phase} ON {table} "
                "FOR EACH ROW EXECUTE FUNCTION t06_reject()"
            )
    try:
        with pytest.raises(DBAPIError) as error:
            worker.deliver(claim)
        assert error.value.orig.sqlstate == "P0001"
        assert snapshot(worker, identifier) == before
    finally:
        with worker.engine.begin() as conn:
            conn.exec_driver_sql(f"DROP TRIGGER t06_reject ON {table}")
            conn.exec_driver_sql("DROP FUNCTION t06_reject()")
    assert worker.fail(claim)
    ready(worker, identifier)
    (retry,) = worker.claim()
    assert worker.deliver(retry)
    assert snapshot(worker, identifier)["attempts"] == 2


def test_expiry_during_insert_rolls_back_materialization(queue):
    worker, _, _ = queue
    _, identifier = assignment(queue)
    (claim,) = worker.claim()
    invoked = []

    def expire_inside_transaction(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO notifications"):
            invoked.append(True)
            conn.execute(
                text(
                    "UPDATE notification_outbox "
                    "SET lease_until=clock_timestamp()-interval '1s' WHERE id=:id"
                ),
                {"id": identifier},
            )

    event.listen(worker.engine, "after_cursor_execute", expire_inside_transaction)
    try:
        assert not worker.deliver(claim)
    finally:
        event.remove(worker.engine, "after_cursor_execute", expire_inside_transaction)
    assert invoked and snapshot(worker, identifier)["inbox"] is None
    assert snapshot(worker, identifier)["status"] == "processing"
    assert worker.deliver(claim)  # Expiry fault and partial insert were rolled back together.


@pytest.mark.parametrize("phase", ["before", "after"])
def test_hard_worker_crash_and_restart(queue, phase):
    worker, _, settings = queue
    _, identifier = assignment(queue)
    code = """
import os, sys
from sqlalchemy import event
from fieldops.database import create_database_engine
from fieldops.settings import Settings
from fieldops.worker import OutboxWorker
engine = create_database_engine(Settings())
worker = OutboxWorker(engine)
claim, = worker.claim()
def crash(conn, cursor, statement, parameters, context, executemany):
    if statement.startswith("INSERT INTO notifications"):
        os._exit(81)
if sys.argv[1] == "before":
    event.listen(engine, "after_cursor_execute", crash)
assert worker.deliver(claim)
os._exit(82)
"""
    env = {**os.environ, "FIELDOPS_DB_NAME": settings.db_name}
    result = subprocess.run(
        [sys.executable, "-c", code, phase], env=env, capture_output=True, timeout=15
    )
    assert result.returncode == (81 if phase == "before" else 82)
    if phase == "before":
        assert snapshot(worker, identifier)["inbox"] is None
        assert snapshot(worker, identifier)["status"] == "processing"
        expire(worker, identifier)
    other = create_database_engine(settings)
    try:
        restarted = OutboxWorker(other)
        assert restarted.run_once() == (1 if phase == "before" else 0)
        assert restarted.run_once() == 0
    finally:
        other.dispose()
    assert snapshot(worker, identifier)["status"] == "delivered"
    with Session(worker.engine) as db:
        assert db.scalar(select(func.count()).select_from(Notification)) == 1


def test_invalid_stored_context_does_not_block_delivery(queue):
    worker, _, _ = queue
    _, identifier = assignment(queue)
    with worker.engine.begin() as conn:
        conn.execute(
            text("UPDATE notification_outbox SET traceparent=:p,tracestate=:s WHERE id=:id"),
            {"p": "invalid-user-text", "s": "untrusted=discard", "id": identifier},
        )
    (claim,) = worker.claim()
    assert claim.context == TraceContext()
    assert worker.deliver(claim)


def test_invalid_context_from_non_http_adapter_does_not_block_assignment(queue):
    worker, _, _ = queue
    _, identifier = assignment(queue, TraceContext("invalid" * 100, "secret=" + "x" * 1000))
    with Session(worker.engine) as db:
        row = db.get(NotificationOutbox, identifier)
        assert row.traceparent is row.tracestate is None
    assert worker.run_once() == 1


def test_twenty_assignment_timing_with_one_worker(queue):
    worker, _, _ = queue
    start = time.monotonic()
    ids = [assignment(queue)[1] for _ in range(20)]
    stop = Event()
    thread = Thread(target=worker.run, args=(stop,), daemon=True)
    thread.start()
    try:
        while time.monotonic() - start < 10:
            with Session(worker.engine) as db:
                if db.scalar(select(func.count()).select_from(Notification)) == 20:
                    break
            stop.wait(0.02)
        else:
            pytest.fail("20 assignments not visible within ten seconds")
    finally:
        stop.set()
        thread.join(timeout=5)
    assert not thread.is_alive()
    with Session(worker.engine) as db:
        latencies = db.execute(
            select(
                Notification.outbox_id,
                func.extract("epoch", Notification.delivered_at - NotificationOutbox.created_at),
            ).join(NotificationOutbox, NotificationOutbox.id == Notification.outbox_id)
        ).all()
    assert {row[0] for row in latencies} == set(ids)
    seconds = [float(row[1]) for row in latencies]
    assert min(seconds) >= 0 and max(seconds) < 10
    print(
        "T06_BENCHMARK "
        + json.dumps(
            {
                "count": 20,
                "workers": 1,
                "poll_seconds": 2,
                "minimum_seconds": min(seconds),
                "maximum_seconds": max(seconds),
                "mean_seconds": sum(seconds) / 20,
                "observed_total_seconds": time.monotonic() - start,
                "platform": platform.platform(),
                "python": platform.python_version(),
            }
        )
    )


def login(client, key):
    csrf = client.get("/auth/csrf").json()["csrf_token"]
    response = client.post(
        "/auth/login", headers={"X-CSRF-Token": csrf}, json={"persona_id": str(persona_id(key))}
    )
    assert response.status_code == 200
    return {"X-CSRF-Token": response.json()["csrf_token"]}


def test_json_inbox_recipient_scope_history_and_mark_read(queue):
    worker, service, settings = queue
    job, _ = assignment(queue)
    assert worker.run_once() == 1
    with TestClient(create_app(settings)) as client:
        path = "/api/v1/notifications"
        assert client.get(path).status_code == 401
        headers = login(client, "demo-technician-a")
        page = client.get(path).json()
        assert page["total"] == 1 and not page["items"][0]["historical_assignment"]
        item = page["items"][0]
        url = path + "/" + item["id"] + "/read"
        assert client.post(url).status_code == 403
        assert client.post(url, headers=headers).status_code == 204
        read = client.get(path).json()["items"][0]["read_at"]
        assert read is not None
        assert client.post(url, headers=headers).status_code == 204
        assert client.get(path).json()["items"][0]["read_at"] == read
        service.assign(MANAGER, job.id, Assignment(expected_version=1, technician_id=B))
        assert worker.run_once() == 1
        historical = client.get(path).json()["items"][0]
        assert historical["historical_assignment"] and historical["summary"] == item["summary"]
        assert client.get(f"/api/v1/interventions/{job.id}").status_code == 403
        headers = login(client, "demo-technician-b")
        assert client.get(path).json()["total"] == 1
        assert client.post(url, headers=headers).status_code == 403
        assert client.get(path + "?page_size=101").status_code == 422
        assert client.get(path + "?page=" + "9" * 30).json()["items"] == []
        headers = login(client, "demo-manager")
        assert client.get(path).status_code == client.post(url, headers=headers).status_code == 403
    # Session/engine boundaries do not lose delivered/read state.
    other = create_database_engine(settings)
    try:
        with Session(other) as db:
            assert db.scalar(select(Notification.read_at).where(Notification.id == item["id"]))
    finally:
        other.dispose()


def test_database_connection_loss_recovers_in_worker_loop(queue):
    worker, _, _ = queue
    _, identifier = assignment(queue)
    killed = []

    def disconnect(conn, cursor, statement, parameters, context, executemany):
        if (
            not killed
            and statement.startswith("UPDATE notification_outbox")
            and isinstance(parameters, dict)
            and parameters.get("status") == "delivered"
        ):
            killed.append(True)
            pid = conn.scalar(text("SELECT pg_backend_pid()"))
            with worker.engine.begin() as control:
                assert control.scalar(text("SELECT pg_terminate_backend(:pid)"), {"pid": pid})

    event.listen(worker.engine, "before_cursor_execute", disconnect)
    stop = Event()
    thread = Thread(target=worker.run, args=(stop,), daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if snapshot(worker, identifier)["status"] == "delivered":
                break
            stop.wait(0.05)
        else:
            pytest.fail("Worker did not recover from terminated PostgreSQL connection")
    finally:
        stop.set()
        thread.join(timeout=5)
        event.remove(worker.engine, "before_cursor_execute", disconnect)
    assert killed and not thread.is_alive()
    assert snapshot(worker, identifier)["attempts"] == 2


def test_failed_claim_commit_does_not_consume_attempt(queue):
    worker, _, _ = queue
    _, identifier = assignment(queue)
    with worker.engine.begin() as conn:
        conn.exec_driver_sql("""CREATE FUNCTION t06_claim_reject() RETURNS trigger
            LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'synthetic claim failure'; END $$""")
        conn.exec_driver_sql("""CREATE CONSTRAINT TRIGGER t06_claim_reject
            AFTER UPDATE ON notification_outbox
            DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION t06_claim_reject()""")
    try:
        with pytest.raises(DBAPIError):
            worker.claim()
        state = snapshot(worker, identifier)
        assert state["status"] == "pending" and state["attempts"] == 0 and state["token"] is None
    finally:
        with worker.engine.begin() as conn:
            conn.exec_driver_sql("DROP TRIGGER t06_claim_reject ON notification_outbox")
            conn.exec_driver_sql("DROP FUNCTION t06_claim_reject()")
    assert worker.run_once() == 1


def test_real_poison_event_retry_loop_and_redacted_error(queue, caplog):
    worker, _, _ = queue
    _, identifier = assignment(queue)
    with worker.engine.begin() as conn:
        conn.exec_driver_sql("""CREATE FUNCTION t06_poison() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'SYNTHETIC-DO-NOT-LOG'; END $$""")
        conn.exec_driver_sql("""CREATE TRIGGER t06_poison BEFORE INSERT ON notifications
            FOR EACH ROW EXECUTE FUNCTION t06_poison()""")
    try:
        for attempt in range(1, 6):
            assert worker.run_once() == 0
            state = snapshot(worker, identifier)
            assert state["attempts"] == attempt and state["inbox"] is None
            assert state["error"] == "delivery_failed"
            if attempt < 5:
                assert worker.claim() == []
                ready(worker, identifier)
        assert snapshot(worker, identifier)["status"] == "failed"
        assert worker.run_once() == 0
    finally:
        with worker.engine.begin() as conn:
            conn.exec_driver_sql("DROP TRIGGER t06_poison ON notifications")
            conn.exec_driver_sql("DROP FUNCTION t06_poison()")
    assert "SYNTHETIC-DO-NOT-LOG" not in " ".join(record.getMessage() for record in caplog.records)
    assert sum(record.getMessage() == "delivery_failed" for record in caplog.records) == 5


@pytest.mark.parametrize(
    "parent,state,expected",
    [
        (PARENT, "fieldops=0123456789abcdef", TraceContext(PARENT, "fieldops=0123456789abcdef")),
        ("invalid-user-text", "secret=discard", TraceContext()),
    ],
)
def test_http_trace_carrier_persists_only_allowed_context(queue, parent, state, expected):
    worker, _, settings = queue
    with TestClient(create_app(settings)) as client:
        headers = login(client, "demo-manager")
        headers.update(traceparent=parent, tracestate=state)
        response = client.post(
            "/api/v1/interventions",
            headers=headers,
            json={
                "title": "Synthetic traced assignment",
                "site": "Demo",
                "technician_id": str(A),
            },
        )
        assert response.status_code == 201
        (claim,) = worker.claim()
        with Session(worker.engine) as db:
            row = db.get(NotificationOutbox, claim.event_id)
            assert (row.traceparent, row.tracestate) == (expected.traceparent, expected.tracestate)
        assert claim.context == expected and worker.deliver(claim)
