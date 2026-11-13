"""Real PostgreSQL test fixtures; never downgrade an existing application database."""

import os
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from fieldops.bootstrap import migrate, seed
from fieldops.database import create_database_engine
from fieldops.settings import Settings
from test_support.database import cleanup, create_owned


@pytest.fixture(scope="session", autouse=True)
def isolated_run_database():
    if os.getenv("FIELDOPS_TEST_DATABASE") != "1":
        yield
        return
    original = Settings()
    if not original.db_name.endswith("_test"):
        pytest.fail("Refusing integration run against a non-test database")
    engine = create_database_engine(original)
    name = "fieldops_t08run_" + uuid4().hex + "_test"
    try:
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            create_owned(connection, name, scope="session")
        os.environ["FIELDOPS_DB_NAME"] = name
        value = original.model_copy(update={"db_name": name})
        migrate(value)
        seed(value)
        yield
    finally:
        engine.dispose()
        os.environ["FIELDOPS_DB_NAME"] = original.db_name
        cleanup()


@pytest.fixture(autouse=True)
def release_case_databases():
    yield
    cleanup(scope="function")


@pytest.fixture(scope="session")
def pg_settings():
    if os.getenv("FIELDOPS_TEST_DATABASE") != "1":
        pytest.skip("Requires explicitly configured PostgreSQL test database")
    value = Settings()
    if not value.db_name.endswith("_test"):
        pytest.fail("PostgreSQL tests require a database name ending _test")
    migrate(value)
    seed(value)
    return value


@pytest.fixture
def pg_engine(pg_settings):
    engine = create_database_engine(pg_settings)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def db(pg_engine):
    with Session(pg_engine) as session:
        try:
            yield session
        finally:
            session.rollback()
