"""Real monitoring and action integration, with an explicitly labeled mock diagnosis."""

import json
import os
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from observability_tests.test_stack import (
    DATABASE,
    PROJECT,
    Client,
    assign,
    compose,
    correlation,
    metrics,
    persisted,
    secret,
    sql,
    wait,
)


def test_live_alert_operator_grant_resume_and_restart_verification():
    if os.getenv("FIELDOPS_RUN_AGENT_TESTS") != "1":
        pytest.skip("Explicit synthetic T11 opt-in required")
    assert PROJECT == "fieldops-t09" and DATABASE == "fieldops_t09_demo_test"
    directory = Path("artifacts") / ("t11-live-" + uuid4().hex)
    directory.mkdir()
    operator = Client("demo-operator")
    worker = operator.request("/api/v1/dashboard")[1]["worker"]
    assert worker["heartbeat_state"] == "fresh" and not worker["paused"]
    assert metrics()[0]["fieldops_notifications_undelivered"] == 0
    previous = {row["id"] for row in operator.request("/api/v1/incidents")[1]}
    compose("stop", "--timeout", "-1", "oncall-agent")
    command = [
        "docker",
        "compose",
        "--project-name",
        PROJECT,
        "--profile",
        "observability",
        "--profile",
        "incident",
        "run",
        "--rm",
        "--no-deps",
        "-v",
        str(Path("fieldops").resolve()) + ":/app/fieldops:ro",
        "-v",
        str(Path("agent_tests/mock_processor.py").resolve()) + ":/app/mock_processor.py:ro",
        "oncall-agent",
        "python",
        "/app/mock_processor.py",
    ]
    children = []
    handles = []
    generation = None
    environment = {**os.environ, "COMPOSE_PROJECT_NAME": PROJECT, "POSTGRES_DB": DATABASE}
    for key, value in {
        "FIELDOPS_SUBNET": "10.254.9.0/24",
        "FIELDOPS_PORT": "18009",
        "FIELDOPS_GRAFANA_PORT": "13009",
        "FIELDOPS_JAEGER_PORT": "16689",
    }.items():
        environment.setdefault(key, value)
    try:
        status, paused = operator.request(
            "/demo/worker/pause",
            {"expected_generation": worker["generation"], "duration_seconds": 240},
        )
        assert status == 200 and paused["paused"]
        generation = paused["generation"]
        started = time.monotonic()
        at = datetime.now(UTC).isoformat()
        row = assign("T11-live-mock")
        assert persisted(row["id"])["inbox_count"] == 0
        incident = wait(
            lambda: next(
                (
                    item
                    for item in operator.request("/api/v1/incidents")[1]
                    if item["id"] not in previous
                    and item["alert_name"] == "NotificationQueueDelayed"
                ),
                None,
            ),
            timeout=110 - (time.monotonic() - started),
        )
        observed = time.monotonic() - started
        assert 60 < observed <= 110 and persisted(row["id"])["inbox_count"] == 0
        handle = (directory / "first-process.log").open("w")
        handles.append(handle)
        first = subprocess.Popen(
            command + [incident["id"], "VERIFYING"],
            stdout=handle,
            stderr=subprocess.STDOUT,
            env=environment,
        )
        children.append(first)
        detail_path = "/api/v1/incidents/" + incident["id"]
        diagnosis = wait(
            lambda: (
                data if (data := operator.request(detail_path)[1])["state"] == "DIAGNOSED" else None
            ),
            timeout=40,
        )
        assert diagnosis["affected"] == [row["id"]]
        agent_containers = subprocess.run(
            [
                "docker",
                "ps",
                "--filter",
                "label=com.docker.compose.service=oncall-agent",
                "--filter",
                "label=com.docker.compose.project=" + PROJECT,
                "--format",
                "{{.ID}}",
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        ).stdout.splitlines()
        resources = subprocess.run(
            [
                "docker",
                "stats",
                "--no-stream",
                "--format",
                "{{json .}}",
                "fieldops-t09-web-1",
                "fieldops-t09-alert-receiver-1",
                *agent_containers,
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        ).stdout
        grant_status, grant = operator.request(
            detail_path + "/authorize", {"expected_generation": generation}
        )
        assert grant_status == 200
        assert first.wait(timeout=40) == 0
        mid = operator.request(detail_path)[1]
        assert mid["state"] == "VERIFYING"
        # A fresh process opens the same durable state and key. No second action is sent.
        with (directory / "second-process.log").open("w") as second_log:
            result = subprocess.run(
                command + [incident["id"], "RESOLVED"],
                stdout=second_log,
                stderr=subprocess.STDOUT,
                timeout=40,
                check=False,
                env=environment,
            )
        assert result.returncode == 0
        final = operator.request(detail_path)[1]
        assert final["state"] == "RESOLVED" and final["verification"]["ok"] is True
        delivered = persisted(row["id"])
        assert delivered["status"] == "delivered" and delivered["inbox_count"] == 1
        actions = json.loads(
            sql(
                "SELECT json_build_object('count',count(*),'success',bool_and(success)) "
                "FROM worker_resume_actions WHERE incident_id='" + str(UUID(incident["id"])) + "'"
            )
        )
        assert actions == {"count": 1, "success": True}
        import observability_tests.test_stack as stack

        stack.EVIDENCE = directory
        correlation(row)
        (directory / "evidence.json").write_text(
            json.dumps(
                {
                    "provider": "deterministic-test-only",
                    "real_model": False,
                    "request_started_at": at,
                    "observed_intake_seconds": observed,
                    "pause_ack": paused,
                    "outbox": row,
                    "incident": final,
                    "grant": grant,
                    "action_result": actions,
                    "delivery": delivered,
                    "processor_restart": True,
                    "resource_sample": [json.loads(line) for line in resources.splitlines()],
                },
                indent=2,
            )
        )
        print("T11_MOCK_LIVE_EVIDENCE", directory)
    finally:
        for child in children:
            if child.poll() is None:
                child.wait(timeout=170)
        for handle in handles:
            handle.close()
        state = operator.request("/api/v1/dashboard")[1]["worker"]
        if generation and state["paused"] and state["generation"] == generation:
            operator.request(
                "/internal/worker/resume",
                {
                    "incident_id": str(uuid4()),
                    "expected_generation": generation,
                    "idempotency_key": str(uuid4()),
                },
                headers={"Authorization": "Bearer " + secret("recovery_key")},
            )
        compose("start", "oncall-agent")
