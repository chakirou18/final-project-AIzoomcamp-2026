"""Real T10 acceptance, reusing the existing isolated T09 PostgreSQL/telemetry stack."""

import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from fieldops.seed import persona_id
from observability_tests.test_stack import (
    DATABASE,
    PROJECT,
    Client,
    assign,
    compose,
    correlation,
    delivered,
    internal,
    metrics,
    persisted,
    secret,
    sql,
    wait,
)

EVIDENCE = Path("artifacts") / ("t10-alerting-" + uuid4().hex)


def receiver(method="GET", path="/internal/receipts", *, key="reader", payload=None):
    # Credentials stay inside the private receiver container and never enter host artifacts.
    assert key in {"reader", "webhook", "invalid", "none"}
    code = """
import sys,json,urllib.request,urllib.error
from pathlib import Path
method,path,key,body=sys.argv[1:]
headers={'Content-Type':'application/json'}
if key!='none':
 filename='/run/fieldops-alert-reader/key' if key=='reader' else '/run/fieldops-webhook/key'
 value=Path(filename).read_text().strip() if key in ['reader','webhook'] else 'invalid'
 headers['Authorization']='Bearer '+value
r=urllib.request.Request('http://127.0.0.1:8010'+path,method=method,
 headers=headers,data=body.encode() if body else None)
try: response=urllib.request.urlopen(r,timeout=4)
except urllib.error.HTTPError as e: response=e
print(json.dumps({'status':response.status,'body':json.load(response)}))
"""
    return json.loads(
        compose(
            "exec",
            "-T",
            "alert-receiver",
            "python",
            "-c",
            code,
            method,
            path,
            key,
            json.dumps(payload) if payload is not None else "",
        )
    )


def receipts(after_id=0):
    result = receiver(path=f"/internal/receipts?after_id={after_id}")
    assert result["status"] == 200
    # Bounded pagination so retained earlier runs cannot hide current receipts.
    rows = result["body"]["receipts"]
    while len(result["body"]["receipts"]) == 100:
        result = receiver(path="/internal/receipts?after_id=" + str(rows[-1]["id"]))
        assert result["status"] == 200
        rows.extend(result["body"]["receipts"])
    return rows


def active():
    return internal("http://prometheus:9090/api/v1/alerts")["data"]["alerts"]


def alertmanager_alerts():
    code = (
        "import urllib.request; "
        "print(urllib.request.urlopen('http://alertmanager:9093/api/v2/alerts',timeout=4).read().decode())"
    )
    return json.loads(compose("exec", "-T", "web", "python", "-c", code))


@pytest.fixture(scope="module", autouse=True)
def isolated():
    if os.getenv("FIELDOPS_RUN_ALERTING_TESTS") != "1":
        pytest.skip("Explicit isolated synthetic T10 opt-in required")
    assert PROJECT.startswith("fieldops-t09") and DATABASE.startswith("fieldops_t09")
    assert DATABASE.endswith("_test")
    EVIDENCE.mkdir(parents=True)
    import observability_tests.test_stack as stack

    stack.EVIDENCE = EVIDENCE
    assert Client().request("/health/ready")[0] == 200
    assert metrics()[0]["fieldops_notifications_undelivered"] == 0
    assert receiver()["status"] == 200
    yield
    print("T10_EVIDENCE", EVIDENCE)


def test_live_receiver_authentication_and_malformed_payload():
    before = receipts()
    for key in ["none", "invalid", "reader"]:
        assert receiver("POST", "/internal/alerts", key=key, payload={})["status"] == 401
    for key in ["none", "invalid", "webhook"]:
        assert receiver(key=key)["status"] == 401
    assert receiver("POST", "/internal/alerts", key="webhook", payload={})["status"] == 422
    assert receipts() == before
    (EVIDENCE / "receiver-negative.json").write_text(
        json.dumps({"auth_denials": 6, "malformed": 422})
    )


def test_fault_control_authorization_and_credential_separation():
    before = Client("demo-operator").request("/api/v1/dashboard")[1]["worker"]
    command = {"expected_generation": before["generation"], "duration_seconds": 180}
    # Fresh unauthenticated client (no persona login).
    import urllib.error
    import urllib.request

    from observability_tests.test_stack import BASE

    request = urllib.request.Request(
        BASE + "/demo/worker/pause",
        data=json.dumps(command).encode(),
        headers={"Content-Type": "application/json"},
    )
    with pytest.raises(urllib.error.HTTPError) as error:
        urllib.request.urlopen(request, timeout=5)
    assert error.value.code in {401, 403}
    for persona in ["demo-technician-a", "demo-manager"]:
        assert Client(persona).request("/demo/worker/pause", command)[0] == 403
    operator = Client("demo-operator")
    assert (
        operator.request("/demo/worker/pause", command, headers={"X-CSRF-Token": "invalid"})[0]
        == 403
    )
    for credential in ["invalid", secret("operator_key")]:
        assert (
            operator.request(
                "/internal/worker/resume",
                {
                    "expected_generation": before["generation"],
                    "incident_id": str(uuid4()),
                    "idempotency_key": str(uuid4()),
                },
                headers={"Authorization": "Bearer " + credential},
            )[0]
            == 401
        )
    assert operator.request("/api/v1/dashboard")[1]["worker"]["generation"] == before["generation"]
    (EVIDENCE / "control-negative.json").write_text(
        json.dumps(
            {
                "anonymous_denied": True,
                "wrong_roles_denied": True,
                "operator_csrf_denied": True,
                "wrong_resume_keys_denied": True,
            }
        )
    )


