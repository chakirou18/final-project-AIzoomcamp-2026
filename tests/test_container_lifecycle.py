"""Opt-in real Docker lifecycle test; all mutations target a unique disposable project."""

import ipaddress
import json
import os
import shutil
import socket
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

import pytest

pytestmark = pytest.mark.container
ROOT = Path(__file__).resolve().parent.parent


def docker(*arguments: str, timeout: int = 240) -> str:
    result = subprocess.run(
        ["docker", *arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout.strip()


def unused_subnet() -> str:
    network_ids = docker("network", "ls", "-q").splitlines()
    configurations = json.loads(docker("network", "inspect", *network_ids))
    existing = [
        ipaddress.ip_network(item["Subnet"])
        for network in configurations
        for item in network["IPAM"]["Config"] or []
        if item.get("Subnet") and ":" not in item["Subnet"]
    ]
    for index in range(1, 255):
        candidate = ipaddress.ip_network(f"10.240.{index}.0/24")
        if not any(candidate.overlaps(network) for network in existing):
            return str(candidate)
    pytest.fail("No free test subnet in 10.240.0.0/16; do not prune unrelated Docker networks")


def http_status(base_url: str, route: str) -> tuple[int, dict]:
    try:
        with urllib.request.urlopen(base_url + route, timeout=8) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, json.load(error)


def wait_for_ready(base_url: str) -> None:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        try:
            if http_status(base_url, "/health/ready")[0] == 200:
                return
        except (OSError, ValueError):
            pass
        time.sleep(1)
    pytest.fail("API did not become ready within 60 seconds")


@pytest.fixture(scope="module")
def isolated_stack(tmp_path_factory):
    if os.getenv("FIELDOPS_RUN_CONTAINER_TESTS") != "1":
        pytest.skip(
            "Opt in with FIELDOPS_RUN_CONTAINER_TESTS=1; creates a disposable Compose project"
        )
    if not shutil.which("docker"):
        pytest.fail("Docker CLI is unavailable; container acceptance cannot be claimed")
    docker("info", "--format", "{{.ServerVersion}}", timeout=30)
    project = "fieldops-t02-test-" + uuid.uuid4().hex[:10]
    config = json.loads(docker("compose", "config", "--format", "json"))
    config["name"] = project
    # A Docker-assigned port 0 can change on restart. Select a fixed free host port instead.
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        host_port = listener.getsockname()[1]
    config["services"]["web"]["ports"] = [
        {"target": 8000, "published": str(host_port), "host_ip": "127.0.0.1", "protocol": "tcp"}
    ]
    config["services"]["db"]["environment"].update(POSTGRES_USER="fieldops", POSTGRES_DB="fieldops")
    for service in ("web", "bootstrap"):
        config["services"][service]["environment"].update(
            FIELDOPS_DB_USER="fieldops", FIELDOPS_DB_NAME="fieldops"
        )
    for volume in config["volumes"].values():
        volume.pop("name", None)
    for network in config["networks"].values():
        network.pop("name", None)
        network["ipam"]["config"] = [{"subnet": unused_subnet()}]
    config_path = tmp_path_factory.mktemp("compose") / "compose.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")

    def compose(*arguments: str) -> str:
        return docker("compose", "--project-name", project, "--file", str(config_path), *arguments)

    try:
        compose("up", "--build", "--wait", "--wait-timeout", "120")
        address = compose("port", "web", "8000")
        base_url = "http://" + address
        wait_for_ready(base_url)
        yield compose, base_url
    finally:
        # Preserve all volumes/data, including audit probes, for owner inspection.
        assert project.startswith("fieldops-t02-test-")
        compose("down", "--remove-orphans")


def test_container_startup_and_persistence_after_restart(isolated_stack):
    compose, base_url = isolated_stack
    assert http_status(base_url, "/health/live") == (200, {"status": "alive"})
    assert http_status(base_url, "/health/ready") == (200, {"status": "ready"})
    assert compose("exec", "-T", "web", "id", "-u") == "10001"
    # A test-only probe in a disposable DB, not a T03 application/business table.
    compose(
        "exec",
        "-T",
        "db",
        "psql",
        "-U",
        "fieldops",
        "-d",
        "fieldops",
        "-v",
        "ON_ERROR_STOP=1",
        "-c",
        "CREATE TABLE t02_persistence_probe (value text); "
        "INSERT INTO t02_persistence_probe VALUES ('synthetic-restart-marker');",
    )
    compose("restart", "db", "web")
    wait_for_ready(base_url)
    value = compose(
        "exec",
        "-T",
        "db",
        "psql",
        "-U",
        "fieldops",
        "-d",
        "fieldops",
        "-Atc",
        "SELECT value FROM t02_persistence_probe",
    )
    assert value == "synthetic-restart-marker"
    mounts = json.loads(docker("inspect", compose("ps", "-q", "db")))[0]["Mounts"]
    assert any(
        mount["Type"] == "volume" and mount["Destination"] == "/var/lib/postgresql/data"
        for mount in mounts
    )
    # Also recreate the container: persistence must come from the volume, not its writable layer.
    compose("up", "-d", "--force-recreate", "db")
    wait_for_ready(base_url)
    assert (
        compose(
            "exec",
            "-T",
            "db",
            "psql",
            "-U",
            "fieldops",
            "-d",
            "fieldops",
            "-Atc",
            "SELECT value FROM t02_persistence_probe",
        )
        == "synthetic-restart-marker"
    )


def test_real_database_outage_and_recovery(isolated_stack):
    compose, base_url = isolated_stack
    # Read only into memory: never print the generated secret in assertion output.
    secret = compose("exec", "-T", "web", "cat", "/run/fieldops/db_password")
    try:
        compose("stop", "db")
        assert http_status(base_url, "/health/live") == (200, {"status": "alive"})
        status, payload = http_status(base_url, "/health/ready")
        assert status == 503
        assert payload["error"]["code"] == "database_unavailable"
        assert "postgresql" not in json.dumps(payload).lower()
        if secret in json.dumps(payload):
            pytest.fail("Generated credential leaked in readiness response")
    finally:
        compose("start", "db")
        wait_for_ready(base_url)
    assert http_status(base_url, "/health/ready") == (200, {"status": "ready"})
    logs = compose("logs", "--no-log-prefix", "web", "bootstrap", "credentials", "db")
    if secret in logs:
        pytest.fail("Generated credential leaked in service logs")
    for line in compose("logs", "--no-log-prefix", "web").splitlines():
        payload = json.loads(line)
        assert {"timestamp", "level", "service", "event"} <= payload.keys()
