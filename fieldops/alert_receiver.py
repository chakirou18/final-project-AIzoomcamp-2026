"""Private T10 test evidence sink. No business DB, control API or remediation authority."""

import hashlib
import hmac
import json
import os
import sqlite3
import sys
from contextlib import asynccontextmanager, closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import UUID

from fastapi import FastAPI, HTTPException, Query, Request
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError, field_validator
from starlette.concurrency import run_in_threadpool

ALERTS = {
    "NotificationQueueDelayed": "warning",
    "NotificationMetricsMissing": "critical",
    "NotificationScrapeFailure": "critical",
    "NotificationDatabaseUnavailable": "critical",
}
MAX_BYTES = 65536
MAX_ROWS = 10000


class Alert(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    status: Literal["firing", "resolved"]
    labels: dict[str, str]
    startsAt: AwareDatetime
    endsAt: AwareDatetime
    annotations: dict[str, str] = Field(default_factory=dict, max_length=8)
    generatorURL: str = Field(default="", max_length=2048)
    fingerprint: str = Field(default="", pattern=r"^[0-9a-f]{0,64}$")

    @field_validator("startsAt", "endsAt")
    @classmethod
    def utc_timestamp(cls, value: datetime) -> datetime:
        try:
            return value.astimezone(UTC)
        except OverflowError:
            raise ValueError("Timestamp outside UTC range") from None

    @field_validator("labels")
    @classmethod
    def bounded_labels(cls, value):
        name = value.get("alertname")
        if (
            set(value) != {"alertname", "severity", "service", "environment"}
            or name not in ALERTS
            or value["severity"] != ALERTS[name]
            or value["service"] != "fieldops-web"
            or value["environment"] != "local"
        ):
            raise ValueError("Unsupported alert labels")
        return value


class Webhook(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    version: Literal["4"]
    receiver: Literal["fieldops-test-evidence"]
    status: Literal["firing", "resolved"]
    alerts: list[Alert] = Field(min_length=1, max_length=20)
    groupLabels: dict[str, str] = Field(default_factory=dict, max_length=8)
    commonLabels: dict[str, str] = Field(default_factory=dict, max_length=8)
    commonAnnotations: dict[str, str] = Field(default_factory=dict, max_length=8)
    # Alertmanager 0.35 template.Data fields; accepted but never persisted as untrusted text.
    routeLabels: dict[str, str] = Field(default_factory=dict, max_length=8)
    notification_reason: str = Field(default="", max_length=128)
    externalURL: str = Field(default="", max_length=2048)
    groupKey: str = Field(default="", max_length=1024)
    truncatedAlerts: int = Field(default=0, ge=0, le=1000000)


def connect(path):
    db = sqlite3.connect(path, timeout=2)
    db.row_factory = sqlite3.Row
    return db


def initialize(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(connect(path)) as db, db:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute(
            "CREATE TABLE IF NOT EXISTS receipts ("
            "id INTEGER PRIMARY KEY, episode TEXT NOT NULL, status TEXT NOT NULL, "
            "alertname TEXT NOT NULL, labels TEXT NOT NULL, starts_at TEXT NOT NULL, "
            "ends_at TEXT NOT NULL, received_at TEXT NOT NULL, run_id TEXT, "
            "UNIQUE(episode,status))"
        )


def persist(path, payload, run_id):
    with closing(connect(path)) as db, db:
        # Serialize capacity check + writes, even for concurrent webhook retries.
        db.execute("BEGIN IMMEDIATE")
        count = db.execute("SELECT count(*) FROM receipts").fetchone()[0]
        for alert in payload.alerts:
            labels = json.dumps(alert.labels, sort_keys=True)
            start = alert.startsAt.isoformat()
            episode = hashlib.sha256((labels + start).encode()).hexdigest()
            if db.execute(
                "SELECT 1 FROM receipts WHERE episode=? AND status=?", (episode, alert.status)
            ).fetchone():
                continue
            if count >= MAX_ROWS:
                raise HTTPException(507, "Evidence capacity reached; operator inspection required")
            db.execute(
                "INSERT INTO receipts (episode,status,alertname,labels,starts_at,ends_at,"
                "received_at,run_id) VALUES (?,?,?,?,?,?,?,?)",
                (
                    episode,
                    alert.status,
                    alert.labels["alertname"],
                    labels,
                    start,
                    alert.endsAt.isoformat(),
                    datetime.now(UTC).isoformat(),
                    run_id,
                ),
            )
            count += 1
    # Acknowledgement means durable receipt only. It never means incident recovery.


def create_app(path=None, webhook_key=None, reader_key=None, run_id=None):
    @asynccontextmanager
    async def lifespan(app):
        app.state.path = Path(
            path or os.getenv("FIELDOPS_ALERT_EVIDENCE", "/var/lib/alerts/receipts.sqlite3")
        )
        app.state.webhook = webhook_key or Path("/run/fieldops-webhook/key").read_text().strip()
        app.state.reader = reader_key or Path("/run/fieldops-alert-reader/key").read_text().strip()
        if min(len(app.state.webhook), len(app.state.reader)) < 32 or hmac.compare_digest(
            app.state.webhook, app.state.reader
        ):
            raise RuntimeError("Distinct strong receiver credentials required")
        value = run_id or os.getenv("FIELDOPS_ALERT_RUN_ID")
        app.state.run_id = str(UUID(value)) if value else None
        initialize(app.state.path)
        app.state.incidents = None
        if os.getenv("FIELDOPS_ONCALL_INTAKE") == "true":
            from fieldops.database import create_database_engine
            from fieldops.oncall.store import Store
            from fieldops.settings import Settings

            app.state.incidents = Store(create_database_engine(Settings()))
        try:
            yield
        finally:
            if app.state.incidents:
                app.state.incidents.engine.dispose()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    def authorize(request, expected):
        supplied = request.headers.get("authorization", "")
        if not hmac.compare_digest(supplied.encode(), ("Bearer " + expected).encode()):
            raise HTTPException(401, "unauthenticated")

    @app.get("/health/ready")
    def ready():
        try:
            with closing(connect(app.state.path)) as db:
                db.execute("SELECT 1 FROM receipts LIMIT 1")
        except sqlite3.Error:
            raise HTTPException(503, "Evidence storage unavailable") from None
        return {"status": "ready"}

    @app.post("/internal/alerts", status_code=202)
    async def receive(request: Request):
        authorize(request, app.state.webhook)
        if request.headers.get("content-type", "").split(";")[0] != "application/json":
            raise HTTPException(415, "JSON required")
        raw = bytearray()
        async for chunk in request.stream():
            if len(raw) + len(chunk) > MAX_BYTES:
                raise HTTPException(413, "Payload too large")
            raw.extend(chunk)
        try:
            payload = Webhook.model_validate_json(raw)
        except ValidationError as error:
            # Schema diagnostics only: never log raw inputs, annotations, keys or values.
            allowed = set(Webhook.model_fields) | set(Alert.model_fields)
            diagnostics = [
                {
                    "type": item["type"],
                    "path": [
                        part if isinstance(part, int) or part in allowed else "<unrecognized>"
                        for part in item["loc"]
                    ],
                }
                for item in error.errors(include_input=False, include_url=False)[:8]
            ]
            print(json.dumps({"event": "alert_payload_invalid", "errors": diagnostics}), flush=True)
            raise HTTPException(422, "Invalid alert payload") from None
        except ValueError:
            raise HTTPException(422, "Invalid alert payload") from None
        try:
            if app.state.incidents:
                await run_in_threadpool(app.state.incidents.intake, payload)
            await run_in_threadpool(persist, app.state.path, payload, app.state.run_id)
        except sqlite3.Error:
            raise HTTPException(503, "Evidence storage unavailable") from None
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(503, "Incident storage unavailable") from None
        return {"receipt": "persisted", "recovery": "not_attempted"}

    @app.get("/internal/receipts")
    def receipts(
        request: Request,
        after_id: int = Query(0, ge=0, le=2**63 - 1),
        limit: int = Query(100, ge=1, le=100),
    ):
        authorize(request, app.state.reader)
        try:
            with closing(connect(app.state.path)) as db:
                rows = db.execute(
                    "SELECT * FROM receipts WHERE id>? ORDER BY id LIMIT ?", (after_id, limit)
                ).fetchall()
        except sqlite3.Error:
            raise HTTPException(503, "Evidence storage unavailable") from None
        return {"receipts": [{**dict(row), "labels": json.loads(row["labels"])} for row in rows]}

    return app


def main():
    if sys.argv[1:] == ["initialize"]:
        # Separate volumes; Alertmanager receives only the webhook key, never read/control keys.
        from fieldops.bootstrap import initialize_credentials

        for directory in ["/run/fieldops-webhook", "/run/fieldops-alert-reader"]:
            initialize_credentials(Path(directory), "key")
        directory = Path("/var/lib/alerts")
        directory.mkdir(parents=True, exist_ok=True)
        os.chown(directory, 10001, 10001)
        os.chmod(directory, 0o700)
        return
    import uvicorn

    uvicorn.run(create_app(), host="0.0.0.0", port=8010, access_log=False, log_level="warning")


if __name__ == "__main__":
    main()
