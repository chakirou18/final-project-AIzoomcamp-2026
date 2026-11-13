"""Explicit deterministic integration helper. This is never a real-model result."""

import sys
import time
from uuid import UUID

from sqlalchemy.orm import Session

from fieldops.database import create_database_engine
from fieldops.models import Incident
from fieldops.oncall.contracts import Diagnosis
from fieldops.oncall.processor import Processor
from fieldops.oncall.runtime import AgentSettings
from fieldops.oncall.tools import Tools


class MockProvider:
    name = "deterministic-test-only"

    def diagnose(self, identifier, evidence):
        return Diagnosis(
            incident_id=identifier,
            category="PAUSED_DELIVERY",
            evidence_references=["database", "metrics", "logs", "traces"],
            confidence=0.95,
            proposed_action="resume_notification_worker",
            explanation="Deterministic test diagnosis using live operational tools",
            risk="low",
            required_authorization="operator_incident_generation",
            escalate=False,
        )


def main():
    identifier = UUID(sys.argv[1])
    expected_state = sys.argv[2]
    settings = AgentSettings()
    assert settings.environment == "local"
    engine = create_database_engine(settings)
    tools = Tools(
        settings.oncall_web_url,
        settings.oncall_recovery_key_file.read_text().strip(),
        settings.oncall_prometheus_url,
        settings.oncall_loki_url,
        settings.oncall_jaeger_url,
    )
    processor = Processor(engine, tools, MockProvider())
    deadline = time.monotonic() + 160
    try:
        while time.monotonic() < deadline:
            processor.run_once()
            with Session(engine) as db:
                row = db.get(Incident, identifier)
                if row.state == expected_state:
                    print("DETERMINISTIC_TEST_STATE", row.state, flush=True)
                    return
                if row.state == "ESCALATED":
                    raise RuntimeError(row.escalation_reason)
            time.sleep(0.5)
        raise RuntimeError("bounded_test_deadline")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
