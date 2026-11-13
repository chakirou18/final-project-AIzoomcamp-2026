"""Leased PostgreSQL poller. Inbox insertion and delivery acknowledgement share one commit."""

import logging
import signal
from dataclasses import dataclass
from datetime import timedelta
from threading import Event
from uuid import UUID, uuid4

from opentelemetry.trace import SpanKind
from sqlalchemy import Engine, and_, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from fieldops.database import create_database_engine
from fieldops.logging import configure_logging
from fieldops.models import Notification, NotificationOutbox
from fieldops.services.controls import gate, heartbeat
from fieldops.settings import Settings
from fieldops.telemetry import configure, log_event, remote_context, shutdown, span
from fieldops.trace_context import TraceContext

logger = logging.getLogger("fieldops.worker")
MAX_ATTEMPTS = 5
LEASE_SECONDS = 30
POLL_SECONDS = 2
BATCH_SIZE = 20


def retry_delay(attempt: int) -> int:
    return min(2 ** min(max(attempt, 1), MAX_ATTEMPTS), 30)


@dataclass(frozen=True)
class Claim:
    event_id: UUID
    token: UUID
    context: TraceContext
    attempt: int | None = None


class LeaseLost(Exception):
    """A completion which lost its lease must roll back any inbox insert."""


class OutboxWorker:
    def __init__(self, engine: Engine):
        self.engine = engine
        self.instance_id = uuid4()

    def claim(self) -> list[Claim]:
        claims = []
        with Session(self.engine) as db, db.begin():
            if gate(db).paused:
                return []
            events = db.scalars(
                select(NotificationOutbox)
                .where(
                    or_(
                        and_(
                            NotificationOutbox.status == "pending",
                            NotificationOutbox.available_at <= func.clock_timestamp(),
                        ),
                        and_(
                            NotificationOutbox.status == "processing",
                            NotificationOutbox.lease_until <= func.clock_timestamp(),
                        ),
                    )
                )
                .order_by(NotificationOutbox.created_at, NotificationOutbox.id)
                .limit(BATCH_SIZE)
                .with_for_update(skip_locked=True)
            ).all()
            now = db.scalar(select(func.clock_timestamp()))
            for event in events:
                if event.attempts >= MAX_ATTEMPTS:
                    event.status = "failed"
                    event.lease_token = event.lease_until = None
                    event.last_error = "attempt_limit_exhausted"
                    continue
                event.attempts += 1
                event.status = "processing"
                event.lease_token = uuid4()
                event.lease_until = now + timedelta(seconds=LEASE_SECONDS)
                event.last_error = None
                claims.append(
                    Claim(
                        event.id,
                        event.lease_token,
                        TraceContext.parse(event.traceparent, event.tracestate),
                        event.attempts,
                    )
                )
        return claims

    def deliver(self, claim: Claim) -> bool:
        with span(
            "notification.deliver",
            context=remote_context(claim.context),
            kind=SpanKind.CONSUMER,
            attributes={
                "fieldops.outbox_id": str(claim.event_id),
                "fieldops.attempt": claim.attempt or 0,
            },
        ):
            if claim.context.traceparent is None:
                log_event(
                    logger, "trace_context_invalid", outbox_id=claim.event_id, attempt=claim.attempt
                )
            try:
                with span("notification.inbox.persist"):
                    result = self._deliver(claim)
                return result
            except Exception:
                log_event(
                    logger,
                    "notification_delivery_failed",
                    outbox_id=claim.event_id,
                    attempt=claim.attempt,
                )
                raise

    def _deliver(self, claim: Claim) -> bool:
        try:
            with Session(self.engine) as db, db.begin():
                if gate(db).paused:
                    return False
                event = db.scalar(
                    select(NotificationOutbox)
                    .where(NotificationOutbox.id == claim.event_id)
                    .with_for_update()
                )
                now = db.scalar(select(func.clock_timestamp()))
                if (
                    event is None
                    or event.status != "processing"
                    or event.lease_token != claim.token
                    or event.lease_until <= now
                ):
                    return False
                db.execute(
                    insert(Notification)
                    .values(
                        id=uuid4(),
                        outbox_id=event.id,
                        recipient_id=event.recipient_id,
                        intervention_id=event.intervention_id,
                        assignment_version=event.assignment_version,
                        created_at=now,
                        delivered_at=now,
                    )
                    .on_conflict_do_nothing(index_elements=[Notification.outbox_id])
                )
                notification = db.scalar(
                    select(Notification).where(Notification.outbox_id == event.id)
                )
                # The composite FK also enforces these identities for a pre-existing inbox row.
                if (
                    notification.recipient_id,
                    notification.intervention_id,
                    notification.assignment_version,
                ) != (event.recipient_id, event.intervention_id, event.assignment_version):
                    raise ValueError("inbox_identity_mismatch")
                # Re-check expiry at the write. Losing the lease rolls back the inbox insert too.
                result = db.execute(
                    update(NotificationOutbox)
                    .where(
                        NotificationOutbox.id == event.id,
                        NotificationOutbox.status == "processing",
                        NotificationOutbox.lease_token == claim.token,
                        NotificationOutbox.lease_until > func.clock_timestamp(),
                    )
                    .values(
                        status="delivered",
                        delivered_at=notification.delivered_at,
                        lease_token=None,
                        lease_until=None,
                        last_error=None,
                    )
                    .execution_options(synchronize_session=False)
                )
                if result.rowcount != 1:
                    raise LeaseLost
                notification_id = notification.id
                attempt = event.attempts
            log_event(
                logger,
                "notification_delivered",
                outbox_id=claim.event_id,
                notification_id=notification_id,
                attempt=attempt,
            )
            return True
        except LeaseLost:
            return False

    def fail(self, claim: Claim) -> bool:
        with Session(self.engine) as db, db.begin():
            event = db.scalar(
                select(NotificationOutbox)
                .where(NotificationOutbox.id == claim.event_id)
                .with_for_update()
            )
            now = db.scalar(select(func.clock_timestamp()))
            if (
                event is None
                or event.status != "processing"
                or event.lease_token != claim.token
                or event.lease_until <= now
            ):
                return False
            # Exception details, SQL and job data must never enter the durable error field.
            result = db.execute(
                update(NotificationOutbox)
                .where(
                    NotificationOutbox.id == event.id,
                    NotificationOutbox.status == "processing",
                    NotificationOutbox.lease_token == claim.token,
                    NotificationOutbox.lease_until > func.clock_timestamp(),
                )
                .values(
                    status="failed" if event.attempts >= MAX_ATTEMPTS else "pending",
                    available_at=now + timedelta(seconds=retry_delay(event.attempts)),
                    lease_token=None,
                    lease_until=None,
                    last_error="delivery_failed",
                )
                .execution_options(synchronize_session=False)
            )
            return result.rowcount == 1

    def run_once(self, stop: Event | None = None) -> int:
        heartbeat(self.engine, self.instance_id)
        delivered = 0
        for claim in self.claim():
            if stop is not None and stop.is_set():
                break  # Remaining claims recover through lease expiry and still consume attempts.
            try:
                delivered += self.deliver(claim)
            except Exception as error:
                logger.warning("delivery_failed", extra={"error_type": type(error).__name__})
                try:
                    self.fail(claim)
                except Exception as failure:
                    logger.warning(
                        "retry_record_unavailable", extra={"error_type": type(failure).__name__}
                    )
        return delivered

    def run(self, stop: Event) -> None:
        failures = 0
        while not stop.is_set():
            try:
                self.run_once(stop)
                failures = 0
            except Exception as error:
                failures = min(failures + 1, MAX_ATTEMPTS)
                logger.warning(
                    "worker_database_unavailable", extra={"error_type": type(error).__name__}
                )
            stop.wait(retry_delay(failures) if failures else POLL_SECONDS)


def main():
    settings = Settings()
    configure_logging(
        settings.environment,
        settings.log_level,
        service="fieldops-worker",
        directory=settings.log_directory,
    )
    provider = configure(settings, "fieldops-worker")
    stop = Event()
    for name in (signal.SIGTERM, signal.SIGINT):
        signal.signal(name, lambda *_: stop.set())
    engine = create_database_engine(settings)
    logger.info("worker_started")
    try:
        OutboxWorker(engine).run(stop)
    finally:
        engine.dispose()
        logger.info("worker_stopped")
        shutdown(provider)


if __name__ == "__main__":
    main()
