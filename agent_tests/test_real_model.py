"""Real-provider acceptance: alert intake, genuine model diagnosis, grant, resume, verification.

Opt-in only. Requires an owner-approved existing provider reachable from the oncall-agent
container, with no purchase or download. Every model call is counted by the durable budget.
"""

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

RESERVED = (
    "SELECT count(*) FROM incident_events "
    "WHERE event_type='model_intent' AND evidence->>'provider'='ollama'"
)
COMPOSE_DEFAULTS = {
    "FIELDOPS_SUBNET": "10.254.9.0/24",
    "FIELDOPS_PORT": "18009",
    "FIELDOPS_GRAFANA_PORT": "13009",
    "FIELDOPS_JAEGER_PORT": "16689",
}


def compose_environment():
    """Render the synthetic project exactly like the shared helper, whatever the shell exported."""
    environment = {**os.environ, "COMPOSE_PROJECT_NAME": PROJECT, "POSTGRES_DB": DATABASE}
    for key, value in COMPOSE_DEFAULTS.items():
        environment.setdefault(key, value)
    return environment


def docker(*args, timeout=20):
    return subprocess.run(
        ["docker", *args], capture_output=True, text=True, check=True, timeout=timeout
    ).stdout


def test_real_model_diagnosis_grant_resume_and_positive_verification():
    if (
        os.getenv("FIELDOPS_RUN_REAL_MODEL_TESTS") != "1"
        or os.getenv("FIELDOPS_ONCALL_PROVIDER_APPROVED") != "true"
    ):
        pytest.skip("Explicit owner-approved real provider opt-in required")
    url = os.environ["FIELDOPS_ONCALL_PROVIDER_URL"]
    model = os.environ["FIELDOPS_ONCALL_MODEL"]
    timeout = os.getenv("FIELDOPS_ONCALL_PROVIDER_TIMEOUT", "30")
    budget = os.getenv("FIELDOPS_ONCALL_MAX_CALLS", "1")
    assert PROJECT == "fieldops-t09" and DATABASE == "fieldops_t09_demo_test"
    directory = Path("artifacts") / ("t11-real-" + uuid4().hex)
    directory.mkdir()
    operator = Client("demo-operator")
    worker = operator.request("/api/v1/dashboard")[1]["worker"]
    assert worker["heartbeat_state"] == "fresh" and not worker["paused"]
    assert metrics()[0]["fieldops_notifications_undelivered"] == 0
    previous = {row["id"] for row in operator.request("/api/v1/incidents")[1]}
    reserved_before = int(sql(RESERVED))
    compose("stop", "--timeout", "-1", "oncall-agent")
    name = "fieldops-t09-oncall-agent-real-" + uuid4().hex[:8]
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
        "--name",
        name,
        "-e",
        "FIELDOPS_ONCALL_PROVIDER=ollama",
        "-e",
        "FIELDOPS_ONCALL_PROVIDER_URL=" + url,
        "-e",
        "FIELDOPS_ONCALL_MODEL=" + model,
        "-e",
        "FIELDOPS_ONCALL_PROVIDER_APPROVED=true",
        "-e",
        "FIELDOPS_ONCALL_MAX_CALLS=" + budget,
        "-e",
        "FIELDOPS_ONCALL_PROVIDER_TIMEOUT=" + timeout,
        "-v",
        str(Path("fieldops").resolve()) + ":/app/fieldops:ro",
        "oncall-agent",
    ]
    log = (directory / "real-agent.log").open("w")
    runtime = subprocess.Popen(
        command, stdout=log, stderr=subprocess.STDOUT, env=compose_environment()
    )
    generation = None
    try:
        wait(
            lambda: docker("ps", "--filter", "name=" + name, "--format", "{{.ID}}").strip() or None,
            timeout=60,
        )
        time.sleep(4)  # The runtime polls every second; a misconfigured process fails at once.
        startup = (directory / "real-agent.log").read_text(encoding="utf-8", errors="replace")
        assert runtime.poll() is None and "oncall_stage_failed" not in startup, startup[-1500:]
        status, paused = operator.request(
            "/demo/worker/pause",
            {"expected_generation": worker["generation"], "duration_seconds": 240},
        )
        assert status == 200 and paused["paused"]
        generation = paused["generation"]
        started = time.monotonic()
        at = datetime.now(UTC).isoformat()
        row = assign("T11-real-model")
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
        detail_path = "/api/v1/incidents/" + incident["id"]
        diagnosed = wait(
            lambda: (
                data
                if (data := operator.request(detail_path)[1])["state"]
                not in {"RECEIVED", "DIAGNOSING"}
                else None
            ),
            timeout=90,
        )
        assert diagnosed["state"] == "DIAGNOSED", (
            diagnosed["state"],
            diagnosed["escalation_reason"],
            diagnosed["diagnosis"],
        )
        intent = next(event for event in diagnosed["events"] if event["type"] == "model_intent")
        assert intent["evidence"]["provider"] == "ollama" and intent["evidence"]["model"] == model
        diagnosed_event = next(
            event for event in diagnosed["events"] if event["type"] == "diagnosed"
        )
        assert diagnosed_event["evidence"]["provider"] == "ollama"
        diagnosis = diagnosed["diagnosis"]
        assert diagnosis["category"] == "PAUSED_DELIVERY", diagnosis
        assert diagnosis["proposed_action"] == "resume_notification_worker"
        assert diagnosis["escalate"] is False and diagnosis["risk"] == "low"
        assert diagnosis["confidence"] >= 0.8
        assert diagnosis["incident_id"] == incident["id"]
        assert diagnosed["affected"] == [row["id"]] and diagnosed["generation"] == generation
        assert int(sql(RESERVED)) == reserved_before + 1
        resources = docker(
            "stats",
            "--no-stream",
            "--format",
            "{{json .}}",
            PROJECT + "-web-1",
            PROJECT + "-alert-receiver-1",
            name,
        )
        grant_status, grant = operator.request(
            detail_path + "/authorize", {"expected_generation": generation}
        )
        assert grant_status == 200
        final = wait(
            lambda: (
                data
                if (data := operator.request(detail_path)[1])["state"] in {"RESOLVED", "ESCALATED"}
                else None
            ),
            timeout=150,
        )
        assert final["state"] == "RESOLVED" and final["verification"]["ok"] is True, (
            final["state"],
            final["escalation_reason"],
        )
        delivered = persisted(row["id"])
        assert delivered["status"] == "delivered" and delivered["inbox_count"] == 1
        actions = json.loads(
            sql(
                "SELECT json_build_object('count',count(*),'success',bool_and(success)) "
                "FROM worker_resume_actions WHERE incident_id='" + str(UUID(incident["id"])) + "'"
            )
        )
        assert actions == {"count": 1, "success": True}
        assert int(sql(RESERVED)) == reserved_before + 1  # exactly one real model call
        telemetry = json.loads(
            sql("SELECT telemetry FROM incidents WHERE id='" + str(UUID(incident["id"])) + "'")
        )
        import observability_tests.test_stack as stack

        stack.EVIDENCE = directory
        correlation(row)
        timeline = {event["type"]: event["at"] for event in final["events"]}
        (directory / "evidence.json").write_text(
            json.dumps(
                {
                    "provider": "ollama",
                    "real_model": True,
                    "model": model,
                    "provider_timeout_seconds": int(timeout),
                    "durable_call_budget": int(budget),
                    "request_started_at": at,
                    "observed_intake_seconds": observed,
                    "pause_ack": paused,
                    "outbox": row,
                    "incident": final,
                    "model_intent_at": timeline.get("model_intent"),
                    "diagnosed_at": timeline.get("diagnosed"),
                    "telemetry_snapshot_seen_by_model": telemetry,
                    "grant": grant,
                    "action_result": actions,
                    "delivery": delivered,
                    "resource_sample": [json.loads(line) for line in resources.splitlines()],
                },
                indent=2,
            )
        )
        print("T11_REAL_MODEL_EVIDENCE", directory)
    finally:
        subprocess.run(
            ["docker", "stop", "--time", "35", name], capture_output=True, text=True, timeout=90
        )
        if runtime.poll() is None:
            runtime.wait(timeout=60)
        log.close()
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
