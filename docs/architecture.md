> T06 local implementation update: a separate Python worker claims PostgreSQL outbox rows with SKIP LOCKED and 30-second fenced leases, consumes at most five attempts, and atomically materializes the unique persistent inbox row with delivery acknowledgement. JSON inbox/list/read routes now exist. T04 shared transactions/authorization remain intact. No UI, worker controls/heartbeat tables, observability stack, alerting or agent was added. Current authorization covers T06 feature-branch publication only; historical status/authorization statements below are superseded. See [T06 evidence](t06-validation.md).

# Architecture

Status: T03 schema, persona/session boundaries and executable draft lifecycle contracts passed independent audit; feature-branch publication authorized, PR review pending. T02 commit 24bde69 and PR #16 remain unchanged; broader workflows/worker/operations are proposed. [Specification](specification.md) defines behavior; [backlog](backlog.md) defines order.

T03 adds users, interventions, append-only intervention_history, notification_outbox, notifications and persona_sessions. Static revisions 0001_t03 and 0002_t03_review, database constraints and shared authorization scope helpers establish the persistence boundary. Bootstrap migrates and seeds four synthetic personas locally; nonlocal startup never seeds implicitly. Sessions are signed, database-revocable and capped at eight hours. Operator activation requires an environment secret. No business CRUD, worker, control or incident tables/routes exist yet. Future lifecycle OpenAPI is served separately and explicitly marked unimplemented; [contract details](t03-contracts.md) and [actual validation](t03-validation.md) distinguish executable foundation evidence from future behavior.

Current owner authorization covers one T03 feature-branch commit/push, a PR targeting feature/t02-foundation and an Issue #3 progress comment. Merge, Issue closure, T04 work, deployment, spending and volume deletion remain unauthorized. Earlier T01/T02 authorization statements in historical documents are superseded for current work.

## Component choices

Use a modular FastAPI monolith with Jinja2, HTMX and locally served Bootstrap assets. JSON and HTML handlers call the same service functions; authorization and transactions live in that service boundary. PostgreSQL is the only durable application store. SQLAlchemy and Alembic are proposed for access and migrations. A separate Python process runs the notification poll loop using the same application image. This avoids a broker, SPA build and distributed business services. Coverage takes priority over the superseded 20-hour target; see the revised estimate in the backlog.

Compose services: web, worker, PostgreSQL, on-call-agent, Prometheus, Alertmanager, Grafana, Loki, Grafana Alloy (structured log shipping), OpenTelemetry Collector and Jaeger. A deployment reverse proxy terminates TLS. Keep the proposed observability coverage; use stock pinned configurations and one Grafana dashboard. OTel SDKs export traces through the collector; logs are JSON to stdout, shipped by Alloy. Prometheus scrapes web-owned database-derived delivery gauges, so a stopped worker cannot hide the backlog. Grafana links metrics, Loki logs and Jaeger traces by service and trace ID.

## Data model

| Entity | Fields and constraints |
| --- | --- |
| users | UUID PK, unique persona_key, display_name, role (dispatcher/technician/operator), active; seeded identities only. |
| persona_sessions | SHA-256 digest of random signed cookie token PK, user_id FK, csrf_token, created_at, expires_at, revoked_at; eight-hour session lifetime. No cookie token/signing key stored in the table. |
| interventions | UUID PK, title, description, site, priority enum, status enum, technician_id nullable FK users, assignment_version default 0, row_version, resolution nullable, created_at, updated_at, started_at, closed_at. Status consistency checked in service and database constraints. |
| intervention_history | UUID PK, intervention_id FK, actor_id FK nullable for system, event_type, changed_fields JSON, created_at. No update/delete API. |
| notification_outbox | UUID PK/event ID, intervention_id FK, recipient_id FK, assignment_version, event_type fixed to assignment, traceparent/tracestate nullable, created_at, status (pending/processing/delivered/failed), available_at, attempts, lease_until, lease_token, delivered_at, last_error. UNIQUE(intervention_id, assignment_version, event_type). |
| notifications | UUID PK, outbox_id UNIQUE FK, recipient_id FK, intervention_id FK, assignment_version, created_at, delivered_at, read_at. |
| worker_control | Singleton key notification-worker, paused flag, generation, updated_at; worker heartbeat stores instance_id and last_seen separately. |
| incidents | UUID PK, fingerprint, alert_starts_at, generation, status, opened_at, closed_at, resolved_at, alert payload summary, verification_deadline, incident_lease_token, incident_lease_until. UNIQUE(fingerprint, alert_starts_at) deduplicates each alert episode; one processing owner per incident lease. |
| incident_events | UUID PK, incident_id FK, event_type, actor, timestamp, correlation_id, redacted structured evidence. Append-only via application permissions. |
| recovery_actions | UUID PK, incident_id FK, action_type, idempotency_key UNIQUE, state, requested_at, completed_at, result. |

