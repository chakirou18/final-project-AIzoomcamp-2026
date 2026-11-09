# Local GitHub Issue drafts

Reviewed publication bodies. Owner authorized T01–T15 Issue creation on 2026-11-09 after documentation Git validation. Txx identifiers are local task IDs, not GitHub Issue numbers. [Backlog](backlog.md) is the status/timebox and eventual public-URL index. [Specification](specification.md) and [architecture](architecture.md) supply detailed contracts. Criteria are not automatically completed by publication; runtime tests are future requirements, not executed results. Scenario/identity decisions are recorded in the readiness summary. No implementation, deployment, paid provisioning or API purchase is authorized.

Topological execution order: **T01 → T02 → T03 → T04 → T06 → T05 → T07 → T08 → T09 → T10 → T11 → T12 → T13 → T14 → T15**. Every dependency points backward in this order. T01 is retained as a planning/review Issue draft; it is not marked accepted.

## T01 — Specify FieldOps MVP, architecture and evidence plan

**Description:** Review and approve documentation-only baseline, resolve identity/budget gates and record rubric-version uncertainty.

**Dependencies:** None. **Role:** Product/specification; integration/review lead.

**Acceptance criteria:** Seven original requested documents plus audit/drafts/final summary are consistent and linked; owner accepts T02 boundaries; past planning/audit effort is honestly marked unmeasured and future actual-time tracking is defined; P01–P05 have explicit owners/gates.

**Tests required:** Read all Markdown including untracked files; check local links, task DAG, score/timebox arithmetic and whitespace.

**Reviewer evidence:** Documentation diff, T01 audit and recorded owner decisions; no runtime claims.

**Final T01 additions:** Approve revised remaining estimate (62 planned + 16 contingency hours; range 58–117), proposed single-command contracts and automatic-dev/manual-prod pipeline. Historical T01 effort is unmeasured. Readiness summary supersedes the old budget, without marking owner approval complete.

## T02 — Add reproducible FastAPI and PostgreSQL skeleton

**Description:** Establish base Compose, application image, environment template, health endpoints and migration/seed entry points without prematurely implementing business schema.

**Dependencies:** T01 approved. **Role:** DevOps/SRE; backend.

**Acceptance criteria:** Proposed base command `docker compose up --build --wait` works on clean checkout with DB-health/bootstrap dependencies (schema/seed completed in T03); live returns 200; ready returns 200 with DB and 503 without DB; volume survives restart; no real secrets in files. No separate manual setup command is hidden in first-run instructions.

**Tests required:** Image build, Compose config validation, ready/live outage and restart smoke.

**Reviewer evidence:** Exact setup/check commands and observed output, Dockerfile/Compose/environment example.

## T03 — Define schema, API contracts and persona permissions

**Description:** Establish migrations, synthetic personas, session boundaries, OpenAPI schemas and role rules for F01–F05/F10; implementation of business behavior follows T04.

**Dependencies:** T02. **Role:** Backend; product/specification; QA.

**Acceptance criteria:** Schema constraints match architecture; seed is idempotent; operator secret is required; cookie/CSRF boundary defined; executable request/error/response schemas include versioning. Empty database migrates successfully through the base command bootstrap. Production seeding is explicit and separate from local startup.

**Tests required:** Migration/seed rerun, invalid enum/FK/uniqueness constraints, session/logout, direct JSON/HTML role and CSRF denial checks against available routes; unimplemented business checks tracked to T04.

**Reviewer evidence:** Migration files, OpenAPI examples, permission matrix and actual test results.

## T04 — Implement intervention lifecycle and transactional assignment

**Description:** Implement F01–F04 using shared services for JSON/HTML, append-only history and outbox insertion.

**Dependencies:** T03. **Role:** Backend; QA.

**Acceptance criteria:** Valid lifecycle and all priorities persist; optional assignee creation is atomic; forbidden edits/transitions fail; same-assignee command is a checked no-op; stale updates return 409; field limits/filter/pagination contract implemented.

