"""Configuration, bootstrap idempotency and structured-log secrecy checks."""

import json
import logging

import pytest
from pydantic import ValidationError

from fieldops.bootstrap import initialize_credentials
from fieldops.logging import JsonFormatter
from fieldops.settings import Settings


@pytest.fixture(autouse=True)
def clear_password_environment(monkeypatch):
    monkeypatch.delenv("FIELDOPS_DB_PASSWORD", raising=False)
    monkeypatch.delenv("FIELDOPS_DB_PASSWORD_FILE", raising=False)


def test_settings_require_a_password():
    with pytest.raises(ValidationError, match="nonempty database password"):
        Settings()


def test_password_file_and_environment_configuration(tmp_path, monkeypatch):
    secret_file = tmp_path / "db_password"
    secret_file.write_text("synthetic-local-only\n", encoding="utf-8")
    monkeypatch.setenv("FIELDOPS_DB_PASSWORD_FILE", str(secret_file))
    monkeypatch.setenv("FIELDOPS_DB_PORT", "5544")
    settings = Settings()
    assert settings.db_port == 5544
    assert settings.db_password.get_secret_value() == "synthetic-local-only"
    assert "synthetic-local-only" not in repr(settings)
    assert "synthetic-local-only" not in str(settings.database_url())


def test_password_sources_are_mutually_exclusive(tmp_path):
    with pytest.raises(ValidationError, match="one database password source"):
        Settings(db_password="synthetic-local-only", db_password_file=tmp_path / "not-read")


def test_local_credential_initialization_reuses_generated_value(tmp_path):
    initialize_credentials(tmp_path)
    original = (tmp_path / "db_password").read_text(encoding="utf-8")
    assert len(original.strip()) >= 32
    initialize_credentials(tmp_path)
    assert (tmp_path / "db_password").read_text(encoding="utf-8") == original


def test_empty_existing_credential_file_fails_closed(tmp_path):
    (tmp_path / "db_password").touch()
    with pytest.raises(RuntimeError, match="empty"):
        initialize_credentials(tmp_path)


def test_json_logging_omits_exception_text_and_unapproved_fields():
    sentinel = "SYNTHETIC_LOG_SENTINEL"
    record = logging.LogRecord("fieldops.http", logging.ERROR, "", 1, "request_failed", (), None)
    record.exc_info = (RuntimeError, RuntimeError(sentinel), None)
    record.password = sentinel
    payload = JsonFormatter().format(record)
    assert sentinel not in payload
    decoded = json.loads(payload)
    assert decoded["event"] == "request_failed"
    assert decoded["error_type"] == "RuntimeError"
    assert decoded["trace_id"] is None


def test_third_party_log_messages_are_not_serialized():
    record = logging.LogRecord("sqlalchemy.engine", logging.ERROR, "", 1, "private-dsn", (), None)
    assert "private-dsn" not in JsonFormatter().format(record)
