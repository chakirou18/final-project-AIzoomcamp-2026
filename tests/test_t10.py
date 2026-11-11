"""T10 sink durability/auth boundaries; application locking stays real PostgreSQL."""

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from fieldops.alert_receiver import Webhook, create_app, persist

WRITE = "synthetic-t10-webhook-write-key-00000"
READ = "synthetic-t10-inspection-read-key-000"


def payload():
    return {
        "version": "4",
        "routeLabels": {},
        "notification_reason": "group_wait",
        "receiver": "fieldops-test-evidence",
        "status": "firing",
        "alerts": [
            {
                "status": "firing",
                "labels": {
                    "alertname": "NotificationQueueDelayed",
                    "severity": "warning",
                    "service": "fieldops-web",
                    "environment": "local",
                },
                "startsAt": "2026-11-10T00:00:00Z",
                "endsAt": "0001-01-01T00:00:00Z",
                "annotations": {"description": "SYNTHETIC-SECRET-NOT-FOR-PERSISTENCE"},
            }
        ],
    }


@pytest.fixture
def sink(tmp_path):
    path = tmp_path / "receipts.sqlite3"
    with TestClient(create_app(path, WRITE, READ)) as client:
        yield client, path


@pytest.mark.parametrize("key", [None, "invalid", READ])
def test_webhook_denies_missing_wrong_and_reader_key(sink, key):
    client, _ = sink
    response = client.post(
        "/internal/alerts",
        json=payload(),
        headers={"Authorization": "Bearer " + key} if key else {},
    )
    assert response.status_code == 401
    assert client.get("/internal/receipts", headers={"Authorization": "Bearer " + READ}).json() == {
        "receipts": []
    }


@pytest.mark.parametrize("key", [None, "invalid", WRITE])
def test_reader_denies_missing_wrong_and_webhook_key(sink, key):
    response = sink[0].get(
        "/internal/receipts", headers={"Authorization": "Bearer " + key} if key else {}
    )
    assert response.status_code == 401


def test_reader_rejects_cursor_outside_sqlite_integer_range(sink):
    client, _ = sink
    headers = {"Authorization": "Bearer " + READ}
    assert client.get(f"/internal/receipts?after_id={2**63}", headers=headers).status_code == 422
    assert client.get(f"/internal/receipts?after_id={2**63 - 1}", headers=headers).json() == {
        "receipts": []
    }


@pytest.mark.parametrize("field", ["startsAt", "endsAt"])
def test_webhook_rejects_timestamps_outside_utc_range(sink, field):
    client, _ = sink
    body = payload()
    body["alerts"][0][field] = "0001-01-01T00:00:00+01:00"
    assert (
        client.post(
            "/internal/alerts", json=body, headers={"Authorization": "Bearer " + WRITE}
        ).status_code
        == 422
    )


def test_receipt_durable_deduplicated_and_not_recovery(sink):
    client, path = sink
    headers = {"Authorization": "Bearer " + WRITE}
    for _ in range(2):
        result = client.post("/internal/alerts", json=payload(), headers=headers)
        assert result.status_code == 202 and result.json()["recovery"] == "not_attempted"
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT count(*) FROM receipts").fetchone()[0] == 1
    data = client.get("/internal/receipts", headers={"Authorization": "Bearer " + READ}).json()
    assert "SYNTHETIC-SECRET" not in json.dumps(data)
    assert datetime.fromisoformat(data["receipts"][0]["received_at"]).tzinfo == UTC
    resolved = payload()
    resolved["status"] = resolved["alerts"][0]["status"] = "resolved"
    resolved["alerts"][0]["endsAt"] = "2026-11-10T00:02:00Z"
    assert client.post("/internal/alerts", json=resolved, headers=headers).status_code == 202
    # Independent connection/process reopen sees both states; receipt resolution is not recovery.
    with TestClient(create_app(path, WRITE, READ)) as reopened:
        assert (
            len(
                reopened.get(
                    "/internal/receipts", headers={"Authorization": "Bearer " + READ}
                ).json()["receipts"]
            )
            == 2
        )


@pytest.mark.parametrize(
    "change", ["unknown_alert", "severity", "unbounded", "timestamp", "empty", "extra"]
)
def test_malformed_and_unbounded_payload_is_redacted(sink, change):
    body = payload()
    if change == "unknown_alert":
        body["alerts"][0]["labels"]["alertname"] = "SYNTHETIC-SECRET"
    if change == "severity":
        body["alerts"][0]["labels"]["severity"] = "critical"
    if change == "unbounded":
        body["alerts"][0]["labels"]["event_id"] = str(uuid4())
    if change == "timestamp":
        body["alerts"][0]["startsAt"] = "SYNTHETIC-SECRET"
    if change == "empty":
        body["alerts"] = []
    if change == "extra":
        body["shell"] = "SYNTHETIC-SECRET"
    response = sink[0].post(
        "/internal/alerts", json=body, headers={"Authorization": "Bearer " + WRITE}
    )
    assert response.status_code == 422 and "SYNTHETIC-SECRET" not in response.text


def test_size_json_and_media_type_limits(sink):
    client, _ = sink
    headers = {"Authorization": "Bearer " + WRITE, "Content-Type": "application/json"}
    assert client.post("/internal/alerts", content="x" * 65537, headers=headers).status_code == 413
    assert client.post("/internal/alerts", content="{broken", headers=headers).status_code == 422
    headers["Content-Type"] = "text/plain"
    assert client.post("/internal/alerts", content="{}", headers=headers).status_code == 415


def test_concurrent_retries_insert_once(sink):
    _, path = sink
    body = Webhook.model_validate(payload())
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: persist(path, body, None), range(8)))
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT count(*) FROM receipts").fetchone()[0] == 1


def test_storage_failure_never_acknowledges(sink):
    client, path = sink
    with sqlite3.connect(path) as db:
        db.execute("DROP TABLE receipts")
    assert (
        client.post(
            "/internal/alerts", json=payload(), headers={"Authorization": "Bearer " + WRITE}
        ).status_code
        == 503
    )


def test_capacity_fails_closed_without_partial_batch(sink, monkeypatch):
    import fieldops.alert_receiver as module

    monkeypatch.setattr(module, "MAX_ROWS", 0)
    assert (
        sink[0]
        .post("/internal/alerts", json=payload(), headers={"Authorization": "Bearer " + WRITE})
        .status_code
        == 507
    )


def test_credentials_must_be_strong_and_separate(tmp_path):
    with pytest.raises(RuntimeError):
        with TestClient(create_app(tmp_path / "evidence", WRITE, WRITE)):
            pass


@pytest.mark.integration
def test_production_demo_flag_cannot_enable_pause(ops):
    from test_t07 import operator

    _, _, _, client, settings = ops
    headers = operator(client)
    client.app.state.settings = settings.model_copy(
        update={"environment": "production", "demo_mode": True}
    )
    assert (
        client.post(
            "/demo/worker/pause", json={"expected_generation": 0}, headers=headers
        ).status_code
        == 404
    )
    dashboard = client.get("/app/dashboard")
    assert dashboard.status_code == 200
    assert 'action="/app/worker/pause"' not in dashboard.text
    assert (
        client.post(
            "/app/worker/pause",
            data={"expected_generation": 0, "csrf_token": headers["X-CSRF-Token"]},
        ).status_code
        == 404
    )


# Existing PostgreSQL ops fixture verifies real sessions/roles, not a mocked authorizer.
from test_t07 import ops as ops  # noqa: E402
from test_t07 import queue as queue  # noqa: E402
