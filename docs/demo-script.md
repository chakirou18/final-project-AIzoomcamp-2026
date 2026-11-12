# FieldOps reviewer walkthrough and incident demonstration script

A reproducible, local, synthetic-data walkthrough of the complete FieldOps journey: dispatcher assignment, technician inbox, operator dashboard, a real delivery delay alert, a genuine model-assisted diagnosis, an operator-approved allowlisted recovery and verified delivery. Every step names the command, the expected observation and the evidence it produced in the recorded run. **No video recording exists yet**; the storyboard at the end is the narration plan for one.

## 0. Prerequisites (5 minutes)

- Docker Desktop (Linux containers), Compose v2, Python 3.12 with uv for host-side tests.
- An existing local Ollama server with `llama3.2:3b` reachable from containers (`host.docker.internal:11434` by default). On this machine the primary instance's folder ACL is broken and structured output crashes the Vulkan backend, so the recorded run used a second CPU-only instance on port 11435; see [T11 audit](t11-audit.md). Without a provider the demo still works up to a safe escalation.
- Synthetic environment variables (`artifacts/t10-env.ps1`): project `fieldops-t09`, web port 18009, Grafana 13009, Jaeger 16689, database `fieldops_t09_demo_test`.

```powershell
. ./artifacts/t10-env.ps1
docker compose --profile observability --profile incident up --build --wait
```

Expected: `web`, `worker`, `alert-receiver`, `oncall-agent`, Prometheus, Alertmanager, Loki, Alloy, OTel collector, Jaeger and Grafana healthy; migration revision `0004_t11_incidents`; four synthetic personas seeded.

## 1. Dispatcher and technician journey (3 minutes)

1. Open `http://127.0.0.1:18009/session`, pick the synthetic dispatcher, create a job, assign it to Technician A. Observation: status `assigned`, history row, one outbox event (dashboard undelivered count rises briefly).
2. Switch to Technician A: the inbox shows the assignment within two seconds; mark read is idempotent. Start and complete the job with a resolution.
3. Evidence: `scripts/smoke/smoke.py` performs exactly this journey through the JSON API; local report `artifacts/claude/smoke-local.json` (inbox delivery 0.67 s after assignment). Chromium evidence: `artifacts/t08-browser-*/pytest.xml` (18 cases, desktop and 375 px).

## 2. Operator dashboard and telemetry (2 minutes)

1. Activate the operator persona with the local operator secret (`docker compose exec -T web cat /run/fieldops-controls/operator_key`; never paste it into documents).
2. `GET /api/v1/dashboard`: five status counts, undelivered total, oldest age, worker heartbeat and pause generation.
3. Grafana (`http://127.0.0.1:13009`): thirteen panels; follow a metric → Loki log → Jaeger trace link for one outbox id. Evidence: T09 validation and `artifacts/t11-t09-regression.xml` (10 cases).

## 3. Incident: real alert, real diagnosis, approved recovery (6 minutes)

Recorded run: `agent_tests/test_real_model.py`, evidence directory `artifacts/t11-real-5bd8899d1d424a9ab234acf3b3f405a1/`.

| Step | Command / action | Expected observation | Recorded value |
|---|---|---|---|
| Pause delivery (demo-only operator control) | `POST /demo/worker/pause {expected_generation, duration_seconds: 240}` | `paused: true`, generation +1, worker heartbeat still fresh | generation 26 |
| Assign a job | dispatcher assignment | outbox pending, inbox empty, dashboard "delayed" after 60 s | outbox `d922fc79…` |
| Alert fires | Prometheus `NotificationQueueDelayed` (age > 60 s for 30 s) → Alertmanager → authenticated intake | incident `RECEIVED` within 110 s | 100.719 s |
| Diagnosis | agent snapshot (DB evidence, Prometheus, Loki, Jaeger) → one bounded model call | `DIAGNOSED`, `PAUSED_DELIVERY`, `model_intent` with provider/model | llama3.2:3b, 29.4 s stage |
| Operator authorization | `POST /api/v1/incidents/{id}/authorize {expected_generation}` (session + CSRF) | grant id, expiry ≤ 5 min | grant `4a7d29a7…` |
| Recovery | agent sends the single allowlisted resume with the stable key and grant id | `worker_resume_actions` row `resumed`, worker unpaused | key `7143ad6b…` |
| Verification | two healthy samples ≥ 5 s apart: affected outbox delivered, one inbox row, zero backlog, fresh heartbeat | `RESOLVED`, `verification.ok = true` | 6 samples, resolved 09:22:45 UTC |
| Audit trail | `GET /api/v1/incidents/{id}` | append-only events from `received` to `resolved` | 18 events |

Negative demonstrations (no model spend): revoke the grant or change the generation before authorization → `authorization_invalid`/`changed_operational_state`; stop telemetry → `missing_telemetry`; an unconfigured provider → `provider_unavailable`. Each path is covered by `tests/test_t11.py` and `tests/test_t11_audit*.py`.

## 4. Safety boundaries to point out (2 minutes)

- The model cannot choose a URL, SQL, shell or tool; its output is validated against a fixed schema and then judged by a deterministic policy that ignores the explanation text. Counterfactual outputs were denied in `artifacts/claude/preflight-probe-6.json`.
- The agent database role cannot read business tables or modify grants; the agent bearer can only resume a persisted, operator-granted incident at the expected generation.
- Resolution is enforced by a PostgreSQL trigger that requires the successful action record, matching grant and delivered affected rows.

## 5. Video storyboard (target 4–5 minutes, not recorded)

1. 0:00 Title, architecture diagram (`docs/architecture.md`), one sentence on the paused-delivery scenario.
2. 0:30 Dispatcher assigns; technician inbox updates; dashboard counts.
3. 1:15 Operator pauses delivery; dashboard shows the delay; Grafana panel turns delayed; Alertmanager shows the firing alert.
4. 2:15 Incident list shows `RECEIVED` → `DIAGNOSED`; show the diagnosis JSON and the `model_intent` event naming the real model.
5. 3:00 Operator authorizes; events show `action_pending` → `action_response` (`resumed`) → verification samples → `RESOLVED`; technician inbox now holds the notification.
6. 4:00 Point at tests and evidence index; state the limitations (local hosting, advisory model, no remote CI run yet).

Narration must say "synthetic data", "local demonstration" and "the policy, not the model, authorizes the action".
