"""Live verification of the public-demo boundary and the core journey (no tunnel needed).

Usage: FIELDOPS_PUBLIC_DEMO_CODE=<access code> python scripts/smoke/public_demo_check.py \
           --base-url http://127.0.0.1:18400 --output public-demo-check.json

The access code is read from the environment and never printed or written to the report.
Cookies are handled explicitly so the Secure flag can be asserted even over loopback HTTP
(the public path is HTTPS at the Cloudflare edge). Exit 0 only when every check passes.
"""

import argparse
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from uuid import NAMESPACE_URL, uuid4, uuid5

PRIVATE = [
    ("GET", "/metrics"),
    ("GET", "/internal/worker/status"),
    ("POST", "/internal/worker/resume"),
    ("GET", "/internal/oncall/evidence"),
    ("POST", "/demo/worker/pause"),
    ("GET", "/docs"),
    ("GET", "/openapi.json"),
    ("GET", "/contracts/openapi.json"),
    ("GET", "/api/v1/incidents"),
    ("GET", "/api/v1/dashboard"),
    ("GET", "/app/operator"),
    ("GET", "/app/dashboard"),
    ("POST", "/app/worker/pause"),
]


def persona_id(key):
    return str(uuid5(NAMESPACE_URL, "https://fieldops.invalid/personas/" + key))


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class Client:
    def __init__(self, base, code):
        self.base, self.code = base.rstrip("/"), code
        self.cookies, self.csrf, self.set_cookie_headers = {}, "", []
        self.opener = urllib.request.build_opener(NoRedirect)

    def request(self, method, path, payload=None, *, auth=True, code=None, form=None, headers=None):
        data, content = None, "application/json"
        if form is not None:
            data, content = (
                urllib.parse.urlencode(form).encode(),
                "application/x-www-form-urlencoded",
            )
        elif payload is not None:
            data = json.dumps(payload).encode()
        h = {"Content-Type": content, **(headers or {})}
        if auth:
            token = base64.b64encode(f"demo:{code or self.code}".encode()).decode()
            h["Authorization"] = "Basic " + token
        if self.csrf:
            h["X-CSRF-Token"] = self.csrf
        if self.cookies:
            h["Cookie"] = "; ".join(f"{k}={v}" for k, v in self.cookies.items())
        req = urllib.request.Request(self.base + path, data=data, headers=h, method=method)
        try:
            response = self.opener.open(req, timeout=10)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            raw = response.read().decode(errors="replace")
            for value in response.headers.get_all("Set-Cookie") or []:
                self.set_cookie_headers.append(value)
                name, _, rest = value.partition("=")
                token = rest.split(";", 1)[0]
                if "max-age=0" in value.lower() or token in ("", '""'):
                    self.cookies.pop(name, None)
                else:
                    self.cookies[name] = token
            ctype = response.headers.get("Content-Type", "")
            body = json.loads(raw) if raw and "json" in ctype else raw
            return response.status, body, response.headers

    def login(self, persona, secret=None):
        status, body, _ = self.request("GET", "/auth/csrf")
        assert status == 200, ("csrf", status)
        self.csrf = body["csrf_token"]
        payload = {"persona_id": persona_id(persona)}
        if secret is not None:
            payload["operator_secret"] = secret
        status, body, _ = self.request("POST", "/auth/login", payload)
        if status == 200:
            self.csrf = body["csrf_token"]
        return status, body


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    code = os.environ.get("FIELDOPS_PUBLIC_DEMO_CODE", "")
    assert len(code) >= 20, "set FIELDOPS_PUBLIC_DEMO_CODE"
    results, failures = [], []

    def check(name, condition, detail=None):
        results.append({"check": name, "pass": bool(condition), "detail": detail})
        if not condition:
            failures.append(name)

    anon = Client(args.base_url, code)
    status, _, headers = anon.request("GET", "/health/ready", auth=False)
    check("health ready without access code", status == 200, status)
    check(
        "security headers present",
        headers.get("X-Frame-Options") == "DENY"
        and "frame-ancestors 'none'" in headers.get("Content-Security-Policy", ""),
    )
    for path in ("/", "/app/login", "/api/v1/interventions", "/static/app.css", "/auth/personas"):
        status, _, headers = anon.request("GET", path, auth=False)
        check(
            f"no access code -> 401 {path}",
            status == 401 and "Basic" in headers.get("WWW-Authenticate", ""),
            status,
        )
    status, _, _ = anon.request("GET", "/app/login", code="wrong-access-code-xxxxxxxx")
    check("wrong access code -> 401", status == 401, status)
    for method, path in PRIVATE:
        status, _, _ = anon.request(method, path, {} if method == "POST" else None)
        check(f"private {method} {path} -> 404 with access code", status == 404, status)

    status, personas, _ = anon.request("GET", "/auth/personas")
    roles = sorted(p["role"] for p in personas) if status == 200 else []
    check("persona list excludes operator", status == 200 and "operator" not in roles, roles)
    op = Client(args.base_url, code)
    status, _ = op.login("demo-operator", secret="x" * 40)
    check("operator persona login refused", status == 403, status)

    dispatcher = Client(args.base_url, code)
    status, _ = dispatcher.login("demo-manager")
    check("dispatcher login", status == 200, status)
    session_cookie = next(
        (h for h in dispatcher.set_cookie_headers if h.startswith("fieldops_session=")), ""
    )
    flags = session_cookie.lower()
    check(
        "session cookie Secure, HttpOnly, SameSite=Lax",
        "secure" in flags and "httponly" in flags and "samesite=lax" in flags,
    )
    saved = dispatcher.csrf
    dispatcher.csrf = ""
    status, _, _ = dispatcher.request("POST", "/api/v1/interventions", {"title": "x", "site": "y"})
    check("mutation without CSRF -> 403", status == 403, status)
    dispatcher.csrf = saved
    marker = "PUBLIC-DEMO " + uuid4().hex[:10]
    status, job, _ = dispatcher.request(
        "POST",
        "/api/v1/interventions",
        {"title": marker, "site": "Synthetic site", "description": "synthetic"},
    )
    check("dispatcher creates intervention", status == 201, status)
    status, assigned, _ = dispatcher.request(
        "POST",
        f"/api/v1/interventions/{job['id']}/assignment",
        {"expected_version": job["row_version"], "technician_id": persona_id("demo-technician-a")},
    )
    check(
        "dispatcher assigns technician",
        status == 200 and assigned.get("status") == "assigned",
        status,
    )
    status, page, _ = dispatcher.request("GET", "/app/interventions")
    check("HTML navigation /app/interventions", status == 200 and marker in page, status)

    tech = Client(args.base_url, code)
    status, _ = tech.login("demo-technician-a")
    check("technician login", status == 200, status)
    status, _, _ = tech.request("POST", "/api/v1/interventions", {"title": "x", "site": "y"})
    check("technician cannot create interventions (403)", status == 403, status)
    status, _, _ = dispatcher.request("GET", "/api/v1/notifications")
    check("dispatcher cannot read technician inbox (403)", status == 403, status)
    deadline, note = time.monotonic() + 30, None
    while time.monotonic() < deadline and note is None:
        status, inbox, _ = tech.request("GET", "/api/v1/notifications?page_size=100")
        note = (
            next((n for n in inbox.get("items", []) if n["intervention_id"] == job["id"]), None)
            if status == 200
            else None
        )
        if note is None:
            time.sleep(0.5)
    check("notification delivered to technician inbox", note is not None)
    status, started, _ = tech.request(
        "POST",
        f"/api/v1/interventions/{job['id']}/transitions",
        {"expected_version": assigned["row_version"], "target_status": "in_progress"},
    )
    check(
        "technician starts work", status == 200 and started.get("status") == "in_progress", status
    )
    status, done, _ = tech.request(
        "POST",
        f"/api/v1/interventions/{job['id']}/transitions",
        {
            "expected_version": started.get("row_version"),
            "target_status": "completed",
            "resolution": "Synthetic resolution",
        },
    )
    check("technician completes work", status == 200 and done.get("status") == "completed", status)
    status, history, _ = dispatcher.request("GET", f"/api/v1/interventions/{job['id']}/history")
    check(
        "history records the lifecycle",
        status == 200 and history.get("total", 0) >= 4,
        history.get("total") if status == 200 else status,
    )
    status, _, _ = tech.request("POST", "/auth/logout")
    after, _, _ = tech.request("GET", "/api/v1/notifications")
    check("logout revokes the session", status == 204 and after == 401, (status, after))

    report = {
        "base_url": args.base_url,
        "passed": len(results) - len(failures),
        "failed": failures,
        "results": results,
    }
    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
    print(json.dumps({"passed": report["passed"], "failed": failures}))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
