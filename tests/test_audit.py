"""Independent audit regressions: raw SQL invariants and live contract accuracy."""

import uuid

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from fieldops.main import create_app
from fieldops.seed import persona_id
from test_support.database import create_owned


@pytest.mark.integration
@pytest.mark.parametrize(
    "field,constraint",
    [
        ("title", "ck_intervention_title"),
        ("site", "ck_intervention_site"),
    ],
)
def test_sql_rejects_tab_only_required_text(db, field, constraint):
    values = {"title": "Synthetic", "site": "Synthetic", field: "\t\n\r"}
    with pytest.raises(IntegrityError) as error, db.begin_nested():
        db.execute(
            text("INSERT INTO interventions(id,title,site) VALUES(:id,:title,:site)"),
            {"id": uuid.uuid4(), **values},
        )
    assert error.value.orig.diag.constraint_name == constraint


@pytest.mark.integration
def test_sql_completion_requires_nonblank_resolution(db):
    with pytest.raises(IntegrityError) as error, db.begin_nested():
        db.execute(
            text("""INSERT INTO interventions(id,title,site,status,technician_id,
            assignment_version,resolution,created_at,updated_at,started_at,closed_at)
            VALUES(:id,'Synthetic','Synthetic','completed',:technician,1,:resolution,
            '2000-01-01Z','2002-01-01Z','2001-01-01Z','2002-01-01Z')"""),
            {
                "id": uuid.uuid4(),
                "technician": persona_id("demo-technician-a"),
                "resolution": "\t\n",
            },
        )
    assert error.value.orig.diag.constraint_name == "ck_intervention_completion"


def test_live_openapi_documents_csrf_and_html_forms():
    schema = create_app().openapi()
    paths = schema["paths"]
    assert paths["/auth/logout"]["post"]["security"] == [{"PersonaSession": [], "CSRFToken": []}]
    assert paths["/auth/login"]["post"]["security"] == [{"LoginCSRFCookie": [], "CSRFToken": []}]
    for path in ["/session/login", "/session/logout"]:
        body = paths[path]["post"]["requestBody"]["content"]["application/x-www-form-urlencoded"]
        assert "csrf_token" in body["schema"]["required"]


@pytest.mark.integration
def test_schema_keys_nullability_and_indexes(pg_engine):
    inspector = inspect(pg_engine)
    for table in [
        "users",
        "interventions",
        "intervention_history",
        "notification_outbox",
        "notifications",
        "persona_sessions",
    ]:
        primary = inspector.get_pk_constraint(table)["constrained_columns"]
        assert len(primary) == 1
        columns = {column["name"]: column for column in inspector.get_columns(table)}
        assert not columns[primary[0]]["nullable"]
    assert {index["name"] for index in inspector.get_indexes("interventions")} >= {
        "ix_intervention_order",
        "ix_intervention_technician",
    }
    assert "ix_notification_recipient_order" in {
        index["name"] for index in inspector.get_indexes("notifications")
    }
    foreign = inspector.get_foreign_keys("notifications")
    assert any(
        item["name"] == "fk_notification_event_identity" and len(item["constrained_columns"]) == 4
        for item in foreign
    )


@pytest.mark.integration
@pytest.mark.parametrize("field", ["title", "site", "priority", "status", "row_version"])
def test_sql_not_null_fields(db, field):
    with pytest.raises(IntegrityError) as error, db.begin_nested():
        db.execute(
            text(
                f"INSERT INTO interventions(id,title,site,{field}) "
                f"VALUES(:id,'Synthetic','Synthetic',NULL)"
            )
            if field not in {"title", "site"}
            else text("INSERT INTO interventions(id,title,site) VALUES(:id,:title,:site)"),
            {
                "id": uuid.uuid4(),
                "title": None if field == "title" else "Synthetic",
                "site": None if field == "site" else "Synthetic",
            },
        )
    assert error.value.orig.sqlstate == "23502"
    assert error.value.orig.diag.column_name == field


@pytest.mark.integration
def test_parameterized_text_is_data_not_sql(db):
    value = "Synthetic'; DROP TABLE users; --"
    identifier = uuid.uuid4()
    db.execute(
        text("INSERT INTO interventions(id,title,site) VALUES(:id,:title,:site)"),
        {"id": identifier, "title": value, "site": "Synthetic"},
    )
    assert (
        db.scalar(text("SELECT title FROM interventions WHERE id=:id"), {"id": identifier}) == value
    )
    assert db.scalar(text("SELECT count(*) FROM users")) == 4