def test_real_pause_assignment_alert_delivery_and_manual_cleanup():
    operator = Client("demo-operator")
    worker = operator.request("/api/v1/dashboard")[1]["worker"]
    assert worker["heartbeat_state"] == "fresh" and not worker["paused"]
    # Verify the empty queue stays quiet across a full queue-alert detection window.
    quiet_start = time.monotonic()
    quiet_receipts = {r["id"] for r in receipts()}
    while time.monotonic() - quiet_start < 100:
        assert metrics()[0]["fieldops_notifications_undelivered"] == 0
        assert not [a for a in active() if a["labels"]["alertname"] == "NotificationQueueDelayed"]
        assert not [
            r
            for r in receipts()
            if r["id"] not in quiet_receipts
            and r["alertname"] == "NotificationQueueDelayed"
            and r["status"] == "firing"
        ]
        time.sleep(1)  # Bounded sampling cadence, not a readiness sleep.
    status, paused = operator.request(
        "/demo/worker/pause",
        {
            "expected_generation": worker["generation"],
            "duration_seconds": 240,
        },
    )
    assert status == 200 and paused["paused"] and paused["effective_at"]
    generation = paused["generation"]
    evidence = {
        "run_id": str(uuid4()),
        "pause_ack": paused,
        "empty_quiet_seconds": time.monotonic() - quiet_start,
    }
    try:
        gate = json.loads(
            sql(
                "SELECT json_build_object('paused',paused,'generation',generation,"
                "'effective_at',effective_at) FROM worker_control "
                "WHERE key='notification-worker'"
            )
        )
        assert gate["paused"] and gate["generation"] == generation
        baseline_id = max((r["id"] for r in receipts()), default=0)
        # Conservative start BEFORE the assignment HTTP request (stronger than commit-to-receipt).
        started = time.monotonic()
        evidence["assignment_request_started_at"] = datetime.now(UTC).isoformat()
        row = assign("T10-real-alert")
        evidence["outbox"] = row
        assert row["status"] == "pending" and row["attempts"] == 0
        state = persisted(row["id"])
        assert state["inbox_count"] == 0
        mapping = json.loads(
            sql(
                "SELECT json_build_object('recipient',recipient_id,"
                "'intervention_id',intervention_id,'history',"
                "(SELECT count(*) FROM intervention_history h "
                "WHERE h.intervention_id=o.intervention_id)) "
                "FROM notification_outbox o WHERE id='" + str(UUID(row["id"])) + "'"
            )
        )
        assert (
            mapping["recipient"] == str(persona_id("demo-technician-a")) and mapping["history"] >= 2
        )
        technician = Client("demo-technician-a")
        samples = []
        found = None
        while time.monotonic() - started < 110:
            elapsed = time.monotonic() - started
            state = persisted(row["id"])
            assert state["inbox_count"] == 0 and state["status"] == "pending"
            assert not any(
                n["outbox_id"] == row["id"]
                for n in technician.request("/api/v1/notifications?page_size=100")[1]["items"]
            )
            values = metrics()[0]
            assert values["fieldops_notifications_undelivered"] == 1
            assert values["fieldops_worker_paused"] == 1
            assert time.time() - values["fieldops_worker_heartbeat_timestamp_seconds"] < 15
            alerts = active()
            samples.append(
                {
                    "elapsed": elapsed,
                    "age": values["fieldops_notification_oldest_undelivered_age_seconds"],
                    "alerts": alerts,
                }
            )
            found = next(
                (
                    r
                    for r in receipts(baseline_id)
                    if r["alertname"] == "NotificationQueueDelayed" and r["status"] == "firing"
                ),
                None,
            )
            if found:
                assert (
                    elapsed > 60
                    and values["fieldops_notification_oldest_undelivered_age_seconds"] > 60
                )
                break
            time.sleep(0.5)
        observed = time.monotonic() - started
        evidence.update({"samples": samples, "observed_seconds": observed})
        (EVIDENCE / "attempt.json").write_text(json.dumps(evidence, indent=2))
        assert found is not None and observed <= 110
        am_alerts = [
            a
            for a in alertmanager_alerts()
            if a["labels"]["alertname"] == "NotificationQueueDelayed"
        ]
        firing_at = datetime.fromisoformat(found["starts_at"])
        received_at = datetime.fromisoformat(found["received_at"])
        assert datetime.fromisoformat(row["created_at"]) < firing_at <= received_at
        assert any(
            a["status"]["state"] == "active"
            and a["labels"] == found["labels"]
            and datetime.fromisoformat(a["startsAt"]) == firing_at
            and {"name": "fieldops-test-evidence"} in a["receivers"]
            for a in am_alerts
        )
        assert any(
            a["state"] == "firing"
            and a["labels"] == found["labels"]
            and abs((firing_at - datetime.fromisoformat(a["activeAt"])).total_seconds() - 30) < 1
            for a in samples[-1]["alerts"]
        )
        evidence.update(
            {
                "mapping": mapping,
                "receipt": found,
                "elapsed_to_observed_receipt_seconds": observed,
                "samples": samples,
                "paused_inbox_count": 0,
                "recovery_attempted_by_receiver": False,
                "alertmanager": am_alerts,
            }
        )
        (EVIDENCE / "real-alert.json").write_text(json.dumps(evidence, indent=2))
    finally:
        status, result = operator.request(
            "/internal/worker/resume",
            {
                "incident_id": str(uuid4()),
                "expected_generation": generation,
                "idempotency_key": str(uuid4()),
            },
            headers={"Authorization": "Bearer " + secret("recovery_key")},
        )
        assert status == 200 and result["success"]
        if "row" in locals():
            state = delivered(row)
            evidence["manual_cleanup_delivery"] = state
            assert state["inbox_count"] == 1
            (EVIDENCE / "cleanup.json").write_text(json.dumps(evidence, indent=2))
            correlation(row)
        (EVIDENCE / "cleanup.json").write_text(json.dumps(evidence, indent=2))
    wait(
        lambda: not [a for a in active() if a["labels"]["alertname"] == "NotificationQueueDelayed"],
        timeout=30,
    )
    resolved = wait(
        lambda: next(
            (
                r
                for r in receipts()
                if r["alertname"] == "NotificationQueueDelayed"
                and r["status"] == "resolved"
                and r["episode"] == found["episode"]
            ),
            None,
        ),
        timeout=30,
    )
    (EVIDENCE / "resolved-receipt.json").write_text(json.dumps(resolved, indent=2))


