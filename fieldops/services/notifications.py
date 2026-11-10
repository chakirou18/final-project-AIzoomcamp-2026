"""Recipient-scoped persistent inbox reads and idempotent mark-read."""

from uuid import UUID

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from fieldops.models import Intervention, Notification
from fieldops.permissions import inbox_scope
from fieldops.policy import DomainError
from fieldops.schemas import NotificationResponse, Page, Pagination
from fieldops.services.interventions import InterventionService


class InboxService:
    def __init__(self, engine: Engine):
        self.engine = engine

    def list(self, actor_id: UUID, pagination: Pagination) -> Page[NotificationResponse]:
        with Session(self.engine) as db, db.begin():
            actor = InterventionService.actor(db, actor_id, "technician")
            statement = inbox_scope(
                select(Notification, Intervention).join(
                    Intervention, Intervention.id == Notification.intervention_id
                ),
                actor,
            )
            total = db.scalar(select(func.count()).select_from(statement.subquery()))
            offset = (pagination.page - 1) * pagination.page_size
            rows = (
                []
                if offset >= total
                else db.execute(
                    statement.order_by(Notification.created_at.desc(), Notification.id.desc())
                    .limit(pagination.page_size)
                    .offset(offset)
                ).all()
            )
            items = [
                NotificationResponse(
                    id=item.id,
                    outbox_id=item.outbox_id,
                    intervention_id=item.intervention_id,
                    assignment_version=item.assignment_version,
                    historical_assignment=(
                        job.technician_id != item.recipient_id
                        or job.assignment_version != item.assignment_version
                    ),
                    # Immutable event identity; never another user's mutable job text.
                    summary=(
                        f"Assignment v{item.assignment_version} "
                        f"for intervention {item.intervention_id}"
                    ),
                    created_at=item.created_at,
                    delivered_at=item.delivered_at,
                    read_at=item.read_at,
                )
                for item, job in rows
            ]
            return Page[NotificationResponse](
                items=items, total=total, page=pagination.page, page_size=pagination.page_size
            )

    def mark_read(self, actor_id: UUID, identifier: UUID) -> None:
        with Session(self.engine) as db, db.begin():
            actor = InterventionService.actor(db, actor_id, "technician")
            item = db.scalar(
                select(Notification).where(Notification.id == identifier).with_for_update()
            )
            if item is None:
                raise DomainError(404, "not_found", "Notification not found")
            if item.recipient_id != actor.id:
                raise DomainError(403, "forbidden", "Notification belongs to another recipient")
            if item.read_at is None:
                item.read_at = max(db.scalar(select(func.clock_timestamp())), item.delivered_at)
