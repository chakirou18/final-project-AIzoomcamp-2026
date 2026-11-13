"""Executable draft OpenAPI; these workflow routes are NOT mounted in the live app."""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, Query, Security
from fastapi.security import APIKeyCookie, APIKeyHeader

from fieldops.schemas import (
    Assignment,
    ErrorResponse,
    HistoryResponse,
    InterventionCreate,
    InterventionEdit,
    InterventionFilters,
    InterventionResponse,
    NotificationResponse,
    Page,
    PersonaResponse,
    Transition,
)


def lifecycle_openapi():
    draft = FastAPI(title="FieldOps T03 lifecycle contracts (unimplemented)", version="0.1.0")
    cookie = APIKeyCookie(name="fieldops_session", scheme_name="PersonaSession")
    csrf = APIKeyHeader(name="X-CSRF-Token", scheme_name="CSRFToken")

    def identity(token: Annotated[str, Security(cookie)]):
        pass

    def mutation(
        token: Annotated[str, Security(cookie)], csrf_token: Annotated[str, Security(csrf)]
    ):
        pass

    errors = {
        code: {"model": ErrorResponse, "description": label}
        for code, label in {
            401: "Missing, expired or revoked session",
            403: "Wrong role, scope or CSRF token",
            404: "Resource not found",
            409: "Stale row version or illegal lifecycle operation",
            422: "Invalid fields",
            500: "Unexpected server error",
            503: "Database unavailable",
        }.items()
    }
    draft.router.dependencies = [Depends(identity)]
    draft.router.responses = errors

    @draft.get(
        "/api/v1/interventions",
        response_model=Page[InterventionResponse],
        description=(
            "Dispatcher: all jobs; technician: currently assigned jobs only. "
            "Operator denied. Scope BEFORE pagination; created_at DESC, id DESC."
        ),
    )
    def interventions(filters: Annotated[InterventionFilters, Query()]):
        raise NotImplementedError

    @draft.post(
        "/api/v1/interventions",
        response_model=InterventionResponse,
        status_code=201,
        dependencies=[Depends(mutation)],
        description=(
            "Dispatcher only. Optional active technician; atomic history/outbox. "
            "Server owns status, versions and timestamps."
        ),
    )
    def create(payload: InterventionCreate):
        raise NotImplementedError

    @draft.get(
        "/api/v1/interventions/{id}",
        response_model=InterventionResponse,
        description=(
            "Dispatcher or currently assigned technician only; historical inbox "
            "does not grant access."
        ),
    )
    def detail(id: UUID):
        raise NotImplementedError

    @draft.patch(
        "/api/v1/interventions/{id}",
        response_model=InterventionResponse,
        dependencies=[Depends(mutation)],
        description=(
            "Dispatcher only; open/assigned only; expected_version required. No "
            "status/technician fields."
        ),
    )
    def edit(id: UUID, payload: InterventionEdit):
        raise NotImplementedError

    @draft.post(
        "/api/v1/interventions/{id}/assignment",
        response_model=InterventionResponse,
        dependencies=[Depends(mutation)],
        description=(
            "Dispatcher only; open/assigned only; active technician; stale version "
            "409 before same-assignee no-op (200 unchanged)."
        ),
    )
    def assign(id: UUID, payload: Assignment):
        raise NotImplementedError

    @draft.post(
        "/api/v1/interventions/{id}/transitions",
        response_model=InterventionResponse,
        dependencies=[Depends(mutation)],
        description=(
            "Technician starts/completes own job; dispatcher cancels eligible jobs."
            " Operator denied. Illegal/stale transitions 409. Completion requires "
            "resolution."
        ),
    )
    def transition(id: UUID, payload: Transition):
        raise NotImplementedError

    @draft.get(
        "/api/v1/interventions/{id}/history",
        response_model=Page[HistoryResponse],
        description="Dispatcher or currently assigned technician only; newest first, append-only.",
    )
    def history(id: UUID, page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100)):
        raise NotImplementedError

    @draft.get(
        "/api/v1/technicians",
        response_model=list[PersonaResponse],
        description="Dispatcher only; active technicians.",
    )
    def technicians():
        raise NotImplementedError

    @draft.get(
        "/api/v1/notifications",
        response_model=Page[NotificationResponse],
        description=(
            "Technician recipient scope BEFORE pagination, newest first. Historical"
            " summaries survive reassignment; no access to formerly assigned jobs."
        ),
    )
    def inbox(page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100)):
        raise NotImplementedError

    @draft.post(
        "/api/v1/notifications/{id}/read",
        status_code=204,
        dependencies=[Depends(mutation)],
        description="Technician recipient only; idempotent; no response body.",
    )
    def mark_read(id: UUID):
        raise NotImplementedError

    schema = draft.openapi()
    schema["info"]["description"] = (
        "Draft contracts only. All lifecycle paths are unimplemented until "
        "T04/T05/T06. No workflow routes are registered by T03."
    )
    schema["x-implementation-status"] = "contracts-only"
    examples = {
        ("/api/v1/interventions", "post"): {
            "title": "Synthetic boiler inspection",
            "site": "Demo Site A",
            "priority": "high",
        },
        ("/api/v1/interventions/{id}", "patch"): {
            "expected_version": 1,
            "priority": "urgent",
        },
        ("/api/v1/interventions/{id}/assignment", "post"): {
            "expected_version": 1,
            "technician_id": "00000000-0000-4000-8000-000000000001",
        },
        ("/api/v1/interventions/{id}/transitions", "post"): {
            "expected_version": 2,
            "target_status": "completed",
            "resolution": "Synthetic repair",
        },
    }
    for (path, method), example in examples.items():
        schema["paths"][path][method]["requestBody"]["content"]["application/json"]["example"] = (
            example
        )
    # Cookie AND CSRF are both required for every mutation, not alternative credentials.
    for path in schema["paths"].values():
        for method, operation in path.items():
            operation["x-implemented"] = False
            if method in {"post", "patch"}:
                operation["security"] = [{"PersonaSession": [], "CSRFToken": []}]
    return schema