**Tests required:** Full transition matrix, completion resolution, cancel timestamps, create-with-assignee, transaction rollback, concurrent stale updates, role/CSRF checks and list boundaries.

**Reviewer evidence:** API examples, unit/PostgreSQL results and database history/outbox assertions.

## T06 — Implement leased outbox worker and inbox persistence

**Description:** Deliver notifications with bounded claims/retries and unique inbox materialization, satisfying F05/N01/N02.

**Dependencies:** T04. **Role:** Backend; DevOps/SRE; QA.

**Acceptance criteria:** Inbox/outbox delivery commits atomically; lease tokens fence stale workers; all claims consume the five-attempt limit; failed rows remain undelivered; 20 assignments each deliver within 10 seconds under stated local conditions. Outbox schema carries optional W3C traceparent/tracestate for T09 instrumentation; delivery does not depend on valid context.

**Tests required:** Concurrent workers, lease expiry at retry limit, crash before/after delivery commit, stale-token completion, duplicate insert, DB outage/recovery and timing fixture.

**Reviewer evidence:** PostgreSQL failure-injection results, timing report and persisted event/inbox mapping.

## T05 — Deliver intervention UI and technician inbox

**Description:** Connect server-rendered forms to real services and persistent inbox; preserve role scope after reassignment.

**Dependencies:** T04, T06. **Role:** Frontend; backend; QA.

**Acceptance criteria:** Dispatcher CRUD/assignment and technician inbox/start/complete work; errors are visible; historical notifications cannot expose unassigned job detail; desktop/375px and full-page fallback remain usable.

**Tests required:** Browser journey, validation failures, filters, direct unauthorized requests, keyboard form use and HTMX-disabled fallback.

**Reviewer evidence:** Browser output, screenshots and usability checklist linked to F01–F05/F10/N07.

## T07 — Add dashboard, worker controls and health indicators

**Description:** Show F06/F09 data and implement generation-scoped pause/resume infrastructure without giving the model arbitrary control.

**Dependencies:** T05, T06. **Role:** Backend; frontend; DevOps/SRE.

**Acceptance criteria:** Dashboard includes failed/processing rows in undelivered count/age; empty age zero; pause acknowledgement waits for active transaction; resume CAS/action result is atomic; credentials isolate operator/webhook/agent permissions.

**Tests required:** Fixture counts, public/internal access checks, wrong generation/key replay, pause auto-expiry audit, action result rollback and readiness/heartbeat separation.

**Reviewer evidence:** Dashboard, API negative tests and transaction/idempotency results.

## T08 — Add critical unit, integration and browser coverage

**Description:** Integrate existing tests and fill coverage gaps, including N03 benchmark and N07 accessibility/fallback checks.

**Dependencies:** T05, T06, T07. **Role:** QA/testing; integration/review lead.

**Acceptance criteria:** Core browser lifecycle, cancellation, permissions, optimistic concurrency, retries and persistence all pass; 1,000-job/5-client/50-request benchmark reports p95 against <1 second target. Proposed combined unit/integration command `docker compose --profile test run --build --rm tests` and browser command `docker compose --profile browser run --build --rm browser-tests` work from clean checkout with disposable separate DBs, readiness dependencies, artifacts and meaningful failure exit codes.

**Tests required:** Unit + real PostgreSQL integration + Playwright; width, keyboard, no-HTMX and performance checks.

**Reviewer evidence:** Commands/results, benchmark host/data, browser artifact and acceptance traceability.

## T09 — Wire metrics, logs, traces and Grafana

**Description:** Add minimal observability profile, database-derived impact gauges and cross-process trace/log correlation.

**Dependencies:** T07. **Role:** DevOps/SRE; backend; QA.

