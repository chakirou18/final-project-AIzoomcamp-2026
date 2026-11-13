"""Drop only UUID-named test databases bearing this run's explicit ownership comment."""

import os
import re
from uuid import uuid4

from sqlalchemy import create_engine, text

RUN_ID = os.environ.setdefault("FIELDOPS_TEST_RUN_ID", uuid4().hex)
if not re.fullmatch(r"[0-9a-f]{32}", RUN_ID):
    raise RuntimeError("Invalid test run identifier")
MARKER = "fieldops-t08:" + RUN_ID
OWNED = {}


def valid_name(name):
    return len(name) <= 63 and bool(re.fullmatch(r"fieldops_[a-z0-9_]+_[0-9a-f]{32}_test", name))


def create_owned(connection, name, *, scope="function"):
    if os.getenv("FIELDOPS_TEST_DATABASE") != "1" or not valid_name(name):
        raise RuntimeError("Refusing unguarded test database creation")
    connection.exec_driver_sql(f'CREATE DATABASE "{name}"')
    connection.exec_driver_sql(f"COMMENT ON DATABASE \"{name}\" IS '{MARKER}'")
    OWNED[name] = (connection.engine.url.set(database="postgres"), scope)


def cleanup(*, scope=None):
    dropped = 0
    for name, (url, lifetime) in list(OWNED.items()):
        if scope is not None and lifetime != scope:
            continue
        engine = create_engine(url, hide_parameters=True, isolation_level="AUTOCOMMIT")
        try:
            with engine.connect() as connection:
                marker = connection.scalar(
                    text(
                        "SELECT shobj_description(oid,'pg_database') "
                        "FROM pg_database WHERE datname=:name"
                    ),
                    {"name": name},
                )
                if not valid_name(name) or marker != MARKER:
                    raise RuntimeError("Refusing database cleanup without matching ownership")
                connection.exec_driver_sql(f'DROP DATABASE "{name}" WITH (FORCE)')
                dropped += 1
                del OWNED[name]
        finally:
            engine.dispose()
    return dropped


def cleanup_run(settings):
    """Supervisor fallback after failed/killed pytest; exact run marker plus strict names only."""
    engine = create_engine(
        settings.database_url().set(database="postgres"),
        hide_parameters=True,
        isolation_level="AUTOCOMMIT",
    )
    try:
        with engine.connect() as connection:
            names = connection.scalars(
                text(
                    "SELECT datname FROM pg_database "
                    "WHERE shobj_description(oid,'pg_database')=:marker"
                ),
                {"marker": MARKER},
            ).all()
            for name in names:
                if not valid_name(name):
                    raise RuntimeError("Refusing cleanup of unexpected database name")
                connection.exec_driver_sql(f'DROP DATABASE "{name}" WITH (FORCE)')
            return len(names)
    finally:
        engine.dispose()
