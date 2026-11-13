"""Opt-in public demonstration boundary (FIELDOPS_PUBLIC_DEMO=true).

Applied as the outermost ASGI middleware, before any route or session code:

* every request except the two health probes needs the shared demo access code (HTTP Basic,
  user ``demo``) delivered over the Cloudflare TLS edge;
* private surfaces (metrics, internal control and agent APIs, fault simulation, operator pages,
  incident API, OpenAPI/docs) answer 404 even with a valid access code;
* per-client request and failed-authentication limits answer 429;
* security headers are added to every response.

The client address is taken from ``CF-Connecting-IP`` only in this mode, where the web port is
bound to loopback and reachable solely through the local cloudflared connector.
"""

import base64
import binascii
import hmac
import json
import time
from collections import deque
from threading import Lock

HEALTH = {"/health/live", "/health/ready"}
BLOCKED_EXACT = {"/metrics", "/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"}
BLOCKED_PREFIXES = (
    "/metrics/",
    "/internal/",
    "/demo/",
    "/contracts/",
    "/api/v1/incidents",
    "/api/v1/dashboard",
    "/app/operator",
    "/app/dashboard",
    "/app/worker/",
)
SECURITY_HEADERS = [
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"same-origin"),
    (b"strict-transport-security", b"max-age=31536000"),
    (b"cross-origin-opener-policy", b"same-origin"),
    (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
    (
        b"content-security-policy",
        b"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        b"img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; "
        b"form-action 'self'; base-uri 'self'; object-src 'none'",
    ),
    (b"cache-control", b"no-store"),
]
USER = "demo"


def blocked(path: str) -> bool:
    return path in BLOCKED_EXACT or path.startswith(BLOCKED_PREFIXES)


class SlidingWindow:
    """Bounded in-memory per-key event counter for one process."""

    def __init__(self, limit: int, seconds: float, max_keys: int = 10000):
        self.limit, self.seconds, self.max_keys = limit, seconds, max_keys
        self.events: dict[str, deque] = {}
        self.lock = Lock()

    def _recent(self, key: str, now: float) -> deque:
        bucket = self.events.get(key)
        if bucket is None:
            if len(self.events) >= self.max_keys:
                # Drop the stalest key instead of growing without bound.
                stalest = min(
                    self.events, key=lambda k: self.events[k][-1] if self.events[k] else 0
                )
                self.events.pop(stalest, None)
            bucket = self.events[key] = deque()
        while bucket and bucket[0] <= now - self.seconds:
            bucket.popleft()
        return bucket

    def exceeded(self, key: str, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        with self.lock:
            return len(self._recent(key, now)) >= self.limit

    def hit(self, key: str, now: float | None = None) -> bool:
        """Record one event; return True when the limit was already reached."""
        now = time.monotonic() if now is None else now
        with self.lock:
            bucket = self._recent(key, now)
            if len(bucket) >= self.limit:
                return True
            bucket.append(now)
            return False


def header(scope, name: bytes) -> str:
    for key, value in scope.get("headers", []):
        if key == name:
            return value.decode("latin-1")
    return ""


def client_key(scope) -> str:
    forwarded = header(scope, b"cf-connecting-ip").strip()
    if forwarded and len(forwarded) <= 64:
        return forwarded
    client = scope.get("client")
    return client[0] if client else "unknown"


def authorized(scope, code: str) -> bool:
    value = header(scope, b"authorization")
    scheme, _, encoded = value.partition(" ")
    if scheme.lower() != "basic" or not encoded or len(encoded) > 512:
        return False
    try:
        user, separator, supplied = base64.b64decode(encoded, validate=True).decode().partition(":")
    except (binascii.Error, UnicodeDecodeError):
        return False
    return bool(separator) and hmac.compare_digest(
        (user + ":" + supplied).encode(), (USER + ":" + code).encode()
    )


class PublicDemoMiddleware:
    def __init__(self, app, settings_provider):
        self.app = app
        self.settings_provider = settings_provider
        self.requests = SlidingWindow(120, 60)  # limit refreshed from settings per request
        self.failures = SlidingWindow(10, 600)

    async def __call__(self, scope, receive, send):
        settings = self.settings_provider()
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        if settings is None:
            # Settings are loaded in the lifespan; never serve requests before that (fail closed).
            await respond(send, 503, "starting", "Service starting")
            return
        if not settings.public_demo:
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")

        async def with_headers(message):
            if message["type"] == "http.response.start":
                existing = {k.lower() for k, _ in message.get("headers", [])}
                message["headers"] = list(message.get("headers", [])) + [
                    (k, v) for k, v in SECURITY_HEADERS if k not in existing
                ]
            await send(message)

        if path in HEALTH:
            await self.app(scope, receive, with_headers)
            return
        key = client_key(scope)
        self.requests.limit = settings.public_demo_requests_per_minute
        if self.requests.hit(key):
            await respond(with_headers, 429, "rate_limited", "Too many requests", retry=60)
            return
        if self.failures.exceeded(key):
            await respond(with_headers, 429, "rate_limited", "Too many failed attempts", retry=600)
            return
        if not authorized(scope, settings.public_demo_access_code.get_secret_value()):
            self.failures.hit(key)
            await respond(
                with_headers,
                401,
                "unauthenticated",
                "Demo access code required",
                challenge=True,
            )
            return
        if blocked(path):
            await respond(with_headers, 404, "not_found", "Not found")
            return
        await self.app(scope, receive, with_headers)


async def respond(send, status, code, message, *, retry=None, challenge=False):
    body = json.dumps({"error": {"code": code, "message": message, "fields": {}}}).encode()
    headers = [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]
    if retry:
        headers.append((b"retry-after", str(retry).encode()))
    if challenge:
        headers.append(
            (b"www-authenticate", b'Basic realm="FieldOps public demo", charset="UTF-8"')
        )
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})
