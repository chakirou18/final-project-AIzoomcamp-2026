"""One durable stage at a time. External I/O never holds incident transactions."""

from datetime import UTC, datetime, timedelta
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from fieldops.control_schemas import ResumeResult
from fieldops.models import Incident, IncidentAction, IncidentAffected, IncidentEvent, IncidentGrant
from fieldops.oncall.contracts import (
    Diagnosis,
    delivered,
    operational_reason,
    paused_evidence,
    policy,
    safe_time,
)
from fieldops.oncall.provider import ProviderFailure
from fieldops.oncall.store import Store, event, transition
from fieldops.oncall.tools import ToolFailure


class Processor:
    def __init__(self, engine, tools, provider):
        self.engine = engine
        self.store = Store(engine)
        self.tools = tools
        self.provider = provider

    def run_once(self):
        claim = self.store.claim()
        if not claim:
            return False
        identifier, token = claim
        try:
            self.process(identifier, token)
        except (ToolFailure, ProviderFailure, ValueError) as failure:
            reason = (
                "provider_unavailable"
                if isinstance(failure, ProviderFailure)
                else "telemetry_or_schema_unavailable"
            )
            if isinstance(failure, ToolFailure) and str(failure) in {
                "application_database_unavailable",
                "tool_timeout",
                "tool_authorization_denied",
                "tool_http_failure",
                "affected_limit_or_changed_queue",
                "unstable_snapshot",
            }:
                reason = str(failure)
            self.escalate(identifier, token, reason, detail=str(failure)[:80])
        finally:
            with Session(self.engine) as db, db.begin():
                row = db.scalar(select(Incident).where(Incident.id == identifier).with_for_update())
                if row.lease_token == token:
                    row.lease_token = row.lease_until = None
                row.last_processed_at = db.scalar(select(func.clock_timestamp()))
        return True

    def escalate(self, identifier, token, reason, detail=None):
        with Session(self.engine) as db, db.begin():
            row = self.store.locked(db, identifier, token)
            row.escalation_reason = reason
            evidence = {"reason": reason}
            if detail and detail != reason:
                evidence["detail"] = detail  # Typed failure code only, never provider text.
            transition(db, row, "ESCALATED", evidence)

    def process(self, identifier, token):
        with Session(self.engine) as db, db.begin():
            row = self.store.locked(db, identifier, token)
            now = db.scalar(select(func.clock_timestamp()))
            if row.deadline <= now:
                row.escalation_reason = "incident_deadline"
                transition(db, row, "ESCALATED", {"reason": "incident_deadline"})
                return
            state = row.state
            if state == "RECEIVED":
                if row.alert_name != "NotificationQueueDelayed" or row.alert_status != "firing":
                    row.escalation_reason = "unsupported_or_resolved_alert"
                    transition(db, row, "ESCALATED", {"reason": row.escalation_reason})
                else:
                    transition(db, row, "DIAGNOSING", {})
                return
            if state == "DIAGNOSING" and row.model_attempts:
                row.escalation_reason = "interrupted_model_attempt"
                transition(db, row, "ESCALATED", {"reason": row.escalation_reason})
                return
        if state == "DIAGNOSING":
            # Read-only evidence first: an incident the deterministic pre-check rejects never
            # consumes the durable model budget. The reservation commits before the model call.
            snapshot = self.tools.snapshot()
            snapshot["prior"] = self.store.history(identifier)
            captured = datetime.now(UTC)
            if not paused_evidence(snapshot, at=captured):
                self.escalate(identifier, token, operational_reason(snapshot))
                return
            if not self.reserve(identifier, token):
                return
            diagnosis = self.provider.diagnose(identifier, snapshot)
            diagnosis = Diagnosis.model_validate(diagnosis)
            with Session(self.engine) as db, db.begin():
                row = self.store.locked(db, identifier, token)
                row.generation = snapshot["database"]["generation"]
                # Model text is bounded data and is never passed to action dispatch.
                row.diagnosis = diagnosis.model_dump(mode="json")
                row.telemetry = {key: value for key, value in snapshot.items() if key != "affected"}
                for item in snapshot["affected"]:
                    db.add(
                        IncidentAffected(
                            incident_id=identifier,
                            outbox_id=item["id"],
                            recipient_id=item["recipient_id"],
                        )
                    )
                transition(
                    db,
                    row,
                    "DIAGNOSED",
                    {
                        "provider": self.provider.name,
                        "category": diagnosis.category,
                        "affected_count": len(snapshot["affected"]),
                        "generation": row.generation,
                    },
                )
            # The model saw this snapshot; its bounded latency must not make the evidence stale.
            # Action time re-captures fresh evidence before any transmission.
            if not policy(
                diagnosis, snapshot, identifier, snapshot["database"]["generation"], at=captured
            ):
                self.escalate(identifier, token, "diagnosis_policy_denied")
            return
        if state == "DIAGNOSED":
            self.prepare(identifier, token)
            return
        if state == "ACTION_PENDING":
            self.execute(identifier, token)
            return
        if state == "ACTION_IN_PROGRESS":
            self.reconcile(identifier, token)
            return
        if state == "VERIFYING":
            self.verify(identifier, token)

    def reserve(self, identifier, token):
        """Commit the single per-incident attempt and the cumulative provider budget."""
        with Session(self.engine) as db, db.begin():
            row = self.store.locked(db, identifier, token)
            if row.model_attempts:
                row.escalation_reason = "interrupted_model_attempt"
                transition(db, row, "ESCALATED", {"reason": row.escalation_reason})
                return False
            budget = getattr(self.provider, "max_calls", None)
            if budget is not None:
                db.execute(select(func.pg_advisory_xact_lock(110012)))
                reserved = db.scalar(
                    select(func.count())
                    .select_from(IncidentEvent)
                    .where(
                        IncidentEvent.event_type == "model_intent",
                        IncidentEvent.evidence["provider"].astext == self.provider.name,
                    )
                )
                if reserved >= budget:
                    row.escalation_reason = "model_budget_exhausted"
                    transition(db, row, "ESCALATED", {"reason": row.escalation_reason})
                    return False
            row.model_attempts = 1
            event(
                db,
                row,
                "model_intent",
                {
                    "provider": self.provider.name,
                    "attempt": 1,
                    "model": getattr(self.provider, "model", None),
                    "output_token_limit": getattr(self.provider, "token_limit", 0),
                    "durable_call_budget": budget,
                },
            )
            return True

    def prepare(self, identifier, token):
        with Session(self.engine) as db, db.begin():
            row = self.store.locked(db, identifier, token)
            grant = db.scalar(select(IncidentGrant).where(IncidentGrant.incident_id == identifier))
            if not grant:
                return  # Bounded by incident deadline; no implicit delegated authority.
            now = db.scalar(select(func.clock_timestamp()))
            if grant.revoked_at or grant.expires_at <= now or grant.generation != row.generation:
                row.escalation_reason = "authorization_invalid"
                transition(db, row, "ESCALATED", {"reason": row.escalation_reason})
                return
            key = uuid5(NAMESPACE_URL, f"fieldops:{identifier}:{row.generation}:resume")
            db.add(
                IncidentAction(
                    idempotency_key=key,
                    incident_id=identifier,
                    grant_id=grant.id,
                    generation=row.generation,
                )
            )
            transition(
                db,
                row,
                "ACTION_PENDING",
                {"key": str(key), "grant_id": str(grant.id), "generation": row.generation},
            )

    def execute(self, identifier, token):
        snapshot = self.tools.snapshot()
        with Session(self.engine) as db, db.begin():
            row = self.store.locked(db, identifier, token)
            action = db.scalar(
                select(IncidentAction).where(IncidentAction.incident_id == identifier)
            )
            expected = set(
                db.scalars(
                    select(IncidentAffected.outbox_id).where(
                        IncidentAffected.incident_id == identifier
                    )
                )
            )
            from uuid import UUID

            if (
                row.alert_status != "firing"
                or not policy(
                    Diagnosis.model_validate(row.diagnosis), snapshot, identifier, row.generation
                )
                or {UUID(item["id"]) for item in snapshot["affected"]} != expected
            ):
                row.escalation_reason = "changed_operational_state"
                transition(db, row, "ESCALATED", {"reason": row.escalation_reason})
                return
            key, grant, generation = action.idempotency_key, action.grant_id, row.generation
            transition(db, row, "ACTION_IN_PROGRESS", {"key": str(key), "attempt": 1})
        try:
            # HTTP response is only transport evidence. Reconciliation reads the persisted result.
            response = ResumeResult.model_validate(
                self.tools.resume(identifier, generation, key, grant)
            ).model_dump(mode="json")
            with Session(self.engine) as db, db.begin():
                row = self.store.locked(db, identifier, token)
                event(db, row, "action_response", response)
        except ToolFailure:
            with Session(self.engine) as db, db.begin():
                row = self.store.locked(db, identifier, token)
                event(db, row, "action_ambiguous", {"key": str(key)})

    def reconcile(self, identifier, token):
        with Session(self.engine) as db:
            action = db.scalar(
                select(IncidentAction).where(IncidentAction.incident_id == identifier)
            )
            key, generation = action.idempotency_key, action.generation
        result = self.tools.reconcile(key)
        with Session(self.engine) as db, db.begin():
            row = self.store.locked(db, identifier, token)
            action = db.get(IncidentAction, key)
            if (
                not result.get("found")
                or result.get("incident_id") != str(identifier)
                or result.get("generation") != generation
                or result.get("success") is not True
                or action.success is not True
                or action.completed_at is None
            ):
                row.escalation_reason = "action_ambiguous_or_denied"
                transition(db, row, "ESCALATED", {"reason": row.escalation_reason})
                return
            # Deadline independent of intake/authorization, at most 120s positive verification.
            row.verification = {
                "deadline": (
                    db.scalar(select(func.clock_timestamp())) + timedelta(seconds=120)
                ).isoformat(),
                "healthy_since": None,
                "ok": False,
            }
            transition(
                db,
                row,
                "VERIFYING",
                {"key": str(key), "success": True, "recorded_at": result["recorded_at"]},
            )

    def verify(self, identifier, token):
        with Session(self.engine) as db:
            row = db.get(Incident, identifier)
            generation = row.generation
            expected = {
                str(item.outbox_id): str(item.recipient_id)
                for item in db.scalars(
                    select(IncidentAffected).where(IncidentAffected.incident_id == identifier)
                )
            }
        items, snapshot = self.tools.delivery(list(expected))
        healthy = (
            snapshot["environment"] == "local"
            and snapshot["demo_mode"]
            and snapshot["heartbeat_fresh"]
            and not snapshot["paused"]
            and snapshot["generation"] == generation
            and snapshot["undelivered"] == 0
            and snapshot["oldest_age"] == 0
            and delivered(items, expected)
        )
        with Session(self.engine) as db, db.begin():
            row = self.store.locked(db, identifier, token)
            now = db.scalar(select(func.clock_timestamp()))
            verification = dict(row.verification)
            first = verification["healthy_since"]
            verification.update(
                {
                    "checked_at": now.isoformat(),
                    "affected_count": len(expected),
                    "positive_count": sum(item["inbox_count"] for item in items),
                }
            )
            event(
                db,
                row,
                "verification_sample",
                {
                    "healthy": healthy,
                    "affected_count": len(expected),
                    "positive_count": verification["positive_count"],
                },
            )
            if not healthy:
                verification["healthy_since"] = None
                if now >= safe_time(verification["deadline"]):
                    row.escalation_reason = "verification_failed"
                    transition(db, row, "ESCALATED", {"reason": row.escalation_reason})
            elif first and (now - safe_time(first)).total_seconds() >= 5:
                verification["ok"] = True
                row.verification = verification
                transition(db, row, "RESOLVED", verification)
            else:
                verification["healthy_since"] = first or now.isoformat()
            row.verification = verification
