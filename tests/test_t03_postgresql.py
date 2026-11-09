"""PostgreSQL migration, invariant, scope and durability tests."""

import uuid
from datetime import UTC, datetime

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import func, inspect, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from fieldops.bootstrap import migrate, seed
from fieldops.database import create_database_engine
from fieldops.models import (
    Base,
    Intervention,
    InterventionHistory,
    Notification,
    NotificationOutbox,
    User,
)
from fieldops.permissions import inbox_scope, intervention_scope, require_intervention_access
from fieldops.seed import persona_id

pytestmark = pytest.mark.integration


def test_empty_database_upgrade_downgrade_upgrade(pg_engine, pg_settings):
    # Unique empty DB; never downgrade the supplied test DB or developer/production state.
    name = "fieldops_t03_" + uuid.uuid4().hex + "_test"
    with pg_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.exec_driver_sql(f'CREATE DATABASE "{name}"')
    settings = pg_settings.model_copy(update={"db_name": name})
    migrate(settings)
    engine = create_database_engine(settings)
    try:
        with engine.connect() as conn:
            assert compare_metadata(MigrationContext.configure(conn), Base.metadata) == []
        config = Config("alembic.ini")
        config.attributes["settings"] = settings
        command.downgrade(config, "base")
        assert set(inspect(engine).get_table_names()) == {"alembic_version"}
        migrate(settings)
        seed(settings)
        seed(settings)
        with Session(engine) as db:
            assert db.scalar(select(func.count()).select_from(User)) == 4
    finally:
        engine.dispose()
    # Deliberately retain the isolated DB; no DROP DATABASE/volume removal.


def test_seed_idempotent_and_does_not_reactivate(db, pg_settings):
    before = db.scalars(select(User).order_by(User.id)).all()
    ids = [user.id for user in before]
    seed(pg_settings)
    assert list(db.scalars(select(User.id).order_by(User.id))) == ids
    from fieldops.seed import seed_personas

    user = db.get(User, persona_id("demo-technician-b"))
    user.active = False
    db.flush()
    seed_personas(db)
    db.refresh(user)
    assert not user.active


@pytest.mark.parametrize(
    "changes",
    [
        {"title": ""},
        {"site": " "},
        {"priority": "critical"},
        {"status": "unknown"},
        {"description": "x" * 4001},
        {"row_version": 0},
        {"assignment_version": -1},
        {"status": "assigned"},
        {"status": "in_progress"},
        {"closed_at": datetime.now(UTC)},
        {
            "technician_id": persona_id("demo-manager"),
            "assignment_version": 1,
            "status": "assigned",
        },
        {"technician_id": uuid.uuid4(), "assignment_version": 1, "status": "assigned"},
        {"technician_id": persona_id("demo-technician-a"), "status": "assigned"},
        {
            "status": "completed",
            "technician_id": persona_id("demo-technician-a"),
            "assignment_version": 1,
            "started_at": datetime.now(UTC),
            "closed_at": datetime.now(UTC),
            "resolution": " ",
        },
    ],
)
def test_intervention_constraints(db, changes):
    if changes.get("status") == "completed":
        # Fix all other invariants so this case really exercises completion resolution.
        now = db.scalar(select(func.now()))
        changes = {
            **changes,
            "created_at": now,
            "updated_at": now,
            "started_at": now,
            "closed_at": now,
        }
    with pytest.raises(IntegrityError) as error, db.begin_nested():
        db.add(Intervention(**{"title": "Synthetic Job", "site": "Synthetic Site", **changes}))
        db.flush()
    if changes.get("status") == "completed":
        assert error.value.orig.diag.constraint_name == "ck_intervention_completion"


@pytest.mark.parametrize("role", ["manager", "admin", ""])
def test_invalid_role(db, role):
    with pytest.raises(IntegrityError), db.begin_nested():
        db.add(User(persona_key=uuid.uuid4().hex, display_name="Synthetic", role=role))
        db.flush()


def graph(db):
    job = Intervention(
        title="Synthetic Job",
        site="Synthetic Site",
        status="assigned",
        technician_id=persona_id("demo-technician-a"),
        assignment_version=1,
    )
    db.add(job)
    db.flush()
    event = NotificationOutbox(
        intervention_id=job.id, recipient_id=job.technician_id, assignment_version=1
    )
    db.add(event)
    db.flush()
    return job, event


