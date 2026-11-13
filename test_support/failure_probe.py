"""Explicit negative runner probe, never part of the normal test inventory."""

from uuid import uuid4

import pytest

from fieldops.database import create_database_engine
from fieldops.settings import Settings
from test_support.database import create_owned


def test_intentional_failure_after_owned_database_creation():
    engine = create_database_engine(Settings())
    try:
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            create_owned(connection, "fieldops_failure_" + uuid4().hex + "_test")
    finally:
        engine.dispose()
    pytest.fail("Intentional runner exit-code and supervisor cleanup probe")
