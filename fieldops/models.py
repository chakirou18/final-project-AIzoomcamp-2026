"""T03 PostgreSQL persistence contracts; no workflow services or worker."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def identity():
    return mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


def timestamp():
    return mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = identity()
    persona_key: Mapped[str] = mapped_column(String(60), unique=True)
    display_name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(20))
    active: Mapped[bool] = mapped_column(Boolean, server_default="true")
    __table_args__ = (
        CheckConstraint("role IN ('dispatcher','technician','operator')", name="ck_user_role"),
        CheckConstraint("display_name ~ '[^[:space:]]'", name="ck_user_name"),
        UniqueConstraint("id", "role", name="uq_user_id_role"),
    )


class Intervention(Base):
    __tablename__ = "interventions"
    id: Mapped[uuid.UUID] = identity()
    title: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text, server_default="")
    site: Mapped[str] = mapped_column(String(250))
    priority: Mapped[str] = mapped_column(String(10), server_default="medium")
    status: Mapped[str] = mapped_column(String(20), server_default="open")
    technician_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    technician_role: Mapped[str] = mapped_column(String(20), server_default="technician")
    assignment_version: Mapped[int] = mapped_column(Integer, server_default="0")
    row_version: Mapped[int] = mapped_column(Integer, server_default="1")
    resolution: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = timestamp()
    updated_at: Mapped[datetime] = timestamp()
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        ForeignKeyConstraint(
            ["technician_id", "technician_role"],
            ["users.id", "users.role"],
            name="fk_intervention_technician",
        ),
        CheckConstraint("technician_role = 'technician'", name="ck_intervention_role"),
        CheckConstraint("title ~ '[^[:space:]]'", name="ck_intervention_title"),
        CheckConstraint("site ~ '[^[:space:]]'", name="ck_intervention_site"),
        CheckConstraint("length(description) <= 4000", name="ck_intervention_description"),
        CheckConstraint(
            "priority IN ('low','medium','high','urgent')", name="ck_intervention_priority"
        ),
        CheckConstraint(
            "status IN ('open','assigned','in_progress','completed','cancelled')",
            name="ck_intervention_status",
        ),
        CheckConstraint(
            "row_version >= 1 AND assignment_version >= 0", name="ck_intervention_versions"
        ),
        CheckConstraint(
            "(technician_id IS NULL AND assignment_version = 0) OR (technician_id "
            "IS NOT NULL AND assignment_version > 0)",
            name="ck_intervention_assignment",
        ),
        CheckConstraint(
            "(status = 'open' AND technician_id IS NULL) OR (status IN "
            "('assigned','in_progress','completed') AND technician_id IS NOT NULL) "
            "OR status = 'cancelled'",
            name="ck_intervention_status_assignment",
        ),
        CheckConstraint(
            "(status IN ('completed','cancelled')) = (closed_at IS NOT NULL)",
            name="ck_intervention_closed",
        ),
        CheckConstraint(
            "status NOT IN ('in_progress','completed') OR started_at IS NOT NULL",
            name="ck_intervention_started",
        ),
        CheckConstraint(
            "status NOT IN ('open','assigned') OR started_at IS NULL",
            name="ck_intervention_not_started",
        ),
        CheckConstraint(
            "resolution IS NULL OR length(resolution) <= 4000",
            name="ck_intervention_resolution_size",
        ),
        CheckConstraint(
            "status <> 'completed' OR (resolution IS NOT NULL AND resolution ~ '[^[:space:]]')",
            name="ck_intervention_completion",
        ),
        CheckConstraint(
            "updated_at >= created_at AND (started_at IS NULL OR started_at >= "
            "created_at) AND (closed_at IS NULL OR closed_at >= "
            "coalesce(started_at, created_at))",
            name="ck_intervention_times",
        ),
        Index("ix_intervention_order", "created_at", "id"),
        Index("ix_intervention_technician", "technician_id", "status"),
    )


class InterventionHistory(Base):
    __tablename__ = "intervention_history"
    id: Mapped[uuid.UUID] = identity()
    intervention_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("interventions.id"))
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    event_type: Mapped[str] = mapped_column(String(20))
    changed_fields: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = timestamp()
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('created','edited','assigned','transitioned')", name="ck_history_event"
        ),
        CheckConstraint("jsonb_typeof(changed_fields) = 'object'", name="ck_history_fields"),
        Index("ix_history_intervention", "intervention_id", "created_at", "id"),
    )


class NotificationOutbox(Base):
    __tablename__ = "notification_outbox"
    id: Mapped[uuid.UUID] = identity()
    intervention_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("interventions.id"))
    recipient_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    recipient_role: Mapped[str] = mapped_column(String(20), server_default="technician")
    assignment_version: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String(20), server_default="assignment")
    traceparent: Mapped[str | None] = mapped_column(String(55))
    tracestate: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = timestamp()
    status: Mapped[str] = mapped_column(String(20), server_default="pending")
    available_at: Mapped[datetime] = timestamp()
    attempts: Mapped[int] = mapped_column(Integer, server_default="0")
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_token: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(500))
    __table_args__ = (
        ForeignKeyConstraint(
            ["recipient_id", "recipient_role"],
            ["users.id", "users.role"],
            name="fk_outbox_technician",
        ),
        CheckConstraint("recipient_role = 'technician'", name="ck_outbox_role"),
        CheckConstraint(
            "event_type = 'assignment' AND assignment_version > 0", name="ck_outbox_assignment"
        ),
        CheckConstraint(
            "status IN ('pending','processing','delivered','failed')", name="ck_outbox_status"
        ),
        CheckConstraint("attempts BETWEEN 0 AND 5", name="ck_outbox_attempts"),
        CheckConstraint(
            "(status = 'processing' AND lease_until IS NOT NULL AND lease_token IS "
            "NOT NULL AND attempts > 0) OR (status <> 'processing' AND lease_until "
            "IS NULL AND lease_token IS NULL)",
            name="ck_outbox_lease",
        ),
        CheckConstraint(
            "(status = 'delivered') = (delivered_at IS NOT NULL)", name="ck_outbox_delivered"
        ),
        UniqueConstraint(
            "intervention_id", "assignment_version", "event_type", name="uq_outbox_assignment"
        ),
        UniqueConstraint(
            "id", "recipient_id", "intervention_id", "assignment_version", name="uq_outbox_identity"
        ),
        Index("ix_outbox_claim", "status", "available_at", "lease_until"),
    )


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[uuid.UUID] = identity()
    outbox_id: Mapped[uuid.UUID] = mapped_column(Uuid, unique=True)
    recipient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    intervention_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("interventions.id"))
    assignment_version: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = timestamp()
    delivered_at: Mapped[datetime] = timestamp()
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        ForeignKeyConstraint(
            ["outbox_id", "recipient_id", "intervention_id", "assignment_version"],
            [
                "notification_outbox.id",
                "notification_outbox.recipient_id",
                "notification_outbox.intervention_id",
                "notification_outbox.assignment_version",
            ],
            name="fk_notification_event_identity",
        ),
        CheckConstraint("read_at IS NULL OR read_at >= delivered_at", name="ck_notification_read"),
        Index("ix_notification_recipient_order", "recipient_id", "created_at", "id"),
    )


class PersonaSession(Base):
    __tablename__ = "persona_sessions"
    token_digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    csrf_token: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = timestamp()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (CheckConstraint("expires_at > created_at", name="ck_session_expiry"),)


class WorkerControl(Base):
    __tablename__ = "worker_control"
    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    paused: Mapped[bool] = mapped_column(Boolean, server_default="false")
    generation: Mapped[int] = mapped_column(Integer, server_default="0")
    effective_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_pause_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = timestamp()
    __table_args__ = (
        CheckConstraint("key = 'notification-worker'", name="ck_control_singleton"),
        CheckConstraint("generation >= 0", name="ck_control_generation"),
        CheckConstraint(
            "(paused AND generation > 0 AND effective_at IS NOT NULL AND expires_at IS NOT NULL "
            "AND expires_at > effective_at AND expires_at <= effective_at + interval '10 minutes') "
            "OR (NOT paused AND effective_at IS NULL AND expires_at IS NULL)",
            name="ck_control_pause",
        ),
    )


class WorkerHeartbeat(Base):
    __tablename__ = "worker_heartbeats"
    instance_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    started_at: Mapped[datetime] = timestamp()
    last_seen: Mapped[datetime] = timestamp()
    observed_generation: Mapped[int] = mapped_column(Integer)
    observed_paused: Mapped[bool] = mapped_column(Boolean)
    __table_args__ = (
        CheckConstraint("observed_generation >= 0", name="ck_heartbeat_generation"),
        Index("ix_heartbeat_last_seen", "last_seen"),
    )


class WorkerControlAudit(Base):
    __tablename__ = "worker_control_audit"
    id: Mapped[uuid.UUID] = identity()
    event_type: Mapped[str] = mapped_column(String(30))
    generation: Mapped[int] = mapped_column(Integer)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    principal: Mapped[str] = mapped_column(String(20))
    outcome: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = timestamp()
    __table_args__ = (
        CheckConstraint("event_type IN ('pause','resume','auto_expired')", name="ck_control_event"),
        CheckConstraint("generation >= 0", name="ck_audit_generation"),
        CheckConstraint("principal IN ('operator','agent','system')", name="ck_control_principal"),
    )


class WorkerResumeAction(Base):
    __tablename__ = "worker_resume_actions"
    idempotency_key: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    incident_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    expected_generation: Mapped[int] = mapped_column(Integer)
    generation: Mapped[int] = mapped_column(Integer)
    outcome: Mapped[str] = mapped_column(String(40))
    success: Mapped[bool] = mapped_column(Boolean)
    recorded_at: Mapped[datetime] = timestamp()
    __table_args__ = (
        CheckConstraint(
            "expected_generation >= 1 AND generation >= 0", name="ck_action_generation"
        ),
        CheckConstraint(
            "(success AND outcome = 'resumed') OR "
            "(NOT success AND outcome IN ('generation_mismatch','not_paused'))",
            name="ck_action_outcome",
        ),
    )