@pytest.mark.parametrize(
    "changes",
    [
        {"recipient_id": persona_id("demo-manager")},
        {"recipient_id": uuid.uuid4()},
        {"assignment_version": 0},
        {"event_type": "email"},
        {"status": "unknown"},
        {"attempts": 6},
        {"status": "processing"},
        {"status": "delivered"},
        {"lease_token": uuid.uuid4()},
    ],
)
def test_outbox_constraints(db, changes):
    job, _ = graph(db)
    with pytest.raises(IntegrityError), db.begin_nested():
        db.add(
            NotificationOutbox(
                **{
                    "intervention_id": job.id,
                    "recipient_id": job.technician_id,
                    "assignment_version": 2,
                    **changes,
                }
            )
        )
        db.flush()


def test_unique_outbox_inbox_and_matching_recipient(db):
    job, event = graph(db)
    with pytest.raises(IntegrityError), db.begin_nested():
        db.add(
            NotificationOutbox(
                intervention_id=job.id, recipient_id=job.technician_id, assignment_version=1
            )
        )
        db.flush()
    with pytest.raises(IntegrityError), db.begin_nested():
        db.add(
            Notification(
                outbox_id=event.id,
                recipient_id=persona_id("demo-technician-b"),
                intervention_id=job.id,
                assignment_version=1,
            )
        )
        db.flush()
    db.add(
        Notification(
            outbox_id=event.id,
            recipient_id=job.technician_id,
            intervention_id=job.id,
            assignment_version=1,
        )
    )
    db.flush()
    with pytest.raises(IntegrityError), db.begin_nested():
        db.add(
            Notification(
                outbox_id=event.id,
                recipient_id=job.technician_id,
                intervention_id=job.id,
                assignment_version=1,
            )
        )
        db.flush()


def test_history_append_only_and_foreign_keys(db):
    job, _ = graph(db)
    history = InterventionHistory(
        intervention_id=job.id,
        actor_id=persona_id("demo-manager"),
        event_type="created",
        changed_fields={"title": "Synthetic Job"},
    )
    db.add(history)
    db.flush()
    for statement in [
        "UPDATE intervention_history SET event_type='edited' WHERE id=:id",
        "DELETE FROM intervention_history WHERE id=:id",
    ]:
        with pytest.raises(DBAPIError), db.begin_nested():
            db.execute(text(statement), {"id": history.id})
    with pytest.raises(IntegrityError), db.begin_nested():
        db.add(
            InterventionHistory(
                intervention_id=uuid.uuid4(), event_type="created", changed_fields={}
            )
        )
        db.flush()


def test_real_recipient_and_current_assignment_scope(db):
    from fastapi import HTTPException

    job, event = graph(db)
    db.add(
        Notification(
            outbox_id=event.id,
            recipient_id=job.technician_id,
            intervention_id=job.id,
            assignment_version=1,
        )
    )
    db.flush()
    a = db.get(User, persona_id("demo-technician-a"))
    b = db.get(User, persona_id("demo-technician-b"))
    manager = db.get(User, persona_id("demo-manager"))
    operator = db.get(User, persona_id("demo-operator"))
    assert job.id in db.scalars(intervention_scope(select(Intervention.id), a)).all()
    assert job.id not in db.scalars(intervention_scope(select(Intervention.id), b)).all()
    assert job.id in db.scalars(intervention_scope(select(Intervention.id), manager)).all()
    assert event.id in db.scalars(inbox_scope(select(Notification.outbox_id), a)).all()
    assert event.id not in db.scalars(inbox_scope(select(Notification.outbox_id), b)).all()
    with pytest.raises(HTTPException):
        inbox_scope(select(Notification), manager)
    with pytest.raises(HTTPException):
        intervention_scope(select(Intervention), operator)
    job.technician_id = b.id
    job.assignment_version = 2
    db.flush()
    with pytest.raises(HTTPException):
        require_intervention_access(a, job.technician_id)
    # Historical inbox remains owned by A, while A loses access to the reassigned job.
    assert event.id in db.scalars(inbox_scope(select(Notification.outbox_id), a)).all()
    assert job.id not in db.scalars(intervention_scope(select(Intervention.id), a)).all()


def test_committed_inbox_survives_engine_reconnect(pg_engine, pg_settings):
    with Session(pg_engine) as db, db.begin():
        job, event = graph(db)
        notification = Notification(
            outbox_id=event.id,
            recipient_id=job.technician_id,
            intervention_id=job.id,
            assignment_version=1,
        )
        db.add(notification)
        db.flush()
        identifier = notification.id
        event_id = event.id
    pg_engine.dispose()
    other = create_database_engine(pg_settings)
    try:
        with Session(other) as db:
            assert db.get(Notification, identifier).outbox_id == event_id
    finally:
        other.dispose()
