# T06 leased outbox worker and persistent inbox validation

> Publication authorization (2026-11-10): the owner authorized one T06 commit, feature-branch
> push, a PR against T04 and an Issue #5 progress comment. Historical local-only snapshots below
> describe earlier phases; no merge, Issue closure or future implementation is authorized.

> Latest independent audit: **PASS; 290 distinct passing tests** (96 unit, 191 PostgreSQL
> integration, 3 Docker lifecycle), zero failures/skips. The independent audit section at the
> end supersedes the original implementation-run totals and benchmark reporting.

Task: [T06 / Issue #5](https://github.com/chakirou18/final-project-AIzoomcamp-2026/issues/5),
requirements F05/N01/N02. Local implementation and testing only.
Branch: `feature/t06-notification-worker` from published T04
`f272f5c70992902bfaa1a53c2075fae525ac1bd0` (PR #18 remains unmerged).
The live Issue and dependency handoff were read before implementation. Initial working tree was clean.
Earlier commits are unchanged; no model, migration, manifest or lockfile changes were needed.

## Worker architecture and transaction boundaries

`python -m fieldops.worker` starts a separate process from the existing nonroot runtime image.
Compose starts credentials -> healthy PostgreSQL -> migration/seed bootstrap -> web and worker.
The worker uses the same DB host/name/user/password source as the API, with its own bounded
connection pool. No worker port, Docker socket, shell actuator or control endpoint is exposed.
It does not run migrations itself. Direct process startup retries unavailable DB/schema operations;
Compose normally prevents startup before bootstrap completes.

| Operation | PostgreSQL behavior |
| --- | --- |
| Claim | Short transaction, eligible pending or expired processing rows, oldest first, maximum 20; `FOR UPDATE SKIP LOCKED` |
| Lease | Fresh random UUID token, database-clock deadline 30 seconds after claim; every committed claim increments attempts |
| Materialize | Lock event, validate processing status/token/expiry, insert one inbox row with `ON CONFLICT(outbox_id) DO NOTHING` |
| Acknowledge | Recheck token/status and `lease_until > clock_timestamp()` in the final UPDATE; mark delivered, use inbox delivered_at, clear lease/error |
| Commit | Inbox insert and acknowledgement commit together; a failed acknowledgement rolls the inbox insert back |
| Retry failure | Separate short transaction, fenced by current token and SQL expiry check; pending with bounded backoff or terminal failed |

No transaction is held during the two-second polling wait or while processing a different event.
Delivery is local PostgreSQL materialization, not an external send. Its atomic commit is the delivery
boundary. Duplicate completion returns no change. A pre-existing matching inbox row can be reconciled
without duplication; recipient/intervention/assignment version must match the originating outbox row,
also enforced by the existing composite FK. Lease validation is linearized at the guarded UPDATE;
the event lock prevents another worker reclaiming before that transaction completes.

Five attempts is a hard lifetime cap, not five retries after an initial attempt. A committed claim
consumes an attempt even if the process crashes or stops before reaching that event in its batch.
Delivery failures retry after 2, 4, 8 and 16 seconds. A fifth failure becomes failed immediately.
Expired processing leases may be reclaimed with a new token while attempts <5; expiration already
imposes the 30-second lease delay. An expired fifth claim becomes failed instead of being reclaimed.
Failed rows are retained with delivered_at NULL and remain countable as undelivered in PostgreSQL.
There is no replay/reset endpoint or autonomous failed-row recovery in T06.

Database claim failures roll back uncommitted attempts. An uncertain/lost claim result recovers by
lease expiry; an uncertain delivery result is safe because inbox and delivered state share a commit.
Per-event failure recording may itself fail during an outage: the durable processing lease remains,
so it can expire/recover. Claim/pool failures trigger process reconnect waits of 2/4/8/16/30 seconds,
capped at 30. Graceful SIGTERM/SIGINT interrupts the wait and stops new delivery work; unfinished
claims recover through expiry and still count. Error rows/logs retain only fixed codes/type names,
never exception strings, SQL parameters or job text.

## Persistent JSON inbox

- GET `/api/v1/notifications`: authenticated active technician only; recipient scope before count
  and pagination. Page defaults 1/25, page_size 1..100; created_at DESC/id DESC. Huge page offsets
  return empty items without PostgreSQL integer overflow.
- POST `/api/v1/notifications/{id}/read`: technician recipient + session CSRF; 204 with no body.
  Repeating it preserves the original read_at. Wrong role/recipient returns 403; missing ID 404;
  invalid UUID 422; missing/invalid session 401. Existing shared error envelope is preserved.
- Reassignment retains the original recipient's inbox and marks it historical. The immutable
  summary contains only intervention ID and assignment version; it does not copy later job text
  or grant access to a former assignment. Job/history permissions remain T04 responsibilities.
- Delivered/read state survives new sessions/processes/containers. Existing inbox reads do not
  depend on a running worker. No HTML inbox UI, dashboard or worker controls were added.

Live OpenAPI includes both existing T03 notification contracts and their required cookie/CSRF
security. Shared schemas/statuses/descriptions are compared in the contract regression. The obsolete
T04 assertion that notifications are absent was replaced by verification of all implemented routes.

## Trace carrier readiness, without T09 instrumentation

Optional traceparent/tracestate columns remain on outbox rows. Create/assignment JSON adapters and
the shared assignment service sanitize optional carriers before persistence. The conservative T06
subset accepts lowercase version-00 traceparent, nonzero trace/span IDs and flags 00/01. Only the
opaque vendor entry `fieldops=<16..32 lowercase hex characters>` is accepted as tracestate; unknown
vendors, other versions/flags, arbitrary text and baggage are dropped. This is intentionally not a
complete W3C/vendor propagation implementation. It prevents copying free text, cookies, secrets
or job data into carriers. Accepted identifiers remain untrusted metadata, never authorization.

`Claim.context` exposes a validated optional carrier for future T09 extraction. Malformed existing
stored context is ignored and does not block delivery. Context is not logged, returned in the inbox
or used for delivery correctness. No spans, exporters, metrics, trace correlation or observability
stack is implemented or claimed; full W3C propagation belongs to T09.

## Exact commands and observed test results

PowerShell from the repository root, Docker Desktop Linux containers, Python 3.12.

```powershell
# Unit gate (no Docker/DB requirement):
.venv/Scripts/python.exe -m pytest -m 'not integration and not container' -q -p no:cacheprovider --basetemp=artifacts/t06-unit-final
# Isolated PostgreSQL profile; it does not start an application worker on the test DB:
$env:FIELDOPS_SUBNET='10.244.0.0/24'
docker compose --project-name fieldops-t06-validation --profile test run --build --rm tests
# Focused timing report:
docker compose --project-name fieldops-t06-validation --profile test run --rm tests .venv/bin/pytest tests/test_t06_postgresql.py::test_twenty_assignment_timing_with_one_worker -q -s
# Generated, isolated Docker projects, with retained named volumes:
$env:FIELDOPS_RUN_CONTAINER_TESTS='1'
.venv/Scripts/python.exe -m pytest tests/test_container_lifecycle.py -v -s --junitxml=artifacts/t06-container-release-check.xml
# Quality/baseline checks:
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m ruff format --check .
uv --cache-dir .cache/uv lock --check
git diff HEAD -- migrations fieldops/models.py pyproject.toml uv.lock
git diff --check
git status --short
```

| Gate | Passed | Failed | Skipped | Deselected | Observed time |
| --- | ---: | ---: | ---: | ---: | --- |
| Final unit | 96 | 0 | 0 | 180 | 1.18s |
| Final unit + real PostgreSQL | 273 | 0 | 0 | 3 container | 37.40s |
| Corrected Docker run before final safeguards | 3 | 0 | 0 | 0 | 81.47s |
| Final Docker rerun | 3 | 0 | 0 | 0 | 81.64s |
| Distinct across final full gates | **276** | **0** | **0** | **0 left unrun** | Unit-only repeat excluded |

The 273-test gate comprises **96 unit + 177 PostgreSQL integration tests**. T02/T03/T04 regressions
passed, including existing migration/constraints, session security, T04 history locking, atomic
assignment, stale updates and append-only history. Models/migrations remain unchanged.
The final total is **96 unit + 177 real PostgreSQL + 3 Docker lifecycle tests**. All 229 prior
T02/T03/T04 test cases remain covered; T06 adds 23 unit, 23 integration and one container case.
The one-command startup result is recorded at the end of this document.

### Fault, concurrency and persistence evidence

- Three concurrent claimers over 20 events return disjoint claim sets. Concurrent delivery and
  repeated completion leave exactly 20 unique inbox records, matching recipient/job/version.
  A separate PostgreSQL row-lock holder proves SKIP LOCKED skips occupied work.
- Expired/wrong/stale tokens cannot deliver or record failure. New claims receive different UUID
  tokens and consume the next attempt. Both repeated lease expiry and delivery failures stop at
  five, leave no inbox row and preserve a visibly undelivered failed event.
- PostgreSQL BEFORE INSERT and deferred COMMIT-rejection triggers prove inbox/ack rollback,
  including failure after outbox UPDATE. Retrying produces one consistent inbox/delivered pair.
  A separate deferred claim-COMMIT failure leaves attempts=0 and no processing lease.
- A SQL fault expires the lease between inbox insertion and final acknowledgement; the guarded
  UPDATE fails and the entire materialization rolls back. The claim can then complete safely once
  the transactional fault is removed. No assertion relies only on a mocked persistence layer.
- Real subprocess `os._exit` occurs immediately after inbox INSERT but before delivery commit,
  and separately immediately after delivery commit. Restart reclaims the former after expiry,
  and leaves the latter delivered. Both end with exactly one inbox row, without silent loss.
- PostgreSQL `pg_terminate_backend` kills the worker connection during acknowledgement. The actual
  worker loop reconnects, retries and delivers with attempt=2. A real poison INSERT trigger drives
  the actual run_once error path through five failures; its exception sentinel is absent from
  captured logs and durable last_error stores only `delivery_failed`.
- API tests verify scoped historical inboxes, idempotent mark-read, CSRF/role denials, read-state
  persistence, valid trace carrier persistence and nonblocking invalid HTTP/service/stored context.
- Docker tests verify same-image nonroot worker, real recipient HTTP delivery, duplicate-free
  worker restart/recreation, readable inbox during worker downtime, worker startup with PostgreSQL
  actually stopped, recovery of a pending assignment, and inbox persistence after DB recreation.

Lease-expiry and backoff tests advance isolated test row eligibility with SQL rather than waiting
30 seconds per expiry. Subprocess crash tests use actual process termination; transaction rejection
tests use actual PostgreSQL triggers. Test databases are unique per T06 integration case and retained;
no application database is reset and no existing volume is removed.

### Benchmark conditions and measurements

Host: Windows PowerShell/Python 3.12.10; Docker Desktop 29.9.3, 12 reported CPUs and 7,978,242,048
bytes (~7.43 GiB) available memory. Linux test/runtime Python 3.12.16 on
`Linux-6.18.33.2-microsoft-standard-WSL2-x86_64-with-glibc2.36`; pinned PostgreSQL 17 image.
One worker, two-second polling, batch maximum 20, empty synthetic queue, no injected delivery fault.
This is a shared local development machine, not a dedicated performance host or production SLO.

| Measurement | Result |
| --- | --- |
| Focused DB fixture, 20 real assignments | min 0.110790s, mean 0.138987s, max 0.168797s |
| Focused DB fixture, creation through observed 20 inbox rows | 0.309155s |
| Corrected real Compose/HTTP run, 20 assignments | max DB latency 1.659884s |
| Same run, first create request through all 20 visible in recipient HTTP inbox | 2.078000s |
| Final real Compose/HTTP run, all 20 assignments | max DB latency **1.584428s** |
| Final run, first create request through all 20 visible in recipient HTTP inbox | **1.984000s** |

The DB fixture starts one worker loop after creating a 20-event batch. The Docker benchmark uses
the separate continuously running worker process and creates jobs over real HTTP, exercising polling.
DB latency is notification.delivered_at minus outbox.created_at for every event, not a mean-only
pass criterion. The HTTP check is stricter than ten seconds per assignment: all 20 must be visible
within ten seconds of the first create request. Final rerun measurements follow below.

### Failures encountered and corrections

- Intermediate lint/format errors were corrected before final gates. No dependency additions needed.
- The first Docker run passed the two prior lifecycle cases and the 20-notification timing check
  (max DB 1.593122s; HTTP observation 1.969000s), but failed the new outage assertion: **2 passed,
  1 failed**, 80.43s. `docker compose start worker` traversed dependencies and restarted PostgreSQL,
  so readiness correctly returned 200. The test now starts exactly the generated worker container
  with `docker start <isolated-worker-id>` and asserts the DB container remains stopped. It then
  requires readiness 503/liveness 200 and proves delivery recovery. No assertion was weakened.
- Shared services now sanitize optional trace carriers too, so invalid context from a future
  non-HTTP adapter cannot overflow columns or block assignment. Failure recording now uses a
  SQL token/status/expiry guard, matching the final delivery-fencing boundary.

## Acceptance and remaining risks

| Issue #5 acceptance criterion | Result | Evidence |
| --- | --- | --- |
| Inbox/outbox delivery commits atomically | PASS | Real PostgreSQL insert/COMMIT faults and process crashes |
| Lease tokens fence stale workers | PASS | Wrong/expired/old token denials; guarded update and expiry-during-insert rollback |
| Every claim consumes the five-attempt limit | PASS | Five committed claims under expiry and failure; rolled-back claim is not a claim |
| Failed rows remain undelivered | PASS | Persistent failed row, NULL delivered_at, no inbox; no further claims |
| 20 assignments each deliver within 10 seconds under stated local conditions | PASS | Per-event DB maxima and actual recipient HTTP timing above |
| Optional trace context persists and invalid context does not block delivery | PASS | Valid HTTP carrier round-trip, invalid HTTP/service/stored context cases |

- Delivery is exactly one persistent inbox row per outbox event, not exactly-once external messaging.
  No external channel exists. Delivery/read timestamps and acknowledgement are database state.
- Demo persona selection is not production identity verification. Local web/worker use database-owner
  credentials and the same read-only credential volume; the worker environment omits session/operator
  keys, but the shared volume still contains local signing material. Production least privilege and
  secret isolation are not claimed. No production credentials or customer data were introduced.
- No worker heartbeat/control tables, pause/resume API, UI, telemetry exporters, alerts or agent.
  Compose worker state means process running, not delivery health; operational health/controls are T07+.
- No lease renewal: batches must finish within 30 seconds or unused claims expire and consume attempts.
  This is safe but can exhaust work under sustained DB outages/slow load. Failed events require future
  authorized human handling; T06 deliberately adds no reset/replay control.
- No stable pagination snapshot across writes. Generic historical summaries deliberately contain no
  title/site snapshot; richer UI content requires a separately reviewed T05 contract/schema decision.
- Trace support is a conservative version-00/opaque fieldops subset. Full vendor propagation, spans,
  parent correlation and redaction export tests are **NOT TESTED**, deferred to T09.
- Large backlogs, production benchmarks, randomized clock jumps, arbitrary external failure timing,
  parallel pytest/xdist execution, browser/UI and production penetration tests are **NOT TESTED**.
  Docker fixed free-port allocation has a small bind race; subnet/VPN conflicts remain host concerns.
- Retained test databases and lifecycle volumes accumulate intentionally. Teardown removes only the
  generated containers/network. No deletion or cleanup of existing volumes/data was performed.

No commit, push, merge, Issue closure, public deployment or purchase is authorized or performed.

## Final local startup and handoff

```powershell
$env:FIELDOPS_SUBNET='10.244.0.0/24'
$env:FIELDOPS_PORT='18006'
docker compose --project-name fieldops-t06-validation config --quiet
docker compose --project-name fieldops-t06-validation up --build --wait
```

Both commands succeeded. The same runtime image starts API and worker separately against the
application PostgreSQL instance; PostgreSQL is not published on a host port. A real network urllib
cookie-jar smoke at `http://127.0.0.1:18006` returned liveness/readiness 200, dispatcher assigned-create
201, and the corresponding notification in technician A's JSON inbox (200) within 1.625 seconds of
starting the recipient observation. This smoke is additional runtime evidence, not another counted
Pytest case. The development stack and its synthetic smoke data remain for owner inspection.

Final Ruff lint/format (53 Python files), frozen lock resolution (36 packages), and `git diff --check`
passed. Final tracked/untracked nonignored source inspection found only synthetic test keys and
example placeholders, with no credential patterns, local environment files, private keys or generated
databases. Runtime logs in the isolated worker lifecycle checks did not contain the generated DB
credential; database failure text was absent from worker logs/durable errors. Existing data/volumes
remain intact. HEAD and merge-base with T04 are still the published baseline, and the index is empty.

Files added: `fieldops/worker.py`, `fieldops/trace_context.py`, `fieldops/services/notifications.py`,
`fieldops/routes/notifications.py`, `tests/test_t06_policy.py`, `tests/test_t06_postgresql.py`, and
this validation document. Updated: Compose, application router registration/contract status,
intervention trace-carrier adapters/service, contract/lifecycle tests, AGENTS, README, specification,
architecture, backlog and T03 contract status notes. No earlier commit was rewritten.

Verdict: **GO for independent T06 review before any separately authorized publication**. All six
Issue #5 acceptance criteria have local evidence above. No authorization is implied for T05 UI,
T07 controls, T09 observability, T10 alerting, T11 agent, commits, pushes or deployment. Stop for owner
review after local implementation and validation.

## Independent reliability, PostgreSQL concurrency and security audit

The audit read the live [Issue #5](https://github.com/chakirou18/final-project-AIzoomcamp-2026/issues/5),
AGENTS, specification, architecture, this validation record, all worker/inbox/API/Compose changes,
the persistence constraints and relevant tests. Origin is the requested repository; branch remains
`feature/t06-notification-worker`. HEAD and merge-base with T04 both remain exactly
`f272f5c70992902bfaa1a53c2075fae525ac1bd0`. Models, migrations, dependency manifest and lockfile
have no differences from that baseline. Earlier commits and existing local work were preserved.

### Execution and exact totals

```powershell
# First independently reproduced existing unit gate:
.venv/Scripts/python.exe -m pytest -m 'not integration and not container' -q -p no:cacheprovider --basetemp=artifacts/t06-review-unit-initial
# A separate audit Compose project/network, never an existing application queue:
$env:FIELDOPS_SUBNET='10.245.0.0/24'
docker compose --project-name fieldops-t06-review --profile test run --build --rm tests
# First seven additional audit cases, then the final expanded full gate:
docker compose --project-name fieldops-t06-review --profile test run --build --rm tests .venv/bin/pytest tests/test_t06_review.py -v
.venv/Scripts/python.exe -m pytest -m 'not integration and not container' -q -p no:cacheprovider --basetemp=artifacts/t06-review-unit-final
docker compose --project-name fieldops-t06-review --profile test run --build --rm tests
$env:FIELDOPS_RUN_CONTAINER_TESTS='1'
.venv/Scripts/python.exe -m pytest tests/test_container_lifecycle.py -v -s --junitxml=artifacts/t06-review-container.xml
docker info --format '{{json .NCPU}} {{json .MemTotal}} {{json .OperatingSystem}} {{json .ServerVersion}}'
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m ruff format --check .
uv --cache-dir .cache/uv lock --check
git diff HEAD -- migrations fieldops/models.py pyproject.toml uv.lock
git merge-base HEAD feature/t04-intervention-lifecycle
git diff --cached --stat
git diff --check
git status --short
```

| Audit gate | Passed | Failed | Skipped | Deselected | Observed time |
| --- | ---: | ---: | ---: | ---: | --- |
| Original unit suite, independently reproduced | 96 | 0 | 0 | 180 | 1.25s |
| Original unit/PostgreSQL suite, independently reproduced | 273 | 0 | 0 | 3 container | 36.69s |
| First seven new audit cases | 7 | 0 | 0 | 0 | 5.16s |
| Final unit gate | 96 | 0 | 0 | 194 | 1.20s |
| Final unit + PostgreSQL gate | 287 | 0 | 0 | 3 container | 45.07s |
| Final Docker lifecycle | 3 | 0 | 0 | 0 | 84.24s |
| Distinct final total | **290** | **0** | **0** | **0 remaining unrun** | Repeated gates excluded |

The final 287-test gate is **96 unit + 191 real PostgreSQL integration cases**. Fourteen audit
integration cases were added to the original 276-test suite. All original T02/T03/T04/T06 cases
remain covered. Ruff lint/format (54 Python files), frozen lock verification (36 packages),
whitespace and baseline checks pass. No failing application test or application-code defect was
found in this audit. Intermediate lint/format issues in the new test code were corrected before
the final gates. No application code, schema or dependency was changed during the audit.

### Concurrency, leases and bounded failure verification

- **Three separate OS processes**, each with its own engine/pool, synchronize through stdin/stdout
  barriers. Each claims a distinct 20-event batch before any process is permitted to deliver.
  PostgreSQL shows 60 processing events, 60 distinct lease UUIDs, attempts=1 and zero inbox rows
  at the barrier. All three processes then deliver their batches: exactly 60 unique inbox mappings
  and 60 delivered events result. Old claim reprocessing produces no changes. This supplements
  the original shared-engine thread test rather than treating threads as process evidence.
- The original SKIP LOCKED test holds an event lock on one actual connection and claims the
  other row on another connection. It passes. No mock storage substitutes for PostgreSQL locking.
- A new lock-wait test holds the event row, starts delivery on a second connection, and observes
  `pg_stat_activity.wait_event_type='Lock'` for that backend. It then expires the lease and releases
  the lock. Delivery returns false, inserts no inbox row, and a fresh token/second attempt safely
  recovers it. Synchronization uses observable server state, not an arbitrary delay.
- New contenders race for the fifth claim after four expired claims. Exactly one fifth token is
  issued. After its expiry, repeated concurrent reclaim attempts issue no sixth token; the row
  stays failed, attempts=5, with no inbox entry. Existing failure/expiry exhaustion cases pass too.
- Five new tests bound the actual persisted available_at between database clock samples plus
  2/4/8/16/30 seconds. Claims cannot run before the retry deadline. The fifth failure is terminal
  even when eligibility time is advanced; its stored 30-second timestamp never makes it reclaimable.
- Committed claims consume attempts; failed claim COMMITs do not create a claim or consume an
  attempt. SQL constraints, explicit lifetime cap and stale-token checks remain intact. Failed rows
  remain stored and visibly undelivered through their DB state; no dashboard was added.

### Atomicity, crash and outage evidence

The complete original PostgreSQL fault suite was independently rerun, including immediate INSERT
rejection, deferred COMMIT rejection after inbox INSERT/outbox UPDATE, failed claim COMMIT and lease
expiry between insertion and acknowledgement. Each checks actual row state after failure. Retrying
creates one matching inbox/delivered pair. Outbox_id uniqueness and the composite event/recipient/
intervention/version FK remain enforced by real PostgreSQL regression tests.

Both hard-exit subprocess cases pass: exit after inbox INSERT but before delivery commit leaves
the processing lease and no visible inbox row; lease recovery/restart delivers once. Exit after
delivery commit leaves one delivered event and one inbox row; a new process does not duplicate it.
The backend-termination test kills a real PostgreSQL connection during acknowledgement and the
worker loop recovers at attempt=2. The poison-event loop stops at five without logging DB error text.

All three Docker lifecycle cases pass, covering healthy startup, persisted data after restart and
recreation, readiness 503 with liveness 200 during real DB outage, worker process startup while the
DB is explicitly confirmed stopped, pending-event recovery, worker restart/recreation and readable
existing inbox while the worker is down. The backlog event is delivered after recovery; the final
21 persisted inbox rows match 21 delivered outbox events. No event was silently lost in these cases.

### Independently repeated performance measurement

Current Docker conditions were read again: Docker Desktop **29.9.3**, **12 CPUs**, **7,978,242,048
bytes (~7.43 GiB)** reported memory. Host tests: Windows/Python 3.12.10; worker runtime: pinned
Python 3.12.16 and PostgreSQL 17 on Docker Linux/WSL2. Shared development host, synthetic empty queue,
one continuously running worker process, batch limit 20 and **two-second polling**. The benchmark
runs before intentional outage injection; existing unrelated environments were not stopped/pruned.

| Independent real network benchmark | Observed result |
| --- | --- |
| Assignments successfully created | **20** |
| Corresponding notifications delivered and visible in recipient API | **20**, with 20 unique job IDs |
| Maximum DB-recorded outbox.created_at -> inbox.delivered_at difference | **1.638561s** |
| Maximum per-assignment HTTP visibility observation from create-request start | **1.703000s** |
| First create request -> all 20 visible through technician API | **1.843000s** |
| Worker count / polling interval | **1 / 2 seconds** |
| Ten-second target | **PASS** for every assignment |

**Measurement correction:** previously `observed_total_seconds` was sampled after a diagnostic
Docker/SQL command, adding unrelated command overhead. It is now frozen when the API first proves
all 20 are visible, before that query. The harness also records each assignment's start and first
recipient observation and asserts a maximum <10 seconds. These HTTP observations are upper bounds
on visible delivery, including request/polling overhead. The DB timestamp is sampled within the
delivery transaction, so its difference is a recorded operation lag, not an exact COMMIT timestamp.
It is reported separately and is not used alone to claim user-visible delivery performance.

### Authorization, trace and secret review

- Direct inbox GET/mark-read requests with missing, tampered, expired and revoked sessions return
  401; SQL timestamp changes simulate expiration without sleeping. Denied attempts leave read_at
  NULL. Two valid sessions concurrently mark the same notification read and both return 204;
  subsequent requests retain the exact original timestamp.
- A new two-page case delivers 26 assignments for A and one for B. A receives exactly 25+1 rows,
  total=26, with its exact job-ID set. B sees exactly its one job and cannot mark A's row read.
  An authenticated operator is denied both inbox listing and mark-read. Existing manager/CSRF,
  cross-technician/history and idempotent mark-read tests also pass.
- Trace-header adapters read only the optional bounded carrier fields; no job text, credentials,
  cookies, CSRF values, authorization header or baggage is copied into them. Valid subset context
  persists; invalid HTTP/service/stored context is ignored without preventing delivery. Claims carry
  sanitized optional context, not raw free text. The published conservative subset limitation remains.
- The Docker harness now retains known login CSRF values, signed session/prelogin cookies and
  generated DB/signing keys in memory only. It checks them against **all service logs** and the
  technician business inbox response. No match occurred; no secret was printed or stored in source.
  Authentication responses intentionally return their CSRF token by contract; that is distinct from
  leaking signing/DB credentials or unrelated session tokens in business responses.
- Final inspection/scanning covered **65 tracked and untracked nonignored files**: no private-key/
  credential-token patterns, local environment files or generated databases are publication candidates.
  Synthetic test keys and `.env.example` placeholders are intentional. The index remains empty.

### Corrections, scope and remaining limitations

Audit changes are limited to new `tests/test_t06_review.py`, stronger lifecycle benchmark/redaction
checks in `tests/test_container_lifecycle.py`, and this evidence document. The benchmark reporting
defect was corrected; application implementation was retained. No assertions were weakened and no
future UI/control/observability/alerting/agent feature was added. No commit or public update occurred.

The following limits remain material:

- This is demo persona authentication and a synthetic workload, not production identity/security
  certification. Web/worker still use local DB-owner credentials and a shared read-only credential
  volume containing signing material. Owner tampering, production privilege isolation and penetration
  testing are **NOT TESTED**. API checks do not cancel requests already executing when logout occurs.
- Context validation checks permitted syntax, not the semantic contents of arbitrary valid hexadecimal
  IDs. Caller-chosen IDs remain untrusted. Full W3C/vendor support, tracing/export redaction and
  correlation are **NOT TESTED** and deferred to T09. No real customer data was used.
- Lease expiry/backoff cases accelerate isolated row timestamps with SQL. The audit does not simulate
  every possible kill instant or system-clock jump. Exactly-one persistent inbox materialization is
  verified; exactly-once delivery to any external transport is not claimed.
- Batch leases are not renewed. Slow work/repeated restarts can consume attempts before all claimed
  rows are reached. Exhausted rows remain failed for future authorized human handling. There is no
  T07 replay/reset/pause control or worker heartbeat; running process is not proof of healthy delivery.
- Parallel pytest/xdist, large-backlog stress, production latency, browser/UI and full observability
  remain **NOT TESTED**. Live READ COMMITTED pagination can shift under writes. Docker host port
  selection has a short bind race; subnet/VPN overlap remains environment-dependent.
- Audit databases and generated lifecycle volumes are retained. Only generated containers/networks
  are removed by test teardown. Existing application volumes and the prior local port-18006 stack
  were preserved. Test artifacts/JUnit XML are ignored; no secret-bearing transcripts were published.

### Issue #5 acceptance after independent audit

| Issue acceptance criterion | Verdict | Independently verified evidence |
| --- | --- | --- |
| Inbox/outbox commit atomically | PASS | Immediate/deferred PostgreSQL failures, pre/post-COMMIT hard exits, exact persisted mappings |
| Lease tokens fence stale workers | PASS | Token/expiry denials, real lock-wait expiry, final guarded UPDATE |
| All claims consume five-attempt limit | PASS | Committed-claim counts, failure/expiry exhaustion, concurrent fifth-attempt race |
| Failed rows remain undelivered | PASS | Retained failed/attempts=5 row, NULL delivered_at, no inbox, no sixth claim |
| Twenty assignments each deliver within ten seconds locally | PASS | 20/20 recipient HTTP visibility, max observed per assignment 1.703s |
| Optional W3C carrier fields; delivery independent of invalid context | PASS | Existing schema, valid subset persistence and nonblocking malformed context cases |

Audit verdict: **PASS**. Recommendation: **GO for separately owner-authorized T06 publication**
within the documented demo scope. No critical unresolved T06 concurrency/atomicity defect was found.
Working-tree changes remain local and unstaged; HEAD is unchanged. No commit, push, merge, Issue
closure, public deployment, purchase or Docker volume deletion was performed. Stop for owner review.

## Final publication checks — 2026-11-10

Confirmed `feature/t06-notification-worker`, with HEAD and merge-base at published T04
`f272f5c70992902bfaa1a53c2075fae525ac1bd0` before publication. Read AGENTS.md and live Issue #5;
all six acceptance criteria retain the audit evidence above. Reviewed all 20 changed/new files.
No earlier commit, model, migration, dependency manifest or lockfile was modified.

Fresh commands and actual results:

```powershell
.venv/Scripts/python.exe -m pytest -m 'not integration and not container' -q -p no:cacheprovider --basetemp=artifacts/t06-publication-unit
# 96 passed, 194 deselected, 2.39s
$env:FIELDOPS_SUBNET='10.245.0.0/24'
docker compose --project-name fieldops-t06-review --profile test run --build --rm tests
# 287 passed (96 unit + 191 real PostgreSQL), 3 deselected, 64.34s
$env:FIELDOPS_RUN_CONTAINER_TESTS='1'
.venv/Scripts/python.exe -m pytest tests/test_container_lifecycle.py -v -s --junitxml=artifacts/t06-publication-container.xml
# 3 passed, 108.77s
uv run ruff check .
uv run ruff format --check .
uv --cache-dir .cache/uv lock --check
git diff --check
```

Ruff lint passed; formatting passed for 54 Python files; lock check passed for 36 packages.
Whitespace check passed. Fresh distinct total: **290 passed, zero failed or skipped**.
Deselection counts above select complementary suites; they are not skipped tests.
The full run includes the three-process/60-event, real lock-wait fencing, atomic rollback,
pre/post-commit crash, five-attempt exhaustion and direct HTTP security regression cases.

The fresh Docker benchmark delivered **20/20**, with one worker, polling every two seconds:
maximum database-recorded latency **2.987460s**, maximum per-assignment HTTP-observed latency
**3.063s**, all twenty visible through the recipient API in **3.281s**. This independently
passes the ten-second local target; the earlier audit's 1.843s remains a separate measurement.
Same local Docker Desktop conditions as documented above; no production latency claim.
Worker restart and database outage/recovery also passed in the fresh lifecycle run.

Scanned all 65 nonignored files for private keys, credential token patterns and runtime database/
environment filenames: no findings. Synthetic fixtures and `.env.example` are intentional.
Only authorization documentation and this final evidence were adjusted during publication;
application and tests remain the audited implementation. Existing limitations above still apply.
