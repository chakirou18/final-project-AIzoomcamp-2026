"""Real PostgreSQL test fixtures; never downgrade an existing application database."""

import os

import pytest
from sqlalchemy.orm import Session

from fieldops.bootstrap import migrate, seed
from fieldops.database import create_database_engine
from fieldops.settings import Settings


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
