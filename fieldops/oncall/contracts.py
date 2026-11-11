"""Validated operational data. Telemetry text has no authority."""

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

ACTION = "resume_notification_worker"
TERMINAL = {"RESOLVED", "ESCALATED"}
TRANSITIONS = {
    "RECEIVED": {"DIAGNOSING", "ESCALATED"},
    "DIAGNOSING": {"DIAGNOSED", "ESCALATED"},
    "DIAGNOSED": {"ACTION_PENDING", "ESCALATED"},
    "ACTION_PENDING": {"ACTION_IN_PROGRESS", "ESCALATED"},
    "ACTION_IN_PROGRESS": {"VERIFYING", "ESCALATED"},
    "VERIFYING": {"RESOLVED", "ESCALATED"},
}


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class Diagnosis(Contract):
    """Field order is the structured-output order: the model restates evidence before deciding."""

    incident_id: UUID
    explanation: str = Field(min_length=1, max_length=1500)
    category: Literal[
        "PAUSED_DELIVERY",
        "WORKER_UNAVAILABLE",
        "DATABASE_UNAVAILABLE",
        "MISSING_TELEMETRY",
        "AMBIGUOUS",
        "UNKNOWN",
    ]
    evidence_references: list[Literal["database", "metrics", "logs", "traces"]] = Field(
        min_length=1, max_length=4
    )
    confidence: float = Field(ge=0, le=1)
    risk: Literal["low", "high", "unknown"]
    proposed_action: Literal["resume_notification_worker", "escalate"]
    required_authorization: Literal["operator_incident_generation"]
    escalate: bool


class OutboxEvidence(Contract):
    id: UUID
    recipient_id: UUID
    status: Literal["pending", "processing", "failed", "delivered"]
    created_at: AwareDatetime
    delivered_at: AwareDatetime | None
    inbox_count: int = Field(ge=0, le=1)
    inbox_recipient: UUID | None
    trace_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{32}$")


class DatabaseEvidence(Contract):
    observed_at: AwareDatetime
    environment: str
    demo_mode: bool
    paused: bool
    generation: int = Field(ge=0)
    pause_expired: bool
    expires_at: AwareDatetime | None
    heartbeat_fresh: bool
    undelivered: int = Field(ge=0)
    oldest_age: float = Field(ge=0)
    items: list[OutboxEvidence] = Field(max_length=100)
    next_cursor: UUID | None


class GrantRequest(Contract):
    expected_generation: int = Field(strict=True, ge=1, le=2147483647)
    duration_seconds: int = Field(default=120, strict=True, ge=1, le=300)


def paused_evidence(
    snapshot: dict, generation: int | None = None, at: datetime | None = None
) -> bool:
    """`at` is the moment the evidence was evaluated as fresh; default is now.

    The diagnosis stage anchors `at` to its capture time so a bounded model call cannot turn
    fresh evidence stale. Action time re-captures a fresh snapshot and uses the default.
    """
    data = snapshot["database"]
    return (
        0 <= ((at or datetime.now(UTC)) - safe_time(data["observed_at"])).total_seconds() <= 15
        and data["environment"] == "local"
        and data["demo_mode"] is True
        and data["paused"] is True
        and data["pause_expired"] is False
        and data["heartbeat_fresh"] is True
        and data["undelivered"] > 0
        and data["oldest_age"] > 60
        and snapshot["monitoring_ok"] is True
        and (generation is None or data["generation"] == generation)
        and bool(snapshot["affected"])
        and len(snapshot["affected"]) == data["undelivered"]
        and all(
            item.get("status") == "pending"
            and item.get("delivered_at") is None
            and item.get("inbox_count") == 0
            for item in snapshot["affected"]
        )
    )


def operational_reason(snapshot: dict) -> str:
    data = snapshot["database"]
    if not data["heartbeat_fresh"]:
        return "worker_unavailable"
    if data["pause_expired"]:
        return "pause_expired_external_recovery"
    if not data["paused"]:
        return "worker_not_paused"
    if data["undelivered"] == 0:
        return "queue_externally_drained"
    if not snapshot["monitoring_ok"]:
        return "missing_telemetry"
    return "unsafe_operational_state"


def policy(
    diagnosis: Diagnosis,
    snapshot: dict,
    incident_id: UUID,
    generation: int,
    at: datetime | None = None,
) -> bool:
    return (
        diagnosis.incident_id == incident_id
        and diagnosis.category == "PAUSED_DELIVERY"
        and diagnosis.proposed_action == ACTION
        and not diagnosis.escalate
        and diagnosis.risk == "low"
        and diagnosis.confidence >= 0.8
        and set(diagnosis.evidence_references) == {"database", "metrics", "logs", "traces"}
        and paused_evidence(snapshot, generation, at)
    )


def delivered(items: list[dict], expected: dict[str, str]) -> bool:
    return (
        len(items) == len(expected)
        and {str(i["id"]) for i in items} == set(expected)
        and all(
            i["status"] == "delivered"
            and i["delivered_at"] is not None
            and i["inbox_count"] == 1
            and str(i["inbox_recipient"]) == expected[str(i["id"])]
            and str(i["recipient_id"]) == expected[str(i["id"])]
            for i in items
        )
    )


def safe_time(value: str | datetime) -> datetime:
    return value if isinstance(value, datetime) else datetime.fromisoformat(value)
