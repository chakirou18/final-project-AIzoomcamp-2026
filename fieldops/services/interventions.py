"""Transaction-owning intervention services shared by JSON and future HTML routes."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from fieldops.models import Intervention, InterventionHistory, NotificationOutbox, User
from fieldops.permissions import intervention_scope, require_intervention_access, require_role
from fieldops.policy import DomainError, check_transition, check_version
from fieldops.schemas import (
    Assignment,
    HistoryResponse,
    InterventionCreate,
    InterventionEdit,
    InterventionFilters,
    InterventionResponse,
    Page,
    Pagination,
    PersonaResponse,
    Status,
    Transition,
)


class InterventionService:
    def __init__(self, engine: Engine):
        self.engine = engine

    @staticmethod
    def actor(db: Session, actor_id: UUID, *roles: str) -> User:
        # Resolve role/active state inside the transaction; never trust caller-supplied role data.
        actor = db.scalar(select(User).where(User.id == actor_id).with_for_update(read=True))
        if actor is None:
            raise DomainError(401, "unauthenticated", "A valid identity is required")
        require_role(actor, *roles)
        return actor

    @staticmethod
    def job(
        db: Session, identifier: UUID, actor: User, *, lock: bool = False, share_lock: bool = False
    ) -> Intervention:
        statement = select(Intervention).where(Intervention.id == identifier)
        if lock or share_lock:
            statement = statement.with_for_update(read=share_lock)
        job = db.scalar(statement)
        if job is None:
            raise DomainError(404, "not_found", "Intervention not found")
        require_intervention_access(actor, job.technician_id)
        return job

    @staticmethod
    def now(db: Session, job: Intervention | None = None) -> datetime:
        # PostgreSQL transaction now() predates lock waits. Clock time is sampled AFTER the lock.
        value = db.scalar(select(func.clock_timestamp()))
        if job is not None:
            value = max(value, job.updated_at, job.created_at)
        return value

    @staticmethod
    def snapshot(job: Intervention) -> dict:
        return InterventionResponse.model_validate(job).model_dump(mode="json")

    @staticmethod
    def history(
        db: Session, job: Intervention, actor: User, event_type: str, before: dict, at: datetime
    ) -> None:
        after = InterventionService.snapshot(job)
        changed = {
            key: {"old": before.get(key), "new": value}
            for key, value in after.items()
            if before.get(key) != value
        }
        db.add(
            InterventionHistory(
                intervention_id=job.id,
                actor_id=actor.id,
                event_type=event_type,
                changed_fields=changed,
                created_at=at,
            )
        )

    @staticmethod
    def technician(db: Session, identifier: UUID) -> User:
        user = db.scalar(select(User).where(User.id == identifier).with_for_update(read=True))
        if user is None or not user.active or user.role != "technician":
            raise DomainError(
                422,
                "validation_error",
                "Choose an active technician",
                {"technician_id": ["An active technician is required"]},
            )
        return user

    def assign_in_transaction(
        self,
        db: Session,
        job: Intervention,
        actor: User,
        technician_id: UUID,
        *,
        initial: bool = False,
    ) -> None:
        if job.status not in {Status.open, Status.assigned}:
            raise DomainError(
                409, "invalid_transition", "Only open or assigned jobs can be assigned"
            )
        self.technician(db, technician_id)
        if job.technician_id == technician_id:
            return
        before = self.snapshot(job)
        if job.status == Status.open:
            check_transition(job.status, Status.assigned)
        job.technician_id = technician_id
        job.status = Status.assigned
        job.assignment_version += 1
        assigned_at = self.now(db, job)
        if not initial:
            job.row_version += 1
            job.updated_at = assigned_at
        self.history(db, job, actor, "assigned", before, assigned_at)
        db.add(
            NotificationOutbox(
                intervention_id=job.id,
                recipient_id=technician_id,
                assignment_version=job.assignment_version,
                created_at=assigned_at,
                available_at=assigned_at,
            )
        )

    def create(self, actor_id: UUID, payload: InterventionCreate) -> InterventionResponse:
        with Session(self.engine, expire_on_commit=False) as db, db.begin():
            actor = self.actor(db, actor_id, "dispatcher")
            now = self.now(db)
            job = Intervention(
                title=payload.title,
                description=payload.description,
                site=payload.site,
                priority=payload.priority,
                status=Status.open,
                row_version=1,
                assignment_version=0,
                created_at=now,
                updated_at=now,
            )
            db.add(job)
            db.flush()
            self.history(db, job, actor, "created", {}, now)
            if payload.technician_id is not None:
                self.assign_in_transaction(db, job, actor, payload.technician_id, initial=True)
            db.flush()
            return InterventionResponse.model_validate(job)

    def detail(self, actor_id: UUID, identifier: UUID) -> InterventionResponse:
        with Session(self.engine) as db, db.begin():
            actor = self.actor(db, actor_id, "dispatcher", "technician")
            return InterventionResponse.model_validate(self.job(db, identifier, actor))

    def edit(
        self, actor_id: UUID, identifier: UUID, payload: InterventionEdit
    ) -> InterventionResponse:
        with Session(self.engine, expire_on_commit=False) as db, db.begin():
            actor = self.actor(db, actor_id, "dispatcher")
            job = self.job(db, identifier, actor, lock=True)
            check_version(job.row_version, payload.expected_version)
            if job.status not in {Status.open, Status.assigned}:
                raise DomainError(
                    409, "invalid_transition", "This intervention can no longer be edited"
                )
            changes = payload.model_dump(
                mode="json", exclude_unset=True, exclude={"expected_version"}
            )
            before = self.snapshot(job)
            if any(getattr(job, key) != value for key, value in changes.items()):
                for key, value in changes.items():
                    setattr(job, key, value)
                job.row_version += 1
                job.updated_at = self.now(db, job)
                self.history(db, job, actor, "edited", before, job.updated_at)
            db.flush()
            return InterventionResponse.model_validate(job)

    def assign(self, actor_id: UUID, identifier: UUID, payload: Assignment) -> InterventionResponse:
        with Session(self.engine, expire_on_commit=False) as db, db.begin():
            actor = self.actor(db, actor_id, "dispatcher")
            job = self.job(db, identifier, actor, lock=True)
            check_version(job.row_version, payload.expected_version)
            self.assign_in_transaction(db, job, actor, payload.technician_id)
            db.flush()
            return InterventionResponse.model_validate(job)

    def transition(
        self, actor_id: UUID, identifier: UUID, payload: Transition
    ) -> InterventionResponse:
        with Session(self.engine, expire_on_commit=False) as db, db.begin():
            role = "dispatcher" if payload.target_status == Status.cancelled else "technician"
            actor = self.actor(db, actor_id, role)
            job = self.job(db, identifier, actor, lock=True)
            check_version(job.row_version, payload.expected_version)
            check_transition(job.status, payload.target_status)
            before = self.snapshot(job)
            now = self.now(db, job)
            job.status = payload.target_status
            job.row_version += 1
            job.updated_at = now
            if payload.target_status == Status.in_progress:
                job.started_at = now
            elif payload.target_status == Status.completed:
                job.closed_at = now
                job.resolution = payload.resolution
            else:
                job.closed_at = now
            self.history(db, job, actor, "transitioned", before, now)
            db.flush()
            return InterventionResponse.model_validate(job)

    @staticmethod
    def page(db: Session, statement, pagination: Pagination, response_type):
        total = db.scalar(select(func.count()).select_from(statement.subquery()))
        offset = (pagination.page - 1) * pagination.page_size
        # Avoid integer overflow in PostgreSQL OFFSET for syntactically valid very large pages.
        rows = (
            []
            if offset >= total
            else db.scalars(statement.limit(pagination.page_size).offset(offset)).all()
        )
        return Page[response_type](
            items=[response_type.model_validate(row) for row in rows],
            page=pagination.page,
            page_size=pagination.page_size,
            total=total,
        )

    def list(self, actor_id: UUID, filters: InterventionFilters) -> Page[InterventionResponse]:
        with Session(self.engine) as db, db.begin():
            actor = self.actor(db, actor_id, "dispatcher", "technician")
            statement = intervention_scope(select(Intervention), actor)
            for key in ("status", "priority", "technician_id"):
                value = getattr(filters, key)
                if value is not None:
                    statement = statement.where(getattr(Intervention, key) == value)
            statement = statement.order_by(Intervention.created_at.desc(), Intervention.id.desc())
            return self.page(db, statement, filters, InterventionResponse)

    def list_history(
        self, actor_id: UUID, identifier: UUID, pagination: Pagination
    ) -> Page[HistoryResponse]:
        with Session(self.engine) as db, db.begin():
            actor = self.actor(db, actor_id, "dispatcher", "technician")
            # Keep the assignee used for authorization stable through both history queries.
            self.job(db, identifier, actor, share_lock=True)
            statement = select(InterventionHistory).where(
                InterventionHistory.intervention_id == identifier
            )
            statement = statement.order_by(
                InterventionHistory.created_at.desc(), InterventionHistory.id.desc()
            )
            return self.page(db, statement, pagination, HistoryResponse)

    def list_technicians(self, actor_id: UUID) -> list[PersonaResponse]:
        with Session(self.engine) as db, db.begin():
            self.actor(db, actor_id, "dispatcher")
            users = db.scalars(
                select(User)
                .where(User.role == "technician", User.active.is_(True))
                .order_by(User.display_name, User.id)
            )
            return [PersonaResponse.model_validate(user) for user in users]
