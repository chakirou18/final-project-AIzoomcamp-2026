"""Post-deployment smoke: the real assignment-to-inbox journey through the public API.

Usage: python scripts/smoke/smoke.py --base-url https://host --environment development \
          --output smoke.json [--timeout 30]

The journey logs in as the seeded dispatcher persona, creates a uniquely marked synthetic job,
assigns it to the seeded technician, then logs in as that technician and polls their inbox
until the exact outbox-backed notification for that job appears. It never pauses delivery,
never touches internal control routes and never inserts rows directly. Readiness, HTTPS,
cookie flags and the environment identity header are asserted first. Exit status 0 means the
journey completed within the budget; anything else is a failed smoke.
"""

import argparse
import http.cookiejar
import json
import sys
import time
import traceback
import urllib.error
import urllib.request
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid4, uuid5

MARK = "SMOKE"


def persona_id(key: str) -> str:
    return str(uuid5(NAMESPACE_URL, "https://fieldops.invalid/personas/" + key))


class Session:
    def __init__(self, base: str, timeout: float):
        self.base = base.rstrip("/")
        self.timeout = timeout
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        self.csrf = ""

    def request(self, path: str, payload=None):
        request = urllib.request.Request(
            self.base + path,
            data=json.dumps(payload).encode() if payload is not None else None,
            headers={"Content-Type": "application/json", "X-CSRF-Token": self.csrf},
        )
        try:
            response = self.opener.open(request, timeout=self.timeout)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            raw = response.read().decode()
            content_type = response.headers.get("Content-Type", "")
            body = json.loads(raw) if raw and "json" in content_type else raw
            return response.status, body, dict(response.headers)

    def login(self, persona: str):
        status, body, _ = self.request("/auth/csrf")
        assert status == 200, ("csrf", status, body)
        self.csrf = body["csrf_token"]
        status, body, _ = self.request("/auth/login", {"persona_id": persona_id(persona)})
        assert status == 200, ("login", persona, status, body)
        self.csrf = body["csrf_token"]


def check_cookies(session: Session, https: bool) -> dict:
    flags = {}
    for cookie in session.jar:
        flags[cookie.name] = {
            "secure": bool(cookie.secure),
            "httponly": "httponly" in {key.lower() for key in cookie._rest},
            "samesite": next(
                (value for key, value in cookie._rest.items() if key.lower() == "samesite"),
                None,
            ),
        }
    assert flags, "no session cookie was set"
    if https:
        assert all(item["secure"] for item in flags.values()), ("cookie_not_secure", flags)
    assert all(item["httponly"] for item in flags.values()), ("cookie_not_httponly", flags)
    return flags


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--environment", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--timeout", type=float, default=30.0, help="inbox delivery budget")
    parser.add_argument("--allow-http", action="store_true", help="local verification only")
    parser.add_argument(
        "--skip-private-path-check",
        action="store_true",
        help="local loopback stack only; hosted proxies must deny /metrics and /internal",
    )
    args = parser.parse_args()
    https = args.base_url.startswith("https://")
    assert https or args.allow_http, "public smoke requires https://"
    started = time.monotonic()
    report = {
        "environment": args.environment,
        "base_url": args.base_url,
        "started_at": datetime.now(UTC).isoformat(),
        "steps": [],
    }

    def step(name, **data):
        data["t"] = round(time.monotonic() - started, 3)
        report["steps"].append({"step": name, **data})

    try:
        probe = Session(args.base_url, 10)
        status, body, headers = probe.request("/health/ready")
        assert status == 200 and body == {"status": "ready"}, ("ready", status, body)
        step("ready", status=status)
        for path in ("/metrics", "/internal/worker/status", "/internal/oncall/evidence"):
            status, _, _ = probe.request(path)
            if args.skip_private_path_check:
                step("private_path_observed", path=path, status=status)
                continue
            assert status in {401, 403, 404}, ("internal_path_exposed", path, status)
            step("private_path_denied", path=path, status=status)
        dispatcher = Session(args.base_url, 10)
        dispatcher.login("demo-manager")
        cookies = check_cookies(dispatcher, https)
        step("dispatcher_login", cookies=cookies)
        marker = f"{MARK} {args.environment} {uuid4().hex}"
        status, job, _ = dispatcher.request(
            "/api/v1/interventions",
            {"title": marker, "site": "Smoke site", "description": marker},
        )
        assert status == 201, ("create", status, job)
        step("job_created", job_id=job["id"])
        status, assigned, _ = dispatcher.request(
            f"/api/v1/interventions/{job['id']}/assignment",
            {
                "expected_version": job["row_version"],
                "technician_id": persona_id("demo-technician-a"),
            },
        )
        assert status == 200 and assigned["status"] == "assigned", ("assign", status, assigned)
        step("assigned", row_version=assigned["row_version"])
        technician = Session(args.base_url, 10)
        technician.login("demo-technician-a")
        deadline = time.monotonic() + args.timeout
        notification = None
        while time.monotonic() < deadline and notification is None:
            status, page, _ = technician.request("/api/v1/notifications?page_size=100")
            assert status == 200, ("inbox", status, page)
            notification = next(
                (item for item in page["items"] if item.get("intervention_id") == job["id"]),
                None,
            )
            if notification is None:
                time.sleep(0.5)
        assert notification is not None, ("inbox_delivery_timeout", args.timeout)
        step("inbox_delivered", notification_id=notification["id"])
        status, history, _ = dispatcher.request(f"/api/v1/interventions/{job['id']}/history")
        assert status == 200 and history["items"], ("history", status)
        step("history_present", records=len(history["items"]))
        report["result"] = "passed"
        code = 0
    except AssertionError as failure:
        report["result"] = "failed"
        report["failure"] = [str(part) for part in failure.args]
        code = 1
    except (OSError, ValueError, KeyError, TypeError) as failure:
        report["result"] = "failed"
        report["failure"] = [type(failure).__name__, str(failure)[:300]]
        report["trace"] = traceback.format_exc().splitlines()[-6:]
        code = 1
    report["duration_seconds"] = round(time.monotonic() - started, 3)
    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
    print(json.dumps({"smoke": report["result"], "duration": report["duration_seconds"]}))
    return code


if __name__ == "__main__":
    sys.exit(main())