**Acceptance criteria:** Observability profile starts all telemetry services; the full-stack command contract is documented with real-agent verification explicitly deferred to T11. W3C context persists with the event and worker explicitly extracts it as remote parent: HTTP→outbox→worker→inbox spans share one trace ID. Web/worker structured logs correlate; metrics and Loki stream labels never include trace/span/event IDs. Dashboard log-derived trace links work; exemplars are optional. Impact metrics survive worker failure, retention/resource limits are measured, and telemetry failure never blocks assignment.

**Tests required:** Observability profile startup; proposed architecture correlation test checks trace IDs/parent_span_id using trace JSON, matching log fields, two concurrent assignments, retry and malformed-context fallback. Also test missing worker/DB, sentinel-secret redaction, bounded metric labels and exporter failure. Before T11, full-stack agent startup is explicitly pending; do not claim the complete profile passed using a mock.

**Reviewer evidence:** Correlated trace JSON and redacted web/worker logs for one real journey, dashboard links, label/redaction assertions and per-service CPU/RSS/disk report. Record full-stack startup verification at T11.

## T10 — Alert on delayed notifications and simulate failure

**Description:** Test user-impact alert rules and controlled delivery pause before connecting real agent processing.

**Dependencies:** T09. **Role:** DevOps/SRE; QA.

**Acceptance criteria:** After pause acknowledgement, real assignment persists an event while its notification remains absent from the recipient inbox for >60 seconds; queue delay alert reaches authenticated labeled test receiver within 110 seconds. Empty queue stays quiet; scrape/DB missing-data rules fire; fault control denied outside DEMO_MODE/operator access. Killed-container remediation is excluded.

**Tests required:** promtool threshold/for/empty/missing tests and real pause→assign→alert timing; bad webhook auth.

**Reviewer evidence:** Rule files/results, actual timestamps and test receiver payload; explicitly no recovery claim yet.

## T11 — Implement bounded model-assisted On-Call recovery

**Description:** Replace test receiver with durable authenticated agent intake, constrained diagnosis, allowlisted action and verified incident closure.

**Dependencies:** T10; owner-approved provider/spend limit and paused-worker scenario. **Role:** DevOps/SRE; backend; QA; integration/review lead.

**Acceptance criteria:** Actual Alertmanager alert is received and persisted; real model diagnoses paused delivery from telemetry; authorized resume action succeeds and agent verifies the specific affected outbox IDs now have delivered_at/inbox rows plus healthy queue/heartbeat. All incident/action/verification evidence persists. Action success is required for resolved status: explanation-only output, natural drain or auto-expiry cannot qualify. Webhook episodes/action keys survive replay/restart; blocked diagnosis escalates. Full-stack command now starts the real agent and monitoring; MVP handles paused delivery loop, not a killed container.

**Tests required:** Replay before/after closure, simultaneous alerts, agent restart, wrong generation, ambiguous action timeout reconciliation, failed audit commit, provider timeout, missing telemetry, malicious log instruction, dead container, auto-expiry, failed verification and >100 events. Mock provider in CI; real provider only for bounded approved demo.

**Reviewer evidence:** Redacted real tool/action transcript, durable incident events, positive delivery assertions and negative/idempotency test results.

## T12 — Build gated GitHub Actions test and release pipeline

**Description:** Automate PR validation and development deployment after validated merge to main; promote the development-tested digest to production only through manual GitHub Actions dispatch and approval.

**Dependencies:** T08, T10, T11. **Role:** DevOps/SRE; QA; integration/review lead.

**External prerequisites:** Owner-approved development hosting/access/database, authorized remote operations and automatic development deployment policy. Production GitHub environment/reviewer policy is configured before testing its approval gate; T13 supplies the production deployment rehearsal. These are prerequisites, not a T13 dependency or current provisioning authorization.

**Acceptance criteria:** PR checks run automatically and block merge on failure. Validated push to main builds/publishes an immutable digest and automatically deploys development with no manual gate. Development has separate DB/user/password/volumes/secrets/network from production. Manual workflow_dispatch selects only a successful development-tested digest; required production environment approval gates access to production secrets. Promote without rebuilding, run smoke in both environments, serialize deployments and retain previous compatible digest for rollback. Remote execution requires owner authorization.