Relationships: users have many assigned interventions and notifications; interventions have many history/outbox rows; each outbox event has at most one inbox notification; incidents have many audit events/actions. Preserve history; omit deletion from MVP. Application audit is append-only, not cryptographically tamper-proof. Assign a dedicated agent database role limited to incident/audit operations; business changes require the control API.

## API boundaries

| Boundary | Proposed routes / semantics |
| --- | --- |
| Business JSON /api/v1 | GET/POST /interventions; GET/PATCH /interventions/{id}; POST /interventions/{id}/assignment; POST /interventions/{id}/transitions; GET /interventions/{id}/history; GET /technicians. PATCH/commands require expected row_version. |
| Inbox and reporting | Under /api/v1: GET /notifications; POST /notifications/{id}/read; GET /dashboard; GET /incidents and /incidents/{id}. Enforce persona scope. |
| HTML | /interventions, /interventions/{id}, /dashboard, /notifications, /incidents; form POST routes share business services with JSON. |
| Health/telemetry | GET /health/live, /health/ready; internal GET /metrics. Readiness tests DB, not worker delivery. |
| Agent ingress | Internal POST /internal/alerts accepts authenticated Alertmanager payload, validates schema and size, deduplicates firing alerts; resolved alerts are recorded but do not prove recovery. |
| Control | Internal GET /internal/worker/status and POST /internal/worker/resume with incident_id, expected generation and idempotency key. Only the notification worker can be targeted. |
| Fault simulation | Operator POST /demo/worker/pause; only when DEMO_MODE enabled, CSRF/session protected and rate limited. Auto-expire pause after 10 minutes; audit every request. No public arbitrary stop/restart endpoint. |

Use 401 for missing identity, 403 for permission failure, 404 for absent resources, 409 for illegal/stale transitions and 422 for validation. Successful creates return 201. No database credentials, unrestricted query execution or user-supplied telemetry URLs reach the model. Bound read tools to fixed queries, service names, time ranges and result sizes. Public proxy routes only UI/business APIs and minimal health responses; internal services stay on private Compose networks. Separate webhook and recovery credentials; never expose the agent credential to browser sessions.

### Minimum JSON contract for T03

POST intervention accepts title, description (default empty), site, priority (default medium), technician_id (optional); status and timestamps are server-owned. PATCH accepts editable fields plus required expected_version. Assignment accepts technician_id and expected_version; transition accepts target_status, expected_version and resolution when completing. Responses include id, status, priority, technician_id, assignment_version, row_version and UTC timestamps; detail adds text fields and resolution. No-op assignment returns 200 with the unchanged version. Successful transition/edit returns 200; mark-read returns 204. Error envelope is `{ "error": { "code": "stale_version", "message": "...", "fields": {} } }`; adapt framework validation errors to this shape. T03 must publish executable OpenAPI schemas/examples before claiming contract verification.

Lists accept page (>=1), page_size (1–100), and the specified filters; return items/page/page_size/total. Use created_at DESC, id DESC ordering. Inbox uses the same pagination and includes historical-assignment flag and read_at. Apply recipient scope before pagination. HTML GET and JSON GET use distinct paths; form mutations use POST /interventions/{id}/edit, /assignment and /transitions. Session-authenticated JSON mutations also require CSRF tokens. Login/logout routes and operator-secret validation are shared session infrastructure, never telemetry tools.

