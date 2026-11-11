"""T11 independent audit regressions: evidence freshness versus bounded model latency."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session
from test_t06_postgresql import queue as queue  # fixture dependency of `incident`
from test_t11 import MockProvider, alert_payload, diagnosis, snapshot, state, tick
from test_t11 import incident as incident  # shared PostgreSQL fixture

import fieldops.oncall.contracts as contracts
from fieldops.models import Incident, IncidentEvent
from fieldops.oncall.contracts import paused_evidence, policy
from fieldops.services.controls import heartbeat


def test_policy_freshness_is_anchored_to_capture_time_not_model_latency():
    evidence = snapshot()
    identifier = uuid4()
    captured = datetime.now(UTC)
    evidence["database"]["observed_at"] = (captured - timedelta(seconds=1)).isoformat()
    assert policy(diagnosis(identifier), evidence, identifier, 1, at=captured)
    # Without an anchor, the same evidence evaluated 25 seconds later is stale at action time.
    later = captured + timedelta(seconds=25)
    assert not policy(diagnosis(identifier), evidence, identifier, 1, at=later)
    # A snapshot from the future is never fresh.
    assert not paused_evidence(evidence, 1, at=captured - timedelta(seconds=5))
    # The default anchor remains "now".
    assert policy(diagnosis(identifier), evidence, identifier, 1)


@pytest.mark.integration
def test_bounded_model_latency_over_15s_does_not_deny_fresh_diagnosis(incident, monkeypatch):
    class SlowProvider(MockProvider):
        name = "slow-test-only"

        def diagnose(self, identifier, evidence):
            real = contracts.datetime

            class Later(real):
                @classmethod
                def now(cls, tz=None):
                    return real.now(tz) + timedelta(seconds=20)

            # Time passes only after the fresh capture, exactly like a 20-second model call.
            monkeypatch.setattr(contracts, "datetime", Later)
            return diagnosis(identifier)

    queue, processor, identifier, _ = incident
    processor.provider = SlowProvider()
    tick(processor, 2)
    assert state(queue[0].engine, identifier) == "DIAGNOSED"
    monkeypatch.undo()
    # Action time still re-captures a fresh snapshot; no authorization means no action.
    tick(processor)
    assert state(queue[0].engine, identifier) == "DIAGNOSED"
    assert processor.tools.resume_calls == 0


def reservations(engine, provider):
    with Session(engine) as db:
        return db.scalar(
            select(func.count())
            .select_from(IncidentEvent)
            .where(
                IncidentEvent.event_type == "model_intent",
                IncidentEvent.evidence["provider"].astext == provider,
            )
        )


@pytest.mark.integration
def test_rejected_precheck_never_consumes_the_durable_model_budget(incident):
    class BudgetedProvider(MockProvider):
        name = "budgeted-audit-only"
        max_calls = 1

    queue, processor, identifier, _ = incident
    worker = queue[0]
    engine = worker.engine
    processor.provider = BudgetedProvider()
    with Session(engine) as db, db.begin():
        db.execute(
            text("UPDATE worker_heartbeats SET last_seen=clock_timestamp()-interval '1 minute'")
        )
    tick(processor, 2)
    with Session(engine) as db:
        row = db.get(Incident, identifier)
        assert (row.state, row.escalation_reason) == ("ESCALATED", "worker_unavailable")
        assert row.model_attempts == 0
    assert reservations(engine, "budgeted-audit-only") == 0
    heartbeat(engine, worker.instance_id)
    other = UUID(processor.store.intake(alert_payload())[0])
    tick(processor, 2)
    assert state(engine, other) == "DIAGNOSED"
    assert reservations(engine, "budgeted-audit-only") == 1
    third = UUID(processor.store.intake(alert_payload())[0])
    # The DIAGNOSED incident still rotates through the claim order while it waits for a grant.
    tick(processor, 4)
    with Session(engine) as db:
        assert db.get(Incident, third).escalation_reason == "model_budget_exhausted"
    assert reservations(engine, "budgeted-audit-only") == 1
