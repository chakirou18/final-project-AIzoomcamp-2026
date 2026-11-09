"""Validated API contracts. Workflow handlers are deliberately absent until T04."""

from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, model_validator


class Role(StrEnum):
    dispatcher = "dispatcher"
    technician = "technician"
    operator = "operator"


class Priority(StrEnum):
    low = "low"
    medium = "medium"
    high = "high"
    urgent = "urgent"


class Status(StrEnum):
    open = "open"
    assigned = "assigned"
    in_progress = "in_progress"
    completed = "completed"
    cancelled = "cancelled"


Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
Site = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=250)]
Text = Annotated[str, StringConstraints(max_length=4000)]
Version = Annotated[int, Field(strict=True, ge=1)]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class InterventionCreate(Contract):
    title: Title
    description: Text = ""
    site: Site
    priority: Priority = Priority.medium
    technician_id: UUID | None = None


class Versioned(Contract):
    expected_version: Version


def edit_json_schema(schema: dict) -> None:
    editable = ("title", "description", "site", "priority")
    schema["anyOf"] = [{"required": [name]} for name in editable]
    for name in editable:
        item = schema["properties"][name]
        item.pop("default", None)
        item["anyOf"] = [choice for choice in item["anyOf"] if choice.get("type") != "null"]


class InterventionEdit(Versioned):
    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
        json_schema_extra=edit_json_schema,
    )
    title: Title | None = None
    description: Text | None = None
    site: Site | None = None
    priority: Priority | None = None

    @model_validator(mode="after")
    def require_edit(self):
        supplied = self.model_fields_set - {"expected_version"}
        if not supplied or any(getattr(self, key) is None for key in supplied):
            raise ValueError("Supply at least one nonnull editable field")
        return self


class Assignment(Versioned):
    technician_id: UUID


class Transition(Versioned):
    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
        json_schema_extra={
            "allOf": [
                {
                    "if": {
                        "properties": {"target_status": {"const": "completed"}},
                        "required": ["target_status"],
                    },
                    "then": {
                        "required": ["resolution"],
                        "properties": {
                            "resolution": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 4000,
                                "pattern": r"\S",
                            }
                        },
                    },
                    "else": {"properties": {"resolution": {"type": "null"}}},
                }
            ],
        },
    )
    target_status: Literal[Status.in_progress, Status.completed, Status.cancelled]
    resolution: Text | None = None

    @model_validator(mode="after")
    def validate_target(self):
        if self.target_status not in {Status.in_progress, Status.completed, Status.cancelled}:
            raise ValueError("Use the assignment command to assign; reopening is unavailable")
        if self.target_status == Status.completed:
            if self.resolution is None or not self.resolution.strip():
                raise ValueError("Completion requires a nonblank resolution")
        elif self.resolution is not None:
            raise ValueError("Resolution is accepted only for completion")
        return self


class InterventionResponse(Contract):
    id: UUID
    title: Title
    description: Text
    site: Site
    priority: Priority
    status: Status
    technician_id: UUID | None
    assignment_version: Annotated[int, Field(ge=0)]
    row_version: Version
    resolution: Text | None
    created_at: AwareDatetime
    updated_at: AwareDatetime
    started_at: AwareDatetime | None
    closed_at: AwareDatetime | None


class HistoryResponse(Contract):
    id: UUID
    intervention_id: UUID
    actor_id: UUID | None
    event_type: str
    changed_fields: dict
    created_at: AwareDatetime


class NotificationResponse(Contract):
    id: UUID
    outbox_id: UUID
    intervention_id: UUID
    assignment_version: Annotated[int, Field(gt=0)]
    historical_assignment: bool
    summary: str
    created_at: AwareDatetime
    delivered_at: AwareDatetime
    read_at: AwareDatetime | None


class PersonaResponse(Contract):
    id: UUID
    display_name: str
    role: Role


class ErrorDetail(Contract):
    code: str
    message: str
    fields: dict[str, list[str]] = Field(default_factory=dict)


class ErrorResponse(Contract):
    error: ErrorDetail


class Pagination(Contract):
    page: Annotated[int, Field(ge=1)] = 1
    page_size: Annotated[int, Field(ge=1, le=100)] = 25


class InterventionFilters(Pagination):
    status: Status | None = None
    priority: Priority | None = None
    technician_id: UUID | None = None


class Page[T](Contract):
    items: list[T]
    page: Annotated[int, Field(ge=1)]
    page_size: Annotated[int, Field(ge=1, le=100)]
    total: Annotated[int, Field(ge=0)]