The web service owns business/control routes; the on-call-agent owns /internal/alerts and its durable incident processing loop. Fixed read-only web telemetry routes provide worker state, a maximum 100 undelivered event IDs and event delivery evidence to the agent. Prometheus/Loki/Jaeger tools use configured private endpoints, maximum 15-minute windows and capped responses. Agent DB credentials permit incident/action/audit writes only; they cannot read business tables directly. The web recovery service owns mutation of worker_control and action-result recording through narrowly scoped database privileges.

## Notification outbox lifecycle

1. Lock/check the intervention version and validate the transition. In one transaction update technician/status/version, append history and insert pending assignment event. A duplicate assignment to the same current technician does nothing. Roll back all changes on failure.
2. Every 2 seconds the worker, unless paused, claims up to 20 eligible events with SELECT FOR UPDATE SKIP LOCKED. Commit processing status, increment attempts and set a 30-second lease with a random fencing token. Never hold a database transaction while waiting on external services.
3. In a short transaction, lock and validate the claim token, insert the inbox row with ON CONFLICT(outbox_id) DO NOTHING, and set delivered/delivered_at atomically. Only mark delivered if the inbox row exists for that event. Delivery is database materialization, not browser receipt.
4. A crash before commit leaves no partial delivery. Expired leases return to eligibility; a stale worker cannot complete an event reclaimed under a different token. Unique outbox/inbox constraints prevent duplicate visible notifications under retries or concurrent workers.
5. On processing errors, record a redacted error and retry after 2, 4, 8 and 16 seconds, capped at 30 seconds. After five failed attempts mark failed. Failed rows remain visible and counted as undelivered impact; autonomous replay of failed events is excluded. Escalate for human repair.

Outbox status: pending → processing → delivered; processing → pending on retry or lease expiry; processing → failed at retry limit. Oldest undelivered age includes pending, processing and failed rows so poison events do not vanish from alerts. A paused worker continues heartbeat/control polling; a genuinely dead process has a stale heartbeat and requires human/container supervision. The MVP agent only recovers the intentionally blocked variant permitted by the scenario, not a killed container.

Each claim consumes one of five attempts, including claims abandoned by a crashed process. Lease expiry after the fifth attempt marks failed rather than reclaiming forever. Pause acknowledges only after any current short delivery transaction finishes and prevents further claims; the demo waits for that acknowledgement before assignment. Fixed polling and database queries enforce the bounded worker policy. Claim/delivery tests must cover crashes before and after inbox transaction commit.

## Observability and incident flow

Planned metrics: fieldops_notifications_undelivered (gauge), fieldops_notification_oldest_undelivered_age_seconds (gauge), delivery latency histogram, delivered/failure counters, worker heartbeat timestamp, worker paused flag and HTTP error/latency metrics. Read queue age from database time and return zero when empty. Do not label metrics with trace IDs, intervention IDs, user IDs or other unbounded values. Logs contain event ID, intervention ID, trace ID and incident ID as structured fields; omit descriptions/sites and secrets. Cross-process propagation uses the persisted parent context below; a link-only new trace does not meet the same-trace acceptance criterion.

### Exact HTTP → outbox → worker → inbox trace contract

