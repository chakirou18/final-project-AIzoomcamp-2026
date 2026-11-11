"""Application-owned read tools and operator grants. Agent DB cannot read business rows."""

from datetime import timedelta
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from fieldops.auth import current_user, fault_simulation_enabled, require_csrf
from fieldops.models import (
    Incident,
    IncidentAction,
    IncidentAffected,
    IncidentEvent,
    IncidentGrant,
    Notification,
    NotificationOutbox,
    User,
    WorkerResumeAction,
)
from fieldops.oncall.contracts import ACTION, DatabaseEvidence, GrantRequest
from fieldops.permissions import require_role
from fieldops.policy import DomainError
from fieldops.routes.controls import internal
from fieldops.services.controls import worker_status

router = APIRouter(tags=["on-call evidence"])
Reader = Annotated[User, Depends(current_user)]
Writer = Annotated[User, Depends(require_csrf)]


def database_evidence(engine, settings, *, cursor=None, ids=None):
    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
        with Session(connection) as db, db.begin():
            now = db.scalar(select(func.clock_timestamp()))
            worker = worker_status(db, now)
            count, oldest = db.execute(
                select(func.count(), func.min(NotificationOutbox.created_at)).where(
                    NotificationOutbox.status != "delivered"
                )
            ).one()
            query = select(NotificationOutbox, Notification).outerjoin(
                Notification, Notification.outbox_id == NotificationOutbox.id
            )
            if ids is not None:
                query = query.where(NotificationOutbox.id.in_(ids))
            else:
                query = query.where(NotificationOutbox.status != "delivered")
                if cursor:
                    query = query.where(NotificationOutbox.id > cursor)
            rows = db.execute(query.order_by(NotificationOutbox.id).limit(101)).all()
            items = []
            for event, inbox in rows[:100]:
                trace = event.traceparent.split("-")[1] if event.traceparent else None
                items.append(
                    {
                        "id": event.id,
                        "recipient_id": event.recipient_id,
                        "status": event.status,
                        "created_at": event.created_at,
                        "delivered_at": event.delivered_at,
                        "inbox_count": int(inbox is not None),
                        "inbox_recipient": inbox.recipient_id if inbox else None,
                        "trace_id": trace,
                    }
                )
            return DatabaseEvidence(
                observed_at=now,
                environment=settings.environment,
                demo_mode=settings.demo_mode,
                paused=worker.paused,
                generation=worker.generation,
                pause_expired=worker.pause_expired,
                expires_at=worker.expires_at,
                heartbeat_fresh=worker.heartbeat_state == "fresh",
                undelivered=count,
                oldest_age=max(0, (now - oldest).total_seconds()) if oldest else 0,
                items=items,
                next_cursor=items[-1]["id"] if len(rows) > 100 else None,
            )


@router.get("/internal/oncall/evidence", dependencies=[Depends(internal)])
def evidence(
    request: Request,
    cursor: UUID | None = None,
    ids: str | None = Query(None, max_length=3700),
):
    try:
        identifiers = [UUID(value) for value in ids.split(",")] if ids else None
    except ValueError:
        raise HTTPException(422, "invalid_event_ids") from None
    if identifiers and len(identifiers) > 100:
        raise HTTPException(422, "event_limit")
    return database_evidence(
        request.app.state.engine, request.app.state.settings, cursor=cursor, ids=identifiers
    )


@router.get("/internal/oncall/actions/{key}", dependencies=[Depends(internal)])
def action_result(key: UUID, request: Request):
    with Session(request.app.state.engine) as db:
        row = db.get(WorkerResumeAction, key)
        if not row:
            return {"found": False}
        return {
            "found": True,
            "incident_id": row.incident_id,
            "generation": row.expected_generation,
            "success": row.success,
            "outcome": row.outcome,
            "recorded_at": row.recorded_at,
        }


@router.get("/api/v1/incidents")
def incidents(request: Request, actor: Reader):
    require_role(actor, "operator")
    with Session(request.app.state.engine) as db:
        return [
            {
                "id": row.id,
                "state": row.state,
                "alert_name": row.alert_name,
                "generation": row.generation,
                "first_seen": row.first_seen,
            }
            for row in db.scalars(select(Incident).order_by(Incident.first_seen.desc()).limit(100))
        ]


@router.get("/api/v1/incidents/{identifier}")
def incident_detail(identifier: UUID, request: Request, actor: Reader):
    require_role(actor, "operator")
    with Session(request.app.state.engine) as db:
        row = db.get(Incident, identifier)
        if not row:
            raise HTTPException(404, "not_found")
        return {
            "id": row.id,
            "state": row.state,
            "alert_name": row.alert_name,
            "generation": row.generation,
            "diagnosis": row.diagnosis,
            "verification": row.verification,
            "escalation_reason": row.escalation_reason,
            "affected": list(
                db.scalars(
                    select(IncidentAffected.outbox_id)
                    .where(IncidentAffected.incident_id == identifier)
                    .order_by(IncidentAffected.outbox_id)
                    .limit(1000)
                )
            ),
            "events": [
                {"type": event.event_type, "at": event.created_at, "evidence": event.evidence}
                for event in db.scalars(
                    select(IncidentEvent)
                    .where(IncidentEvent.incident_id == identifier)
                    .order_by(IncidentEvent.created_at)
                    .limit(200)
                )
            ],
        }


