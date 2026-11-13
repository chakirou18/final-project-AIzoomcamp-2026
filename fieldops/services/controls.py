"""Persistent control gate; no host process, shell or arbitrary action capabilities."""

from datetime import timedelta
from uuid import UUID

from sqlalchemy import Engine, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from fieldops.control_schemas import (
    Dashboard,
    PauseRequest,
    ResumeRequest,
    ResumeResult,
    WorkerStatus,
)
from fieldops.models import (
    Intervention,
    NotificationOutbox,
    User,
    WorkerControl,
    WorkerControlAudit,
    WorkerHeartbeat,
    WorkerResumeAction,
)
from fieldops.permissions import require_role
from fieldops.policy import DomainError
from fieldops.schemas import Status
from fieldops.services.interventions import InterventionService

CONTROL_KEY = "notification-worker"
HEARTBEAT_SECONDS = 15
PAUSE_RATE_SECONDS = 10


def gate(db: Session, *, shared: bool = True) -> WorkerControl:
    row = db.scalar(
        select(WorkerControl).where(WorkerControl.key == CONTROL_KEY).with_for_update(read=shared)
    )
    if row is None:
        raise RuntimeError("worker_control_uninitialized")
    return row


def audit(db, row, event, principal, outcome, actor_id=None):
    db.add(
        WorkerControlAudit(
            event_type=event,
            generation=row.generation,
            principal=principal,
            outcome=outcome,
            actor_id=actor_id,
        )
    )


def expire(db, row, now):
    # Caller owns the exclusive gate. Expiry is external recovery, never an agent success.
    if row.paused and row.expires_at <= now:
        row.paused = False
        row.effective_at = row.expires_at = None
        row.updated_at = now
        audit(db, row, "auto_expired", "system", "externally_recovered")


def heartbeat(engine: Engine, instance_id: UUID):
    with Session(engine) as db, db.begin():
        row = gate(db, shared=False)
        now = db.scalar(select(func.clock_timestamp()))
        expire(db, row, now)
        db.execute(
            insert(WorkerHeartbeat)
            .values(
                instance_id=instance_id,
                last_seen=now,
                observed_generation=row.generation,
                observed_paused=row.paused,
            )
            .on_conflict_do_update(
                index_elements=[WorkerHeartbeat.instance_id],
                set_={
                    "last_seen": now,
                    "observed_generation": row.generation,
                    "observed_paused": row.paused,
                },
            )
        )


def worker_status(db, now) -> WorkerStatus:
    control = db.get(WorkerControl, CONTROL_KEY)
    if control is None:
        raise RuntimeError("worker_control_uninitialized")
    latest = db.scalar(
        select(WorkerHeartbeat)
        .order_by(WorkerHeartbeat.last_seen.desc(), WorkerHeartbeat.instance_id)
        .limit(1)
    )
    fresh = db.scalar(
        select(func.count())
        .select_from(WorkerHeartbeat)
        .where(
            WorkerHeartbeat.last_seen > now - timedelta(seconds=HEARTBEAT_SECONDS),
            WorkerHeartbeat.last_seen <= now,
        )
    )
    return WorkerStatus(
        paused=control.paused,
        generation=control.generation,
        effective_at=control.effective_at,
        expires_at=control.expires_at,
        pause_expired=bool(control.paused and control.expires_at <= now),
        last_heartbeat=latest.last_seen if latest else None,
        last_instance_id=latest.instance_id if latest else None,
        fresh_instances=fresh,
        heartbeat_state="fresh" if fresh else "stale" if latest else "missing",
    )