@pytest.mark.integration
def test_existing_data_survives_corrective_migration(pg_engine, pg_settings):
    from alembic import command
    from alembic.config import Config

    from fieldops.bootstrap import migrate, seed
    from fieldops.database import create_database_engine

    name = "fieldops_review_" + uuid.uuid4().hex + "_test"
    with pg_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        create_owned(connection, name)
    settings = pg_settings.model_copy(update={"db_name": name})
    config = Config("alembic.ini")
    config.attributes["settings"] = settings
    command.upgrade(config, "0001_t03")
    seed(settings)
    engine = create_database_engine(settings)
    identifier = uuid.uuid4()
    try:
        with engine.begin() as connection:
            connection.execute(
                text("INSERT INTO interventions(id,title,site) VALUES(:id,:title,:site)"),
                {"id": identifier, "title": "Audit retained data", "site": "Synthetic"},
            )
            connection.execute(text("CREATE TABLE audit_prior_data(value text NOT NULL)"))
            connection.execute(text("INSERT INTO audit_prior_data VALUES('synthetic-retained')"))
        for target in ["head", "0001_t03", "head"]:
            if target == "head":
                migrate(settings)
            else:
                command.downgrade(config, target)
            seed(settings)
            with engine.connect() as connection:
                assert (
                    connection.scalar(
                        text("SELECT title FROM interventions WHERE id=:id"), {"id": identifier}
                    )
                    == "Audit retained data"
                )
                assert (
                    connection.scalar(text("SELECT value FROM audit_prior_data"))
                    == "synthetic-retained"
                )
                assert connection.scalar(text("SELECT count(*) FROM users")) == 4
        checks = {
            item["name"]: item["sqltext"]
            for item in inspect(engine).get_check_constraints("interventions")
        }
        assert "~" in checks["ck_intervention_completion"]
    finally:
        engine.dispose()
    # Retain this uniquely created database; never delete an existing application database.


@pytest.mark.parametrize(
    "field,value",
    [
        ("priority", "critical"),
        ("status", "unknown"),
        ("row_version", 0),
        ("created_at", "2000-01-01T00:00:00"),
    ],
)
def test_response_contract_rejects_invalid_state_and_naive_time(field, value):
    from pydantic import ValidationError

    from fieldops.schemas import InterventionResponse

    payload = dict(
        id=uuid.uuid4(),
        title="Synthetic",
        description="",
        site="Synthetic",
        priority="medium",
        status="open",
        technician_id=None,
        assignment_version=0,
        row_version=1,
        resolution=None,
        created_at="2000-01-01T00:00:00Z",
        updated_at="2000-01-01T00:00:00Z",
        started_at=None,
        closed_at=None,
    )
    with pytest.raises(ValidationError):
        InterventionResponse.model_validate({**payload, field: value})


def test_draft_schema_expresses_conditional_command_rules():
    from fieldops.contracts import lifecycle_openapi

    schemas = lifecycle_openapi()["components"]["schemas"]
    transition = schemas["Transition"]
    assert transition["properties"]["target_status"]["enum"] == [
        "in_progress",
        "completed",
        "cancelled",
    ]
    assert transition["allOf"][0]["then"]["required"] == ["resolution"]
    edit = schemas["InterventionEdit"]
    assert edit["anyOf"] == [
        {"required": [name]} for name in ["title", "description", "site", "priority"]
    ]
    assert all(item.get("type") != "null" for item in edit["properties"]["title"]["anyOf"])


@pytest.mark.integration
def test_actual_nonlocal_bootstrap_requires_explicit_seed(pg_engine, pg_settings):
    import os
    import subprocess
    import sys

    from fieldops.database import create_database_engine

    name = "fieldops_nonlocal_" + uuid.uuid4().hex + "_test"
    with pg_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        create_owned(connection, name)
    settings = pg_settings.model_copy(update={"db_name": name})
    environment = {**os.environ, "FIELDOPS_DB_NAME": name, "FIELDOPS_ENVIRONMENT": "production"}

    def bootstrap(*arguments):
        result = subprocess.run(
            [sys.executable, "-m", "fieldops.bootstrap", *arguments],
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.returncode

    engine = create_database_engine(settings)
    try:
        assert bootstrap("all") == 0
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT count(*) FROM users")) == 0
        assert bootstrap("seed") == 1
        assert bootstrap("seed", "--allow-nonlocal") == 0
        assert bootstrap("seed", "--allow-nonlocal") == 0
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT count(*) FROM users")) == 4
    finally:
        engine.dispose()


@pytest.mark.integration
def test_corrective_migration_fails_without_rewriting_invalid_data(pg_engine, pg_settings):
    from alembic import command
    from alembic.config import Config

    from fieldops.database import create_database_engine

    name = "fieldops_invalid_" + uuid.uuid4().hex + "_test"
    with pg_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        create_owned(connection, name)
    settings = pg_settings.model_copy(update={"db_name": name})
    config = Config("alembic.ini")
    config.attributes["settings"] = settings
    command.upgrade(config, "0001_t03")
    engine = create_database_engine(settings)
    identifier = uuid.uuid4()
    try:
        with engine.begin() as connection:
            connection.execute(
                text("INSERT INTO interventions(id,title,site) VALUES(:id,:title,:site)"),
                {"id": identifier, "title": "\t", "site": "Synthetic"},
            )
        with pytest.raises(IntegrityError) as error:
            command.upgrade(config, "head")
        assert error.value.orig.diag.constraint_name == "ck_intervention_title"
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0001_t03"
            assert (
                connection.scalar(
                    text("SELECT title FROM interventions WHERE id=:id"), {"id": identifier}
                )
                == "\t"
            )
    finally:
        engine.dispose()
