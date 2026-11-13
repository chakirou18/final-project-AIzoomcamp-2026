# Temporary public demo through Cloudflare Tunnel

This publishes the FieldOps synthetic intervention journey over HTTPS for a reviewer, for a limited time, from the owner's Windows machine. It does not replace the hosted deployment in T13. **The tunnel must not be started until the owner approves exposure.** As of 2026-11-13 it has never been started.

## What is public and what is not

| Surface | Through the tunnel |
|---|---|
| `/app/*` HTML journeys, `/api/v1/interventions*`, `/api/v1/notifications*`, `/auth/*`, `/session*`, `/static/*` | Reachable **only with the demo access code** (HTTP Basic, user `demo`); then normal persona session, CSRF and role checks apply |
| `/health/live`, `/health/ready` | Public (status only) |
| `/metrics`, `/internal/*`, `/demo/*` (fault simulation), `/app/operator*`, `/app/dashboard`, `/app/worker/*`, `/api/v1/dashboard`, `/api/v1/incidents*`, `/docs`, `/redoc`, `/openapi.json`, `/contracts/*` | **404**, even with the access code |
| PostgreSQL, worker, Ollama, Prometheus, Alertmanager, Loki, Jaeger, Grafana, agent | Not part of the demo project; nothing else is published |

Additional controls:

- **Configuration fails closed.** `FIELDOPS_PUBLIC_DEMO=true` refuses to start unless the environment is non-local, demo personas are on, an access code of at least 20 characters exists, and no operator, recovery or agent credential is loaded.
- **Operator access is off.** The persona list never offers the operator, and an operator login is refused.
- **Local-only controls stay off.** Fault simulation and pause controls are local-only in code, so they are unavailable in the `public-demo` environment.
- **Session cookies** are `Secure`, `HttpOnly` and `SameSite=Lax`. Sessions last at most 8 hours and logout revokes them.
- **Rate limits per client address:** 120 requests per minute, and a 10-minute lockout after 10 failed access-code attempts. The client address comes from Cloudflare's `CF-Connecting-IP`, which is trusted only because the web port is loopback-only.
- **Security headers:** CSP, HSTS, `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy` and `Cache-Control: no-store`.
- **Isolation:** a separate Compose project `fieldops-public-demo` with its own PostgreSQL volume, credentials and network (10.254.40.0/24). Synthetic personas are seeded on start, and the existing projects and volumes are untouched.
- **Container hardening:** the web container runs read-only as UID 10001 with all capabilities dropped and a 512 MiB memory limit.

The access code is one shared secret for the demo, not per-user authentication. Anyone who holds it can choose the synthetic dispatcher or a technician. That is acceptable for a short reviewer demonstration with synthetic data only. If you have a Cloudflare account, put Cloudflare Access (email one-time PIN) in front of a named tunnel as an extra layer; see below.

## Start the isolated demo stack

```powershell
$env:COMPOSE_PROJECT_NAME='fieldops-public-demo'
docker compose --env-file deploy/environments/public-demo.env.example -f docker-compose.yml -f docker-compose.public-demo.yml up --build --wait
```

To read the generated access code for the reviewer, run the command below. Share the code through a private channel; never paste it into issues, PRs or documents. In Git Bash, prefix the command with `MSYS_NO_PATHCONV=1`.

```powershell
docker exec fieldops-public-demo-web-1 cat /run/fieldops-public/access_code
```

## Verify before exposure (must pass)

```powershell
$env:FIELDOPS_PUBLIC_DEMO_CODE = (docker exec fieldops-public-demo-web-1 cat /run/fieldops-public/access_code).Trim()
.venv/Scripts/python.exe scripts/smoke/public_demo_check.py --base-url http://127.0.0.1:18400 --output public-demo-check.json
Remove-Item Env:FIELDOPS_PUBLIC_DEMO_CODE
```

## Option 1: quick tunnel (no Cloudflare account; random `*.trycloudflare.com` URL)

Run this only after owner approval. The tunnel lives as long as the process does; stop it with Ctrl+C.

```powershell
& "C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel --no-autoupdate --url http://127.0.0.1:18400
```

Cloudflare prints the HTTPS URL. Cloudflare documents quick tunnels as intended for testing, without uptime guarantees. Check the public boundary from outside, then share the URL and the access code separately:

```powershell
.venv/Scripts/python.exe scripts/smoke/public_demo_check.py --base-url https://<random>.trycloudflare.com --output public-demo-check-public.json
```

## Option 2: named tunnel with your own domain, optionally behind Cloudflare Access

This requires a Cloudflare account and a zone. Commands:

```powershell
$cf = "C:\Program Files (x86)\cloudflared\cloudflared.exe"
& $cf tunnel login                              # opens the browser; stores a cert in %USERPROFILE%\.cloudflared
& $cf tunnel create fieldops-demo
& $cf tunnel route dns fieldops-demo demo.<your-domain>
& $cf tunnel --config deploy/cloudflared/config.example.yml run fieldops-demo
```

Fill in `deploy/cloudflared/config.example.yml` with the tunnel ID and credentials path. Its ingress allows only the demo hostname to reach `http://127.0.0.1:18400` and answers 404 for everything else. In the Cloudflare Zero Trust dashboard, an Access application for `demo.<your-domain>` with an email one-time-PIN policy adds per-person authentication in front of the access code.

## Stop and clean up (non-destructive)

```powershell
# Ctrl+C in the cloudflared window ends public exposure immediately.
$env:COMPOSE_PROJECT_NAME='fieldops-public-demo'
docker compose --env-file deploy/environments/public-demo.env.example -f docker-compose.yml -f docker-compose.public-demo.yml stop
```

`stop` keeps the demo volumes. Remove them only deliberately. Deleting the demo's own volumes with `down -v` affects only `fieldops-public-demo_*`, but it is still a destructive step that needs owner approval.

## Verification evidence (2026-11-13, local, tunnel not started)

| Check | Result |
|---|---|
| `tests/test_public_demo.py` (gate, private paths, lockout, per-client limits, rate limit, headers, fail-closed config) | 37 passed |
| Full backend unit suite | 244 passed |
| Targeted PostgreSQL regression (sessions, settings and bootstrap, web, controls, public demo) on the retained test DB | 120 passed |
| Live `public_demo_check.py` against the isolated project | 37/37 checks passed: 401 without code or with a wrong code, 404 on 13 private surfaces, operator refused, cookie flags, CSRF, role denials, create → assign → inbox delivery → start → complete → history, logout revocation |
| Exposure | only `127.0.0.1:18400` published; db and worker unpublished; web read-only, all capabilities dropped, no operator/recovery/agent credential in its environment |
