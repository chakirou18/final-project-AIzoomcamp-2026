"""Privacy, actual SDK context boundaries and real persisted queue metric regressions."""

import json
import logging
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind
from prometheus_client.parser import text_string_to_metric_families
from sqlalchemy import text
from test_t06_postgresql import assignment, snapshot
from test_t06_postgresql import queue as queue

from fieldops import telemetry
from fieldops.logging import JsonFormatter
from fieldops.main import create_app
from fieldops.metrics import Metrics
from fieldops.trace_context import TraceContext


@pytest.fixture
def spans(monkeypatch):
    provider = TracerProvider(shutdown_on_exit=False)
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(telemetry, "_tracer", provider.get_tracer("fieldops-test"))
    yield exporter
    provider.shutdown()


def values(payload):
    return {
        (sample.name, tuple(sorted(sample.labels.items()))): sample.value
        for family in text_string_to_metric_families(payload)
        for sample in family.samples
    }


def test_w3c_delivery_uses_persisted_remote_parent_without_cross_event_leak(spans):
    carriers = []
    for _ in range(2):
        with telemetry.span("HTTP", kind=SpanKind.SERVER):
            with telemetry.span("notification.enqueue", kind=SpanKind.PRODUCER):
                carriers.append(telemetry.current_carrier())
    for carrier in carriers:
        extracted = telemetry.remote_context(carrier)
        assert trace.get_current_span(extracted).get_span_context().is_remote
        with telemetry.span("unrelated.worker.poll"):
            for _ in range(2):
                with telemetry.span("notification.deliver", context=extracted):
                    assert (
                        telemetry.current_carrier().traceparent.split("-")[1]
                        == carrier.traceparent.split("-")[1]
                    )
        assert not trace.get_current_span().get_span_context().is_valid
    recorded = spans.get_finished_spans()
    assert carriers[0].traceparent.split("-")[1] != carriers[1].traceparent.split("-")[1]
    deliveries = [s for s in recorded if s.name == "notification.deliver"]
    assert len({s.context.span_id for s in deliveries}) == 4
    for s in deliveries:
        carrier = next(
            c for c in carriers if c.traceparent.split("-")[1] == format(s.context.trace_id, "032x")
        )
        assert format(s.parent.span_id, "016x") == carrier.traceparent.split("-")[2]


def test_invalid_context_cannot_inherit_another_event(spans):
    with telemetry.span("another.event") as unrelated:
        with telemetry.span(
            "notification.deliver",
            context=telemetry.remote_context(TraceContext("invalid", "secret=data")),
        ) as delivery:
            assert delivery.get_span_context().trace_id != unrelated.get_span_context().trace_id
    recorded = [s for s in spans.get_finished_spans() if s.name == "notification.deliver"]
    assert recorded[0].parent is None


@pytest.mark.parametrize("flags", ["01", "03"])
def test_w3c_carriers_accept_current_sdk_random_id_flag(flags):
    parent = "00-0123456789abcdef0123456789abcdef-0123456789abcdef-" + flags
    assert TraceContext.parse(parent).traceparent == parent
    assert (
        trace.get_current_span(telemetry.remote_context(TraceContext(parent)))
        .get_span_context()
        .is_remote
    )


@pytest.mark.parametrize(
    "field",
    [
        "password",
        "authorization",
        "cookie",
        "csrf_token",
        "site",
        "description",
        "sql",
        "outbox_id",
        "notification_id",
        "attempt",
    ],
)
def test_log_sentinel_fields_are_redacted(field):
    sentinel = "SYNTHETIC-T09-DO-NOT-LOG"
    record = logging.LogRecord("fieldops.test", logging.INFO, "", 1, "request_failed", (), None)
    setattr(record, field, sentinel)
    assert sentinel not in JsonFormatter().format(record)


def test_log_uses_real_active_ids_and_discards_unknown_messages(spans):
    record = logging.LogRecord(
        "fieldops.test", logging.INFO, "", 1, "notification_delivered", (), None
    )
    record.outbox_id = uuid4()
    record.notification_id = uuid4()
    record.attempt = 2
    with telemetry.span("notification.deliver") as active:
        result = json.loads(JsonFormatter(service="fieldops-worker").format(record))
        assert result["trace_id"] == format(active.get_span_context().trace_id, "032x")
        assert result["span_id"] == format(active.get_span_context().span_id, "016x")
    assert result["outbox_id"] == str(record.outbox_id) and result["attempt"] == 2
    record.msg = "SYNTHETIC-CREDENTIAL-IN-MESSAGE"
    assert record.msg not in JsonFormatter().format(record)


