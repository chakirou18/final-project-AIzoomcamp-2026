"""Render both hosted environments and prove their configuration is separate and immutable.

Usage: python scripts/deploy/check_isolation.py [--output isolation.json]

Uses only `docker compose config` (CLI rendering, no daemon). Asserts that development and
production use different Compose projects, database names, database users, host ports,
subnets and volume names; that every application service runs a registry digest and defines
no build; and that no port is published outside loopback. Secrets are never printed.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP_SERVICES = {
    "credentials",
    "bootstrap",
    "web",
    "worker",
    "alert-credentials",
    "alert-receiver",
    "oncall-bootstrap",
    "oncall-agent",
}
DIGEST = re.compile(r"@sha256:[0-9a-f]{64}$")


PLACEHOLDER_DIGEST = "ghcr.io/example/fieldops@sha256:" + "0" * 64


def render(environment: str, env_file: Path, image: str | None = None) -> dict:
    environment_variables = dict(os.environ)
    if image:
        environment_variables["FIELDOPS_IMAGE"] = image  # process env outranks --env-file
    result = subprocess.run(
        [
            "docker",
            "compose",
            "--project-directory",
            str(ROOT),
            "--env-file",
            str(env_file),
            "-f",
            str(ROOT / "docker-compose.yml"),
            "-f",
            str(ROOT / "docker-compose.deploy.yml"),
            "--profile",
            "observability",
            "--profile",
            "incident",
            "config",
            "--format",
            "json",
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=120,
        env=environment_variables,
    )
    config = json.loads(result.stdout)
    config["_environment"] = environment
    return config


def summarize(config: dict) -> dict:
    services = config["services"]
    db = services["db"]["environment"]
    ports = sorted(
        (service, str(port.get("host_ip", "")), int(port["published"]))
        for service, definition in services.items()
        for port in definition.get("ports", []) or []
    )
    networks = config.get("networks", {})
    subnets = sorted(
        block["subnet"]
        for network in networks.values()
        for block in (network.get("ipam", {}) or {}).get("config", []) or []
    )
    return {
        "environment": config["_environment"],
        "project": config["name"],
        "db_name": db["POSTGRES_DB"],
        "db_user": db["POSTGRES_USER"],
        "fieldops_environment": services["web"]["environment"]["FIELDOPS_ENVIRONMENT"],
        "ports": ports,
        "subnets": subnets,
        "volumes": sorted(config.get("volumes", {}).keys()),
        "volume_names": sorted(
            (definition.get("name") or f"{config['name']}_{key}")
            for key, definition in config.get("volumes", {}).items()
        ),
        "app_images": {name: services[name]["image"] for name in APP_SERVICES if name in services},
        "app_builds": [name for name in APP_SERVICES if services.get(name, {}).get("build")],
    }


def check(dev: dict, prod: dict) -> list[str]:
    problems = []
    for key in ("project", "db_name", "db_user", "fieldops_environment"):
        if dev[key] == prod[key]:
            problems.append(f"shared {key}: {dev[key]}")
    if set(dev["volume_names"]) & set(prod["volume_names"]):
        problems.append("shared volume names")
    if {p[2] for p in dev["ports"]} & {p[2] for p in prod["ports"]}:
        problems.append("shared host ports")
    if set(dev["subnets"]) & set(prod["subnets"]):
        problems.append("shared subnets")
    for summary in (dev, prod):
        for name, image in summary["app_images"].items():
            if not DIGEST.search(image):
                problems.append(f"{summary['environment']} {name} is not pinned by digest")
        if summary["app_builds"]:
            problems.append(
                f"{summary['environment']} has build definitions {summary['app_builds']}"
            )
        for service, host, _ in summary["ports"]:
            if host != "127.0.0.1":
                problems.append(f"{summary['environment']} {service} publishes on {host or '*'}")
        if summary["fieldops_environment"] != summary["environment"]:
            problems.append(f"{summary['environment']} runs as {summary['fieldops_environment']}")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output")
    parser.add_argument(
        "--development", default=ROOT / "deploy/environments/development.env.example"
    )
    parser.add_argument("--production", default=ROOT / "deploy/environments/production.env.example")
    parser.add_argument(
        "--image",
        default=PLACEHOLDER_DIGEST,
        help="digest reference substituted for the example placeholder; omit with real env files",
    )
    args = parser.parse_args()
    image = args.image or None
    dev = summarize(render("development", Path(args.development), image))
    prod = summarize(render("production", Path(args.production), image))
    problems = check(dev, prod)
    version = subprocess.run(
        ["docker", "compose", "version", "--short"], capture_output=True, text=True, timeout=60
    ).stdout.strip()
    report = {
        "compose_version": version,
        "development": dev,
        "production": prod,
        "problems": problems,
        "ok": not problems,
    }
    if args.output:
        Path(args.output).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"ok": report["ok"], "problems": problems}))
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
