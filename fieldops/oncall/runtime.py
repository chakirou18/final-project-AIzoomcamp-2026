"""Private process entrypoint and explicit least-privilege provisioning."""

import json
import signal
import sys
import time
from contextlib import closing
from pathlib import Path
from threading import Event

from psycopg import sql
from pydantic import Field
from sqlalchemy import text

from fieldops.bootstrap import initialize_credentials
from fieldops.database import create_database_engine
from fieldops.oncall.processor import Processor
from fieldops.oncall.provider import OllamaProvider, UnconfiguredProvider
from fieldops.oncall.tools import Tools
from fieldops.settings import Settings


class AgentSettings(Settings):
    oncall_web_url: str = "http://web:8000"
    oncall_prometheus_url: str = "http://prometheus:9090"
    oncall_loki_url: str = "http://loki:3100"
    oncall_jaeger_url: str = "http://jaeger:16686"
    oncall_recovery_key_file: Path = Path("/run/oncall-action/oncall_key")
    oncall_provider: str = "unconfigured"
    oncall_provider_url: str = "http://host.docker.internal:11434"
    oncall_model: str = ""
    oncall_provider_approved: bool = False
    oncall_output_tokens: int = Field(default=1024, ge=128, le=2048)
    oncall_max_calls: int = Field(default=1, ge=1, le=10)
    oncall_provider_timeout: int = Field(default=20, ge=5, le=30)


def provision():
    settings = Settings()
    if settings.environment != "local" or not settings.demo_mode:
        raise RuntimeError("oncall_provision_requires_local_demo")
    directory = Path("/run/oncall-db")
    initialize_credentials(directory, "password")
    action_directory = Path("/run/oncall-action")
    action_directory.mkdir(parents=True, exist_ok=True)
    initialize_credentials(action_directory, "oncall_key")
    password = (directory / "password").read_text().strip()
    engine = create_database_engine(settings)
    try:
        # Driver-level DDL avoids placing a credential in SQL tracing.
        with closing(engine.raw_connection()) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1 FROM pg_roles WHERE rolname='fieldops_oncall'")
                if not cursor.fetchone():
                    cursor.execute("CREATE ROLE fieldops_oncall LOGIN")
                cursor.execute(
                    sql.SQL(
                        "ALTER ROLE fieldops_oncall LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
                        "NOINHERIT PASSWORD {}"
                    ).format(sql.Literal(password))
                )
                cursor.execute(
                    sql.SQL("GRANT CONNECT ON DATABASE {} TO fieldops_oncall").format(
                        sql.Identifier(settings.db_name)
                    )
                )
                cursor.execute("""
                    GRANT USAGE ON SCHEMA public TO fieldops_oncall;
                    GRANT SELECT, INSERT, UPDATE ON incidents TO fieldops_oncall;
                    GRANT SELECT, INSERT ON incident_events, incident_affected, incident_actions
                      TO fieldops_oncall;
                    GRANT SELECT ON incident_grants TO fieldops_oncall;
                """)
            connection.commit()
    finally:
        engine.dispose()


def main():
    if sys.argv[1:] == ["provision"]:
        provision()
        return
    settings = AgentSettings()
    engine = create_database_engine(settings)
    if sys.argv[1:] == ["health"]:
        marker = Path("/tmp/oncall-heartbeat")
        if not marker.exists() or time.time() - marker.stat().st_mtime > 40:
            raise SystemExit(1)
        with engine.connect() as connection:
            connection.execute(text("SELECT 1 FROM incidents LIMIT 1"))
        return
    if settings.oncall_provider == "ollama":
        provider = OllamaProvider(
            settings.oncall_provider_url,
            settings.oncall_model,
            settings.oncall_provider_approved,
            settings.oncall_output_tokens,
            settings.oncall_max_calls,
            settings.oncall_provider_timeout,
        )
    elif settings.oncall_provider == "unconfigured":
        provider = UnconfiguredProvider()
    else:
        raise RuntimeError("unknown_provider")
    tools = Tools(
        settings.oncall_web_url,
        settings.oncall_recovery_key_file.read_text().strip(),
        settings.oncall_prometheus_url,
        settings.oncall_loki_url,
        settings.oncall_jaeger_url,
    )
    processor = Processor(engine, tools, provider)
    stop = Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    try:
        while not stop.is_set():
            try:
                processor.run_once()
                Path("/tmp/oncall-heartbeat").touch()
            except Exception as failure:
                print(
                    json.dumps(
                        {"event": "oncall_stage_failed", "error_type": type(failure).__name__}
                    ),
                    flush=True,
                )
            stop.wait(1)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
