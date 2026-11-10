"""Independent reliability audit using separate OS processes and observable PostgreSQL locks."""

import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier, Event
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import event, func, select, text
from sqlalchemy.orm import Session
from test_t06_postgresql import assignment, expire, login, ready, snapshot
from test_t06_postgresql import queue as queue

from fieldops.auth import COOKIE, digest
from fieldops.main import create_app
from fieldops.models import Notification, NotificationOutbox, PersonaSession
from fieldops.schemas import InterventionCreate
from fieldops.seed import persona_id
from fieldops.trace_context import TraceContext
from fieldops.worker import Claim

pytestmark = pytest.mark.integration


def test_three_worker_processes_claim_and_deliver_disjoint_batches(queue):
    worker, _, settings = queue
    identifiers = {assignment(queue)[1] for _ in range(60)}
    code = """
import json, os, sys
from fieldops.database import create_database_engine
from fieldops.settings import Settings
from fieldops.worker import OutboxWorker
engine = create_database_engine(Settings())
worker = OutboxWorker(engine)
assert sys.stdin.readline().strip() == "claim"
claims = worker.claim()
print(json.dumps({"pid":os.getpid(),
    "claims":[[str(c.event_id),str(c.token)] for c in claims]}), flush=True)
assert sys.stdin.readline().strip() == "deliver"
print(json.dumps({"delivered":sum(worker.deliver(c) for c in claims)}), flush=True)
engine.dispose()
"""
    processes = []
    try:
        for _ in range(3):
            processes.append(
                subprocess.Popen(
                    [sys.executable, "-c", code],
                    env={**os.environ, "FIELDOPS_DB_NAME": settings.db_name},
                    text=True,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
            )
        for process in processes:
            process.stdin.write("claim\n")
            process.stdin.flush()
        reader = ThreadPoolExecutor(max_workers=3)
        try:
            results = [
                future.result(timeout=15)
                for future in [reader.submit(process.stdout.readline) for process in processes]
            ]
        finally:
            reader.shutdown(wait=False, cancel_futures=True)
        batches = [json.loads(result) for result in results]
        assert len({batch["pid"] for batch in batches}) == 3
        assert [len(batch["claims"]) for batch in batches] == [20, 20, 20]
        pairs = [pair for batch in batches for pair in batch["claims"]]
        assert {UUID(pair[0]) for pair in pairs} == identifiers
        assert len({pair[1] for pair in pairs}) == 60
        with Session(worker.engine) as db:
            rows = db.scalars(select(NotificationOutbox)).all()
            assert len(rows) == 60
            assert all(row.status == "processing" and row.attempts == 1 for row in rows)
            assert db.scalar(select(func.count()).select_from(Notification)) == 0
        for process in processes:
            process.stdin.write("deliver\n")
            process.stdin.flush()
        for process in processes:
            process.wait(timeout=15)
            assert process.returncode == 0
            assert json.loads(process.stdout.readline())["delivered"] == 20
        with Session(worker.engine) as db:
            rows = db.scalars(select(Notification)).all()
            assert len(rows) == len({row.outbox_id for row in rows}) == 60
            assert {row.outbox_id for row in rows} == identifiers
            assert all(
                row.status == "delivered" and row.attempts == 1
                for row in db.scalars(select(NotificationOutbox))
            )
        for identifier, token in pairs:
            assert not worker.deliver(Claim(UUID(identifier), UUID(token), TraceContext()))
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=10)
            for stream in (process.stdin, process.stdout, process.stderr):
                stream.close()


