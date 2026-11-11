"""Local credential initialization, migrations and explicit synthetic persona seed."""

import argparse
import logging
import os
import secrets
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.orm import Session

from fieldops.database import check_database, create_database_engine
from fieldops.logging import configure_logging
from fieldops.seed import seed_personas
from fieldops.settings import Settings

logger = logging.getLogger("fieldops.bootstrap")
ROOT = Path(__file__).resolve().parent.parent


def initialize_credentials(directory: Path, filename: str = "db_password") -> None:
    """Generate once and reuse. Never print the password or silently rotate an existing file."""
    directory.mkdir(parents=True, exist_ok=True)
    password_path = directory / filename
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


def seed(settings: Settings, *, allow_nonlocal: bool = False) -> None:
    if settings.environment != "local" and not allow_nonlocal:
        raise ValueError("Nonlocal seeding requires explicit seed --allow-nonlocal")
    engine = create_database_engine(settings)
    try:
        check_database(engine)
        with Session(engine) as session, session.begin():
            seed_personas(session)
    finally:
        engine.dispose()
    logger.info("synthetic_personas_seeded")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["credentials", "migrate", "seed", "all"])
    parser.add_argument("--directory", type=Path, default=Path("/run/fieldops"))
    parser.add_argument("--control-directory", type=Path, default=Path("/run/fieldops-controls"))
    parser.add_argument("--allow-nonlocal", action="store_true")
    arguments = parser.parse_args()
    configure_logging("local", "INFO", "fieldops-bootstrap")
    try:
        if arguments.action == "credentials":
            initialize_credentials(arguments.directory)
            initialize_credentials(arguments.directory, "session_key")
            initialize_credentials(arguments.control_directory, "operator_key")
            initialize_credentials(arguments.control_directory, "recovery_key")
            oncall_directory = Path("/run/oncall-action")
            if oncall_directory.exists():
                initialize_credentials(oncall_directory, "oncall_key")
            # Dedicated telemetry volume; never chmod/chown existing application data volumes.
            for telemetry_path in ("/var/log/fieldops", "/var/lib/fieldops-jaeger"):
                telemetry_directory = Path(telemetry_path)
                if telemetry_directory.exists():
                    os.chown(telemetry_directory, 10001, 10001)
                    os.chmod(telemetry_directory, 0o755)
        else:
            settings = Settings()
            configure_logging(settings.environment, settings.log_level, "fieldops-bootstrap")
            if arguments.action in {"migrate", "all"}:
                migrate(settings)
            if arguments.action == "seed":
                seed(settings, allow_nonlocal=arguments.allow_nonlocal)
            elif arguments.action == "all" and settings.environment == "local":
                seed(settings)
    except Exception as error:
        logger.error("bootstrap_failed", extra={"error_type": type(error).__name__})
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
