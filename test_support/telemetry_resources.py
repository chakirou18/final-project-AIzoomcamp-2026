"""Opt-in host-side T09 resource sampling; no Docker socket in application containers."""

import json
import os
import subprocess
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

from observability_tests.test_stack import GRAFANA, PROJECT, assign, compose, delivered

SERVICES = {
    "prometheus": "/prometheus",
    "grafana": "/var/lib/grafana",
    "loki": "/loki",
    "alloy": "/var/lib/alloy",
    "otel-collector": None,  # Stateless; bounded in-memory queue, no writable data mount.
    "jaeger": "/data",
    "alertmanager": "/alertmanager",
}


def snapshot():
    names = [f"{PROJECT}-{name}-1" for name in SERVICES]
    result = subprocess.run(
        ["docker", "stats", "--no-stream", "--format", "{{json .}}", *names],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    rows = {row["Name"]: row for line in result.stdout.splitlines() if (row := json.loads(line))}
    values = {}
    for name, directory in SERVICES.items():
        status = compose("exec", "-T", name, "/busybox", "cat", "/proc/1/status")
        rss = next(
            int(line.split()[1]) for line in status.splitlines() if line.startswith("VmRSS:")
        )
        disk = (
            int(compose("exec", "-T", name, "/busybox", "du", "-sk", directory).split()[0])
            if directory
            else 0
        )
        row = rows[f"{PROJECT}-{name}-1"]
        values[name] = {
            "cpu_percent": float(row["CPUPerc"].rstrip("%")),
            "container_memory": row["MemUsage"],
            "pid1_rss_kib": rss,
            "data_directory": directory,
            "data_kib": disk,
        }
    return {"at": datetime.now(UTC).isoformat(), "services": values}


def main():
    if os.getenv("FIELDOPS_RUN_OBSERVABILITY_TESTS") != "1":
        raise SystemExit("Requires the explicit isolated T09 validation opt-in")
    destination = Path("artifacts") / ("t09-resources-" + str(time.time_ns()))
    destination.mkdir(parents=True)
    idle = snapshot()
    stop_at = time.monotonic() + 25
    events = []

    def load(client):
        group = []
        while time.monotonic() < stop_at:
            row = assign("resource-load")
            group.append(row["id"])
            delivered(row)
        return group

    def queries():
        count = 0
        while time.monotonic() < stop_at:
            parameters = urllib.parse.urlencode({"query": "fieldops_notifications_undelivered"})
            with urllib.request.urlopen(
                GRAFANA
                + "/api/datasources/proxy/uid/fieldops-prometheus/api/v1/query?"
                + parameters,
                timeout=5,
            ) as response:
                assert json.load(response)["status"] == "success"
            count += 1
            time.sleep(
                0.25
            )  # Fixed read-query load cadence, not a test synchronization assumption.
        return count

    with ThreadPoolExecutor(max_workers=3) as executor:
        tasks = [executor.submit(load, n) for n in range(2)]
        query_task = executor.submit(queries)
        time.sleep(3)
        active = snapshot()
        for future in tasks:
            events.extend(future.result(timeout=60))
        query_count = query_task.result(timeout=30)
    final = snapshot()
    report = {
        "idle": idle,
        "active": active,
        "final": final,
        "assignments_delivered": len(events),
        "event_ids": events,
        "active_clients": 2,
        "grafana_prometheus_queries": query_count,
        "minimum_load_seconds": 25,
    }
    report["data_growth_kib"] = {
        name: final["services"][name]["data_kib"] - idle["services"][name]["data_kib"]
        for name in SERVICES
    }
    (destination / "resources.json").write_text(json.dumps(report, indent=2))
    print("T09_RESOURCES", destination, json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
