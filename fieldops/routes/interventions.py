"""Versioned JSON adapters; business rules belong to the shared service."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from fieldops.auth import current_user, require_csrf
from fieldops.models import User
from fieldops.schemas import (
    Assignment,
    ErrorResponse,
    HistoryResponse,
    InterventionCreate,
    InterventionEdit,
    InterventionFilters,
    InterventionResponse,
    Page,
    Pagination,
    PersonaResponse,
    Transition,
)
from fieldops.services.interventions import InterventionService
from fieldops.trace_context import TraceContext

router = APIRouter(
    prefix="/api/v1",
    tags=["interventions"],
    responses={code: {"model": ErrorResponse} for code in (401, 403, 404, 409, 422, 500, 503)},
)
Reader = Annotated[User, Depends(current_user)]
Writer = Annotated[User, Depends(require_csrf)]


def service(request: Request) -> InterventionService:
    return InterventionService(request.app.state.engine)


Service = Annotated[InterventionService, Depends(service)]


@router.post("/interventions", status_code=201, response_model=InterventionResponse)
def create(payload: InterventionCreate, actor: Writer, domain: Service, request: Request):
    return domain.create(
        actor.id,
        payload,
        TraceContext.parse(request.headers.get("traceparent"), request.headers.get("tracestate")),
    )


@router.get("/interventions", response_model=Page[InterventionResponse])
def list_jobs(filters: Annotated[InterventionFilters, Query()], actor: Reader, domain: Service):
    return domain.list(actor.id, filters)


@router.get("/interventions/{id}", response_model=InterventionResponse)
def detail(id: UUID, actor: Reader, domain: Service):
    return domain.detail(actor.id, id)


@router.patch("/interventions/{id}", response_model=InterventionResponse)
def edit(id: UUID, payload: InterventionEdit, actor: Writer, domain: Service):
    return domain.edit(actor.id, id, payload)


@router.post("/interventions/{id}/assignment", response_model=InterventionResponse)
def assign(id: UUID, payload: Assignment, actor: Writer, domain: Service, request: Request):
    return domain.assign(
        actor.id,
        id,
        payload,
        TraceContext.parse(request.headers.get("traceparent"), request.headers.get("tracestate")),
    )


@router.post("/interventions/{id}/transitions", response_model=InterventionResponse)
def transition(id: UUID, payload: Transition, actor: Writer, domain: Service):
    return domain.transition(actor.id, id, payload)


@router.get("/interventions/{id}/history", response_model=Page[HistoryResponse])
def history(id: UUID, pagination: Annotated[Pagination, Query()], actor: Reader, domain: Service):
    return domain.list_history(actor.id, id, pagination)


@router.get("/technicians", response_model=list[PersonaResponse])
def technicians(actor: Reader, domain: Service):
    return domain.list_technicians(actor.id)