def document_session_boundaries(schema: dict) -> dict:
    """Describe enforced cookie/header/form inputs that Request-based adapters cannot infer."""
    schemes = schema["components"].setdefault("securitySchemes", {})
    schemes["CSRFToken"] = {"type": "apiKey", "in": "header", "name": "X-CSRF-Token"}
    schemes["LoginCSRFCookie"] = {"type": "apiKey", "in": "cookie", "name": "fieldops_login_csrf"}
    paths = schema["paths"]
    for path, operations in paths.items():
        if path.startswith("/api/v1/"):
            for method, operation in operations.items():
                operation["security"] = (
                    [{"PersonaSession": [], "CSRFToken": []}]
                    if method in {"post", "patch"}
                    else [{"PersonaSession": []}]
                )
                operation["x-implemented"] = True
    paths["/auth/login"]["post"]["security"] = [{"LoginCSRFCookie": [], "CSRFToken": []}]
    paths["/auth/logout"]["post"]["security"] = [{"PersonaSession": [], "CSRFToken": []}]
    if "/demo/worker/pause" in paths:
        paths["/demo/worker/pause"]["post"]["security"] = [{"PersonaSession": [], "CSRFToken": []}]
    for path in ["/session/login", "/session/logout"]:
        operation = paths[path]["post"]
        properties = {
            "csrf_token": {"type": "string", "description": "Required matching CSRF token"}
        }
        required = ["csrf_token"]
        if path.endswith("/login"):
            properties.update(
                persona_id={"type": "string", "format": "uuid"},
                operator_secret={"type": "string", "writeOnly": True},
            )
            required.append("persona_id")
            operation["security"] = [{"LoginCSRFCookie": []}]
        else:
            operation["security"] = [{"PersonaSession": []}]
        operation["requestBody"] = {
            "required": True,
            "content": {
                "application/x-www-form-urlencoded": {
                    "schema": {
                        "type": "object",
                        "properties": properties,
                        "required": required,
                        "additionalProperties": False,
                    }
                },
            },
        }
    return schema
