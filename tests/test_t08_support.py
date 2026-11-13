"""Risk-based runner checks: cleanup guard boundaries and explicit percentile convention."""

import pytest

from test_support.database import valid_name
from test_support.performance import percentile


@pytest.mark.parametrize(
    "name",
    [
        "fieldops",
        "fieldops_test",
        "postgres",
        "fieldops_prod_test",
        'fieldops_x_";DROP DATABASE postgres;--_test',
    ],
)
def test_unowned_or_nongenerated_database_names_are_never_cleanup_targets(name):
    assert not valid_name(name)


def test_n03_p95_uses_nearest_rank_without_dropping_slow_samples():
    assert percentile(list(range(1, 51)), 0.95) == 48


@pytest.mark.parametrize("failure", ["shutdown", "cleanup"])
def test_runner_reports_failure_and_still_attempts_cleanup(monkeypatch, tmp_path, failure):
    import json
    from types import SimpleNamespace

    from test_support import runner

    calls = []

    def close():
        if failure == "shutdown":
            raise OSError("Injected child termination failure")

    def clean(_):
        calls.append("cleanup")
        if failure == "cleanup":
            raise ConnectionError("Injected database cleanup failure")
        return 1

    monkeypatch.setattr(runner, "cleanup_run", clean)
    assert runner.finalize(SimpleNamespace(close=close), None, tmp_path, {}, 0) == 1
    report = json.loads((tmp_path / "summary.json").read_text())
    assert calls == ["cleanup"] and report[failure] == "FAIL" and report["exit_code"] == 1


@pytest.mark.integration
def test_owned_cleanup_preserves_unrelated_marker_and_cleans_failed_scope(pg_settings):
    from uuid import uuid4

    from sqlalchemy import text

    from fieldops.database import create_database_engine
    from test_support.database import MARKER, OWNED, cleanup, create_owned

    engine = create_database_engine(pg_settings)
    name = "fieldops_guard_" + uuid4().hex + "_test"
    try:
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            create_owned(connection, name)
            connection.exec_driver_sql(f"COMMENT ON DATABASE \"{name}\" IS 'not-this-run'")
        with pytest.raises(RuntimeError, match="matching ownership"):
            cleanup(scope="function")
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            assert (
                connection.scalar(
                    text("SELECT count(*) FROM pg_database WHERE datname=:name"), {"name": name}
                )
                == 1
            )
            # Restore only this owned test database for its normal finalizer.
            connection.exec_driver_sql(f"COMMENT ON DATABASE \"{name}\" IS '{MARKER}'")
        assert cleanup(scope="function") == 1 and name not in OWNED
        with engine.connect() as connection:
            assert (
                connection.scalar(
                    text("SELECT count(*) FROM pg_database WHERE datname=:name"), {"name": name}
                )
                == 0
            )
    finally:
        engine.dispose()
