"""Independent T07 audit: distinct-key races, direct HTTP and database mutation denial."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from test_t06_postgresql import queue as queue
from test_t07 import OPERATOR, RECOVERY_SECRET, counts, operator, resume_command
from test_t07 import ops as ops

from fieldops.control_schemas import PauseRequest

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("route", ["/demo/worker/pause", "/internal/worker/resume"])
def test_generation_outside_postgresql_range_is_422_without_writes(ops, route):
    worker, _, control, client, _ = ops
    if route.endswith("pause"):
        headers = operator(client)
        body = {"expected_generation": 2**63}
    else:
        headers = {"Authorization": "Bearer " + RECOVERY_SECRET}
        body = resume_command().model_dump(mode="json")
        body["expected_generation"] = 2**63
    response = client.post(route, json=body, headers=headers)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert not control.status().paused and counts(worker.engine) == (0, 0, 0)


def test_distinct_resume_keys_cannot_produce_two_successes(ops):
    worker, _, control, _, _ = ops
    control.pause(OPERATOR, PauseRequest(expected_generation=0))
    barrier = Barrier(2)

    def invoke(_):
        barrier.wait()
        return control.resume(resume_command())

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(invoke, range(2)))
    assert sorted(result.outcome for result in results) == ["not_paused", "resumed"]
    assert sum(result.success for result in results) == 1
    assert counts(worker.engine) == (0, 3, 2)
    assert not control.status().paused


def test_wrong_generation_http_result_is_durable_and_replayed(ops):
    worker, _, control, client, _ = ops
    control.pause(OPERATOR, PauseRequest(expected_generation=0))
    command = resume_command(99).model_dump(mode="json")
    headers = {"Authorization": "Bearer " + RECOVERY_SECRET}
    first = client.post("/internal/worker/resume", json=command, headers=headers)
    replay = client.post("/internal/worker/resume", json=command, headers=headers)
    assert first.status_code == replay.status_code == 409
    assert first.json() == replay.json()
    assert first.json()["outcome"] == "generation_mismatch"
    assert not first.json()["success"] and control.status().paused
    assert counts(worker.engine) == (0, 2, 1)


@pytest.mark.parametrize("state", ["expired", "revoked"])
def test_invalidated_operator_cannot_read_or_pause_through_html_or_json(ops, state):
    worker, _, control, client, _ = ops
    headers = operator(client)
    with worker.engine.begin() as connection:
        if state == "expired":
            connection.execute(
                text(
                    "UPDATE persona_sessions SET created_at=clock_timestamp()-interval '2s', "
                    "expires_at=clock_timestamp()-interval '1s'"
                )
            )
        else:
            connection.execute(text("UPDATE persona_sessions SET revoked_at=clock_timestamp()"))
    for path in ("/app/dashboard", "/api/v1/dashboard"):
        assert client.get(path).status_code == 401
    assert (
        client.post(
            "/demo/worker/pause", json={"expected_generation": 0}, headers=headers
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/app/worker/pause",
            data={"expected_generation": 0, "csrf_token": headers["X-CSRF-Token"]},
        ).status_code
        == 401
    )
    assert not control.status().paused and counts(worker.engine) == (0, 0, 0)


def test_html_pause_csrf_and_unexpected_fields_cannot_mutate_controls(ops):
    worker, _, control, client, _ = ops
    headers = operator(client)
    assert client.post("/app/worker/pause", data={"expected_generation": 0}).status_code == 403
    assert (
        client.post(
            "/app/worker/pause",
            data={
                "expected_generation": 0,
                "csrf_token": headers["X-CSRF-Token"],
                "target": "shell",
            },
        ).status_code
        == 422
    )
    assert not control.status().paused and counts(worker.engine) == (0, 0, 0)


@pytest.mark.parametrize("table", ["worker_control_audit", "worker_resume_actions"])
def test_database_rejects_updates_to_existing_control_records(ops, table):
    worker, _, control, _, _ = ops
    control.pause(OPERATOR, PauseRequest(expected_generation=0))
    control.resume(resume_command())
    before = counts(worker.engine)
    with pytest.raises(DBAPIError), worker.engine.begin() as connection:
        connection.execute(text(f"UPDATE {table} SET outcome=outcome"))
    assert counts(worker.engine) == before
