"""T12 pipeline checks: promotion gate, secret scan, hosted configuration isolation."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if not (ROOT / "scripts" / "deploy" / "verify_digest.py").exists():
    pytest.skip("pipeline scripts are not mounted in this test image", allow_module_level=True)
DIGEST = "sha256:" + "a" * 64
OTHER = "sha256:" + "b" * 64


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


verify_digest = load("verify_digest", "scripts/deploy/verify_digest.py")
secret_scan = load("secret_scan", "scripts/ci/secret_scan.py")


def deployment(**overrides):
    record = {
        "id": 1,
        "environment": "development",
        "sha": "c" * 40,
        "payload": {"digest": DIGEST, "run_url": "https://example.invalid/run/1"},
        "latest_status": "success",
    }
    record.update(overrides)
    return record


def test_only_a_successful_development_tested_digest_is_promotable():
    assert verify_digest.eligible(DIGEST, [deployment()])["id"] == 1
    assert verify_digest.eligible(OTHER, [deployment()]) is None
    assert verify_digest.eligible(DIGEST, [deployment(latest_status="failure")]) is None
    assert verify_digest.eligible(DIGEST, [deployment(latest_status="in_progress")]) is None
    assert verify_digest.eligible(DIGEST, [deployment(environment="production")]) is None
    assert verify_digest.eligible(DIGEST, []) is None
    # Payload may arrive JSON-encoded from the API; malformed payloads are ignored.
    encoded = deployment(payload=json.dumps({"digest": DIGEST}))
    assert verify_digest.eligible(DIGEST, [encoded])["id"] == 1
    assert verify_digest.eligible(DIGEST, [deployment(payload="{not json")]) is None


@pytest.mark.parametrize("value", ["", "latest", "main", "sha-abc", "sha256:short", DIGEST.upper()])
def test_tags_branches_and_malformed_digests_are_rejected(value):
    assert verify_digest.eligible(value, [deployment(payload={"digest": value})]) is None


def test_rollback_gate_requires_a_previous_production_success():
    production = deployment(environment="production", payload={"digest": OTHER})
    assert verify_digest.eligible(OTHER, [production], "production")["environment"] == "production"
    assert verify_digest.eligible(OTHER, [production], "development") is None


def test_secret_scan_flags_credentials_and_allows_documented_synthetic_values(tmp_path):
    leaked = tmp_path / "leaked.txt"
    leaked.write_text(
        "AWS_KEY=AKIAABCDEFGHIJKLMNOP\n"
        "-----BEGIN OPENSSH PRIVATE KEY-----\n"
        'token = "ghp_0123456789abcdefghijklmnopqrstuvwxyz0123"\n',
        encoding="utf-8",
    )
    synthetic = tmp_path / "synthetic.txt"
    synthetic.write_text(
        'FIELDOPS_DB_PASSWORD: "synthetic-isolated-test-only-password"\n'
        "FIELDOPS_IMAGE=ghcr.io/example@sha256:REPLACE_WITH_DEVELOPMENT_DIGEST\n",
        encoding="utf-8",
    )
    found = secret_scan.findings([leaked, synthetic])
    assert {name for _, _, name in found} >= {"aws_access_key", "private_key", "github_token"}
    assert all(path == str(leaked) for path, _, _ in found)
    assert secret_scan.findings([synthetic]) == []


@pytest.mark.pipeline
def test_hosted_environments_render_isolated_and_digest_pinned(tmp_path):
    output = tmp_path / "isolation.json"
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/deploy/check_isolation.py"), "--output", str(output)],
        capture_output=True,
        text=True,
        timeout=300,
        cwd=ROOT,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["ok"] and report["problems"] == []
    dev, prod = report["development"], report["production"]
    assert dev["project"] != prod["project"] and dev["db_name"] != prod["db_name"]
    assert dev["db_user"] != prod["db_user"]
    assert not set(dev["volume_names"]) & set(prod["volume_names"])
    assert all(host == "127.0.0.1" for _, host, _ in dev["ports"] + prod["ports"])
    assert dev["app_builds"] == [] and prod["app_builds"] == []
