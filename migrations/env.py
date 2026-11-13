"""Online PostgreSQL migration runner with T03 metadata for drift checks."""

from alembic import context

from fieldops.database import create_database_engine
from fieldops.models import Base
from fieldops.settings import Settings

if context.is_offline_mode():
    raise RuntimeError("T02 migrations require an online PostgreSQL connection")

settings = context.config.attributes.get("settings") or Settings()
engine = create_database_engine(settings)
try:
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata)
        with context.begin_transaction():
            context.run_migrations()
finally:
    engine.dispose()
