"""Intervention lifecycle policy, independent from HTTP and persistence."""

from dataclasses import dataclass, field

from fieldops.schemas import Status


@dataclass
class DomainError(Exception):
    status_code: int
    code: str
    message: str
    fields: dict[str, list[str]] = field(default_factory=dict)


TRANSITIONS = {
    Status.open: frozenset({Status.assigned, Status.cancelled}),
    Status.assigned: frozenset({Status.in_progress, Status.cancelled}),
    Status.in_progress: frozenset({Status.completed, Status.cancelled}),
    Status.completed: frozenset(),
    Status.cancelled: frozenset(),
}


def check_transition(source: str, target: str) -> None:
    if target not in TRANSITIONS.get(source, ()):
        raise DomainError(409, "invalid_transition", "This lifecycle transition is not permitted")


def check_version(current: int, expected: int) -> None:
    if current != expected:
        raise DomainError(
            409,
            "stale_version",
            "Refresh the intervention before retrying",
            {"expected_version": ["The intervention has changed"]},
        )
