"""HTTP contract tests, independent from Docker or a running database."""

from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from fieldops.main import create_app
from fieldops.settings import Settings


@pytest.fixture
def client(monkeypatch):
    engine = Mock()
    monkeypatch.setattr("fieldops.main.create_database_engine", lambda settings: engine)
    monkeypatch.setattr("fieldops.main.check_database", lambda current_engine: None)
    settings = Settings(db_password="synthetic-test-only", db_password_file=None)
    with TestClient(create_app(settings), raise_server_exceptions=False) as test_client:
        yield test_client
    engine.dispose.assert_called_once()


def test_liveness_does_not_query_database(client, monkeypatch):
    def forbidden_query(engine):
        raise AssertionError("Liveness must not depend on PostgreSQL")

    monkeypatch.setattr("fieldops.main.check_database", forbidden_query)
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


def test_readiness_checks_database(client, monkeypatch):
    check = Mock()
    monkeypatch.setattr("fieldops.main.check_database", check)
    response = client.get("/health/ready")
    check.assert_called_once_with(client.app.state.engine)
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_database_outage_is_503_without_sensitive_details(client, monkeypatch, capsys):
    sentinel = "SYNTHETIC_SENSITIVE_SENTINEL"
    outage = OperationalError("SELECT 1", {}, RuntimeError(sentinel))
    monkeypatch.setattr("fieldops.main.check_database", Mock(side_effect=outage))
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {
        "error": {"code": "database_unavailable", "message": "Service is not ready", "fields": {}}
    }
    assert client.get("/health/live").status_code == 200
    assert sentinel not in response.text + capsys.readouterr().out


def test_unexpected_error_has_generic_response(client, monkeypatch, capsys):
    sentinel = "SYNTHETIC_INTERNAL_SENTINEL"
    monkeypatch.setattr("fieldops.main.check_database", Mock(side_effect=RuntimeError(sentinel)))
    response = client.get("/health/ready")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert sentinel not in response.text + capsys.readouterr().out


def test_unknown_route_does_not_echo_query_string(client, capsys):
    sentinel = "SYNTHETIC_QUERY_SENTINEL"
    response = client.get(f"/missing?token={sentinel}")
    assert response.status_code == 404
    assert sentinel not in response.text + capsys.readouterr().out


def test_internal_model_validation_is_not_a_client_422(client):
    from fieldops.schemas import InterventionCreate

    @client.app.get("/qa/invalid-server-model")
    def broken():
        return InterventionCreate(title="", site="Synthetic")

    response = client.get("/qa/invalid-server-model")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
