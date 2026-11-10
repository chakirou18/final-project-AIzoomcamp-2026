"""One bounded synchronous connection pool per application process."""

from sqlalchemy import Engine, create_engine, text

from fieldops.settings import Settings
from fieldops.telemetry import instrument_database


def create_database_engine(settings: Settings) -> Engine:
    engine = create_engine(
        settings.database_url(),
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=0,
        pool_timeout=2,
        hide_parameters=True,
        connect_args={
            "connect_timeout": settings.db_connect_timeout,
            "options": "-c statement_timeout=2000 -c timezone=UTC",
        },
    )
    instrument_database(engine)
    return engine


def check_database(engine: Engine) -> None:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