This is a proposed instrumentation design. OpenTelemetry Python supports explicit context injection/extraction for propagation; implementation should use its W3C trace-context propagator rather than reconstructing trace IDs manually. See [official Python propagation documentation](https://opentelemetry.io/docs/languages/python/propagation/).

1. FastAPI instrumentation extracts valid inbound W3C trace context and opens an HTTP server span. Without valid context it starts a new trace. Within that request, open `intervention.assign`, then a PRODUCER span `notification.enqueue`. PostgreSQL assignment/history/outbox INSERT spans are children of the enqueue span while that transaction executes.
2. While `notification.enqueue` is current, call `TraceContextTextMapPropagator().inject(carrier)`. Persist carrier `traceparent` and optional `tracestate` in that same outbox row and transaction. Do not persist baggage, user headers or arbitrary carrier keys. Persist the span context, not only a trace ID; never assume process memory survives the handoff.
3. For each claimed event, create a fresh carrier from that row and call `TraceContextTextMapPropagator().extract(carrier=carrier, context=Context())` using `Context` from `opentelemetry.context`. Start `notification.deliver` as a CONSUMER span with `context=extracted_context`, even though the originating HTTP request has ended. It therefore has the enqueue span as remote parent and the **same trace ID**. Do not parent delivery to the worker polling span. End/detach the event context in a finally block before processing another event, preventing cross-event context leakage.
4. Under the delivery span, open `notification.inbox.persist` and instrument PostgreSQL inbox INSERT/outbox delivered UPDATE spans. End spans after the short transaction commits or rolls back; report outcome/attempt as bounded attributes, with event ID as a span/log field. Retries extract the original row context and create distinct delivery spans under the same enqueue parent. Malformed/missing context starts a new root and emits a redacted propagation-warning field; it must not prevent delivery.
5. Structured JSON logs use `timestamp`, `level`, `service`, `environment`, `event`, `trace_id` (32 lowercase hex digits), `span_id` (16 hex digits), `outbox_id`, `notification_id` when available, and `attempt`. Pull trace/span IDs from the active OTel context; logs outside a span use null, never a made-up trace. Web enqueue and worker delivered logs share trace_id and outbox_id. A later inbox-view HTTP request is a separate trace; join it to the delivery record by outbox/notification ID rather than falsely continuing the old request.

For the demonstration/test environment use AlwaysOn sampling so the chosen journey cannot be lost to sampling. Resource attributes distinguish `fieldops-web` and `fieldops-worker` and development/production. Enforce valid bounded tracestate and never use it for authorization. Invalid context tests must prove delivery remains unaffected. Export asynchronously; no collector availability is needed for assignment commit.

**Correlation acceptance test (T09 / N05):** start a fresh assignment request without inbound context, persist its real outbox event, and let a separate worker process deliver it. Obtain the enqueue trace/span IDs from the outbox carrier. Poll the test collector/Jaeger for at most 30 seconds; assert HTTP, assign, enqueue, outbox INSERT, delivery, inbox persist and inbox INSERT spans have one trace ID, with delivery parent_span_id equal to the persisted enqueue span ID. Assert JSON logs from both processes carry that trace ID/outbox ID and the expected inbox row exists exactly once. Repeat with two concurrent assignments and a retry to prove no context leakage and stable event parentage. Save trace JSON and redacted log excerpts, not just a screenshot. This test is proposed and NOT RUN.

Metrics use only bounded labels such as service, environment, route template and status class. Required correlation uses a Grafana metric panel → bounded time-window Loki query → derived `trace_id` field → Jaeger link; query IDs as JSON fields, not Loki stream labels. Optional sampled histogram exemplars may attach trace/span context to a single observation when the chosen client/OpenMetrics exporter supports them; they are not time-series labels. If exemplars are unavailable, the log-derived dashboard link still meets the planned evidence requirement. T09 validates that no trace_id/span_id/event ID is a metric or stream label.

Prometheus alert expression: `(fieldops_notification_oldest_undelivered_age_seconds > 60) and (fieldops_notifications_undelivered > 0)`, `for: 30s`; 5-second scrape/evaluation and Alertmanager group_wait 5 seconds. This is a proposed expression to validate with promtool. Separate scrape failure/DB unavailable alerts prevent missing gauges being interpreted as healthy. The queue alert describes recipient impact; heartbeat is diagnostic evidence. Document the 110-second detection budget including polling/scheduling margin.

```mermaid
sequenceDiagram
  participant D as Dispatcher
  participant W as Web / PostgreSQL
  participant N as Worker
  participant M as Prometheus / Alertmanager
  participant A as On-Call Agent
  D->>W: Assign; persist history + outbox
  Note over N: Demo pause blocks delivery
  M->>W: Scrape undelivered count and age
  M->>A: Authenticated delayed-delivery alert
  A->>W: Fixed telemetry reads + worker status
  A->>A: Model proposes diagnosis/action
  A->>W: Policy-validated resume(incident, generation, key)
  N->>W: Claim events and commit inbox delivery
  A->>W: Verify event IDs, queue and heartbeat
  A->>W: Append evidence and incident outcome
```

The agent uses a constrained model tool loop (maximum three model calls, 30-second call timeout) to summarize fixed telemetry and propose `resume_notification_worker` or `escalate`. A deterministic policy layer permits resume only for a firing delivery incident, reachable DB, current paused flag and matching pause generation. The model cannot override that policy. Logs/alert annotations are untrusted text, never executable instructions. If evidence is missing, the provider fails or the action is disallowed, append an escalation and take no recovery action.

Resume sets paused=false via compare-and-set, never toggles or restarts a healthy worker. A durable idempotency key is derived from incident ID + pause generation + action type. Write action intent before execution; a retry after uncertain response retrieves/reconciles the prior result. Concurrent/replayed requests return the recorded result; changed generations yield 409 and new diagnosis. Bound to one effective action per incident/generation. No Docker socket, privileged container or shell tool is mounted in the agent.

Persist alert, telemetry snapshot, model/provider identifier, redacted model explanation, policy decision, tool arguments/results, verification samples and terminal outcome. Record provider timeout and telemetry failures too. Capture undelivered event IDs at diagnosis (bounded to 100 for the demo). Verify those IDs have delivered_at and inbox rows, queue count/age return to zero and worker heartbeat is fresh across two samples 5 seconds apart within 120 seconds. New continuing workload or >100 affected rows causes escalation rather than false closure. Alertmanager resolution alone cannot close an incident. Failed verification marks escalated; successful verification plus a successful authorized action marks resolved. Duplicate firing webhooks attach to the same alert episode; a later fresh firing creates a new incident generation.

### Durable incident processing and closure rules

Webhook acceptance returns 202 only after an incident receipt commits. Database failure returns 503 so Alertmanager retries. Use canonical alert labels + startsAt for a unique alert episode; replay after closure cannot create another incident for that episode. A genuinely later startsAt creates a fresh episode. Persist Alertmanager retries with bounded receiver payloads (64 KiB); invalid authentication returns 401, invalid schema 422. The agent leases incident work for 30 seconds, renews while processing and resumes persisted nonterminal states after restart. Never start another effective action merely because the agent restarted.

Incident states: received → diagnosing → action_requested → verifying → resolved, with escalated or externally_recovered terminal alternatives. Resume must atomically compare generation, persist paused=false and record action success in one web-service database transaction; rollback all if the action result/audit cannot persist. Agent action intent is written beforehand; retry reconciliation queries the same durable key. A successful model output cannot directly set resolved. Closure requires that successful action record, matching pause generation, affected event delivery and fresh heartbeat (<15 seconds). If no action succeeded, record externally_recovered if evidence proves drain, otherwise escalated. Auto-expiry of a pause is audited as external recovery. Verification's 120-second deadline starts after the successful action commit; diagnosis has a separate overall 100-second deadline and at most three model calls. HTTP control calls time out after 5 seconds with at most three attempts sharing one key, then reconcile/escalate.

Episode uniqueness includes escalated incidents; repeated alerts for the same startsAt attach without rerunning recovery, even after closure. Record closed_at separately from resolved_at for non-resolved terminal outcomes. If DB/audit storage fails, stop new recovery actions, emit a redacted structured error and resume/reconcile from durable state when available; never claim an unaudited success.

Telemetry exports use allowlisted fields: never capture request bodies, cookies, Authorization headers, operator secrets, SQL parameters or free-text history changes. Agent/provider inputs contain operational aggregates and pseudonymous event IDs only, not job descriptions/sites or raw unfiltered logs. Use asynchronous bounded export queues. Demo retention defaults: metrics/logs/traces 24 hours, persistent incident audit until explicit owner-approved reset; document disk limits and verify redaction with sentinel-secret fixtures.

## Proposed single-command local workflows

None of these commands is executable evidence yet. They specify the implementation contract for T02/T08/T09 and must be verified from a clean checkout before replacing the proposed label in README.

| Purpose | Proposed command | Required runner/profile behavior |
| --- | --- | --- |
| Core application + PostgreSQL | `docker compose up --build --wait` | Default services web/worker/db plus one-shot bootstrap: wait for healthy DB, migrate, idempotently seed synthetic data, then start healthy web and worker. Bootstrap fails closed on migration errors; no manual migration command needed for first-run local startup. |
| Complete required stack | `docker compose --profile observability --profile incident up --build --wait` | Core + all telemetry services + agent; preflight fails clearly if required operator/model credentials are missing. Agent health does not imply successful remediation. |
| Unit + integration tests | `docker compose --profile test run --build --rm tests` | Runner starts healthy test-db, applies migrations to a disposable test DB and runs both Pytest suites with one exit code. No browser or external model dependency. Includes real PostgreSQL concurrency/failure tests; never points at dev/prod DB. |
| Browser tests | `docker compose --profile browser run --build --rm browser-tests` | Runner depends on isolated browser-db/bootstrap/web/worker and a pinned Playwright image; seeds deterministic fixtures, waits for real readiness, executes browser suite and saves artifacts. |

Use explicit Compose dependencies/healthchecks and one-shot service completion, not shell sleep timing. Test runners reset only their disposable database/schema between runs and return nonzero on any failure. Document non-destructive teardown and artifact locations when implemented. Test services are opt-in profiles; bare startup must not run tests or the model. Compose run must start required profile dependencies automatically. Base command is locally HTTP, full hosted environments terminate HTTPS at the proxy. Local secret preflight/config defaults must be documented without committing secrets. The corresponding future Compose/image/runner files do not exist at T01.

## Deployment, delivery and rollback

Propose a Linux Compose deployment with **separate development and production environments and PostgreSQL databases**. Each has its own Compose project name, DB container/user/password, application/session/operator/webhook/recovery secrets, persistent volumes, networks, hostnames and environment-scoped telemetry. Development reset/deployment cannot change production data. They may share one host only if capacity/isolation checks pass; separate hosts are also valid and add cost. No shared DB or fallback production DSN is permitted. Hosting, capacity and cost remain unconfirmed. Use pinned service versions/image digests; no credentials are committed. Hosted migration and seed steps are explicit release jobs; never auto-seed production on every web startup.

Local base Compose starts web/worker/PostgreSQL plus the one-shot local bootstrap; an observability profile adds telemetry services and an incident profile adds the agent and requires a configured provider (or an explicitly labeled test stub). Full demonstration uses all profiles with a real configured provider. Persist Loki/Jaeger data for the 24-hour evidence window, subject to measured disk limits. Seed command is idempotent and creates deterministic synthetic personas/jobs; separate destructive demo reset requires explicit confirmation and is never agent-callable. Before fault injection verify empty queue, normal delivery, receiver connectivity and no concurrent job generation; wait for pause acknowledgement, assign, then record actual timestamps. Repeat from a clean seeded state to establish reproducibility.

### CI/CD contract for the supplied 3-point criterion

1. **Pull requests:** GitHub Actions automatically runs lint/static checks, unit + real PostgreSQL integration tests, Playwright critical journey, image build, migration smoke and promtool rule tests. Required checks gate merge to main. Untrusted PR jobs receive no deployment/model credentials; model responses are mocked.
2. **Merge to main:** a push-to-main workflow automatically runs the required checks against the actual merged commit, builds/publishes one commit-tagged application image and records its registry digest. After successful validation it **automatically deploys to the GitHub `development` environment without manual dispatch or approval**. Use a protected main branch. Provisioning and authorizing this automation is future owner-approved work; planning it does not authorize current remote actions.
3. **Development CD:** use development-only credentials/DB, migrate with backward-compatible changes, deploy web/worker/agent by `image@sha256:...` and perform smoke tests. Record commit SHA, digest, migration version, workflow run and smoke result as the eligible development release. Failures block production eligibility. Serialize releases by environment and skip stale queued commits before deployment so an older run cannot overwrite a newer deployment.
4. **Production promotion:** a separate GitHub Actions `workflow_dispatch` accepts only an image digest from a successful development release record, not an arbitrary tag/branch. A human initiates it. The production job uses the protected GitHub `production` environment with a **required reviewer approval gate** before accessing production secrets or making changes. Restrict trusted workflow refs and the authorized reviewer; owner selects the reviewer/self-approval policy before T12. Reuse the exact development-tested digest without rebuilding. GitHub environments can require approval before jobs/secrets become available; see [official environment protection documentation](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments).
5. **Post-deployment smoke, both environments:** verify HTTPS/readiness, create a uniquely marked synthetic job through a dedicated smoke persona, assign it, assert its exact outbox ID becomes one inbox notification within the normal-delivery budget, and verify history and environment identity. Polling is bounded; no direct DB insertion can substitute for the journey. Production smoke never pauses delivery. Keep marked fixtures auditable; do not grant the runtime agent deployment privileges.
6. **Rollback:** record previous image digest and migration version before each deployment; back up that environment's DB before hosted migrations. If smoke fails, redeploy the previous compatible digest for all app processes, rerun smoke, mark the new release failed and retain logs. If no previous digest exists, mark bootstrap failed and require operator intervention. Never silently downgrade schema or restore data. A manual rollback workflow uses the same production approval boundary. Migration compatibility/backup restoration restrictions below still apply.

Required reviewer evidence is an automatic PR run, merge-to-main development deploy run with no manual gate, proof of distinct DB/volume/secret targets, manual production dispatch + approval record, post-deploy smoke results and the reused digest/rollback rehearsal. Writing workflow YAML alone is insufficient.

### Resource planning assumptions

No resource use is measured. Initial sizing hypotheses for investigation: core development 2 vCPU/4 GiB RAM; a full environment 4 vCPU/8–12 GiB with 40–60 GiB disk and bounded 24-hour telemetry retention. Two concurrent full environments on one host may need roughly 8 vCPU/16–24 GiB and 80–120 GiB disk; these are planning envelopes, not purchasing recommendations or verified minima. Test runners/CI require additional ephemeral capacity. T09 measures per-service idle/active CPU/RSS/disk growth and an incident workload; T13 validates both environments under concurrent smoke. If shared-host interference is material, isolate hosts or revise capacity before release. Do not drop required telemetry to preserve the old estimate. Provider price, region, DNS/TLS, backups and CI availability remain open; no purchase/provisioning is authorized.

Before deployment record the previous digest and backup location. On smoke failure redeploy previous compatible digest; do not automatically downgrade schemas. Use expand-only migrations for MVP. Restore a tested backup only with explicit owner approval because newer writes could be lost. Preserve incident history across redeployments. Document public URL, demo access, SSH/deployment procedure and measured rollback/restart evidence during implementation.

## Decision register

| ID | Decision / status | Consequence |
| --- | --- | --- |
| A01 | Proposed: monolith + PostgreSQL poller, no broker | Simpler transactional correctness; bounded demo throughput. |
| A02 | Proposed: persistent inbox is delivery | Clearly observable effect without third-party messaging. |
| A03 | Approved scenario: paused delivery loop; proposed DB-backed control implementation | No privileged host actuator; killed worker recovery remains manual. |
| A04 | Proposed: real model diagnosis + deterministic policy guard | Requires approved provider/key/budget; mocks only cover CI. |
| A05 | Open: authoritative cohort rubric and existing/no-purchase hosting/model access; manager/technician demo separation approved | Resolve external access before the relevant integration/deployment phase; no purchases authorized. |
| A06 | Proposed: retain all requested telemetry services | Biggest time/resource risk; use one configuration and one dashboard, avoid custom exporters. |