**Tests required:** PR passing/failing gates, merge-to-main automatic development deployment with API→inbox smoke, rendered development/production DSN/volume configuration separation, unknown/failed-development digest promotion rejection, manual approval enforcement and stale-run prevention. Mock model in CI; no production pause. Actual production DB isolation and promotion/rollback smoke are exercised in T13, not prerequisites for T12's development deployment.

**Reviewer evidence:** Public PR/check run, automatic main→development run without human dispatch, distinct target DB/volume proof without secrets, immutable digest/release record, blocked production gate and failed-check denial. T13 adds real production dispatch/approval/smoke/rollback run URLs.

## T13 — Deploy public demo and rehearse rollback

**Description:** Exercise production promotion and a public HTTPS demo with private operations endpoints, persistent data and isolation from the automatically deployed development environment. Each environment uses its own Compose project/database; host sharing requires measured capacity.

**Dependencies:** T11, T12; approved hosting budget/access and rubric scope. **Role:** DevOps/SRE; integration/review lead.

**Acceptance criteria:** Public synthetic-data journey works; internal services remain private; development changes/resets cannot mutate production data. Manual dispatch plus production approval promotes the exact successful development digest. Both environments pass bounded assignment/inbox smoke; restart preserves inbox/history; backups are verified; previous compatible digest rollback passes smoke and concurrent environments stay within measured resources. No destructive restore without separate approval.

**Tests required:** External endpoint exposure scan, cookie/TLS checks, seed/startup, assignment/inbox and persistence smoke, prior-image rollback rehearsal.

**Reviewer evidence:** Both environment URLs, automatic development deployment run, manual production dispatch and approval record, matching digests, both smoke outputs, isolation/resource checks, backup and rollback report without secrets.

## T14 — Capture incident demonstration and complete evidence index

**Description:** Produce reproducible reviewer walkthrough with observed results for every requirement and supplied rubric criterion.

**Dependencies:** T13. **Role:** Product/specification; QA; DevOps/SRE.

**Acceptance criteria:** F01–F10/N01–N07 mapped to actual artifacts; full successful incident recorded; current rubric verification status retained; no planned checks presented as passed.

**Tests required:** Repeat seeded demo from baseline; verify artifact links and all measured timings; scan exported evidence for secrets.

**Reviewer evidence:** Short video with timestamps, rubric index, CI/deploy links and incident audit.

## T15 — Resolve integration defects and verify release gate

**Description:** Perform planned final regression fixes and independent review. This task has four most-likely hours; the separate 16-hour contingency reserve is not counted again here.

**Dependencies:** T14. **Role:** QA/testing; integration/review lead; relevant component owner.

**Acceptance criteria:** No unresolved critical defect; relevant tests rerun after fixes; all remaining limitations documented; owner review obtained before unauthorized publication/commit/push.

**Tests required:** Targeted regression checks and final required CI gate; evidence/link consistency.

**Reviewer evidence:** Final checklist with actual results, defect resolutions and explicit release recommendation.

## Issue field verification and public update rules

All 15 drafts contain Description, Dependencies, Role, Acceptance criteria, Tests required and Reviewer evidence fields. Dependency names refer to local tasks until real Issue URLs exist. Every dependency points backward in the stated topological order; hosting/provider/reviewer approvals are external gates, not hidden cyclic task dependencies. T09 does not require the future real agent to pass its observability work; T11 owns complete-stack verification. T12 prepares/exercises development CD; T13 exercises production, preventing a pipeline/deployment dependency cycle.

For the authorized tracker publication and subsequent separately authorized development, Codex follows the [public tracker protocol](agent-team.md): map Txx to real public Issue URLs, reference them in task/PR summaries, post progress/validation updates, maintain checklists, and link reviewer evidence before authorized closure. Issue creation does not authorize task implementation or closure.
