"""Local credential initialization and schema-free migration/seed entry points."""

import argparse
import logging
import os
import secrets
from pathlib import Path

from alembic import command
from alembic.config import Config

from fieldops.database import check_database, create_database_engine
from fieldops.logging import configure_logging
from fieldops.settings import Settings

logger = logging.getLogger("fieldops.bootstrap")
ROOT = Path(__file__).resolve().parent.parent


def initialize_credentials(directory: Path) -> None:
    """Generate once and reuse. Never print the password or silently rotate an existing file."""
    directory.mkdir(parents=True, exist_ok=True)
    password_path = directory / "db_password"
    try:
        descriptor = os.open(password_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
    except FileExistsError:
        if not password_path.read_text(encoding="utf-8").strip():
            raise RuntimeError(
                "Existing local credential file is empty; manual repair required"
            ) from None
        logger.info("local_credentials_reused")
        return
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(secrets.token_urlsafe(32) + "\n")
    logger.info("local_credentials_initialized")


def migrate(settings: Settings) -> None:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.attributes["settings"] = settings
    command.upgrade(config, "head")
    logger.info("migrations_completed")


def seed(settings: Settings) -> None:
    # T02 deliberately creates no business tables, personas or synthetic jobs.
    engine = create_database_engine(settings)
    try:
        check_database(engine)
    finally:
        engine.dispose()
    logger.info("seed_noop_t02")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["credentials", "migrate", "seed", "all"])
    parser.add_argument("--directory", type=Path, default=Path("/run/fieldops"))
    arguments = parser.parse_args()
    configure_logging("local", "INFO", "fieldops-bootstrap")
    try:
        if arguments.action == "credentials":
            initialize_credentials(arguments.directory)
        else:
            settings = Settings()
            if arguments.action in {"migrate", "all"}:
                migrate(settings)
            if arguments.action in {"seed", "all"}:
                seed(settings)
    except Exception as error:
        logger.error("bootstrap_failed", extra={"error_type": type(error).__name__})
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
