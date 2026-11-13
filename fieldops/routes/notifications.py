"""JSON inbox contracts; no HTML UI or worker-control endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response

from fieldops.auth import current_user, require_csrf
from fieldops.models import User
from fieldops.schemas import ErrorResponse, NotificationResponse, Page, Pagination
from fieldops.services.notifications import InboxService

router = APIRouter(
    prefix="/api/v1/notifications",
    tags=["notifications"],
    responses={code: {"model": ErrorResponse} for code in (401, 403, 404, 409, 422, 500, 503)},
)


def service(request: Request) -> InboxService:
    return InboxService(request.app.state.engine)


@router.get("", response_model=Page[NotificationResponse])
def inbox(
    pagination: Annotated[Pagination, Query()],
    actor: Annotated[User, Depends(current_user)],
    domain: Annotated[InboxService, Depends(service)],
):
    return domain.list(actor.id, pagination)


@router.post("/{id}/read", status_code=204)
def mark_read(
    id: UUID,
    actor: Annotated[User, Depends(require_csrf)],
    domain: Annotated[InboxService, Depends(service)],
):
    domain.mark_read(actor.id, id)
    return Response(status_code=204)
