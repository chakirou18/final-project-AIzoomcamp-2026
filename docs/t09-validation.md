# T09 observability implementation and validation

Task: [Issue #9](https://github.com/chakirou18/final-project-AIzoomcamp-2026/issues/9), branch `feature/t09-observability`, unchanged T08 parent `fcc5bf7090d248fb667b4e26169f3bf76f24b151`. Latest owner authorization permits T09-only commit/push/PR/Issue progress publication **only after all release gates pass**. Fresh post-recovery release gates pass; conditional publication is authorized. Merge, Issue closure, T10/T11 implementation, public deployment, purchase, database/volume deletion, global cleanup, force-killing Docker processes and engine-wide restart without separate approval remain unauthorized.

Status: **PASS / GO for T09 feature-branch publication: source verified, 438 distinct fresh tests passed, worker restored.** All 123 ZIP files matched SHA256 before edits. Windows was restarted manually by the owner; this task did not restart Docker Desktop. Web and worker were started without recreating healthy telemetry services. Historical blocked results below remain historical and are superseded only by the fresh evidence in the recovery section at the end. All runtime, regression, security and resource gates pass; the audited 32-file index passed final review. No T10/T11 work is authorized.

## Design and bounded data flow

HTTP middleware opens a genuine SDK SERVER span after conservative W3C extraction. Shared assignment service opens `intervention.assign` then PRODUCER `notification.enqueue`, enclosing SQL updates/history/outbox flush and transaction completion. The active enqueue context is injected into the same transactional outbox row. SQLAlchemy hooks export only operation/table names from a fixed allowlist, not statements, parameters or exception details.

The separate worker extracts the row carrier into a fresh OTel Context, starts CONSUMER `notification.deliver` and child `notification.inbox.persist`, preserving existing lease/fencing, idempotency and transaction boundaries. Retries reuse the original enqueue parent. Invalid context starts a root and emits a bounded warning. Structured enqueue logs run only after commit. Worker delivered logs run after the inbox/outbox commit. IDs are log/span fields, never metric/Loki stream labels. The SDK uses AlwaysOn demo sampling and bounded asynchronous batches (512 spans, 64 per batch, 500ms scheduling, one-second OTLP HTTP timeout).

Web-owned `/metrics` derives queue, terminal counters, delivery histogram, worker pause and heartbeat from a read-only consistent PostgreSQL snapshot. Pending, processing and failed all count as undelivered; empty age is zero. `fieldops_metrics_database_up=0` omits unavailable queue values rather than presenting a healthy zero. HTTP count/duration have bounded method, route-template and status-class labels. SQL aggregates return fixed bucket counts, not all delivery rows. Metrics remain exposed when the worker is stopped. Local Compose publishes web only on loopback; a future hosted reverse proxy must exclude `/metrics` and internal routes from public access.

JSON stdout is mirrored into one rotating log file per service (active plus two backups, five MiB each: 30MiB combined web/worker maximum). Alloy tails a dedicated read-only log volume and retains only `service`/`environment` stream labels; Loki additionally derives the bounded `service_name` label. Neither has a Docker socket, app credentials or privileged control. Loki push retry is bounded. Dropped telemetry never changes a committed business outcome.

Prometheus scrapes the web every five seconds. Grafana provisions Prometheus/Loki/Jaeger sources, thirteen real-data panels, bounded 15-minute/100-line log queries, metric-to-log investigation links and log-derived Jaeger links. Only Grafana/Jaeger UI ports are loopback-published; other telemetry ports remain private. Grafana is an explicitly local anonymous read-only Viewer with initial admin creation, basic login and signup disabled. Hosted authentication is future authorized deployment work.

## Components and configuration

Fixed image versions and immutable digests are in `docker-compose.yml`: Prometheus 3.16.0, Grafana 13.3.0, Loki 3.7.9, Alloy 1.21.3, OTel Collector Contrib 0.165.0, Jaeger 2.23.0 and Alertmanager 0.35.0. Vendor images are wrapped only to add a digest-pinned static BusyBox 1.37.0-musl HTTP readiness client. Dependencies are locked: OTel SDK/OTLP HTTP 1.45.2 and prometheus-client 0.26.0. No trace IDs are manually generated.

Prometheus has 24-hour/256MB retention. Loki has 24-hour retention with one-minute compaction, bounded 0.05MiB/s ingest, sixteen streams, capped query duration/parallelism/entries. Jaeger Badger has 24-hour trace TTL and one-minute maintenance. Named telemetry volumes preserve data across process/container restarts; time retention is asynchronous and not a hard filesystem quota. Alloy positions and Grafana provisioning state have dedicated volumes. Docker JSON log rotation and measured disk growth are validated below before final claims.

Alertmanager has a no-op receiver and 24-hour local state. Prometheus references it but has no alert-rule files. No incident webhook or mock agent is included.

## Reproduction

```powershell
# Choose an unused project, subnet and loopback ports; preserve these values for every invocation.
$env:COMPOSE_PROJECT_NAME='fieldops-t09'
$env:FIELDOPS_SUBNET='10.254.9.0/24'
$env:FIELDOPS_PORT='18009'
$env:FIELDOPS_GRAFANA_PORT='13009'
$env:FIELDOPS_JAEGER_PORT='16689'
$env:POSTGRES_DB='fieldops_t09_demo_test'
docker compose --profile observability up --build --wait --wait-timeout 240

# Opt-in failure tests mutate only this explicitly synthetic test project's state.
$env:FIELDOPS_RUN_OBSERVABILITY_TESTS='1'
uv run pytest observability_tests -v -s -p no:cacheprovider --tb=short
```

The future complete-stack contract remains:

```sh
docker compose --profile observability --profile incident up --build --wait
```

**NOT TESTED as a complete stack.** T11's real On-Call Agent/incident profile does not exist. Supplying an otherwise unused profile name is not evidence of agent startup; no mock is used to claim this gate.

## Observations and corrections during implementation

- Existing unit regression initially passed: 124 passed, 261 deselected, 3.17s.
- First targeted T09 unit selection: thirteen passed/one failed, six integration deselections. The new SDK's valid W3C random-ID flag `03` was rejected by the old T06 `00|01` carrier regex. Accepting valid lowercase hexadecimal flags and delegating interpretation to the official propagator fixed it; fourteen targeted unit cases then passed in 0.60s. Explicit `01`/`03` regression cases were added afterward.
- Initial profile built every component but failed readiness: the renamed BusyBox binary dispatched an unknown applet; Jaeger could not create its Badger directory as UID 10001. Kept the binary name `/busybox`; the existing credential initializer now sets ownership only on dedicated new telemetry log/Jaeger volume roots. No existing application data directory is chmod/chowned.
- Initial Alloy/collector 128MiB limits caused kernel reclaim and CPU throttling, not OOM kills: Alloy recorded 646,288 cgroup memory-limit events and 2,664 throttled periods. Increased their explicit caps to 384MiB; both became ready. Grafana's initial 256MiB cap was increased to 512MiB. These are observed local resource corrections, not a claim that the entire stack has passed.
- Host before T09: Docker Desktop/WSL2, twelve visible CPUs, 7,978,242,048 bytes RAM; Windows C: approximately 142.6GB free. Thirty-four retained containers included a historical test PostgreSQL using about 2.98GiB and another about 623MiB. No old service/database/volume was removed or globally pruned. Validation is sequenced when this shared resource pressure prevents reliable checks.
- The first overlapping backend run had 398 passes, four failures, one setup error and four Docker deselections in 438.22s (`artifacts/t08-backend-9069f732f9914232a99ba64bd78200ab/`). Failures were Docker DNS/503 and child-worker startup timeouts under shared memory pressure. The first real correlation probe also timed out on Docker exec after 90 seconds. These runs are retained as failures, not acceptance evidence. SDK/exporter imports were made lazy for telemetry-disabled test/CLI processes; expensive suites were then sequenced with only the T09 profile stopped and its volumes retained. The final unchanged backend assertions passed 403/403 in 71.39s with cleanup and shutdown PASS. No old service needed stopping.
- Grafana Viewer initially could not reach Explore; the pinned-version transient-inspection setting fixes this, with an explicit persistent-write denial test. At 512MiB, a later browser trace-link run timed out loading the dashboard, while the two presentation cases passed. Final Grafana cap 768MiB/Go soft limit 384MiB plus disabled plugin preinstallation removed the observed reclaim/startup issue. A focused trace-link rerun and then the entire thirteen-case gate passed. Browser screenshot assertions were subsequently strengthened for all virtualized panels, as described below.

## Metric inventory and semantics

| Metric | Type / bounded labels | Source |
|---|---|---|
| `fieldops_metrics_database_up` | Gauge, none | Complete consistent DB snapshot succeeded (1) or failed (0) |
| `fieldops_notifications_undelivered` | Gauge, none | Pending + processing + failed persisted rows |
| `fieldops_notification_oldest_undelivered_age_seconds` | Gauge, none | DB clock minus minimum undelivered created_at; empty=0 |
| `fieldops_notification_events` | Gauge, status: four states | Persisted state counts, including failed |
| `fieldops_notifications_delivered_total`, `fieldops_notifications_failed_total` | Counters, none | Persistent terminal rows, not process-local delivery attempts |
| `fieldops_notification_delivery_latency_seconds` | Histogram, fixed le buckets | Committed delivered_at minus created_at; fixed SQL aggregate buckets |
| `fieldops_worker_heartbeat_timestamp_seconds` | Gauge, none | Latest persisted heartbeat timestamp, never inferred from API readiness |
| `fieldops_worker_paused` | Gauge, none | Persisted control gate; interpret alongside heartbeat freshness |
| `fieldops_http_requests_total` | Counter, method/route/status_class | Response status, including denied/failed requests |
| `fieldops_http_request_duration_seconds` | Histogram, method/route/fixed le | Application request processing through response creation, not client network/body-download time |

Routes are registered templates or `<unmatched>`, methods use seven allowlisted verbs plus OTHER, status classes are bounded. Database snapshot gauges/counters/histogram survive web/worker restarts; HTTP metrics are intentionally process-local and Prometheus handles counter resets. Terminal counters assume the current append-preserving outbox policy; deleting terminal rows or adding future failed-event requeue needs metric-semantic review. No migrations were required: T03 carrier/outbox/inbox and T07 control/heartbeat tables are reused unchanged.

## Executed regression and quality commands

Local dependency preparation used `uv sync --frozen`. The SDK and metrics packages are exact pins in the locked manifest. Commands below use PowerShell; the T09 environment values are the reproduction block above. For backend/browser regressions, use separate `COMPOSE_PROJECT_NAME=fieldops-t09-regression`, `FIELDOPS_TEST_SUBNET=10.254.10.0/24`, `FIELDOPS_BROWSER_SUBNET=10.254.11.0/24`. Preserve consistent overrides between all operations in one project.

```powershell
uv run pytest tests -m 'not container and not integration' -p no:cacheprovider --junitxml=artifacts/t09-unit-final.xml
docker compose --profile test run --build --rm tests
$env:FIELDOPS_RUN_CONTAINER_TESTS='1'
.venv/Scripts/python.exe -m pytest tests/test_container_lifecycle.py -v -s -p no:cacheprovider --junitxml=artifacts/t09-container.xml --tb=short
docker compose --profile browser run --build --rm browser-tests
# Restore the T09 project environment before these operations.
docker compose --profile observability up --build --wait --wait-timeout 240
$env:FIELDOPS_RUN_OBSERVABILITY_TESTS='1'
.venv/Scripts/python.exe -m pytest observability_tests -v -s -p no:cacheprovider --tb=short --junitxml=artifacts/t09-stack-complete.xml
.venv/Scripts/python.exe -m test_support.telemetry_resources
.venv/Scripts/ruff.exe check .
.venv/Scripts/ruff.exe format --check .
uv lock --check
docker compose --profile observability --profile test --profile browser config --quiet
git diff --check
git status --short --untracked-files=all
git diff --cached --stat
git rev-parse HEAD
git merge-base HEAD feature/t08-testing
```

Observed final unit-only run: **140 passed, 267 deselected**, zero failures/errors/skips, 2.05s. This intentionally deselects PostgreSQL/Docker cases and is a subset of the combined runner, not additional distinct tests. Backend runner: **403 passed, four Docker deselected**, zero failures/errors/skips, 71.39s, `artifacts/t08-backend-80ae3a30f49240379760ac20f71acbc5/pytest.xml`; summary reports cleanup PASS, shutdown PASS, zero fallback database removals and exit 0. It contains 140 unit plus 263 PostgreSQL cases. Docker gate: **four passed**, zero failures/errors/skips/deselections, 142.95s, `artifacts/t09-container.xml`. Its real delivery timing was 20/20 visible within 2.532s (maximum DB latency 2.310s), followed by restart/outage/recreation persistence assertions.

Both required T08 runner commands build locked dependencies inside containers without relying on the host venv or preseeded demo data. Existing ownership-guarded disposable databases and 512MiB tmpfs services remain isolated from development. T09 reruns validate the modified application/dependencies; the earlier clean-source export evidence belongs to the published T08 baseline and is not represented as a new T09 clean-source run.

Browser runner: **18 passed**, zero failures/errors/skips/deselections, 118.24s, `artifacts/t08-browser-a6cc7652f22a4ad690205d3a6c6f3205/pytest.xml`. It exercised desktop/375px, JS enabled/disabled, manager create/edit/assign, technician start/complete, inbox/reassignment scope, cancellation, filters/pagination, invalid/revoked session, focus/keyboard and T07 controls. The controlled-pause regression persisted event `550db09c-ae1b-45f0-8283-4350a5225ae5`, held it for 61.083s and delivered it at `2026-11-10T08:20:31.102148Z`. Summary: exit 0, shutdown/cleanup PASS, exactly two owned browser/benchmark databases removed by ownership-guarded finalization.

The same runner's N03 report `n03-performance.json` contains 1,000 synthetic records, five clients, fifty measured valid HTTP requests (25 list/25 detail), ten excluded warmups, nearest-rank p95 (sorted sample 48) and complete raw durations. Actual results: **p50 39.847ms, p95 53.916ms, max 54.685ms, zero errors, 123.412 requests/s**, measured request window 0.405146s. This is the existing short local T08 regression harness with its telemetry-disabled setting, not a production-load or always-on-exporter benchmark. Full observability load is measured separately below.

Ruff lint and formatting pass (86 Python files), `uv lock --check` resolves the locked 52 packages, and all-profile Compose config validates. `git diff --check` passes; informational LF/CRLF notices are not whitespace errors. HEAD/merge-base both remain `fcc5bf7090d248fb667b4e26169f3bf76f24b151`. Existing migrations, application browser tests, lifecycle tests and T08 runner source are unchanged. All 31 modified/untracked source paths were inspected/scanned for private-key/token signatures and forbidden runtime artifact extensions; no unsafe candidate and no staged file were found. The ignored source SHA256 inventory is `artifacts/t09-source-manifest.json`. Runtime keys remain in separate generated credential volumes; source test-only credentials inherited from T08 are explicitly synthetic.

Volume inventory comparison: **109 pre-existing volumes before, 125 after, zero pre-existing volumes missing**. Added volumes belong to the new isolated T09 telemetry/test projects. The previously persisted trace `71f99216b4152cec785db40e5013b564` still returns nineteen spans after stopping the whole T09 stack and rebuilding/recreating its application containers. No named volume deletion, old-service stop or global cleanup occurred.

### Late repeat failures and synchronization corrections

After the earlier thirteen-case pass, stronger per-panel browser assertions exposed another repeat failure: **nine passed/four failed**, zero errors/skips/deselections, 321.54s, preserved in `artifacts/t09-stack-panel-failures.xml`. The prior passing XML was preserved as `artifacts/t09-stack-before-panels.xml`; its JSON evidence remains under the original directory. Failures were Collector restart/recovery correlation, both presentation cases and the metric-to-log browser link. Do not use the earlier thirteen-pass result to claim the stronger gate passed.

Measured diagnostics at the failure: Docker VM `MemAvailable=653596KiB`; memory pressure `full avg300=18.82%` and `some avg300=27.39%`. No telemetry container OOM kill occurred. Grafana reached CPU 102.49%/492.4MiB, Prometheus 15.51%/56.84MiB and Collector 50.44%/110.9MiB. Most charged CPU time was kernel/system time during reclaim. Collector reported bounded retry exhaustion/trace drops to Jaeger; Alloy reported a timed-out Loki batch drop. These are real lost telemetry, not lost assignments/inbox data. The seven-service short resource sample is not a peak-memory promise.

Grafana queries took more than five seconds while the dashboard refreshed every five seconds, leaving lower panels loading. Dashboard version 3 now refreshes every **15 seconds** to avoid that overlap. The next focused six-case run had **four passed/two failed/seven deselected** in 221.00s, `artifacts/t09-recovery-panel-check.xml`. Both desktop and 375px now scrolled, rendered and captured all thirteen real-data panels; actual images were inspected, including delivery p95 1.93s, HTTP p95 44.6ms and JSON delivery logs. Panel screenshots are `artifacts/t09-stack-1bdaa652ae934078855c0c4c36055ca4/grafana-{width}-panel-{id}.png`. The other two failures remained recovery/readiness and browser log investigation.

Corrections keep business/persistence assertions intact: wait for the complete HTTP/enqueue/delivery/SQL trace rather than whichever asynchronous batch arrives first; explicitly wait for restarted telemetry service readiness; treat a successful empty readiness response by its exit status; wait for both event logs to reach real Loki before opening Explore's one-time query snapshot; and always screenshot/close browsers on failure. One intermediate focused rerun still failed both cases (79.41s; eleven deselected, `artifacts/t09-readiness-shipping.xml`). A cold Collector became available only after the test's assumed 30-second startup budget under the measured pressure. Startup readiness now uses the existing Compose health envelope (30 probes x five seconds = 150s), separately from the **unchanged 30-second trace-correlation deadline after readiness**. This changes the infrastructure startup assumption, not the trace, transaction, recipient, redaction or duplicate assertions.

No permission was received to stop unrelated services or alter Docker VM RAM, so those resources remain unchanged. Additional runs are sequenced. The latest focused and full-gate results below determine the final verdict; unresolved failures must stay FAIL.

## Real correlation and failure evidence

The earlier complete telemetry/browser selection before the additional per-panel screenshot assertion passed **13 tests in 119.69s**, zero failures/errors/skips/deselections: `artifacts/t09-stack-before-panels.xml`. Sanitized trace JSON, committed row mappings, paired JSON logs, Loki/Grafana responses and screenshots are under `artifacts/t09-stack-84fbc2e323554c63840ab0ae42129ae1/`. These are historical ignored local evidence, not committed runtime data. Final resumed results below supersede this weaker browser selection. Rerunning a case never adds to distinct totals.

One concrete event is `037b4955-29ad-436b-ba9c-efde57f49f29`, created at `2026-11-10T08:00:13.511540Z`, delivered at `08:00:15.427369Z`, with exactly one inbox row `0baa2629-718f-44ed-941e-389c3a59331a`. Its persisted carrier is `00-71f99216b4152cec785db40e5013b564-069752afd873da7b-03`. Retrieved Jaeger JSON contains the HTTP SERVER, assignment, enqueue, outbox SQL INSERT, remote-parent delivery, inbox persist and inbox SQL INSERT spans with trace ID `71f99216b4152cec785db40e5013b564`. The delivery CHILD_OF reference equals persisted enqueue span `069752afd873da7b`. Both process log excerpts carry that trace/outbox ID and the delivery log has the matching inbox ID. The event JSON contains the complete backend evidence; screenshots are supplementary.

The same gate verifies two simultaneous assignments have different traces and no context leakage. A real PostgreSQL sequence/trigger fails the first inbox INSERT only: the event consumes two attempts, materializes exactly one inbox row, and both delivery spans have the original persisted enqueue parent. Malformed stored context delivers under a fresh root rather than another event's trace; its raw invalid carrier and synthetic secret never enter telemetry. Collector outage still allows assignment/history/outbox/inbox commits, and a new assignment is correlated after recovery. Separate Prometheus and Loki outages likewise leave committed delivery intact. Telemetry lost beyond bounded queues/retries is deliberately not promised to be durable.

Worker-stop tests retain a visible backlog and a stale heartbeat on the web metrics endpoint. PostgreSQL outage produces readiness 503, liveness 200 and metrics database-up 0 with queue metrics omitted. After recovery the same persisted event delivers once. Authorized T07 pause keeps heartbeat advancing and backlog age increasing, then the existing generation-checked internal resume drains it. This is manually authorized recovery, not a T10 alert or T11 agent.

Prometheus label inspection and three distinct unmatched UUID URLs verify bounded route labels; all three 404s share one `<unmatched>` series. Real Loki stored-series inspection permits only service/environment/service_name, while JSON-extracted trace/event fields remain query-time fields. The Loki API returns matching enqueue/delivery logs from both services. Grafana's datasource proxy retrieves the same Jaeger trace. Chromium actually follows metric -> bounded Loki Explore -> expanded log -> View Jaeger trace, rendering two services and nineteen spans. A valid dashboard-write request from the same anonymous Viewer returns 403.

Sentinel tests cover authorization/cookie/CSRF/password/API-key/body/site/description/SQL/exception fields and arbitrary library messages. No raw request headers, query strings, bodies, SQL parameters or exception strings are exported. SQL instrumentation records only fixed operation/table names. Unknown library log messages are suppressed to `library_log`; exception type is retained without message/stack. Outage/retry evidence is checked for the sentinel before writing.

Grafana Explore requires `GF_USERS_VIEWERS_CAN_EDIT=true` on the pinned version. It permits transient inspection, while provisioned dashboards and persistent writes stay denied. This setting is deprecated upstream and must be revalidated before a Grafana upgrade. Initial screenshots showed virtualized panels below the viewport as blank placeholders; browser checks now scroll each panel and require actual returned values/logs before capturing individual panel images. This avoids mistaking a title-only render for successful data presentation.

## Measured resources and retention

Command: `.venv/Scripts/python.exe -m test_support.telemetry_resources` after loading the isolated project environment and setting `FIELDOPS_RUN_OBSERVABILITY_TESTS=1`. Final report: `artifacts/t09-resources-1794297858969442100/resources.json`.

Host CPU is AMD Ryzen 5 5600H (six cores/twelve threads); Windows reports 16,477,282,304 bytes physical RAM. Docker Desktop/WSL2 exposes twelve CPUs and 7,978,242,048 bytes RAM (about 7.43GiB). Windows C: had approximately 142.6GB free before execution and 130,708,975,616 bytes free after image/browser builds. Retained unrelated test databases already consumed significant RAM; they were not stopped, removed or pruned. This short sample spans `08:04:24.009120Z` to `08:04:55.619850Z` on 2026-11-10. Two clients delivered 26 real assignments, while a third ran 93 Grafana-to-Prometheus queries during a minimum 25-second load window. Docker CPU is percent of one logical core, not whole-host utilization. Memory is cgroup usage; RSS is PID 1 from `/proc/1/status`, not the sum of processes/page cache. Disk is `du -sk` for the named data directory, not image layers or all Docker storage.

| Service | Idle CPU % | Active CPU % | Active cgroup MiB | Active RSS KiB | Initial data KiB | Growth KiB | Memory cap MiB |
|---|---:|---:|---:|---:|---:|---:|---:|
| Prometheus | 0.15 | 0.93 | 34.83 | 33144 | 1088 | 8 | 192 |
| Grafana | 1.02 | 6.87 | 284.60 | 186664 | 1720 | 0 | 768 |
| Loki | 1.76 | 1.29 | 89.69 | 81168 | 420 | 76 | 256 |
| Alloy | 0.40 | 4.54 | 88.25 | 52464 | 28 | 0 | 384 |
| OTel Collector | 2.69 | 4.91 | 67.20 | 51288 | 0 | 0 | 384 |
| Jaeger | 4.39 | 2.30 | 69.88 | 60004 | 13300 | 956 | 384 |
| Alertmanager | 2.50 | 0.00 | 13.26 | 12852 | 4 | 0 | 64 |

Active aggregate cgroup memory is **647.71MiB**; seven hard caps sum to 2432MiB. The earlier commentary estimate of 628MiB was arithmetic error; the per-service report above is authoritative. CPU values are snapshots under stated load, not sustained peak promises. Grafana was increased again from 512 to 768MiB after observed cgroup reclaim and slow dashboard loading; its Go soft memory limit is 384MiB. A complete thirteen-case gate passed with the final caps. Alloy/Collector use 256MiB Go soft limits within 384MiB containers. Grafana plugin preinstallation and Alloy usage reporting are disabled to avoid unnecessary network/startup load.

Prometheus retains 24h/256MB; Loki and Jaeger retain 24h with asynchronous compaction/maintenance. Collector queues are bounded in memory and have no data directory. Alloy positions, Grafana provisioning state and Alertmanager silence state have small persistent volumes. Application log files cap at 30MiB combined; Docker stdout/stderr JSON files cap at 5MB x three files per configured container. Measured short-run growth is not a sustained capacity guarantee. **NOT TESTED:** waiting a full 24h for retention deletion, filesystem-full behavior, sustained high-volume ingestion, production HA/storage and strict per-volume filesystem quotas. Disk space still needs operational monitoring in future phases.

## Resumed Grafana debugging and final handoff

### Recovered interrupted state

The owner requested resumption, not a new implementation. Repository/branch/status, AGENTS.md, live Issue #9 and the existing reports were reread. Branch remains `feature/t09-observability`; HEAD remains published T08 `fcc5bf7090d248fb667b4e26169f3bf76f24b151`. All existing T09 changes and evidence were preserved. No application code, dependency, migration or Compose definition was changed in this resumption.

The latest prior complete observability run was **12 passed / one failed**, zero errors/skips/deselections, 305.84s, preserved as `artifacts/t09-pre-resume-12-1.xml`. Its only failure was `test_metric_logs_to_jaeger_browser_link`. The existing isolated fix had also recorded one focused pass in 10.00s (`artifacts/t09-link-final.xml`); that was checked rather than assumed. Backend 403, Docker four and application-browser eighteen successful cases remain valid: SHA256 comparison of thirteen application/dependency/Compose paths against the earlier source manifest found **zero changes**. Those expensive suites were not rerun.

### Exact cause and scoped correction

1. The link test demanded backlog zero immediately after delivery. Prometheus can legitimately still show the last five-second snapshot containing one pending event. The failing browser showed database-up 1, backlog 1 and age 286ms while the matching PostgreSQL event had already delivered. This was a test snapshot assumption, not a fabricated metric or wrong datasource.
2. Clicking a derived link updates Grafana Explore asynchronously. A substring check for `notification.deliver` could match the Loki JSON event `notification_delivered` before the Jaeger pane opened. The test now waits for the real trace ID in navigation **and the exact `notification.deliver` operation rendered by the trace viewer**.
3. With only one event in the log window, Grafana repeats its outbox ID in the common-label header. A locator selecting the first bare UUID clicked that header, not a JSON row. The first resumed stronger focused run failed here (one failed, twelve deselected, 30.12s; screenshot/trace data in `artifacts/t09-stack-e56f94c3a1a4431f8707e9bd66258da9/`). Selecting the quoted JSON `"outbox_id": "<actual UUID>"` fixes the ambiguity.

Only `observability_tests/test_stack.py` was changed for executable behavior. Its existing one browser case now proves **both** valid backlog states independently of other tests: use the existing authenticated/audited T07 pause gate, create one real pending assignment, wait for Prometheus to record one, resume in `finally`, verify actual delivery and wait for Prometheus zero. It opens Grafana at each real stored snapshot timestamp, requires its exact displayed value, and follows metric -> matching JSON log -> derived Jaeger link -> actual delivery span for the same trace. No mocked responses, fabricated IDs or forced frontend values are used. A valid persistent dashboard-write request remains denied with HTTP 403. The test remains one pytest case; the two snapshots are not counted twice.

### Successful focused evidence

```powershell
. ./artifacts/t09-environment.ps1  # ignored helper containing only the project/port/subnet values above
$env:FIELDOPS_RUN_OBSERVABILITY_TESTS='1'
.venv/Scripts/python.exe -m pytest observability_tests -k metric_logs_to_jaeger_browser_link -v -s -p no:cacheprovider --tb=short --junitxml=artifacts/t09-resume-link.xml
```

Observed after the selector correction: **one passed, zero failed/errors/skipped, twelve deselected, 16.83s**. Evidence: `artifacts/t09-stack-ef28110211384b0fa31991a3e95ed3ec/`.

| Actual evidence | Value |
|---|---|
| Trace ID from persisted W3C carrier / both process logs / Jaeger | `3ebb9b27764f22786534101b9ef3ca08` |
| Outbox event | `a64f0f4e-d700-4bf1-a9b5-1f1915dd0930` |
| Persisted enqueue span / delivery CHILD_OF span | `9d8bcc7fd0d829ae` / same |
| Stored trace | Nineteen spans; fieldops-web and fieldops-worker |
| Backlog-one real Prometheus snapshot | `2026-11-10T15:09:21.676Z` |
| Committed delivery | `2026-11-10T15:09:22.379759Z` |
| Backlog-zero real Prometheus snapshot | `2026-11-10T15:09:26.629Z` |
| Unique persisted inbox record | `479cc608-68cd-4c76-80eb-99ffc96d5313`, inbox count one |

`browser-link-snapshots.json` records both actual timestamp/value pairs and resulting Grafana URLs. The outbox-ID JSON file contains the full retrieved trace, references, committed row mapping and correlated redacted logs. Actual screenshots inspected: `grafana-log-to-trace-backlog-1.png` and `grafana-log-to-trace-backlog-0.png`, both showing the same stored trace with two services/nineteen spans. URL strings alone are not the pass condition.

An additional bounded read-only runtime verification fetched Grafana's Loki/Jaeger datasource APIs and the trace through Grafana's Jaeger proxy: `artifacts/t09-resume-datasources.json`. Actual Loki UID/URL are `fieldops-loki` / `http://loki:3100`; Jaeger UID/URL are `fieldops-jaeger` / `http://jaeger:16686`. The derived field extracts the JSON `trace_id` and resolves `${__value.raw}` through `fieldops-jaeger`. Its proxy returns the same nineteen-span trace. A five-minute stored-label API query returns only **environment, service, service_name**, with no trace/span/event IDs. An initial default one-hour metadata query was rejected by Loki's configured fifteen-minute maximum; the bounded query passed. This rejection is not counted as trace-link failure or ignored by relaxing the retention/query policy.

### Complete-suite attempt blocked by Docker

```powershell
.venv/Scripts/python.exe -m pytest observability_tests -v -s -p no:cacheprovider --tb=short --junitxml=artifacts/t09-resume-observability.xml
```

Thirteen cases were selected. **Two completed and passed** (normal correlation and concurrent assignments); the third, retry/failure injection, blocked in `docker compose ... stop worker` before its fault trigger was installed. Its Compose child survived the helper's parent timeout. A separate direct `docker inspect ... fieldops-t09-worker-1` also hung. The exact underlying Docker Desktop cause is **not established**; current VM pressure was much lower than the earlier stress episode, so memory pressure is not asserted as the sole cause.

Only the identified owned pytest/Compose/inspection client processes were terminated to prevent an indefinite run. No Docker daemon restart, unrelated container stop, duplicate stack, database deletion, volume removal or global cleanup was performed. This interrupted invocation produced **no completed JUnit report**. `artifacts/t09-resume-blocked-run.json` explicitly records **two passes, one blocked case, ten not executed**, not a manufactured successful XML. A final direct `docker start fieldops-t09-worker-1` restoration attempt also timed out at its explicit fifteen-second subprocess limit; only that client was terminated. Worker stop/restart control remains unresolved in this environment; the worker was not claimed restored. Following containment, web liveness returned 200 and metrics returned DB-up 1, backlog zero, oldest age zero and pause flag zero; heartbeat no longer advanced after the attempted stop. API liveness is not worker recovery evidence.

### Current resource safety and final quality

Before the attempt all seven existing telemetry services and PostgreSQL/web were healthy; worker was running; initializers had exited zero. Ten existing T09 named data/credential/telemetry volumes were inspected. No new stack or volume was created. Docker stats itself hung; its identified read-only CLI was stopped, and direct cgroup/VM readings were used instead. Current sample: VM available memory **917560KiB (about 896MiB)**, full-memory-pressure avg300 **0.01%**; Grafana cgroup memory **578519040 bytes** within **805306368 bytes (768MiB)**. Free C: storage was **121314443264 bytes**. Earlier peak pressure, caps, measured per-service resources and asynchronous retention limitations remain recorded above. Low headroom and the new Docker control blockage must remain separate limitations.

Resumption changes are limited to `observability_tests/test_stack.py`, this validation document and the README status. Other local T09 implementation files remain preserved. Ruff lint and formatting pass (86 Python files). All-profile `docker compose ... config --quiet` and `git diff --check` pass. Only LF/CRLF conversion notices are emitted. Git status remains the preserved uncommitted T09 changes; index empty, HEAD unchanged. Source/runtime-artifact scans found no credentials or generated databases among candidate files. Sanitized browser/trace reports remain ignored under `artifacts/`; the final resumed source hashes are in `artifacts/t09-resume-source-manifest.json`.

### Test accounting and acceptance verdicts

There is valid retained/current passing evidence for **438 distinct cases**: 403 backend (140 unit + 263 PostgreSQL), four Docker lifecycle, eighteen application Chromium, twelve unchanged earlier observability cases and the corrected focused link case. New two-case partial execution and every earlier rerun are subsets, not additional tests. This is **not** a claim that the resumed combined thirteen-case command passed. Its actual completed/blocked/not-executed breakdown is above; no new complete 13/13 result can be given.

| Live Issue #9 criterion | Verdict | Evidence and limit |
|---|---|---|
| Observability profile starts all seven services | PASS, retained | Pinned profile startup and current preflight health; later worker Docker-control blockage remains open |
| Full-stack command documented, real agent deferred | PASS for documentation; agent startup NOT TESTED | Exact command above; no incident agent/mock substituted |
| W3C same trace / explicit worker remote parent / outbox-to-inbox | PASS | Real nineteen-span JSON and exact persisted enqueue-parent reference; prior concurrent/retry/malformed cases retained |
| Correlated structured logs, bounded metric/Loki labels | PASS | Sentinel tests, paired real logs and current stored-label API verification |
| Dashboard log-derived trace links work | PASS | Both real one/zero snapshots navigate and render the exact stored delivery span |
| Impact gauges survive worker failure; empty/unavailable distinguished | PASS, retained | Existing real PG/outage cases, plus web-owned metrics after current worker stop attempt |
| Retention/resource limits configured and measured | PASS for measured scope | Per-service table, current cgroup/disk checks; 24-hour expiry/full-disk/high-volume behavior NOT TESTED |
| Telemetry outage never blocks assignment | PASS, retained | Three prior real service-outage cases with one committed inbox row each; app/config hashes unchanged |
| Resumed complete thirteen-check execution / current worker control recovery | NOT TESTED to completion; BLOCKED | Docker stop and inspect hung; two passed, one blocked, ten not executed |

**Final recommendation: NO-GO for claiming completed T09 independent-audit validation in the current Docker environment.** The Grafana defect is corrected and demonstrated. An owner-approved Docker environment repair and an observability-only thirteen-case rerun remain necessary; unchanged backend/Docker/application-browser suites need not be repeated solely for this test fix. Restarting the shared Docker VM without owner approval could disrupt retained databases, including volatile test storage, so it was not attempted. No application functionality or future phase was rewritten.

## Bounded Docker reliability investigation (2026-11-10, 15:40-15:47 UTC)

### Preserved state and diagnostic method

The owner requested Docker diagnosis and recovery, not a new T09 implementation. Read AGENTS.md, the live open [Issue #9](https://github.com/chakirou18/final-project-AIzoomcamp-2026/issues/9), this document and `artifacts/t09-resume-blocked-run.json`. Branch remains `feature/t09-observability`, HEAD remains `fcc5bf7090d248fb667b4e26169f3bf76f24b151`, index empty. All existing tracked/untracked work was preserved. Before this documentation update, every file in `artifacts/t09-resume-source-manifest.json` still matched its recorded SHA256. No application, test, dependency or Compose source was changed in this investigation.

Existing Compose project is `fieldops-t09`. Container names use `fieldops-t09-<service>-1`: web, worker, db, prometheus, grafana, loki, alloy, otel-collector, jaeger, alertmanager, bootstrap and credentials. Initializers remain exited zero. No duplicate stack was launched. Docker Desktop reports 4.99.0 (245822), Engine 29.9.3, Linux/amd64 on WSL2 kernel 6.18.33.2.

Ignored diagnostic helper `artifacts/t09_docker_reliability.py` runs each Docker client with stdout/stderr directed to temporary files and a **ten-second command deadline**. On timeout it terminates only its own newly created CLI process tree, with bounded cleanup waits. This avoids the previous inherited-pipe problem where Compose descendants survived `subprocess.run(... capture_output=True, timeout=90)`. It never kills Desktop/backend/daemon/container processes. It is a diagnostic helper, not a replacement or a verified fix for the existing observability harness. Sandbox named-pipe/network denials were distinguished from runtime faults; required read-only commands were retried outside the sandbox with permission. Filtered host-log inspection omits credential-bearing lines; saved summaries contain only safe event fields and error-category counts.

Commands executed (the helper records exact Docker argument lists and UTC timings in individual JSON reports):

```powershell
git branch --show-current
git rev-parse HEAD
git status --short
git diff --cached --stat
gh issue view 9 --repo chakirou18/final-project-AIzoomcamp-2026 --json number,title,state,body
.venv/Scripts/python.exe artifacts/t09_docker_reliability.py version version --format '{{json .Server}}'
.venv/Scripts/python.exe artifacts/t09_docker_reliability.py baseline
.venv/Scripts/python.exe artifacts/t09_docker_reliability.py project-list ps -a --filter label=com.docker.compose.project=fieldops-t09 --format '{{.Names}} {{.Status}}'
.venv/Scripts/python.exe artifacts/t09_docker_reliability.py read-only-state
.venv/Scripts/python.exe artifacts/t09_docker_reliability.py file-logs
.venv/Scripts/python.exe artifacts/t09_docker_reliability.py data-preservation
.venv/Scripts/python.exe artifacts/t09_host_diagnostics.py
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m ruff format --check .
.venv/Scripts/python.exe artifacts/t09_docker_reliability.py compose-validation compose --profile observability --profile test --profile browser config --quiet
git diff --check
git status --short
```

Host inspection also enumerated Desktop/backend processes, available disk and recent host/VM Docker logs. Raw diagnostic logs were not copied into project reports. `artifacts/t09-reliability-host-summary.json` preserves selected safe lifecycle messages. Individual `t09-reliability-*.json` reports contain exit code, timeout, duration and sanitized output. No new pytest result file was fabricated.

### Diagnosis and uncertainty

| Observation | Actual result |
|---|---|
| General daemon responsiveness | `version` 0.11s; `info` 0.469s; project `ps` 0.094s, all successful |
| Database inspection | 0.062s; running; restart count zero; OOMKilled false |
| Worker direct inspection | Timed out at 10.266s; only its client tree was terminated |
| Worker Docker log request | Timed out at 10.234s; no output; only its client tree was terminated |
| Cached project listing | Worker still listed Up seven hours; other persistent T09 services healthy |
| Persisted heartbeat | Last seen `2026-11-10T15:10:20.808318Z`; unchanged through `15:47:05Z` |
| Pause / generation | Not paused; generation seven; effective/expiry null |
| Live / expired processing leases | Zero / zero |
| Web liveness, readiness, metrics | HTTP 200 for each; backlog zero; pause flag zero; heartbeat remains stale |

The worker's shared file is readable through the healthy web container even though Docker's worker log API hangs. Its final entry is **`worker_stopped` at 15:10:22.165942Z**. This entry follows database engine disposal and precedes telemetry provider shutdown in the source; it alone cannot prove Python process exit or identify the remaining blocked component.

VM Docker logs identify the affected container as `1039e4320049d6843aac8f120b77ad2f78b6942b8674431d03f8622aab494fca` and show:

| UTC timestamp | Docker runtime event |
|---|---|
| 15:10:22.085134762 | Compose stop request entered Docker API |
| 15:10:22.112861065 | Stopping restart-manager |
| 15:10:22.784772588 | Received task-delete event from containerd |
| 15:10:22.794884805 | Shim disconnected |
| 15:10:22.799068546 | Cleaning up after shim disconnected |
| 15:10:22.799135082 | Cleaning up dead shim |
| 15:10:32.156205106 | Container failed to exit within ten seconds of signal 15; Docker reported escalation |

Worker inspection requests appear later in the API log without matching completion in the inspected log range. This supports **a worker-specific Docker/containerd lifecycle reconciliation stall**: general API/database operations work, but worker state/control operations do not complete after runtime task deletion. A blocked daemon lock or runtime cleanup is a plausible mechanism, **not a proven root cause**. No goroutine dump or engine restart was taken. The historical Compose-child timeout defect contributes to the unbounded test wait but cannot alone explain independent direct Docker inspect/log timeouts. Docker's recorded automatic stop escalation was part of the earlier stop request; this investigation issued no stop, kill, start, restart or recreate operation.

Classification: **A (daemon globally unavailable): not supported. B (affected worker lifecycle/control unresponsive): supported, with inconsistent cached state. C (resource exhaustion): limited headroom is observed, but causation is unproven. D (harness synchronization): timeout containment defect is known; it is not the sole failure.** Reading additional ordinary worker state safely remains blocked, including its current PID, restart count and OOM flag; these must not be inferred from database/container status or cached `ps` output.

### Resource and data safety findings

Daemon info reports twelve logical CPUs, **7,978,242,048 bytes RAM**, **53 running and 239 stopped containers** across the shared engine. VM `/proc/meminfo` at 15:44:06Z reports **1,068,924KiB available**, 2,097,152KiB total swap and **zero free swap**. Memory-pressure avg10/avg60/avg300 are all 0.00%; CPU some-pressure avg10/avg60/avg300 are 0.82/0.91/1.10%. Web cgroup memory is 95,715,328 bytes. C: free storage at 15:47:14Z is **121,272,811,520 bytes**. These readings show low memory headroom/exhausted swap, not proof of an active OOM event; sampled host/VM log categories contained no OOM matches. The earlier per-service measured table and retention limits remain valid historical evidence; current per-worker CPU/memory cannot be reliably collected through its blocked control path. Another aggregate Docker stats attempt was avoided.

Read-only PostgreSQL snapshot at `2026-11-10T15:47:05.461862Z`: **134 outbox rows, all delivered; 134 inbox rows; zero duplicate outbox-ID groups**. The previously verified Grafana event `a64f0f4e-d700-4bf1-a9b5-1f1915dd0930` still has exactly **one** inbox notification. No new synthetic event was created while worker recovery was unverified. No SQL mutation, database deletion, volume operation, unrelated container action or global cleanup occurred. This verifies the observed persisted rows, not a full database integrity/backup audit.

### Recovery decision and exact test accounting

**Worker restored: NOT VERIFIED.** Its heartbeat does not advance, and the state/control API for that container remains blocked. A fresh synthetic delivery/recovery check is **NOT TESTED**. Repeating stop/start/inspect against this unresolved state would not establish safe recovery; no additional restoration mutation was attempted. The worker cannot be called running solely because cached `ps` says Up.

The owner explicitly requires restoration before executing the suite. Consequently **no new 13-case invocation was started** in this investigation: zero executed, **thirteen NOT EXECUTED due to the blocked recovery prerequisite**. There are no new test failures or skips to report. The latest actually invoked complete-suite attempt remains exactly:

| Passed | Failed | Blocked | Skipped | Not executed | Selected |
|---:|---:|---:|---:|---:|---:|
| 2 | 0 completed assertions | 1 | 0 | 10 | 13 |

The one blocked case is `test_retry_keeps_original_enqueue_parent_and_redacts_sql_error`; there is no completed JUnit for that interrupted invocation. This ledger is reused, not counted as a new run. The corrected focused Grafana case remains a valid retained **one pass / twelve deselected**, with real nineteen-span Jaeger JSON, both zero/one snapshot browser screenshots and exactly one matching inbox notification. Existing 403 backend, four lifecycle, eighteen application-browser and earlier observability evidence remains unchanged; reruns are not additional distinct tests. No fresh 13/13 success is claimed.

Ruff lint **PASS**; Ruff formatting **PASS (86 files)**; bounded all-relevant-profile Compose configuration **PASS**; `git diff --check` **PASS** (LF/CRLF notices only). Final working tree remains the existing uncommitted T09 work plus this validation update and ignored diagnostic evidence. Index remains empty; no commit/push was made.

### Updated Issue #9 acceptance matrix and handoff

| Live acceptance criterion | Verdict | Current evidence / limitation |
|---|---|---|
| Observability profile starts telemetry services | PASS, retained | All seven existing telemetry services report healthy; new startup not rerun |
| Full-stack command documented; real-agent verification deferred | PASS documentation; agent NOT TESTED | T11 remains explicitly deferred |
| Persisted W3C remote parent and same HTTP/outbox/worker/inbox trace | PASS, retained | Real trace JSON/parent assertions; worker recovery still blocked |
| Correlated structured logs; bounded metric/Loki labels | PASS, retained | Paired logs and label checks; sanitized new worker file inspection |
| Functional dashboard log-derived trace links | PASS, retained | Actual zero/one snapshot navigation to nineteen-span trace; one persisted notification reconfirmed |
| Impact metrics survive worker failure | PASS for current read-only observation | Metrics HTTP 200 with stale worker heartbeat and zero queue; prior DB-unavailable checks retained |
| Retention/resource limits measured | PASS for documented sample | Current VM/swap/disk readings added; sustained load, hard disk quotas and 24h expiry remain NOT TESTED |
| Telemetry failure never blocks assignment | PASS, retained | Prior real outage cases unchanged; fresh failure suite not run |
| Current worker restoration and complete 13-case validation | BLOCKED / NOT TESTED to completion | Lifecycle APIs stall; no safe service-only recovery established |

**NO-GO for independent T09 audit completion/publication.** Safest next option is an **owner-approved graceful Docker Desktop restart**, coordinated with the other shared workloads and preservation of any volatile/tmpfs test databases first. Restart may interrupt all 53 running containers and may discard volatile storage; named volumes must be retained. No restart, engine reset, system-process termination or cleanup is authorized or performed. Following approval/recovery, first verify the existing T09 worker's state, advancing heartbeat and one idempotent synthetic delivery, then run only the thirteen observability checks with bounded client handling and confirm final worker restoration. Any harness timeout correction needs its own focused validation; unchanged backend/browser suites do not need repetition solely for Docker repair. Await owner approval rather than retrying the blocked lifecycle commands.

## Restart preparation and host backups

The subsequent owner-authorized inventory/backup preparation is recorded in [T09 restart readiness](t09-restart-readiness.md). Nineteen running FieldOps PostgreSQL clusters, including all eight tmpfs clusters, were logically backed up to a protected Windows directory outside Git; all 429 enumerated non-template databases have verified dump sections. Readability, gzip integrity and recorded hashes passed; restoration is NOT TESTED. The container list identifies 44 running containers (43 FieldOps and one unrelated ingestor), while daemon info still reports 53, an unresolved accounting discrepancy. Current VM available memory is about 746MiB with no free swap; two historical audit databases alone use about 3.94GiB of cgroup memory. No worker inspection was repeated, no service/engine restart or process kill occurred, and no T09 tests ran. Immediate restart remains NO-GO until coordination, a write freeze/final backup refresh and a plan for preserving/restoring the volatile databases are agreed. Await explicit owner approval.

## Conditional release request: preflight still blocked (2026-11-10, 17:28 UTC)

The owner authorized publication only after gates A-H pass and explicitly withheld engine-wide restart, Docker force-kill, unapproved volatile-data loss, database/volume deletion and unrelated workload actions. This supersedes the older local-only permission wording in AGENTS/README, but does not permit publication while the infrastructure gate remains blocked. AGENTS.md, README and this document now reflect that conditional authorization.

Repository/branch/status, live Issue #9, relevant specification/architecture contracts, all tracked/untracked paths, Grafana test source and existing reports were inspected again. Published T08, local feature/t08-testing, HEAD and their merge base are all `fcc5bf7090d248fb667b4e26169f3bf76f24b151`; no earlier commit was changed. SHA256 comparison against `artifacts/t09-resume-source-manifest.json` found only this documentation file changed before the current authorization wording updates. Existing application, observability test, Compose and dependency sources still matched; backend/browser evidence is therefore retained rather than rerun.

One bounded native Docker API worker inspection was attempted at `17:28:43Z`; it timed out at **exactly four seconds**. Only that client's IO was cancelled/closed; no process was terminated. No worker log/stop/start/inspect retry, duplicate worker/stack, service mutation, new assignment or engine restart followed. General daemon/database/web requests returned promptly. Current safe snapshot:

- Container API still lists 44 running, while daemon summary reports 53; the accounting discrepancy remains unresolved. All seven T09 telemetry services, web and PostgreSQL report healthy in the existing list. This cached health list does not establish worker restoration or newly exercised ingestion.
- PostgreSQL time `17:28:49.090070Z`: latest heartbeat is still `15:10:20.808318Z`, over two hours old. Paused=false, generation seven, no processing leases. All 134 outbox rows remain delivered; inbox count 134; zero duplicate outbox groups; the prior Grafana event still has exactly one matching inbox row.
- Web liveness, readiness and metrics each return HTTP 200. Metrics report database_up=1, backlog=0, paused=0 and the stale heartbeat. Healthy API/database status is not worker health.
- Docker VM available memory is **764,788KiB (about 747MiB)**, free swap zero. Memory full-pressure avg10/avg60/avg300 is 0.14/0.10/0.41%. The last per-container/disk/CPU/RSS/retention measurements remain in the earlier sections/readiness report; no blocked stats scan or new load measurement was repeated.
- The unrelated `mlops_course_project_6` project remains listed active and was not touched. Historical tmpfs databases were not stopped. Existing host backups were reread: nineteen hashes match, all 429 database sections are covered, zero missing. Restoration remains NOT TESTED; later writes are not protected by those earlier snapshots.

Evidence: `artifacts/t09-conditional-release-preflight.json`, retained source manifest and rechecked `artifacts/t09-restart-backup-verification.json`. The failure locus remains the independently documented worker-specific Docker lifecycle reconciliation path. The precise daemon/runtime defect and causal role of memory pressure remain unproven; no claim of a proven Python/OTel shutdown bug is made. A new isolated worker would not resolve the existing container's blocked lifecycle required by the acceptance suite and would add resource pressure, so none was launched.

Current commands/outcomes:

| Command | Actual outcome |
|---|---|
| `gh issue view 9 --repo chakirou18/final-project-AIzoomcamp-2026 --json number,title,state,body` | PASS after sandbox network escalation; Issue remains open |
| `.venv/Scripts/python.exe artifacts/t09_restart_safety.py release-preflight` | Diagnostic completed; one worker inspection BLOCKED by four-second timeout; safe read-only probes returned |
| `.venv/Scripts/python.exe artifacts/t09_restart_safety.py verify-backups` | PASS: 19/19 hash matches, 429/429 covered sections |
| `.venv/Scripts/python.exe -m ruff check .` | PASS |
| `.venv/Scripts/python.exe -m ruff format --check .` | PASS: 87 files already formatted |
| `uv lock --check --offline` | PASS: 52 packages resolved; sandbox cache denial required approved escalation, not a lock defect |
| `git merge-base HEAD feature/t08-testing`, `git rev-parse feature/t08-testing` | PASS: unchanged published T08 SHA |
| Compose configuration | Retained PASS; Compose/application/lock source hashes unchanged; no new Compose lifecycle command issued |
| `git diff --check`, `git status --short`, `git diff --cached --name-only` | PASS whitespace; existing work preserved; index empty |

No pytest invocation was started after the unresolved recovery prerequisite. **Current requested suite: thirteen NOT EXECUTED.** Latest actually invoked complete-suite attempt stays **2 passed / 0 failed / 1 blocked / 0 skipped / 10 not executed**; it has no completed JUnit. The focused Grafana test stays **1 passed / 12 deselected**, with real nineteen-span JSON and both snapshot screenshots. Retained 403 backend (140 unit + 263 PostgreSQL), four Docker lifecycle and eighteen application Chromium cases are not fresh runs and are not counted twice. Earlier twelve observability passes plus the corrected focused case are retained evidence, not a completed thirteen-case release run.

### Release-gate requirement matrix

| Owner gate | Verdict | Evidence / blocker |
|---|---|---|
| A: All critical Issue #9 criteria | BLOCKED for release | Retained criterion evidence exists; required complete execution/current delivery cannot be established |
| B: Completed thirteen-case observability run | BLOCKED | Latest invoked run 2 PASS, 1 BLOCKED, 10 NOT EXECUTED; no 13/13 report |
| C: Worker restoration and normal delivery | BLOCKED | Four-second API timeout, frozen heartbeat; fresh synthetic delivery NOT TESTED |
| D: Real trace/log correlation | PASS, retained | Real nineteen-span JSON, exact enqueue parent, paired logs and one matching persisted inbox row |
| E: Telemetry outage transaction safety | PASS, retained | Prior real service/exporter-outage tests; implementation/configuration unchanged |
| F: No credentials/private data staged | PASS for current empty index | Nothing staged; backups outside Git/artifacts ignored. Final candidate/staged release review NOT TESTED because publication halted |
| G: Lint, format, lock, Compose, whitespace | PASS for available evidence | Fresh lint/format/offline lock/diff checks; unchanged Compose configuration's prior PASS retained |
| H: T08 baseline unchanged | PASS | HEAD/base/merge-base equal published T08 commit |

**Release decision: PARTIAL / NO-GO. Worker restored: NO verified restoration.** Publication phases were not entered: no staging, commit, push, T09 PR or Issue comment was created. Current local modifications remain available for owner review. No recommendation to begin T10 implementation is given while the critical T09 gate is blocked.

The smallest next decision is explicit owner approval for the **coordinated graceful Docker Desktop recovery procedure** in [restart readiness](t09-restart-readiness.md), including unrelated-workload coordination, a write freeze/final backup refresh and an agreed preservation/restoration plan for the 407 volatile databases. That approval has not been granted. If the owner prefers an environment repair that avoids engine restart, it must still make the existing worker lifecycle API responsive; the same blocked inspection will not be repeatedly retried. After approved repair, verify heartbeat and exactly-once synthetic delivery before running the thirteen checks. The known Compose-child timeout containment issue must be addressed/contained in a scoped, verified way before another potentially hanging suite; it has not been hidden by weakening assertions. Stop here pending the infrastructure decision.

## Conditional restart safety execution: blocked before restart

The owner subsequently authorized **one graceful Docker Desktop restart only after all safety conditions pass**. It has **not been attempted**. The detailed execution record is in [restart readiness](t09-restart-readiness.md#execution-of-conditional-safety-authorization-2026-11-10-1746-1804-utc).

New verified evidence improves data safety without changing application code:

- Existing T09 backup was actually restored into retained isolated database `fieldops_t09_restore_probe_20261110175220_test`: revision 0003_t07_controls, eleven tables, 134 outbox/134 inbox rows, zero duplicate mappings and one matching Grafana event. No existing database was overwritten/deleted. Other databases/global settings were not individually restore-tested.
- All nineteen PostgreSQL cluster backups were refreshed in protected host directory `C:\Users\chaki\FieldOps-backups\t09-final-safety-20261110T175300Z`. Nineteen integrity/hash checks and **430/430** database-section coverage pass, including the new retained probe. All **407 volatile databases** remain covered. The original backups remain untouched.
- A consistent read-only SQLite backup of the unrelated ingestor passes quick_check with two incidents/two decisions. Its running code matches source, observations/summary are stale and Prometheus is unavailable. A verified 123-source-file ZIP and hash manifest preserve FieldOps work outside Git.
- The first unrelated writer's normal `stop?t=-1` timed out after twelve seconds, with forced-kill escalation disabled. A supported SIGINT/KeyboardInterrupt was subsequently requested once after a handler check; shutdown still could not be confirmed, and a separate eight-second wait timed out. No further writer shutdowns, force-kill, engine restart or cleanup occurred. Unrelated workload state and any pending stop must be checked by its operator; it is not falsely reported restored.

This is a **new blocker before restart**, not a failed thirteen-case pytest result. The required safety condition for interrupting unrelated workloads remains BLOCKED, so recovery/testing/publication phases were not entered. All thirteen observability checks are NOT EXECUTED in this attempt. Latest actually invoked complete-suite result remains **2 passed / 0 failed / 1 blocked / 0 skipped / 10 not executed**. Retained focused Grafana PASS and historical regression/trace/metrics/logging evidence are unchanged. **Worker restored: NO verified restoration. Commit/PR/Issue comment: none.**

Current changes are authorization/evidence updates in AGENTS.md, README.md, this document and restart-readiness documentation, plus ignored local diagnostics. No domain, telemetry, Compose, lock or acceptance-test implementation was changed. Git branch/HEAD and earlier work remain preserved. Follow the latest safety matrix in restart readiness; the owner-approved single restart allowance is unused and must not bypass its shutdown prerequisite. Final verdict stays **PARTIAL / NO-GO**, with T10/T11 deferred.

## Read-only ingestor follow-up: runtime exit confirmed

The later read-only task resolved the unrelated ingestor's process question using **containerd task deletion at 18:02:37.951894989Z and shim disconnection/cleanup**, despite Docker's stale running status and timed-out inspection/exec. No additional signal or restart was issued. Live host SQLite passes quick_check and all three tables' logical hashes match the verified backup. Two host samples **87.032076 seconds apart** show no database/input metadata changes or journal/WAL sidecars. There are two saved incidents, two decisions and one historical stream marker. No current Compose dependent, documented review UI listener or upstream Prometheus listener was identified.

See the latest [read-only ingestor diagnosis](t09-restart-readiness.md#read-only-ingestor-diagnosis-2026-11-10-1812-1818-utc) for evidence and limits. **Ingestor process state: STOPPED by runtime evidence; no running process-local pending work remains.** Any transient poll data at the original interruption cannot be reconstructed. Persisted data is intact; additional interruption of this exited process is no longer the safety blocker. Docker engine metadata remains inconsistent and T09 worker recovery is still NOT VERIFIED.

The latest owner instruction holds Docker restart during this read-only task. Obtain execution go-ahead and complete the remaining FieldOps backup/write-freeze gates before spending the previously conditionally authorized single graceful restart. No engine restart, T09 test, staging, commit, push, PR or Issue comment occurred. Full T09 validation/publication remains PARTIAL / NO-GO; the prior actual suite ledger is unchanged.

## Reference implementations checked

- [OTel Python exporters](https://opentelemetry.io/docs/languages/python/exporters/) and [W3C propagation](https://opentelemetry.io/docs/languages/python/propagation/).
- [Jaeger 2.23 Badger configuration](https://github.com/jaegertracing/jaeger/blob/v2.23.0/cmd/jaeger/config-badger.yaml).
- [Grafana Loki derived-field provisioning](https://grafana.com/docs/grafana/latest/datasources/loki/configure/).
- [Alloy file log collection](https://grafana.com/docs/alloy/latest/reference/components/loki/loki.source.file/) and [Prometheus storage](https://prometheus.io/docs/prometheus/latest/storage/).


## Source recovery and fresh acceptance (2026-11-10, after owner Windows restart)

This section supersedes historical BLOCKED status above. The owner manually restarted Windows after the Docker/WSL lifecycle incident. A later accidental hard reset/clean removed uncommitted source; recovery restored the verified source ZIP. This task ran no destructive Git command, Docker Desktop restart, unrelated service operation, historical database restoration or volume deletion. CODEX_HOME was unchanged. The exact low-level original Docker reconciliation defect remains unproven; restored lifecycle operations now work.

### Source integrity and inventory

Before any edit, all **123 regular archive entries existed and matched SHA256 byte for byte** against `C:/Users/chaki/FieldOps-backups/t09-cutover-20261110T183600Z/fieldops-working-tree-pre-restart.zip`. The ZIP was preserved. Full entry inventory: ignored `artifacts/t09-recovery-integrity.json`. All application/test Python files parsed successfully. Running web and worker each matched all 28 recovered application Python files; both use image `sha256:50872f6b249703b5dcb66e0e28fe2929bf038c139354b7d795f1c71177ee662e`. No application/test/dependency change was required during recovery; only evidence/status documentation was updated.

Recovered T09 inventory (32 changed source/document paths relative to T08):

- Application: `fieldops/metrics.py`, `telemetry.py`, `logging.py`, `trace_context.py`, `main.py`, `database.py`, `bootstrap.py`, `settings.py`, `worker.py`, `services/interventions.py`.
- Runtime/dependencies: `docker-compose.yml`, `pyproject.toml`, `uv.lock`.
- Telemetry: `observability/Dockerfile.probe`, `prometheus.yml`, `alertmanager.yml`, `loki.yml`, `config.alloy`, `collector.yml`, `jaeger.yml`, and `observability/grafana/{dashboard.json,dashboards.yml,datasources.yml}`.
- Verification: `observability_tests/test_stack.py`, `tests/test_t09.py`, `test_support/telemetry_resources.py`.
- Documentation: `AGENTS.md`, `README.md`, `docs/architecture.md`, `docs/backlog.md`, `docs/t09-validation.md`, `docs/t09-restart-readiness.md`.

HEAD and local T08 branch started at `fcc5bf7090d248fb667b4e26169f3bf76f24b151`. Live PR #22 remains open/unmerged with that exact head. Existing migrations, domain/browser/lifecycle test assertions and T08 runner source remain unchanged. No files were recreated unnecessarily.

### Database and application recovery

Daemon Engine 29.9.3 responded normally. PostgreSQL and seven telemetry services were already healthy. Web/worker were exited 255 at `2026-11-10T19:51:49Z`, with OOMKilled false and no State.Error; this matches the restart interruption, with no evidence of an application crash defect. `docker compose start web worker` started existing application containers and reran their existing idempotent credential/bootstrap dependencies; healthy telemetry containers were not recreated. The acceptance suite subsequently stopped/started only the explicitly synthetic T09 services as its existing fault cases require.

Initial read-only PostgreSQL checks: migration `0003_t07_controls`; **134 delivered outbox rows / 134 inbox rows**, zero duplicate outbox groups, zero delivered events missing inbox rows. Persistent mounts remain `fieldops-t09_postgres_data` plus its matching credential volume. No tmpfs historical database is required: regression runners create their own isolated run-owned databases. No historical database was restored or populated data overwritten.

Post-suite snapshot at `20:57:06.177342Z`: **147 outbox / 147 inbox / zero undelivered / zero duplicates / zero missing inbox**. Worker instance `0b359f27-afdc-4a22-bb80-d3863af1ea9f` advanced from `20:53:54.811794Z` to `20:54:49.398336Z` and `20:57:04.900445Z`, unpaused. Fresh heartbeat, pause/resume and actual delivery evidence replace cached Docker-running state as the health proof. Final samples are saved in `artifacts/t09-recovered-database-samples.json`.

### Fresh observability evidence

Exact command: `$env:FIELDOPS_RUN_OBSERVABILITY_TESTS='1'; .venv/Scripts/python.exe -m pytest observability_tests -v -s -p no:cacheprovider --tb=short --junitxml=artifacts/t09-recovered-stack.xml` against the isolated project/ports/database documented above.

**13 PASSED / 0 FAILED / 0 BLOCKED / 0 SKIPPED / 0 NOT EXECUTED**, 166.54 seconds. Raw log: `artifacts/t09-recovered-stack.log`; JUnit: `artifacts/t09-recovered-stack.xml`; JSON/screenshots: `artifacts/t09-stack-c1bf9cb642c542b38a94bae7d88cfd8a/`. This is a new complete run, not reuse or addition of the historical two-pass blocked attempt. No assertion was changed, case excluded or tracing mocked.

| Fresh case | Result |
|---|---|
| Actual HTTP/outbox/worker/inbox trace and JSON logs | PASS |
| Two concurrent assignments, distinct contexts | PASS |
| Real first-insert failure/retry, original parent and SQL redaction | PASS |
| Malformed carrier independent-root delivery | PASS |
| Business transactions during Prometheus outage | PASS |
| Business transactions during Collector outage and recovered trace | PASS |
| Business transactions during Loki outage | PASS |
| Worker stopped and PostgreSQL unavailable metrics semantics | PASS |
| Advancing paused heartbeat and generation-checked resume | PASS |
| Stored bounded labels and Grafana trace backend proxy | PASS |
| Desktop dashboard, all thirteen panels | PASS |
| 375px dashboard, all thirteen panels | PASS |
| Browser metric to Loki to Jaeger for real backlog one and zero; Viewer write denied | PASS |

Concrete browser event `7a7908a7-f6e2-4dca-ab0c-07f4598d15e4` persisted carrier `00-dbfa1b37074bfbb96424fa37454abfc6-2347a75d046f6158-03`. Real Jaeger trace `dbfa1b37074bfbb96424fa37454abfc6` has **19 spans / two services**; delivery CHILD_OF equals persisted enqueue span `2347a75d046f6158`. Exactly one inbox `e1931cd7-92a3-418e-b213-f96277f65a9e` committed at `20:53:54.834059Z`, one attempt. Both process logs share trace/outbox IDs. `browser-link-snapshots.json` records actual Prometheus one/zero snapshot timestamps; both screenshots were produced by real navigation and the zero-backlog trace screenshot was visually inspected. Backend JSON includes complete span references, logs and committed mapping. Local UI: Grafana `http://127.0.0.1:13009/d/fieldops-operations`, Jaeger `http://127.0.0.1:16689`.

### Fresh regression and security review

- Unit command from reproduction: **140 passed / 267 deselected**, 2.30s; `artifacts/t09-recovered-unit.xml`. These 140 are included in backend, not additional distinct tests.
- `docker compose --profile test run --build --rm tests`, project `fieldops-t09-regression`, CIDRs `10.254.10.0/24` and `10.254.11.0/24`: **403 passed / four Docker deselected**, 101.13s. `artifacts/t08-backend-8e31f2c9210747f7b2150c41d1cf6c70/{pytest.xml,summary.json}` reports cleanup PASS, shutdown PASS, exit 0.
- `docker compose --profile browser run --build --rm browser-tests`, same regression project: **18 passed**, 133.58s. `artifacts/t08-browser-1a120674588d406b951c62342d79cf38/{pytest.xml,summary.json}` reports cleanup/shutdown PASS, exit 0, two run-owned DBs removed by the existing ownership guard. Docker build progress on stderr caused the PowerShell launcher to report status 1 despite both runners' successful exit-0 summaries; raw launcher logs are preserved and are not interpreted as failed pytest results.
- Fresh N03 benchmark: 1,000 records / five clients / 50 requests / ten excluded warmups; p50 **48.692ms**, p95 **59.855ms**, max **69.447ms**, zero errors, 101.502 requests/s. This is the telemetry-disabled regression harness, not sustained production capacity evidence.
- Fresh controlled browser incident held event `b0471b1b-a926-4717-b238-9756a776b161` for **61.132776s** before authorized resume and delivery at `20:58:48.755889Z`; no alert or model-agent behavior is claimed.
- Ruff lint PASS; format PASS (87 files); `uv lock --check` PASS (52 packages); all-profile Compose config PASS; Python syntax PASS; Git whitespace PASS.
- Static credential/private-key and runtime-extension scan: **32 audited changed paths, zero findings**. In-memory comparison of all four generated runtime credential values against **78 source/fresh evidence files** found zero matches; values were never printed or saved. Reports: `artifacts/t09-recovered-source-security.json`, `t09-recovered-credential-scan.json`.
- Fresh real sentinel-secret, SQL-error, malformed-context, metric/Loki label and Viewer write-denial assertions all PASS. No HAR, browser storage-state or trace ZIP was generated. Application logs use allowlisted fields; SQL parameters/request bodies/authorization/cookies are excluded. Metric labels remain route templates/method/status class; stored Loki labels remain service/environment/service_name.
- Runtime inspection confirms Grafana/Jaeger ports bind **127.0.0.1 only**, other telemetry services have no published ports, all seven are nonprivileged and none reports OOMKilled. Alloy has no Docker socket or app credential mount. Local anonymous Viewer/trace reading remains intentional demo access; production authentication/network isolation is deferred to authorized deployment.

Independent review was a separate manual source/config/evidence pass by the same engineer, not a delegated reviewer: transaction/lease assertions, bounded queues, redaction, label cardinality, network bindings and unchanged T08 boundaries were checked. No separate reviewer approval is implied.


Fresh Docker lifecycle command: `$env:FIELDOPS_RUN_CONTAINER_TESTS='1'; .venv/Scripts/python.exe -m pytest tests/test_container_lifecycle.py -v -s -p no:cacheprovider --junitxml=artifacts/t09-recovered-container.xml --tb=short`. **Four passed**, zero failures/errors/skips/deselections, **182.54s**; log `artifacts/t09-recovered-container.log`. Real 20-event delivery: all 20 visible, maximum HTTP-observed **4.140s**, maximum database latency **4.010s**, within the ten-second target. Restart/outage/recreation retained inbox exactly once; runtime credentials/cookie/CSRF did not leak. This test's teardown removes only its generated containers/network and preserves every named volume. Fresh distinct test total: **438 = 403 backend + four lifecycle + eighteen Chromium + thirteen observability**. Unit reruns and historical executions add zero to this total.


### Fresh resources and release gate

Resource command `.venv/Scripts/python.exe -m test_support.telemetry_resources` with the explicit observability opt-in passed. Report: `artifacts/t09-resources-1794344571016490200/resources.json`, log `artifacts/t09-recovered-resources.log`. Sample window **21:02:57.435986Z to 21:03:30.107006Z**: two assignment clients delivered **26 events**, with **95 Grafana-to-Prometheus queries** over at least 25 seconds. Docker reports 12 CPUs / 7.43GiB; Windows C: free space was 120,893,820,928 bytes during review.

| Service | Idle CPU % | Active CPU % | Active Docker stats MiB | Active PID1 RSS KiB | Initial data KiB | Growth KiB |
|---|---:|---:|---:|---:|---:|---:|
| prometheus | 0.64 | 0.59 | 34 | 97840 | 3004 | 8 |
| grafana | 1.64 | 3.85 | 461.1 | 230152 | 1736 | 0 |
| loki | 1.05 | 1.1 | 77.57 | 169352 | 1584 | 92 |
| alloy | 5.42 | 5.76 | 146 | 202248 | 28 | 0 |
| otel-collector | 0.27 | 0.32 | 44.68 | 213472 | 0 | 0 |
| jaeger | 1.37 | 2.19 | 63.74 | 135204 | 49564 | 956 |
| alertmanager | 0.0 | 0.0 | 12.11 | 36784 | 4 | 0 |

Active Docker-stats memory totals **839.20MiB** across seven telemetry services. Docker CLI memory excludes reclaimable cache on Linux; PID1 RSS and CLI memory are different accounting views, not additive measures. CPU snapshots are percent of one logical CPU. Existing caps total 2,432MiB. No OOMKilled flags were observed; all services are healthy after validation. Short-run growth does not prove a 24-hour filesystem quota or sustained peak capacity. Retention remains asynchronous (Prometheus 24h/256MB, Loki/Jaeger 24h, rotated logs); full-disk, 24-hour expiry, HA, public authentication, sustained high-volume capacity and non-Chromium browsers are **NOT TESTED**. Telemetry may be dropped beyond bounded retry/queue capacity; business transactions remain independent.

Final DB sample at **21:03:29.840214Z**: **173 outbox / 173 inbox / zero undelivered / zero duplicates / zero missing inbox**, migration unchanged. Same worker instance heartbeat advanced to **21:03:29.439728Z**, unpaused; web readiness and metrics both HTTP 200. Together with the 20-event lifecycle delivery gate and thirteen real observability cases this verifies restored processing, not merely container Up.

| Release / Issue #9 criterion | Fresh verdict / evidence |
|---|---|
| Source recovery complete | PASS: 123/123 SHA256, syntax, running image source matches |
| PostgreSQL/migration/data preservation | PASS: expected migration, named volumes, initial 134/134 and final 173/173, no duplicates/orphans |
| Web and advancing worker heartbeat | PASS: readiness 200, same instance advancing, actual delivery |
| Synthetic exactly-once-visible inbox delivery/pause/resume | PASS: full trace journey, real pause/resume and 20-event lifecycle checks |
| Seven telemetry services and Alertmanager base | PASS: healthy runtime/configuration; no T10 rules/receiver claimed |
| Full 13-case observability gate | PASS: 13 passed, zero failed/blocked/skipped/not executed |
| W3C remote parent, concurrent/retry/malformed paths | PASS: retrieved real Jaeger span JSON and paired process logs |
| Metrics, truthful empty/unavailable states and bounded labels | PASS: real worker/DB outages and storage label queries |
| Actual Grafana log-derived Jaeger navigation | PASS: desktop/375px panels and both real backlog snapshots |
| Telemetry failure isolation | PASS: Prometheus/Collector/Loki outages preserve business delivery |
| Resources/retention/security/quality | PASS for measured local scope; explicit limits above |
| Complete stack with real agent | DEFERRED TO T11; documented command only, no mock substituted |
| Audited staging and T08 parent preservation | PASS: exactly 32 allowlisted files, no runtime artifacts/credential signatures, cached whitespace check clean; T08 parent unchanged |

**T09 GO for conditional publication**; final index review passed. All prior failures/blockers remain recorded as historical evidence. **T10 technically ready for owner review; implementation is not authorized by this handoff.** PR must target `feature/t08-testing`, remain open/unmerged, reference Issue #9 and leave the Issue open. No production/public deployment or purchases occurred.


Publication preflight: all four fresh JUnit reports were parsed independently: 403 + 4 + 18 + 13 tests, zero failures/errors/skips. Index contains exactly the 32 inventoried T09 paths, with no artifacts, database/archive files or credential signatures; `git diff --cached --check` passes. Running T09 PostgreSQL/web and all seven telemetry services are healthy, worker remains active with verified fresh delivery/heartbeat. All-profile Compose, lock, Ruff and Git whitespace checks pass after documentation edits. The source ZIP and T08 branch remain unchanged. Owner's conditional publication authorization is now satisfied; publish one T09 commit and leave PR/Issue open for review.
