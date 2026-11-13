"""Promotion gate: only a digest that completed a successful deployment is eligible.

Reads GitHub Deployment records for one environment and their latest statuses. A digest is
eligible when exactly that digest appears in a deployment payload whose latest status is
"success". Promotion checks the development environment; rollback checks production. Stale-run
prevention happens at deployment time. Pure functions are unit-tested; the GitHub client is
the only I/O.
"""

import json
import os
import re
import subprocess
import sys

DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


def eligible(digest: str, deployments: list[dict], environment: str = "development") -> dict | None:
    """Return the successful deployment record of `environment` for `digest`, else None."""
    if not DIGEST.match(digest or ""):
        return None
    for record in deployments:
        payload = record.get("payload") or {}
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except ValueError:
                continue
        if (
            record.get("environment") == environment
            and payload.get("digest") == digest
            and record.get("latest_status") == "success"
        ):
            return record
    return None


def github(path: str) -> list | dict:
    result = subprocess.run(
        ["gh", "api", "--paginate", path], capture_output=True, text=True, check=True, timeout=60
    )
    return json.loads(result.stdout)


def load_deployments(repository: str, environment: str = "development") -> list[dict]:
    records = github(f"repos/{repository}/deployments?environment={environment}&per_page=50")
    for record in records:
        statuses = github(f"repos/{repository}/deployments/{record['id']}/statuses?per_page=1")
        record["latest_status"] = statuses[0]["state"] if statuses else "unknown"
    return records


def main() -> int:
    digest = sys.argv[1] if len(sys.argv) > 1 else ""
    environment = sys.argv[2] if len(sys.argv) > 2 else "development"
    repository = os.environ["GITHUB_REPOSITORY"]
    record = eligible(digest, load_deployments(repository, environment), environment)
    if record is None:
        print(
            json.dumps(
                {
                    "eligible": False,
                    "digest": digest,
                    "reason": f"no successful {environment} deployment with this exact digest",
                }
            )
        )
        return 1
    payload = (
        record["payload"] if isinstance(record["payload"], dict) else json.loads(record["payload"])
    )
    output = {
        "eligible": True,
        "digest": digest,
        "source_environment": environment,
        "source_deployment_id": record["id"],
        "commit": record.get("sha"),
        "migration_version": payload.get("migration_version"),
        "source_run": payload.get("run_url"),
    }
    print(json.dumps(output))
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as handle:
            for key, value in output.items():
                handle.write(f"{key}={value}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