def test_exception_events_cannot_capture_customer_or_sql_text(spans):
    with pytest.raises(RuntimeError):
        with telemetry.span("operation"):
            raise RuntimeError("SYNTHETIC-CUSTOMER-DESCRIPTION")
    result = spans.get_finished_spans()[0]
    assert result.status.status_code.name == "ERROR" and not result.events


@pytest.mark.integration
@pytest.mark.parametrize("state", ["pending", "processing", "failed"])
def test_metrics_include_all_undelivered_states_and_database_age(queue, state):
    worker, _, _ = queue
    _, identifier = assignment(queue)
    if state != "pending":
        (claim,) = worker.claim()
        if state == "failed":
            with worker.engine.begin() as db:
                db.execute(
                    text("UPDATE notification_outbox SET attempts=5 WHERE id=:id"),
                    {"id": identifier},
                )
            assert worker.fail(claim)
    with worker.engine.begin() as db:
        db.execute(
            text(
                "UPDATE notification_outbox SET created_at=clock_timestamp()-interval '90s' "
                "WHERE id=:id"
            ),
            {"id": identifier},
        )
    samples = values(Metrics(worker.engine).render().decode())
    assert samples[("fieldops_notifications_undelivered", ())] == 1
    assert 89 <= samples[("fieldops_notification_oldest_undelivered_age_seconds", ())] < 100
    assert samples[("fieldops_notification_events", (("status", state),))] == 1
    assert samples[("fieldops_metrics_database_up", ())] == 1
    if state == "failed":
        assert samples[("fieldops_notifications_failed_total", ())] == 1


@pytest.mark.integration
def test_empty_queue_and_persisted_delivery_histogram_survive_new_registry(queue):
    worker, _, _ = queue
    samples = values(Metrics(worker.engine).render().decode())
    assert samples[("fieldops_notification_oldest_undelivered_age_seconds", ())] == 0
    _, identifier = assignment(queue)
    assert worker.run_once() == 1 and snapshot(worker, identifier)["inbox"] is not None
    samples = values(Metrics(worker.engine).render().decode())
    assert samples[("fieldops_notifications_undelivered", ())] == 0
    assert samples[("fieldops_notifications_delivered_total", ())] == 1
    assert samples[("fieldops_notification_delivery_latency_seconds_count", ())] == 1
    assert (
        samples[("fieldops_notification_delivery_latency_seconds_bucket", (("le", "+Inf"),))] == 1
    )


@pytest.mark.integration
def test_real_postgresql_spans_are_enqueue_and_inbox_children_without_sql_values(
    queue, spans, monkeypatch
):
    worker, _, _ = queue
    monkeypatch.setattr(telemetry, "_enabled", True)
    telemetry.instrument_database(worker.engine)
    with telemetry.span("HTTP"):
        _, identifier = assignment(queue)
    (claim,) = worker.claim()
    assert worker.deliver(claim)
    recorded = spans.get_finished_spans()
    enqueue = next(s for s in recorded if s.name == "notification.enqueue")
    delivery = next(s for s in recorded if s.name == "notification.deliver")
    assert enqueue.context.trace_id == delivery.context.trace_id
    assert delivery.parent.span_id == enqueue.context.span_id
    for name in ("postgresql INSERT notification_outbox", "postgresql INSERT notifications"):
        statement = next(s for s in recorded if s.name == name)
        assert statement.context.trace_id == enqueue.context.trace_id
        assert "db.statement" not in statement.attributes
    assert snapshot(worker, identifier)["status"] == "delivered"


@pytest.mark.integration
def test_http_traces_and_metric_labels_never_capture_headers_queries_or_ids(queue, spans):
    _, _, settings = queue
    sentinel = "SYNTHETIC-HTTP-SECRET"
    with TestClient(create_app(settings)) as client:
        for _ in range(3):
            assert (
                client.get(
                    "/does-not-exist/" + str(uuid4()) + "?secret=" + sentinel,
                    headers={"Authorization": sentinel, "Cookie": sentinel},
                ).status_code
                == 404
            )
        payload = client.get("/metrics").text
    assert sentinel not in payload
    errors = [
        sample
        for family in text_string_to_metric_families(payload)
        for sample in family.samples
        if sample.name == "fieldops_http_requests_total"
        and sample.labels.get("status_class") == "4xx"
    ]
    assert len(errors) == 1 and errors[0].value == 3
    assert errors[0].labels["route"] == "<unmatched>"
    for family in text_string_to_metric_families(payload):
        for sample in family.samples:
            assert set(sample.labels) <= {"method", "route", "status_class", "status", "le"}
    encoded = str([(s.attributes, s.events) for s in spans.get_finished_spans()])
    assert sentinel not in encoded
