"""Allowlisted JSON logs. Exception strings, headers and SQL values are not serialized."""

import json
import logging
import sys
from datetime import UTC, datetime


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
            "event": record.getMessage() if record.name.startswith("fieldops") else "library_log",
            "logger": record.name,
            "trace_id": None,  # W3C instrumentation belongs to T09; do not fabricate trace IDs.
            "span_id": None,
        }
        for key in ("method", "route", "status_code", "duration_ms", "error_type"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info and record.exc_info[0]:
            payload["error_type"] = record.exc_info[0].__name__
        return json.dumps(payload)


def configure_logging(environment: str, level: str, service: str = "fieldops-web") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter(environment, service))
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True
    logging.getLogger("uvicorn.access").disabled = True
