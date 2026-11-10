"""Container-only test supervisor: fresh owned DBs, bounded children, safe artifacts and cleanup."""

import argparse
import json
import os
import secrets
import signal
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from uuid import uuid4

from fieldops.bootstrap import migrate, seed
from fieldops.database import create_database_engine
from fieldops.settings import Settings
from test_support.database import RUN_ID, cleanup_run, create_owned


class Stack:
    def __init__(self, artifacts):
        self.artifacts = artifacts
        self.children = {}
        self.handles = []

    def start(self, name, module):
        handle = (self.artifacts / (name + ".jsonl")).open("a", encoding="utf-8")
        self.handles.append(handle)
        self.children[name] = subprocess.Popen(
            [sys.executable, "-m", module], stdout=handle, stderr=subprocess.STDOUT
        )

    def stop(self, name):
        child = self.children.pop(name, None)
        if child is not None:
            child.terminate()
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=5)

    def restart_worker(self, *_):
        self.stop("worker")
        self.start("worker", "fieldops.worker")

    def close(self):
        failures = []
        for name in ["suite", *list(self.children)]:
            try:
                self.stop(name)
            except Exception as error:
                failures.append(type(error).__name__)
        for handle in self.handles:
            handle.close()
        if failures:
            raise RuntimeError("Test child shutdown failed")

    def execute(self, command, *, cwd=None):
        child = subprocess.Popen(command, cwd=cwd)
        self.children["suite"] = child
        result = child.wait(timeout=1200)
        del self.children["suite"]
        return result


def ready():
    deadline = time.monotonic() + 40
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(
                "http://127.0.0.1:8000/health/ready", timeout=2
            ) as response:
                if response.status == 200:
                    return
        except OSError:
            pass
        time.sleep(0.1)
    raise RuntimeError("Test HTTP readiness deadline exceeded")


def owned_settings(admin):
    name = "fieldops_runner_" + uuid4().hex + "_test"
    engine = create_database_engine(admin)
    try:
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            create_owned(connection, name, scope="session")
    finally:
        engine.dispose()
    os.environ["FIELDOPS_DB_NAME"] = name
    value = Settings()
    migrate(value)
    seed(value)
    return value


def finalize(stack, admin, artifacts, summary, result):
    # Shutdown failure must not bypass the database cleanup attempt or diagnostic summary.
    try:
        stack.close()
        summary["shutdown"] = "PASS"
    except Exception as error:
        summary["shutdown"] = "FAIL"
        summary["shutdown_error_type"] = type(error).__name__
        result = 1
    try:
        summary["fallback_databases_removed"] = cleanup_run(admin)
        summary["cleanup"] = "PASS"
    except Exception as error:
        summary["cleanup"] = "FAIL"
        summary["cleanup_error_type"] = type(error).__name__
        result = 1
    summary["exit_code"] = result
    (artifacts / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print("T08_RUN " + json.dumps(summary), flush=True)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("suite", choices=["backend", "browser"])
    parser.add_argument("--failure-probe", action="store_true")
    parser.add_argument("--pytest-target", default="tests")
    args = parser.parse_args()

    def interrupted(*_):
        raise RuntimeError("Test run interrupted")

    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    artifacts = Path("artifacts") / ("t08-" + args.suite + "-" + RUN_ID)
    artifacts.mkdir(parents=True)
    # Each pytest/browser process gets its own artifact cwd; no shared screenshot names.
    admin = Settings()
    if os.getenv("FIELDOPS_TEST_DATABASE") != "1" or not admin.db_name.endswith("_test"):
        raise RuntimeError("Runner requires explicit isolated test database settings")
    result = 1
    stack = Stack(artifacts)
    summary = {"run_id": RUN_ID, "suite": args.suite, "cleanup": "NOT RUN"}
    try:
        if args.suite == "backend":
            command = [
                sys.executable,
                "-m",
                "pytest",
                args.pytest_target,
                "-m",
                "not container",
                "-p",
                "no:cacheprovider",
                "--junitxml=" + str(artifacts / "pytest.xml"),
                "--tb=short",
            ]
            if args.failure_probe:
                command[3] = "test_support/failure_probe.py"
            result = stack.execute(command)
        else:
            with tempfile.TemporaryDirectory(prefix="fieldops-test-controls-") as directory:
                os.environ["FIELDOPS_TEST_CONTROL_DIRECTORY"] = directory
                for name, setting in [
                    ("operator_key", "OPERATOR"),
                    ("recovery_key", "RECOVERY"),
                    ("session_key", "SESSION"),
                ]:
                    path = Path(directory) / name
                    path.write_text(secrets.token_urlsafe(32), encoding="utf-8")
                    os.environ["FIELDOPS_" + setting + "_SECRET_FILE"] = str(path)
                os.environ["FIELDOPS_BROWSER_URL"] = "http://127.0.0.1:8000"
                os.environ["FIELDOPS_TEST_SUPERVISOR_PID"] = str(os.getpid())
                owned_settings(admin)
                stack.start("web", "fieldops")
                stack.start("worker", "fieldops.worker")
                signal.signal(signal.SIGUSR1, stack.restart_worker)
                ready()
                # Isolate browser artifacts without changing source imports.
                work = artifacts / "browser"
                work.mkdir()
                os.environ["PYTHONPATH"] = "/app"
                command = [
                    sys.executable,
                    "-m",
                    "pytest",
                    "/app/browser_tests" if args.pytest_target == "tests" else args.pytest_target,
                    "-v",
                    "-s",
                    "-p",
                    "no:cacheprovider",
                    "--tb=short",
                    "--junitxml=" + str((artifacts / "pytest.xml").resolve()),
                ]
                if args.failure_probe:
                    command[3] = "/app/browser_tests/failure_probe.py"
                result = stack.execute(command, cwd=work)
                if result == 0:
                    from test_support.performance import benchmark

                    stack.close()
                    settings = owned_settings(admin)
                    benchmark(stack, settings, artifacts)
    except Exception as error:
        summary["error_type"] = type(error).__name__
        print("test_runner_failed", type(error).__name__, flush=True)
        result = 1
    finally:
        result = finalize(stack, admin, artifacts, summary, result)
    raise SystemExit(result)


if __name__ == "__main__":
    main()