def test_lease_expiring_during_real_lock_wait_cannot_deliver(queue):
    worker, _, _ = queue
    _, identifier = assignment(queue)
    (claim,) = worker.claim()
    entering = Event()
    pids = []

    def identify(conn, cursor, statement, parameters, context, executemany):
        if (
            statement.startswith("SELECT")
            and "FROM notification_outbox" in statement
            and "FOR UPDATE" in statement
        ):
            pids.append(conn.scalar(text("SELECT pg_backend_pid()")))
            entering.set()

    with worker.engine.connect() as holder:
        transaction = holder.begin()
        holder.execute(
            text("SELECT id FROM notification_outbox WHERE id=:id FOR UPDATE"), {"id": identifier}
        )
        event.listen(worker.engine, "before_cursor_execute", identify)
        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(worker.deliver, claim)
                try:
                    assert entering.wait(timeout=5)
                    deadline = time.monotonic() + 1.5  # Existing statement timeout is two seconds.
                    observed = False
                    while time.monotonic() < deadline:
                        with worker.engine.connect() as observer:
                            observed = observer.scalar(
                                text(
                                    "SELECT wait_event_type='Lock' FROM pg_stat_activity "
                                    "WHERE pid=:pid"
                                ),
                                {"pid": pids[0]},
                            )
                        if observed:
                            break
                    assert observed, "Delivery never reached a PostgreSQL row-lock wait"
                    holder.execute(
                        text(
                            "UPDATE notification_outbox "
                            "SET lease_until=clock_timestamp()-interval '1s' WHERE id=:id"
                        ),
                        {"id": identifier},
                    )
                finally:
                    transaction.commit()
                assert future.result(timeout=5) is False
        finally:
            event.remove(worker.engine, "before_cursor_execute", identify)
    state = snapshot(worker, identifier)
    assert state["inbox"] is None and state["attempts"] == 1
    (next_claim,) = worker.claim()
    assert next_claim.token != claim.token and worker.deliver(next_claim)
    assert snapshot(worker, identifier)["attempts"] == 2


@pytest.mark.parametrize("session_state", ["missing", "tampered", "expired", "revoked"])
def test_inbox_rejects_invalid_sessions_direct_http(queue, session_state):
    worker, _, settings = queue
    _, identifier = assignment(queue)
    assert worker.run_once() == 1
    item = snapshot(worker, identifier)["inbox"]
    with TestClient(create_app(settings)) as client:
        headers = login(client, "demo-technician-a")
        cookie = client.cookies.get(COOKIE)
        if session_state == "expired":
            with worker.engine.begin() as conn:
                conn.execute(
                    text("""UPDATE persona_sessions SET
                    created_at=clock_timestamp()-interval '2h',
                    expires_at=clock_timestamp()-interval '1s' WHERE token_digest=:digest"""),
                    {"digest": digest(cookie.split(".")[0])},
                )
        elif session_state == "revoked":
            assert client.post("/auth/logout", headers=headers).status_code == 204
        client.cookies.clear()
        if session_state != "missing":
            headers["Cookie"] = (
                COOKIE + "=" + (cookie + "bad" if session_state == "tampered" else cookie)
            )
        assert client.get("/api/v1/notifications", headers=headers).status_code == 401
        response = client.post(f"/api/v1/notifications/{item}/read", headers=headers)
        assert response.status_code == 401 and response.json()["error"]["code"] == "unauthenticated"
    with Session(worker.engine) as db:
        assert db.get(Notification, item).read_at is None
        assert db.scalar(select(func.count()).select_from(PersonaSession)) == 1


def test_two_sessions_mark_read_concurrently_and_preserve_timestamp(queue):
    worker, _, settings = queue
    _, identifier = assignment(queue)
    assert worker.run_once() == 1
    item = snapshot(worker, identifier)["inbox"]
    with TestClient(create_app(settings)) as first, TestClient(create_app(settings)) as second:
        headers = [login(first, "demo-technician-a"), login(second, "demo-technician-a")]
        url = f"/api/v1/notifications/{item}/read"
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(
                executor.map(
                    lambda index: [first, second][index].post(url, headers=headers[index]), [0, 1]
                )
            )
        assert [response.status_code for response in results] == [204, 204]
        before = first.get("/api/v1/notifications").json()["items"][0]["read_at"]
        assert before is not None
        assert first.post(url, headers=headers[0]).status_code == 204
        assert second.get("/api/v1/notifications").json()["items"][0]["read_at"] == before
        assert (
            first.post(f"/api/v1/notifications/{uuid4()}/read", headers=headers[0]).status_code
            == 404
        )


