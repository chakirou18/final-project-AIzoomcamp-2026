"""Bounded asynchronous tracing with explicit W3C handoff and no SQL/request payloads."""

import re
from contextlib import contextmanager

from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.trace import SpanKind, Status, StatusCode
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from sqlalchemy import event

from fieldops.trace_context import TraceContext

_tracer = trace.NoOpTracer()
_enabled = False
PROPAGATOR = TraceContextTextMapPropagator()
TABLES = {
    "users",
    "persona_sessions",
    "interventions",
    "intervention_history",
    "notification_outbox",
    "notifications",
    "worker_control",
    "worker_heartbeats",
    "worker_control_audit",
    "worker_resume_actions",
}


def configure(settings, service):
    """One SDK per web/worker process. No exporter is contacted on the business thread."""
    global _tracer, _enabled
    if not settings.telemetry_enabled:
        return None
    # Keep opt-out/test/CLI startup light; protobuf/HTTP exporters are needed only when enabled.
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.sdk.trace.sampling import ALWAYS_ON

    provider = TracerProvider(
        resource=Resource(
            {"service.name": service, "deployment.environment.name": settings.environment}
        ),
        sampler=ALWAYS_ON,
        shutdown_on_exit=False,
    )
    exporter = OTLPSpanExporter(endpoint=settings.otlp_endpoint, timeout=1)
    provider.add_span_processor(
        BatchSpanProcessor(
            exporter,
            max_queue_size=512,
            max_export_batch_size=64,
            schedule_delay_millis=500,
            export_timeout_millis=1500,
        )
    )
    _tracer = provider.get_tracer("fieldops")
    _enabled = True
    return provider


def shutdown(provider):
    global _tracer, _enabled
    if provider is not None:
        provider.shutdown()
        _tracer, _enabled = trace.NoOpTracer(), False


def remote_context(carrier: TraceContext):
    # A fresh Context is essential: never inherit another event or a poll-loop span.
    safe = TraceContext.parse(carrier.traceparent, carrier.tracestate)
    values = {"traceparent": safe.traceparent} if safe.traceparent else {}
    if safe.tracestate:
        values["tracestate"] = safe.tracestate
    return PROPAGATOR.extract(carrier=values, context=Context())


def current_carrier(fallback=None):
    if trace.get_current_span().get_span_context().is_valid:
        values = {}
        PROPAGATOR.inject(values)
        return TraceContext.parse(values.get("traceparent"), values.get("tracestate"))
    return fallback or TraceContext()


@contextmanager
def span(name, *, context=None, kind=SpanKind.INTERNAL, enabled=True, attributes=None):
    tracer = _tracer if enabled else trace.NoOpTracer()
    # SDK's default exception events include exception strings/stack traces: prohibit them.
    with tracer.start_as_current_span(
        name,
        context=context,
        kind=kind,
        attributes=attributes,
        record_exception=False,
        set_status_on_exception=False,
    ) as active:
        try:
            yield active
        except Exception:
            active.set_status(Status(StatusCode.ERROR))
            raise


def log_event(logger, name, **fields):
    # Telemetry/log-storage failures must not turn a committed transaction into a failed request.
    try:
        logger.info(name, extra=fields)
    except Exception:
        pass


def instrument_database(engine):
    if not _enabled:
        return

    def before(connection, cursor, statement, parameters, context, many):
        operation = statement.lstrip().split(None, 1)[0].upper() if statement.strip() else "OTHER"
        if operation not in {"SELECT", "INSERT", "UPDATE", "DELETE"}:
            return
        # Parse only fixed table names; never record SQL text, bindings, DB/user/host or error text.
        match = re.search(r"\b(?:FROM|INTO|UPDATE)\s+([a-z_]+)", statement, re.I)
        table = match[1].lower() if match and match[1].lower() in TABLES else "other"
        context.fieldops_span = _tracer.start_span(
            f"postgresql {operation} {table}",
            kind=SpanKind.CLIENT,
            attributes={
                "db.system.name": "postgresql",
                "db.operation.name": operation,
                "db.collection.name": table,
            },
        )

    def after(connection, cursor, statement, parameters, context, many):
        active = getattr(context, "fieldops_span", None)
        if active is not None:
            active.end()
            context.fieldops_span = None

    def failed(error):
        context = error.execution_context
        active = getattr(context, "fieldops_span", None)
        if active is not None:
            active.set_status(Status(StatusCode.ERROR))
            active.end()
            context.fieldops_span = None

    event.listen(engine, "before_cursor_execute", before)
    event.listen(engine, "after_cursor_execute", after)
    event.listen(engine, "handle_error", failed)
