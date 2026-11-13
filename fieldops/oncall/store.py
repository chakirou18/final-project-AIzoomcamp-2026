"""PostgreSQL episode identity, fenced work leases and append-only transition evidence."""

import hashlib
import json
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from fieldops.models import Incident, IncidentAction, IncidentEvent
from fieldops.oncall.contracts import TERMINAL, TRANSITIONS


def event(db, incident, kind, evidence):
    db.add(IncidentEvent(incident_id=incident.id, event_type=kind, evidence=evidence))


def transition(db, row, state, evidence):
    if state not in TRANSITIONS.get(row.state, set()):
        raise ValueError("illegal_incident_transition")
    row.state = state
    event(db, row, state.lower(), evidence)
    if state in TERMINAL:
        row.closed_at = db.scalar(select(func.clock_timestamp()))
        row.lease_token = row.lease_until = None
    if state == "RESOLVED":
        row.resolved_at = row.closed_at


class Store:
    def __init__(self, engine):
        self.engine = engine

    def history(self, identifier):
        """Bounded own-store evidence; never consult business tables with the agent role."""
        with Session(self.engine) as db:
            row = db.get(Incident, identifier)
            action = db.scalar(
                select(IncidentAction).where(IncidentAction.incident_id == identifier)
            )
            names = db.scalars(
                select(IncidentEvent.event_type)
                .where(IncidentEvent.incident_id == identifier)
                .order_by(IncidentEvent.created_at.desc())
                .limit(20)
            ).all()
            return {
                "state": row.state,
                "model_attempts_reserved": row.model_attempts,
                "action_recorded": action is not None,
                "action_success": action.success if action else None,
                "event_count_sampled": len(names),
            }

    def intake(self, payload):
        identifiers = []
        with Session(self.engine) as db, db.begin():
            now = db.scalar(select(func.clock_timestamp()))
            # Serialize capacity checks, never delete old incident evidence.
            db.execute(select(func.pg_advisory_xact_lock(110011)))
            count = db.scalar(select(func.count()).select_from(Incident))
            for alert in payload.alerts:
                start = alert.startsAt
                labels = json.dumps(alert.labels, sort_keys=True)
                episode = hashlib.sha256((labels + start.isoformat()).encode()).hexdigest()
                existing = db.scalar(
                    select(Incident).where(Incident.episode == episode).with_for_update()
                )
                if existing:
                    existing.latest_seen = now
                    if existing.alert_status == "firing" and alert.status == "resolved":
                        existing.alert_status = alert.status
                        event(db, existing, "alert_status", {"status": alert.status})
                    identifiers.append(str(existing.id))
                    continue
                if count >= 10000:
                    raise RuntimeError("incident_capacity")
                identifier = uuid4()
                db.execute(
                    insert(Incident).values(
                        id=identifier,
                        episode=episode,
                        alert_name=alert.labels["alertname"],
                        labels=alert.labels,
                        starts_at=start,
                        alert_status=alert.status,
                        first_seen=now,
                        latest_seen=now,
                        deadline=now + timedelta(seconds=240),
                    )
                )
                row = db.get(Incident, identifier)
                event(
                    db, row, "received", {"alert_name": row.alert_name, "status": row.alert_status}
                )
                identifiers.append(str(identifier))
                count += 1
        return identifiers

    def claim(self):
        with Session(self.engine) as db, db.begin():
            now = db.scalar(select(func.clock_timestamp()))
            row = db.scalar(
                select(Incident)
                .where(
                    Incident.state.not_in(TERMINAL),
                    (Incident.lease_until.is_(None)) | (Incident.lease_until < now),
                )
                .order_by(Incident.last_processed_at, Incident.first_seen)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if not row:
                return None
            row.lease_token = uuid4()
            row.lease_until = now + timedelta(seconds=45)
            return row.id, row.lease_token

    def locked(self, db, identifier, token):
        row = db.scalar(select(Incident).where(Incident.id == identifier).with_for_update())
        now = db.scalar(select(func.clock_timestamp()))
        if (
            row is None
            or row.lease_token != token
            or row.lease_until is None
            or row.lease_until <= now
            or row.state in TERMINAL
        ):
            raise RuntimeError("incident_lease_lost")
        return row
