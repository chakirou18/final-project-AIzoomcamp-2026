"""Optional real PostgreSQL readiness/bootstrap checks; never substitute SQLite."""

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect

from fieldops.bootstrap import migrate, seed
from fieldops.database import create_database_engine
from fieldops.main import create_app
from fieldops.models import Base
from fieldops.settings import Settings

pytestmark = pytest.mark.integration


@pytest.fixture
def settings():
    if os.getenv("FIELDOPS_TEST_DATABASE") != "1":
        pytest.skip("Set FIELDOPS_TEST_DATABASE=1 with a disposable PostgreSQL test database")
    configured = Settings()
    if not configured.db_name.endswith("_test"):
        pytest.fail("Integration tests require a database name ending in _test")
    return configured


def test_real_postgresql_readiness(settings):
    with TestClient(create_app(settings)) as client:
        assert client.get("/health/live").status_code == 200
        response = client.get("/health/ready")
        assert response.status_code == 200
        assert response.json() == {"status": "ready"}


def test_migration_and_seed_entry_points_match_t03_schema(settings):
    migrate(settings)
    seed(settings)
    migrate(settings)
    seed(settings)
    engine = create_database_engine(settings)
    try:
        assert set(inspect(engine).get_table_names()) == {"alembic_version", *Base.metadata.tables}
    finally:
        engine.dispose()
