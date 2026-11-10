"""Bounded operator and internal worker-control contracts."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, Field

from fieldops.schemas import Contract


class PauseRequest(Contract):
    expected_generation: Annotated[int, Field(strict=True, ge=0, le=2147483647)]
    duration_seconds: Annotated[int, Field(strict=True, ge=1, le=600)] = 600


class ResumeRequest(Contract):
    incident_id: UUID
    expected_generation: Annotated[int, Field(strict=True, ge=1, le=2147483647)]
    idempotency_key: UUID


class ResumeResult(Contract):
    idempotency_key: UUID
    incident_id: UUID
    expected_generation: int
    generation: int
    outcome: Literal["resumed", "generation_mismatch", "not_paused"]
    success: bool
    recorded_at: AwareDatetime


class WorkerStatus(Contract):
    paused: bool
    generation: int
    effective_at: AwareDatetime | None
    expires_at: AwareDatetime | None
    pause_expired: bool
    last_heartbeat: AwareDatetime | None
    last_instance_id: UUID | None
    fresh_instances: int
    heartbeat_state: Literal["fresh", "stale", "missing"]


class Dashboard(Contract):
    observed_at: AwareDatetime
    interventions: dict[str, int]
    unfinished: int
    assigned: int
    pending_interventions: int
    notifications: dict[str, int]
    undelivered: int
    oldest_undelivered_age_seconds: float
    delayed: bool
    worker: WorkerStatus
