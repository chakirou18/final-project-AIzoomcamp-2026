"""Allowlisted JSON logs. Exception strings, headers and SQL values are not serialized."""

import json
import logging
import re
import sys
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from uuid import UUID

from opentelemetry import trace

EVENTS = {
    "local_credentials_reused",
    "local_credentials_initialized",
    "migrations_completed",
    "synthetic_personas_seeded",
    "bootstrap_failed",
    "application_started",
    "application_stopped",
    "database_unavailable",
    "http_request",
    "unexpected_error",
    "request_failed",
    "delivery_failed",
    "retry_record_unavailable",
    "worker_database_unavailable",
    "worker_started",
    "worker_stopped",
    "configuration_invalid",
    "notification_enqueued",
    "notification_delivered",
    "notification_delivery_failed",
    "trace_context_invalid",
    "logging_storage_unavailable",
}


class JsonFormatter(logging.Formatter):
    def __init__(self, environment: str = "local", service: str = "fieldops-web") -> None:
        super().__init__()
        self.environment = environment
        self.service = service

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "service": self.service,
            "environment": self.environment,
            # Third-party messages can contain connection details; retain only logger identity.
            "event": record.msg
            if record.name.startswith("fieldops")
            and isinstance(record.msg, str)
            and record.msg in EVENTS
            else "library_log",
            "logger": record.name,
            "trace_id": None,
            "span_id": None,
            "outbox_id": None,
            "notification_id": None,
            "attempt": None,
        }
        context = trace.get_current_span().get_span_context()
        if context.is_valid:
            payload["trace_id"] = format(context.trace_id, "032x")
            payload["span_id"] = format(context.span_id, "016x")
        for key in ("outbox_id", "notification_id"):
            value = getattr(record, key, None)
            try:
                payload[key] = str(UUID(str(value))) if value is not None else None
            except ValueError:
                pass
        attempt = getattr(record, "attempt", None)
        if type(attempt) is int and 1 <= attempt <= 5:
            payload["attempt"] = attempt
        for key in ("method", "route", "status_code", "duration_ms", "error_type"):
            if hasattr(record, key):
                value = getattr(record, key)
                if key in {"status_code", "duration_ms"} and isinstance(value, (int, float)):
                    payload[key] = value
                elif key == "method" and value in {
                    "GET",
                    "POST",
                    "PATCH",
                    "PUT",
                    "DELETE",
                    "HEAD",
                    "OPTIONS",
                }:
                    payload[key] = value
                elif (
                    key == "route"
                    and isinstance(value, str)
                    and re.fullmatch(r"[/a-zA-Z0-9_{}:.*<>-]{1,160}", value)
                ):
                    payload[key] = value
                elif (
                    key == "error_type"
                    and isinstance(value, str)
                    and re.fullmatch(r"[A-Za-z_]{1,80}", value)
                ):
                    payload[key] = value
        if record.exc_info and record.exc_info[0]:
            payload["error_type"] = record.exc_info[0].__name__
        return json.dumps(payload)


def configure_logging(
    environment: str, level: str, service: str = "fieldops-web", directory: Path | None = None
) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter(environment, service))
    root = logging.getLogger()
    for existing in root.handlers:
        existing.close()
    root.handlers = [handler]
    if directory:
        try:
            directory.mkdir(parents=True, exist_ok=True)
            file = RotatingFileHandler(
                directory / (service + ".jsonl"),
                maxBytes=5 * 1024 * 1024,
                backupCount=2,
                encoding="utf-8",
            )
            file.setFormatter(JsonFormatter(environment, service))
            root.addHandler(file)
        except OSError:
            logging.getLogger("fieldops.logging").warning("logging_storage_unavailable")
    root.setLevel(level.upper())
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True
    logging.getLogger("uvicorn.access").disabled = True
