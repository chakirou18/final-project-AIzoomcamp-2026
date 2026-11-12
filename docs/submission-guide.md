# FieldOps submission guide

Reviewer-facing entry point for the AI Dev Tools Zoomcamp 2026 final project. Every statement below points at something you can run or open; items that could not be produced are named as missing rather than implied. Supplied rubric: 12 criteria, 24 points ([rubric evidence](rubric-evidence.md)); the provisional 41-point interpretation is kept separate there and is not used for any claim.

## Purpose

FieldOps is a single-company technical maintenance application: dispatchers register and assign interventions, technicians receive durable assignment notifications and progress the work, operators watch delivery health. On top of that business flow sits a bounded, auditable On-Call agent: when a real Prometheus alert reports delayed notification delivery, the agent gathers fixed telemetry, asks a model for a structured diagnosis, waits for an operator's incident-specific grant, executes exactly one allowlisted recovery action and resolves the incident only after the affected notifications are verifiably delivered.

## Main features

- Intervention lifecycle with optimistic versioning, append-only history and transactional outbox (F01–F04).
- Durable technician inbox fed by a leased worker; idempotent delivery; restart survival (F05).
- Operator dashboard with real PostgreSQL counts, delayed-delivery detection and pause/resume demo controls (F06).
- Prometheus alert rules, Alertmanager, authenticated intake, Grafana with metric→log→trace links (F07, N05).
- On-Call agent: durable incidents, structured model diagnosis (local Ollama `llama3.2:3b` demonstrated), deterministic policy, operator grant, idempotent allowlisted resume, positive delivery verification (F08).
- OpenAPI, health endpoints, role/CSRF enforcement, private metrics and controls (F09, F10).

## Agent architecture (short)

`alert-receiver` (private, authenticated) commits an incident episode → `oncall-agent` claims it with a fenced lease → fixed read-only tools (application evidence endpoint, Prometheus, Loki, Jaeger) → one bounded structured-output model call → deterministic `policy()` → operator grant via session + CSRF → single `resume_notification_worker` with a stable key through the web execution guard → reconciliation → two healthy verification samples → `RESOLVED` or `ESCALATED`, all persisted in PostgreSQL with append-only events. Details: [architecture](architecture.md), [T11 validation](t11-validation.md), [T11 audit](t11-audit.md).

## Technologies

Python 3.12, FastAPI, Jinja2/HTMX, SQLAlchemy 2, Alembic, PostgreSQL 17, a separate Python worker, Prometheus, Alertmanager, Loki, Grafana Alloy, OpenTelemetry Collector, Jaeger, Grafana, Docker Compose, uv, Ruff, pytest, Playwright, GitHub Actions, Ollama (local model), Caddy (hosted edge).

## Local installation and startup

Prerequisites: Docker Engine/Desktop (Linux containers), Compose v2, optionally Python 3.12 + uv for host-side tests.

```bash
docker compose up --build --wait                                             # application + worker + PostgreSQL
docker compose --profile observability --profile incident up --build --wait  # full demo stack with monitoring and agent
```

Open `http://127.0.0.1:8000/session`. Demo identities are seeded synthetic personas (dispatcher, two technicians). The operator persona needs the locally generated operator secret: `docker compose exec -T web cat /run/fieldops-controls/operator_key` (never paste it into documents or chats). All data is synthetic.

## Reproduce the intervention workflow

Dispatcher: create an intervention, assign it to Technician A. Technician A: the inbox shows the assignment within seconds; start and complete the job with a resolution. Operator: dashboard counts and undelivered total. Scripted equivalent: `python scripts/smoke/smoke.py --base-url http://127.0.0.1:8000 --environment local --allow-http --skip-private-path-check --output smoke.json`.

## Reproduce a controlled incident and verify the agent

Follow [demo-script.md](demo-script.md) section 3. In short: operator pauses delivery (`POST /demo/worker/pause`), dispatcher assigns a job, the `NotificationQueueDelayed` alert fires after about 100 s, the incident appears in `GET /api/v1/incidents`, the agent persists a diagnosis (`model_intent` names the provider and model), the operator grants `POST /api/v1/incidents/{id}/authorize`, the agent resumes the worker once, verifies delivery and resolves. To use the real model set `FIELDOPS_ONCALL_PROVIDER=ollama`, `FIELDOPS_ONCALL_PROVIDER_URL`, `FIELDOPS_ONCALL_MODEL=llama3.2:3b`, `FIELDOPS_ONCALL_PROVIDER_APPROVED=true`, `FIELDOPS_ONCALL_PROVIDER_TIMEOUT=30` (CPU inference; structured output crashed this machine's Vulkan backend). Without a provider the incident escalates safely.

Inspect evidence: `GET /api/v1/incidents/{id}` (events, diagnosis, verification, affected outbox ids); SQL on `incidents`, `incident_events`, `incident_actions`, `worker_resume_actions`, `notification_outbox`, `notifications`. The recorded real-model run is `artifacts/t11-real-5bd8899d1d424a9ab234acf3b3f405a1/evidence.json` (local artifacts are git-ignored; the audit documents quote the values).

## Observe the alert and monitoring

Grafana `http://127.0.0.1:3000` (thirteen panels, metric→Loki→Jaeger links), Prometheus and Alertmanager on the private Compose network, Jaeger `http://127.0.0.1:16686`. Alert rules and their 27 promtool assertions: `observability/notification-rules*.yml`.

## Tests

```bash
uv sync --frozen
uv run pytest -m "not integration and not container"            # backend unit + pipeline checks (mock model)
docker compose --profile test run --build --rm tests            # real PostgreSQL integration suite
docker compose --profile browser run --build --rm browser-tests # Chromium journeys + N03 benchmark
FIELDOPS_RUN_OBSERVABILITY_TESTS=1 uv run pytest observability_tests   # against the isolated synthetic stack
FIELDOPS_RUN_ALERTING_TESTS=1 uv run pytest alerting_tests
FIELDOPS_RUN_AGENT_TESTS=1 uv run pytest agent_tests/test_live.py      # mock live incident
```

Latest fresh ledger and counts: [T15 final review](t15-final-review.md).

## CI/CD, deployment, rollback

- Workflows: `.github/workflows/` ([T12 validation](t12-validation.md), [T12 audit](t12-audit.md)). Real PR validation runs exist for PR #26; the production promotion and development deployment jobs cannot run until branch protection, GitHub environments, secrets and hosting exist.
- Deployment and rollback procedures: [T13 deployment](t13-deployment.md), [T13 rollback](t13-rollback.md), [T13 validation](t13-validation.md). **No public deployment exists.** No public URL is claimed.

## Demo video

**Not recorded.** The timestamped recording plan and narration are in [demo-script.md](demo-script.md) section 5.

## Known limitations

Local hosting only; the 3B model is advisory and unreliable on counterfactuals (the deterministic policy decides); CPU inference required on this GPU; five worker-stop cases and one database-deletion assertion are unexecuted under the data-preservation rule; remote CI/CD acceptance, hosting, production approval, rollback rehearsal and the video are pending owner actions.

## Links for submission

- Repository: https://github.com/chakirou18/final-project-AIzoomcamp-2026
- Pull requests: #21–#26 (feature chain T07→T12), see [evidence index](evidence-index.md)
- Issues: #1–#15 public tracker
- Evidence index and rubric mapping: [evidence-index.md](evidence-index.md)
- Final review and checklist: [t15-final-review.md](t15-final-review.md), [final-release-checklist.md](final-release-checklist.md)