@pytest.mark.parametrize("attempt,seconds", [(1, 2), (2, 4), (3, 8), (4, 16), (5, 30)])
def test_retry_deadline_written_with_bounded_database_clock(queue, attempt, seconds):
    worker, _, _ = queue
    _, identifier = assignment(queue)
    for index in range(attempt):
        (claim,) = worker.claim()
        if index < attempt - 1:
            assert worker.fail(claim)
            ready(worker, identifier)
    with worker.engine.connect() as conn:
        before = conn.scalar(text("SELECT clock_timestamp()"))
    assert worker.fail(claim)
    state = snapshot(worker, identifier)
    with worker.engine.connect() as conn:
        after = conn.scalar(text("SELECT clock_timestamp()"))
    assert (
        before + timedelta(seconds=seconds)
        <= state["available"]
        <= after + timedelta(seconds=seconds)
    )
    assert state["attempts"] == attempt
    assert worker.claim() == []
    if attempt == 5:
        ready(worker, identifier)
        assert worker.claim() == [] and snapshot(worker, identifier)["status"] == "failed"


def test_concurrent_reclaim_cannot_create_sixth_attempt(queue):
    worker, _, _ = queue
    _, identifier = assignment(queue)
    tokens = []
    for _ in range(4):
        (claim,) = worker.claim()
        tokens.append(claim.token)
        expire(worker, identifier)

    def concurrent_claims():
        barrier = Barrier(3)

        def contender(_):
            barrier.wait(timeout=5)
            return worker.claim()

        with ThreadPoolExecutor(max_workers=3) as executor:
            return [claim for batch in executor.map(contender, range(3)) for claim in batch]

    (final,) = concurrent_claims()
    assert final.token not in tokens and snapshot(worker, identifier)["attempts"] == 5
    expire(worker, identifier)
    assert concurrent_claims() == []
    assert concurrent_claims() == []
    state = snapshot(worker, identifier)
    assert state["status"] == "failed" and state["attempts"] == 5 and state["inbox"] is None


def test_scoped_inbox_pagination_and_operator_denial(queue):
    worker, service, settings = queue
    jobs = {assignment(queue)[0].id for _ in range(26)}
    other = service.create(
        persona_id("demo-manager"),
        InterventionCreate(
            title="Synthetic other recipient",
            site="Demo",
            technician_id=persona_id("demo-technician-b"),
        ),
    )
    assert worker.run_once() == 20 and worker.run_once() == 7
    settings = settings.model_copy(
        update={"operator_secret": SecretStr("synthetic-review-operator-key-only-32")}
    )
    with TestClient(create_app(settings)) as client:
        login(client, "demo-technician-a")
        first = client.get("/api/v1/notifications").json()
        second = client.get("/api/v1/notifications?page=2").json()
        assert first["total"] == second["total"] == 26
        assert len(first["items"]) == 25 and len(second["items"]) == 1
        assert {UUID(row["intervention_id"]) for row in first["items"] + second["items"]} == jobs
        old_item = first["items"][0]["id"]
        headers = login(client, "demo-technician-b")
        page = client.get("/api/v1/notifications").json()
        assert page["total"] == 1 and page["items"][0]["intervention_id"] == str(other.id)
        assert (
            client.post(f"/api/v1/notifications/{old_item}/read", headers=headers).status_code
            == 403
        )
        csrf = client.get("/auth/csrf").json()["csrf_token"]
        response = client.post(
            "/auth/login",
            headers={"X-CSRF-Token": csrf},
            json={
                "persona_id": str(persona_id("demo-operator")),
                "operator_secret": "synthetic-review-operator-key-only-32",
            },
        )
        assert response.status_code == 200
        assert client.get("/api/v1/notifications").status_code == 403
        assert (
            client.post(
                f"/api/v1/notifications/{old_item}/read",
                headers={
                    "X-CSRF-Token": response.json()["csrf_token"],
                },
            ).status_code
            == 403
        )
