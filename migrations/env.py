"""Migration runner only. T03 owns business metadata and the first business revision."""

from alembic import context

from fieldops.database import create_database_engine
from fieldops.settings import Settings

if context.is_offline_mode():
    raise RuntimeError("T02 migrations require an online PostgreSQL connection")

settings = context.config.attributes.get("settings") or Settings()
engine = create_database_engine(settings)
try:
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=None)
        with context.begin_transaction():
            context.run_migrations()
finally:
    engine.dispose()