@pytest.mark.parametrize("fault", ["missing_metrics", "failed_scrape"])
def test_real_scrape_pipeline_missing_data_alerts_without_business_outage(fault):
    # Alter only Prometheus collection temporarily. Never fabricate metric values or crash DB.
    # The rule's DB-up=0 path is separately evaluated by promtool against the T09 contract.
    configuration = Path("observability/prometheus.yml")
    original = configuration.read_bytes()
    text = original.decode()
    if fault == "missing_metrics":
        text = text.replace(
            "rule_files:",
            "    metric_relabel_configs:\n"
            "      - source_labels: [__name__]\n"
            "        regex: fieldops_metrics_database_up\n"
            "        action: drop\nrule_files:",
        )
        expected = "NotificationMetricsMissing"
    else:
        text = text.replace(
            "    scrape_timeout: 4s",
            "    scrape_timeout: 4s\n    metrics_path: /t10-intentionally-missing-metrics-path",
        )
        expected = "NotificationScrapeFailure"
    baseline = {r["id"] for r in receipts()}
    row = None
    started = time.monotonic()
    try:
        configuration.write_text(text)
        compose(
            "exec",
            "-T",
            "prometheus",
            "promtool",
            "check",
            "config",
            "/etc/prometheus/prometheus.yml",
        )
        compose("exec", "-T", "prometheus", "/busybox", "kill", "-HUP", "1")
        row = assign("T10-" + fault)
        state = delivered(row)
        assert state["inbox_count"] == 1  # Collection failure never becomes business failure.
        found = wait(
            lambda: next(
                (
                    r
                    for r in receipts()
                    if r["id"] not in baseline
                    and r["alertname"] == expected
                    and r["status"] == "firing"
                ),
                None,
            ),
            timeout=60,
        )
        assert any(
            a["labels"]["alertname"] == expected and a["state"] == "firing" for a in active()
        )
        (EVIDENCE / (fault + ".json")).write_text(
            json.dumps(
                {
                    "receipt": found,
                    "elapsed_seconds": time.monotonic() - started,
                    "real_outbox": row,
                    "actual_delivery": state,
                    "alerts": active(),
                },
                indent=2,
            )
        )
    finally:
        configuration.write_bytes(original)
        compose("exec", "-T", "prometheus", "/busybox", "kill", "-HUP", "1")
    wait(lambda: not [a for a in active() if a["labels"]["alertname"] == expected], timeout=30)