@router.post(
    "/api/v1/incidents/{identifier}/authorize", dependencies=[Depends(fault_simulation_enabled)]
)
def authorize(
    identifier: UUID,
    command: GrantRequest,
    request: Request,
    actor: Writer,
):
    with Session(request.app.state.engine) as db, db.begin():
        user = db.get(User, actor.id)
        if not user or not user.active:
            raise HTTPException(403, "operator_inactive")
        require_role(user, "operator")
        row = db.scalar(select(Incident).where(Incident.id == identifier).with_for_update())
        now = db.scalar(select(func.clock_timestamp()))
        if (
            not row
            or row.state != "DIAGNOSED"
            or row.generation != command.expected_generation
            or row.deadline <= now
            or row.alert_status != "firing"
        ):
            raise HTTPException(409, "incident_not_authorizable")
        existing = db.scalar(select(IncidentGrant).where(IncidentGrant.incident_id == identifier))
        if existing:
            if existing.revoked_at or existing.expires_at <= now:
                raise HTTPException(409, "authorization_expired_or_revoked")
            return {"id": existing.id, "expires_at": existing.expires_at}
        grant = IncidentGrant(
            id=uuid4(),
            incident_id=identifier,
            actor_id=actor.id,
            generation=command.expected_generation,
            action=ACTION,
            created_at=now,
            expires_at=min(row.deadline, now + timedelta(seconds=command.duration_seconds)),
        )
        db.add(grant)
        db.add(
            IncidentEvent(
                incident_id=identifier,
                event_type="operator_authorized",
                evidence={
                    "grant_id": str(grant.id),
                    "actor_id": str(actor.id),
                    "generation": command.expected_generation,
                },
            )
        )
        return {"id": grant.id, "expires_at": grant.expires_at}


@router.post(
    "/api/v1/incidents/{identifier}/revoke", dependencies=[Depends(fault_simulation_enabled)]
)
def revoke(identifier: UUID, request: Request, actor: Writer):
    require_role(actor, "operator")
    with Session(request.app.state.engine) as db, db.begin():
        grant = db.scalar(
            select(IncidentGrant).where(IncidentGrant.incident_id == identifier).with_for_update()
        )
        if not grant:
            raise HTTPException(404, "not_found")
        grant.revoked_at = db.scalar(select(func.clock_timestamp()))
        db.add(
            IncidentEvent(
                incident_id=identifier,
                event_type="operator_revoked",
                evidence={"actor_id": str(actor.id)},
            )
        )
    return {"revoked": True}


def execution_guard(db, command, control, context):
    """Called under the existing exclusive worker gate in the resume transaction."""
    row = db.scalar(select(Incident).where(Incident.id == command.incident_id).with_for_update())
    if row is None:
        if context and len(context) > 3 and context[3]:
            raise DomainError(403, "oncall_incident_required", "Persisted incident required")
        return None
    if context is None or context[0] != "local" or not context[1]:
        raise DomainError(403, "oncall_local_only", "Local demo authorization required")
    grant = db.scalar(
        select(IncidentGrant).where(IncidentGrant.incident_id == row.id).with_for_update()
    )
    action = db.get(IncidentAction, command.idempotency_key)
    now = db.scalar(select(func.clock_timestamp()))
    user = (
        db.scalar(select(User).where(User.id == grant.actor_id).with_for_update(read=True))
        if grant
        else None
    )
    heartbeat = worker_status(db, now)
    if (
        not grant
        or str(grant.id) != context[2]
        or grant.revoked_at
        or grant.expires_at <= now
        or not user
        or not user.active
        or user.role != "operator"
        or not action
        or action.incident_id != row.id
        or action.grant_id != grant.id
        or grant.generation != command.expected_generation
        or action.generation != command.expected_generation
        or row.generation != command.expected_generation
        or row.state != "ACTION_IN_PROGRESS"
        or row.alert_status != "firing"
        or row.deadline <= now
        or not control.paused
        or heartbeat.pause_expired
        or control.generation != command.expected_generation
        or heartbeat.heartbeat_state != "fresh"
    ):
        raise DomainError(409, "oncall_policy_denied", "Incident recovery authorization is invalid")
    affected = db.scalars(
        select(IncidentAffected).where(IncidentAffected.incident_id == row.id)
    ).all()
    events = db.scalars(
        select(NotificationOutbox).where(
            NotificationOutbox.id.in_([item.outbox_id for item in affected])
        )
    ).all()
    if (
        not affected
        or len(events) != len(affected)
        or any(event.status != "pending" or event.delivered_at for event in events)
    ):
        raise DomainError(409, "oncall_external_recovery", "Affected events are no longer pending")
    return action
