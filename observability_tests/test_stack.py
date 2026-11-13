"""Opt-in real Compose/HTTP/Jaeger/Loki failures. Never target a development database."""

import http.cookiejar
import json
import os
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from prometheus_client.parser import text_string_to_metric_families

from fieldops.seed import persona_id

ROOT = Path(__file__).resolve().parent.parent
PROJECT = os.getenv("FIELDOPS_OBSERVABILITY_PROJECT", "fieldops-t09")
BASE = os.getenv("FIELDOPS_OBSERVABILITY_URL", "http://127.0.0.1:18009")
GRAFANA = os.getenv("FIELDOPS_GRAFANA_URL", "http://127.0.0.1:13009")
DATABASE = os.getenv("POSTGRES_DB", "fieldops_t09_demo_test")
EVIDENCE = ROOT / "artifacts" / ("t09-stack-" + uuid4().hex)
SENTINEL = "SYNTHETIC-T09-SECRET-CUSTOMER-NOT-TELEMETRY"


def compose(*args):
    assert (
        PROJECT.startswith("fieldops-t09")
        and DATABASE.startswith("fieldops_t09")
        and DATABASE.endswith("_test")
    )
    environment = {**os.environ, "COMPOSE_PROJECT_NAME": PROJECT, "POSTGRES_DB": DATABASE}
    for key, value in {
        "FIELDOPS_SUBNET": "10.254.9.0/24",
        "FIELDOPS_PORT": "18009",
        "FIELDOPS_GRAFANA_PORT": "13009",
        "FIELDOPS_JAEGER_PORT": "16689",
    }.items():
        environment.setdefault(key, value)
    result = subprocess.run(
        [
            "docker",
            "compose",
            "--file",
            str(ROOT / "docker-compose.yml"),
            "--project-name",
            PROJECT,
            "--profile",
            "observability",
            *args,
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, "Isolated Compose operation failed: " + result.stderr[-1500:]
    return result.stdout.strip()


def sql(statement):
    return compose(
        "exec",
        "-T",
        "db",
        "psql",
        "-U",
        "fieldops",
        "-d",
        DATABASE,
        "-v",
        "ON_ERROR_STOP=1",
        "-At",
        "-c",
        statement,
    )


def internal(url):
    # Only the test invokes a fixed internal HTTP client; no app control endpoint or Docker socket.
    assert url.startswith(("http://jaeger:", "http://prometheus:", "http://loki:"))
    code = (
        "import sys,urllib.request; "
        "print(urllib.request.urlopen(sys.argv[1],timeout=5).read().decode())"
    )
    return json.loads(compose("exec", "-T", "web", "python", "-c", code, url))


def wait(check, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            value = check()
            if value:
                return value
        except (AssertionError, OSError, ValueError):
            pass
        time.sleep(0.2)
    raise AssertionError("Persisted/telemetry state not observed before bounded deadline")


class Client:
    def __init__(self, persona="demo-manager"):
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
        )
        self.csrf = self.request("/auth/csrf")[1]["csrf_token"]
        payload = {"persona_id": str(persona_id(persona))}
        if persona == "demo-operator":
            payload["operator_secret"] = secret("operator_key")
        status, response = self.request("/auth/login", payload)
        assert status == 200
        self.csrf = response["csrf_token"]

    def request(self, path, payload=None, headers=None):
        req = urllib.request.Request(
            BASE + path,
            data=json.dumps(payload).encode() if payload is not None else None,
            headers={
                "Content-Type": "application/json",
                "X-CSRF-Token": self.csrf if hasattr(self, "csrf") else "",
                **(headers or {}),
            },
        )
        try:
            response = self.opener.open(req, timeout=8)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            raw = response.read().decode()
            return response.status, json.loads(raw) if raw and not path.startswith(
                "/metrics"
            ) else raw


def secret(name):
    assert name in {"operator_key", "recovery_key"}
    return compose(
        "exec",
        "-T",
        "web",
        "python",
        "-c",
        "import sys; from pathlib import Path; "
        "print(Path('/run/fieldops-controls',sys.argv[1]).read_text().strip())",
        name,
    )


def assign(label, *, headers=None):
    client = Client()
    status, job = client.request(
        "/api/v1/interventions",
        {
            "title": "T09 " + label + " " + uuid4().hex[:12],
            "site": SENTINEL,
            "description": SENTINEL,
        },
    )
    assert status == 201
    status, assigned = client.request(
        "/api/v1/interventions/" + job["id"] + "/assignment",
        {"expected_version": 1, "technician_id": str(persona_id("demo-technician-a"))},
        headers=headers,
    )
    assert status == 200 and assigned["row_version"] == 2
    identifier = str(UUID(job["id"]))
    row = json.loads(
        sql(
            "SELECT json_build_object('id',id,'traceparent',traceparent,"
            "'tracestate',tracestate,'status',status,'attempts',attempts,"
            "'created_at',created_at) FROM notification_outbox WHERE intervention_id='"
            + identifier
            + "'"
        )
    )
    return row


def persisted(identifier):
    identifier = str(UUID(identifier))
    return json.loads(
        sql(
            "SELECT json_build_object('status',o.status,'attempts',o.attempts,"
            "'inbox_count',(SELECT count(*) FROM notifications n WHERE n.outbox_id=o.id),"
            "'notification_id',(SELECT id FROM notifications n WHERE n.outbox_id=o.id),"
            "'delivered_at',o.delivered_at) FROM notification_outbox o WHERE o.id='"
            + identifier
            + "'"
        )
    )


def delivered(row):
    return wait(
        lambda: (
            state
            if (state := persisted(row["id"]))["status"] == "delivered"
            and state["inbox_count"] == 1
            else None
        )
    )


def metrics():
    payload = Client().request("/metrics")[1]
    return {
        sample.name: sample.value
        for family in text_string_to_metric_families(payload)
        for sample in family.samples
        if not sample.labels
    }, payload


def trace_json(identifier):
    return internal("http://jaeger:16686/api/traces/" + identifier).get("data", [])


def logs():
    result = []
    for line in compose(
        "exec",
        "-T",
        "web",
        "python",
        "-c",
        "from pathlib import Path; "
        "[print(p.read_text()) for p in Path('/var/log/fieldops').glob('*.jsonl')]",
    ).splitlines():
        if line.strip():
            result.append(json.loads(line))
    return result


def correlation(row, *, retry=False):
    state = delivered(row)
    assert row["traceparent"] is not None
    _, identifier, parent, _ = row["traceparent"].split("-")
    required = {
        "intervention.assign",
        "notification.enqueue",
        "postgresql INSERT notification_outbox",
        "notification.deliver",
        "notification.inbox.persist",
        "postgresql INSERT notifications",
    }

    def complete_trace():
        value = trace_json(identifier)
        if not value:
            return None
        spans = value[0]["spans"]
        names = {item["operationName"] for item in spans}
        # Web and worker export independent asynchronous batches. One delivery span
        # arriving first does not establish that the complete trace has arrived.
        return (
            value
            if required <= names
            and sum(item["operationName"] == "notification.deliver" for item in spans)
            == (2 if retry else 1)
            and any(name.startswith("POST /api/v1/interventions/{id}/assignment") for name in names)
            else None
        )

    trace = wait(complete_trace)[0]
    names = {s["operationName"] for s in trace["spans"]}
    assert required <= names
    assert any(
        s["operationName"].startswith("POST /api/v1/interventions/{id}/assignment")
        for s in trace["spans"]
    )
    assert all(s["traceID"] == identifier for s in trace["spans"])
    assert {p["serviceName"] for p in trace["processes"].values()} == {
        "fieldops-web",
        "fieldops-worker",
    }
    deliveries = [s for s in trace["spans"] if s["operationName"] == "notification.deliver"]
    assert len(deliveries) == (2 if retry else 1)
    assert all(
        any(ref["refType"] == "CHILD_OF" and ref["spanID"] == parent for ref in s["references"])
        for s in deliveries
    )
    correlated = [line for line in logs() if line.get("outbox_id") == row["id"]]
    assert {line["service"] for line in correlated} == {"fieldops-web", "fieldops-worker"}
    assert all(line["trace_id"] == identifier for line in correlated)
    assert any(
        line["event"] == "notification_delivered"
        and line["notification_id"] == state["notification_id"]
        for line in correlated
    )
    safe = {"outbox": row, "persisted": state, "trace": trace, "logs": correlated}
    encoded = json.dumps(safe, indent=2)
    assert SENTINEL not in encoded
    (EVIDENCE / (row["id"] + ".json")).write_text(encoded, encoding="utf-8")
    return identifier


@pytest.fixture(scope="module", autouse=True)
def isolated_stack_only():
    if os.getenv("FIELDOPS_RUN_OBSERVABILITY_TESTS") != "1":
        pytest.skip("Opt in only against a dedicated synthetic T09 Compose project")
    assert (
        PROJECT.startswith("fieldops-t09")
        and DATABASE.startswith("fieldops_t09")
        and DATABASE.endswith("_test")
    )
    EVIDENCE.mkdir(parents=True)
    assert Client().request("/health/ready")[0] == 200
    yield
    print("T09_EVIDENCE", EVIDENCE.relative_to(ROOT))


def test_actual_http_outbox_worker_inbox_trace_and_logs():
    row = assign(
        "correlation", headers={"Authorization": SENTINEL, "tracestate": "customer=" + SENTINEL}
    )
    correlation(row)


def test_two_concurrent_assignments_have_distinct_trace_context():
    with ThreadPoolExecutor(max_workers=2) as pool:
        rows = list(pool.map(assign, ["concurrent-a", "concurrent-b"]))
    assert correlation(rows[0]) != correlation(rows[1])


def test_retry_keeps_original_enqueue_parent_and_redacts_sql_error():
    compose("stop", "worker")
    row = assign("retry")
    identifier = str(UUID(row["id"]))
    try:
        sql(
            "CREATE SEQUENCE t09_retry_sequence; CREATE FUNCTION t09_retry() RETURNS trigger "
            "LANGUAGE plpgsql AS $$ BEGIN IF NEW.outbox_id='"
            + identifier
            + "' AND nextval('t09_retry_sequence')=1 THEN RAISE EXCEPTION '"
            + SENTINEL
            + "'; END IF; RETURN NEW; END $$; CREATE TRIGGER t09_retry "
            "BEFORE INSERT ON notifications FOR EACH ROW EXECUTE FUNCTION t09_retry();"
        )
        compose("start", "worker")
        state = delivered(row)
        assert state["attempts"] == 2
        correlation(row, retry=True)
    finally:
        sql(
            "DROP TRIGGER IF EXISTS t09_retry ON notifications; "
            "DROP FUNCTION IF EXISTS t09_retry(); DROP SEQUENCE IF EXISTS t09_retry_sequence;"
        )
        compose("start", "worker")


def test_malformed_context_is_delivered_as_independent_root():
    compose("stop", "worker")
    try:
        row = assign("malformed")
        sql(
            "UPDATE notification_outbox SET traceparent='invalid',tracestate='secret="
            + SENTINEL
            + "' WHERE id='"
            + str(UUID(row["id"]))
            + "'"
        )
    finally:
        compose("start", "worker")
    delivered(row)
    entry = wait(
        lambda: next(
            (
                v
                for v in logs()
                if v.get("outbox_id") == row["id"] and v["event"] == "notification_delivered"
            ),
            None,
        )
    )
    assert entry["trace_id"] != row["traceparent"].split("-")[1]
    data = wait(lambda: value if (value := trace_json(entry["trace_id"])) else None)
    delivery = next(s for s in data[0]["spans"] if s["operationName"] == "notification.deliver")
    assert not delivery["references"]
    assert SENTINEL not in json.dumps(data)
    (EVIDENCE / "malformed.json").write_text(
        json.dumps({"event": row["id"], "trace": data, "log": entry}, indent=2)
    )


@pytest.mark.parametrize("service", ["prometheus", "otel-collector", "loki"])
def test_business_transactions_survive_telemetry_service_outage(service):
    compose("stop", service)
    try:
        row = assign("outage-" + service)
        state = delivered(row)
        assert state["inbox_count"] == 1
        correlated = [line for line in logs() if line.get("outbox_id") == row["id"]]
        assert {v["trace_id"] for v in correlated} == {row["traceparent"].split("-")[1]}
        assert metrics()[0]["fieldops_metrics_database_up"] == 1
        (EVIDENCE / ("outage-" + service + ".json")).write_text(
            json.dumps({"event": row, "persisted": state, "logs": correlated}, indent=2)
        )
    finally:
        compose("start", service)
        # Match the Compose readiness envelope (30 probes x 5s), separately from
        # the unchanged 30s trace-correlation deadline after readiness. Under the
        # measured shared-host pressure a cold Collector needed over 30s to start.
        endpoints = {
            "prometheus": "http://127.0.0.1:9090/-/ready",
            "otel-collector": "http://127.0.0.1:13133/",
            "loki": "http://127.0.0.1:3100/ready",
        }

        def service_ready():
            compose(
                "exec",
                "-T",
                service,
                "/busybox",
                "wget",
                "-q",
                "-O",
                "-",
                endpoints[service],
            )
            # The healthy endpoint may return an empty body. Success is its exit status.
            return True

        wait(service_ready, timeout=150)
    if service == "otel-collector":
        correlation(assign("exporter-recovered"))


def test_worker_stop_and_database_outage_keep_metrics_truthful():
    compose("stop", "worker")
    row = assign("worker-down")
    try:
        current, _ = metrics()
        assert current["fieldops_notifications_undelivered"] >= 1
        assert current["fieldops_notification_oldest_undelivered_age_seconds"] >= 0
        assert current["fieldops_worker_paused"] == 0
        wait(
            lambda: metrics()[0]["fieldops_worker_heartbeat_timestamp_seconds"] < time.time() - 15,
            timeout=20,
        )
        compose("stop", "db")
        try:
            # Health/metrics remain reachable without a session or a working database.
            for path, expected in [
                ("/health/live", 200),
                ("/health/ready", 503),
                ("/metrics", 200),
            ]:
                try:
                    response = urllib.request.urlopen(BASE + path, timeout=8)
                except urllib.error.HTTPError as error:
                    response = error
                with response:
                    payload = response.read().decode()
                    assert response.status == expected
                    if path == "/metrics":
                        assert "fieldops_metrics_database_up 0.0" in payload
                        assert "fieldops_notifications_undelivered" not in payload
        finally:
            compose("start", "db")
            wait(lambda: urllib.request.urlopen(BASE + "/health/ready", timeout=8).status == 200)
    finally:
        compose("start", "worker")
    delivered(row)
    correlation(row)


def test_pause_is_fresh_and_generation_resume_recovers_metric_backlog():
    operator = Client("demo-operator")
    assert metrics()[0]["fieldops_notifications_undelivered"] == 0
    current = operator.request("/api/v1/dashboard")[1]["worker"]
    status, paused = operator.request(
        "/demo/worker/pause", {"expected_generation": current["generation"], "duration_seconds": 60}
    )
    assert status == 200 and paused["paused"]
    row = assign("pause")
    try:
        current, _ = metrics()
        assert (
            current["fieldops_worker_paused"] == 1
            and current["fieldops_notifications_undelivered"] == 1
        )
        assert time.time() - current["fieldops_worker_heartbeat_timestamp_seconds"] < 15
        assert persisted(row["id"])["inbox_count"] == 0
        first_age = current["fieldops_notification_oldest_undelivered_age_seconds"]
        effective = datetime.fromisoformat(
            paused["effective_at"].replace("Z", "+00:00")
        ).timestamp()

        def advanced():
            value = metrics()[0]
            return (
                value
                if value["fieldops_worker_heartbeat_timestamp_seconds"] > effective
                and value["fieldops_notification_oldest_undelivered_age_seconds"] > first_age + 0.5
                else None
            )

        current = wait(advanced)
        assert current["fieldops_worker_paused"] == 1
        (EVIDENCE / "paused-metrics.json").write_text(json.dumps(current, indent=2))
    finally:
        status, result = operator.request(
            "/internal/worker/resume",
            {
                "incident_id": str(uuid4()),
                "idempotency_key": str(uuid4()),
                "expected_generation": paused["generation"],
            },
            headers={"Authorization": "Bearer " + secret("recovery_key")},
        )
        assert status == 200 and result["success"]
    correlation(row)
    assert metrics()[0]["fieldops_notifications_undelivered"] == 0


def test_prometheus_loki_labels_and_actual_grafana_trace_backend_link():
    response = internal(
        "http://prometheus:9090/api/v1/query?"
        + urllib.parse.urlencode({"query": "fieldops_notifications_undelivered"})
    )
    assert response["status"] == "success" and response["data"]["result"]
    labels = internal("http://prometheus:9090/api/v1/labels")["data"]
    assert not {
        "trace_id",
        "span_id",
        "outbox_id",
        "notification_id",
        "intervention_id",
        "user_id",
    } & set(labels)
    row = assign("loki-link")
    identifier = correlation(row)
    query = '{service=~"fieldops-web|fieldops-worker"} | json | outbox_id="' + row["id"] + '"'
    parameters = urllib.parse.urlencode(
        {
            "query": query,
            "start": str(int((time.time() - 300) * 1e9)),
            "end": str(time.time_ns()),
            "limit": 100,
        }
    )

    def complete_streams():
        data = internal("http://loki:3100/loki/api/v1/query_range?" + parameters)
        entries = [
            json.loads(line) for stream in data["data"]["result"] for _, line in stream["values"]
        ]
        return (
            data
            if {line["service"] for line in entries} == {"fieldops-web", "fieldops-worker"}
            else None
        )

    records = wait(complete_streams)
    streams = records["data"]["result"]
    # JSON query extraction creates temporary result labels; storage series labels are tested below.
    entries = [json.loads(line) for stream in streams for _, line in stream["values"]]
    assert {e["service"] for e in entries} == {"fieldops-web", "fieldops-worker"}
    assert all(e["trace_id"] == identifier for e in entries)
    window = urllib.parse.urlencode(
        {"start": str(int((time.time() - 300) * 1e9)), "end": str(time.time_ns())}
    )
    stored_labels = internal("http://loki:3100/loki/api/v1/labels?" + window)["data"]
    # Loki additionally derives service_name from the bounded service label, never an event ID.
    assert set(stored_labels) <= {"service", "environment", "service_name"}
    series = internal(
        "http://loki:3100/loki/api/v1/series?"
        + window
        + "&"
        + urllib.parse.urlencode({"match[]": '{service=~"fieldops-web|fieldops-worker"}'})
    )["data"]
    assert series
    for labels in series:
        assert set(labels) <= {"service", "environment", "service_name"}
        assert labels["service"] in {"fieldops-web", "fieldops-worker"}
        assert labels.get("service_name", labels["service"]) in {"fieldops-web", "fieldops-worker"}
        assert labels["environment"] == "local"
    data = json.loads(urllib.request.urlopen(GRAFANA + "/api/datasources/uid/fieldops-loki").read())
    derived = data["jsonData"]["derivedFields"][0]
    assert derived["datasourceUid"] == "fieldops-jaeger" and derived["url"] == "${__value.raw}"
    proxied = json.loads(
        urllib.request.urlopen(
            GRAFANA + "/api/datasources/proxy/uid/fieldops-jaeger/api/traces/" + identifier
        ).read()
    )
    assert proxied["data"][0]["traceID"] == identifier
    encoded = json.dumps(
        {
            "loki": records,
            "stored_labels": stored_labels,
            "derived_field": derived,
            "trace_id": identifier,
        },
        indent=2,
    )
    assert SENTINEL not in encoded
    (EVIDENCE / "loki-grafana-correlation.json").write_text(encoded)


@pytest.mark.parametrize("width", [1440, 375])
def test_actual_grafana_dashboard_browser(width):
    from playwright.sync_api import expect, sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": 1000})
        try:
            page.goto(GRAFANA + "/d/fieldops-operations", wait_until="domcontentloaded")
            expect(page.get_by_text("Undelivered (includes failed)", exact=True)).to_be_visible(
                timeout=30000
            )
            expect(page.get_by_text("Oldest undelivered age", exact=True)).to_be_visible()
            available = page.locator(
                'section[data-testid="data-testid Panel header Queue database available (1=yes)"]'
            )
            expect(available.get_by_role("link", name="1", exact=True)).to_be_visible(timeout=30000)
            backlog = page.locator(
                'section[data-testid="data-testid Panel header Undelivered (includes failed)"]'
            )
            expect(backlog.get_by_role("link", name="0", exact=True)).to_be_visible(timeout=30000)
            assert SENTINEL not in page.content()
            # Grafana virtualizes panels below the viewport. Scroll and validate all data.
            definition = json.loads((ROOT / "observability/grafana/dashboard.json").read_text())
            for specification in definition["panels"]:
                panel = page.locator(
                    'section[data-testid="data-testid Panel header ' + specification["title"] + '"]'
                )
                panel.scroll_into_view_if_needed()
                if specification["type"] == "stat":
                    value = panel.locator('a[href^="/explore?"]').first
                    expect(value).to_be_visible(timeout=30000)
                    assert value.inner_text().strip()
                else:
                    expect(
                        panel.get_by_text("notification_delivered", exact=False).first
                    ).to_be_visible(timeout=30000)
                panel.screenshot(
                    path=str(EVIDENCE / f"grafana-{width}-panel-{specification['id']}.png"),
                    animations="disabled",
                )
            page.evaluate("window.scrollTo(0, 0)")
            page.screenshot(
                path=str(EVIDENCE / f"grafana-{width}.png"), full_page=True, animations="disabled"
            )
        except BaseException:
            page.screenshot(path=str(EVIDENCE / f"grafana-{width}-failure.png"), full_page=True)
            raise
        finally:
            browser.close()


def test_metric_logs_to_jaeger_browser_link():
    from playwright.sync_api import expect, sync_playwright

    def queue_snapshot(expected):
        response = internal(
            "http://prometheus:9090/api/v1/query?"
            + urllib.parse.urlencode({"query": "fieldops_notifications_undelivered"})
        )
        results = response["data"]["result"]
        if results and float(results[0]["value"][1]) == expected:
            return {"at": results[0]["value"][0], "backlog": expected}
        return None

    # Capture genuine Prometheus snapshots for both states, independently of other
    # tests. Use the existing audited T07 gate; never mock a metric or stop a container.
    operator = Client("demo-operator")
    assert metrics()[0]["fieldops_notifications_undelivered"] == 0
    generation = operator.request("/api/v1/dashboard")[1]["worker"]["generation"]
    status, paused = operator.request(
        "/demo/worker/pause", {"expected_generation": generation, "duration_seconds": 180}
    )
    assert status == 200 and paused["paused"]
    try:
        row = assign("browser-trace-link")
        assert persisted(row["id"])["status"] == "pending"
        pending = wait(lambda: queue_snapshot(1))
    finally:
        status, result = operator.request(
            "/internal/worker/resume",
            {
                "incident_id": str(uuid4()),
                "idempotency_key": str(uuid4()),
                "expected_generation": paused["generation"],
            },
            headers={"Authorization": "Bearer " + secret("recovery_key")},
        )
        assert status == 200 and result["success"]
    identifier = correlation(row)
    empty = wait(lambda: queue_snapshot(0))

    def shipped_logs():
        query = '{service=~"fieldops-web|fieldops-worker"} | json | outbox_id="' + row["id"] + '"'
        parameters = urllib.parse.urlencode(
            {
                "query": query,
                "start": str(int((time.time() - 300) * 1e9)),
                "end": str(time.time_ns()),
                "limit": 100,
            }
        )
        records = internal("http://loki:3100/loki/api/v1/query_range?" + parameters)
        entries = [
            json.loads(line) for stream in records["data"]["result"] for _, line in stream["values"]
        ]
        return {entry["service"] for entry in entries} == {"fieldops-web", "fieldops-worker"}

    # Explore takes a query snapshot when opened. Wait for asynchronous Alloy ingestion
    # before opening that snapshot, rather than hoping it arrived before first rendering.
    wait(shipped_logs)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1100})
        try:
            for snapshot in (pending, empty):
                end_ms = int(float(snapshot["at"]) * 1000)
                page.goto(
                    GRAFANA
                    + "/d/fieldops-operations?"
                    + urllib.parse.urlencode({"from": end_ms - 900000, "to": end_ms})
                )
                backlog = page.locator(
                    'section[data-testid="data-testid Panel header Undelivered (includes failed)"]'
                )
                value = backlog.get_by_role("link", name=str(snapshot["backlog"]), exact=True)
                expect(value).to_be_visible(timeout=30000)
                assert persisted(row["id"])["inbox_count"] == 1
                value.click()
                page.wait_for_url("**/explore?**")
                # With only this event in the window, Grafana also shows its ID
                # in the common-label header. Select the JSON log record itself.
                event = page.get_by_text('"outbox_id": "' + row["id"] + '"', exact=False).first
                expect(event).to_be_visible(timeout=30000)
                event.click()
                link = page.get_by_role("link", name="View Jaeger trace", exact=True).first
                expect(link).to_be_visible(timeout=15000)
                link.click()
                page.wait_for_url("**" + identifier + "**", timeout=30000)
                # Exact operation name excludes the notification_delivered JSON event.
                expect(page.get_by_text("notification.deliver", exact=True).first).to_be_visible(
                    timeout=30000
                )
                snapshot["trace_url"] = page.url
                page.screenshot(
                    path=str(EVIDENCE / f"grafana-log-to-trace-backlog-{snapshot['backlog']}.png"),
                    full_page=True,
                    animations="disabled",
                )
            (EVIDENCE / "browser-link-snapshots.json").write_text(
                json.dumps(
                    {"trace_id": identifier, "outbox_id": row["id"], "snapshots": [pending, empty]},
                    indent=2,
                )
            )
            # Explore does not confer persistent dashboard-write authority on the Viewer.
            denied = page.request.post(
                GRAFANA + "/api/dashboards/db",
                data={
                    "dashboard": {
                        "uid": "t09-denied-" + uuid4().hex,
                        "title": "Synthetic denied write",
                        "schemaVersion": 39,
                        "panels": [],
                    },
                    "overwrite": False,
                },
            )
            assert denied.status == 403
        except BaseException:
            page.screenshot(
                path=str(EVIDENCE / "grafana-link-failure.png"),
                full_page=True,
                animations="disabled",
            )
            raise
        finally:
            browser.close()