class ControlService:
    def __init__(self, engine: Engine):
        self.engine = engine

    def status(self) -> WorkerStatus:
        self.reconcile_expiry()
        with Session(self.engine) as db, db.begin():
            return worker_status(db, db.scalar(select(func.clock_timestamp())))

    def reconcile_expiry(self):
        # No long-held lock or shared->exclusive lock upgrade. Recheck after exclusive acquisition.
        with Session(self.engine) as db:
            due = db.scalar(
                select(WorkerControl.key).where(
                    WorkerControl.key == CONTROL_KEY,
                    WorkerControl.paused.is_(True),
                    WorkerControl.expires_at <= func.clock_timestamp(),
                )
            )
        if due:
            with Session(self.engine) as db, db.begin():
                row = gate(db, shared=False)
                expire(db, row, db.scalar(select(func.clock_timestamp())))

    def pause(self, actor_id: UUID, command: PauseRequest) -> WorkerStatus:
        failure = None
        with Session(self.engine) as db, db.begin():
            InterventionService.actor(db, actor_id, "operator")
            row = gate(db, shared=False)
            # Lock acquisition waits for every active claim/delivery shared gate to COMMIT/ROLLBACK.
            now = db.scalar(select(func.clock_timestamp()))
            expire(db, row, now)
            if row.generation != command.expected_generation:
                failure = (409, "generation_mismatch", "Refresh the worker generation")
            elif row.paused:
                failure = (409, "already_paused", "The worker is already paused")
            elif row.last_pause_at and now < row.last_pause_at + timedelta(
                seconds=PAUSE_RATE_SECONDS
            ):
                failure = (429, "rate_limited", "Pause requests are limited to one per ten seconds")
            if failure:
                audit(db, row, "pause", "operator", failure[1], actor_id)
            else:
                row.generation += 1
                row.paused = True
                row.effective_at = row.last_pause_at = row.updated_at = now
                row.expires_at = now + timedelta(seconds=command.duration_seconds)
                audit(db, row, "pause", "operator", "effective", actor_id)
            db.flush()
            response = worker_status(db, now)
        if failure:
            raise DomainError(*failure)
        return response

    def resume(self, command: ResumeRequest, oncall_context=None) -> ResumeResult:
        with Session(self.engine, expire_on_commit=False) as db, db.begin():
            row = gate(db, shared=False)
            previous = db.get(WorkerResumeAction, command.idempotency_key)
            if previous is not None:
                if (previous.incident_id, previous.expected_generation) != (
                    command.incident_id,
                    command.expected_generation,
                ):
                    raise DomainError(
                        409, "idempotency_conflict", "Key is bound to another request"
                    )
                return ResumeResult.model_validate(previous)
            from fieldops.oncall.web_tools import execution_guard

            incident_action = execution_guard(db, command, row, oncall_context)
            now = db.scalar(select(func.clock_timestamp()))
            expire(db, row, now)
            outcome = (
                "generation_mismatch"
                if row.generation != command.expected_generation
                else ("not_paused" if not row.paused else "resumed")
            )
            if outcome == "resumed":
                row.paused = False
                row.effective_at = row.expires_at = None
                row.updated_at = now
            result = WorkerResumeAction(
                **command.model_dump(),
                generation=row.generation,
                outcome=outcome,
                success=outcome == "resumed",
                recorded_at=now,
            )
            db.add(result)
            if incident_action is not None:
                incident_action.success = result.success
                incident_action.completed_at = now
            audit(db, row, "resume", "agent", outcome)
            db.flush()
            response = ResumeResult.model_validate(result)
        # Exiting db.begin commits all three writes before a successful response escapes.
        return response

    def dashboard(self, actor_id: UUID) -> Dashboard:
        with Session(self.engine) as authorization:
            actor = authorization.get(User, actor_id)
            if actor is None:
                raise DomainError(401, "unauthenticated", "A valid identity is required")
            require_role(actor, "operator")
        self.reconcile_expiry()
        with self.engine.connect().execution_options(
            isolation_level="REPEATABLE READ"
        ) as connection:
            with Session(connection) as db, db.begin():
                # Read authorization shares the snapshot, and holds no write locks on controls.
                actor = db.get(User, actor_id)
                if actor is None:
                    raise DomainError(401, "unauthenticated", "A valid identity is required")
                require_role(actor, "operator")
                now = db.scalar(select(func.clock_timestamp()))
                counts = {state.value: 0 for state in Status}
                counts.update(
                    dict(
                        db.execute(
                            select(Intervention.status, func.count()).group_by(Intervention.status)
                        ).all()
                    )
                )
                deliveries = {
                    state: 0 for state in ("pending", "processing", "failed", "delivered")
                }
                deliveries.update(
                    dict(
                        db.execute(
                            select(NotificationOutbox.status, func.count()).group_by(
                                NotificationOutbox.status
                            )
                        ).all()
                    )
                )
                oldest = db.scalar(
                    select(func.min(NotificationOutbox.created_at)).where(
                        NotificationOutbox.status.in_(["pending", "processing", "failed"])
                    )
                )
                age = max(0.0, (now - oldest).total_seconds()) if oldest else 0.0
                return Dashboard(
                    observed_at=now,
                    interventions=counts,
                    unfinished=sum(counts[s] for s in ("open", "assigned", "in_progress")),
                    assigned=counts["assigned"],
                    pending_interventions=counts["open"],
                    notifications=deliveries,
                    undelivered=sum(deliveries[s] for s in ("pending", "processing", "failed")),
                    oldest_undelivered_age_seconds=age,
                    delayed=age > 60,
                    worker=worker_status(db, now),
                )
