"""Test-only adapters for existing browser probes; no Docker socket or app control route."""

import json
import os
import signal
from pathlib import Path

import psycopg

from fieldops.settings import Settings


def compose(*args):
    if args == ("restart", "worker"):
        os.kill(int(os.environ["FIELDOPS_TEST_SUPERVISOR_PID"]), signal.SIGUSR1)
        return "worker restart requested"
    if args[:4] == ("exec", "-T", "web", "cat") and len(args) == 5:
        name = Path(args[4]).name
        if name not in {"operator_key", "recovery_key"}:
            raise RuntimeError("Unsupported test credential")
        return (Path(os.environ["FIELDOPS_TEST_CONTROL_DIRECTORY"]) / name).read_text()
    if args[:4] == ("exec", "-T", "db", "psql") and "-c" in args:
        sql = args[args.index("-c") + 1]
        if not sql.lstrip().upper().startswith("SELECT ") or ";" in sql:
            raise RuntimeError("Only a single read-only test SELECT is supported")
        value = Settings()
        with psycopg.connect(
            host=value.db_host,
            port=value.db_port,
            user=value.db_user,
            dbname=value.db_name,
            password=value.db_password.get_secret_value(),
        ) as db:
            with db.transaction():
                db.execute("SET TRANSACTION READ ONLY")
                row = db.execute(sql).fetchone()
                return json.dumps(row[0])
    raise RuntimeError("Unsupported test supervisor command")
