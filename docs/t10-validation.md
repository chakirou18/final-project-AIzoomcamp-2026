# T10 alerting implementation and local validation

Publication authorization was granted by the owner on 2026-11-11 for the audited commit, normal push, one PR against feature/t09-observability and one Issue #10 progress comment. The historical authorization and working-tree statements below describe their validation sessions. Raw artifacts and retained databases remain local. The committed documents publish redacted measurements and results.


The subsequent [independent audit](t10-audit.md) records receiver hardening, stricter live episode correlation and fresh final-source evidence. This document retains the implementation-session results and timestamps.

Task: [Issue #10](https://github.com/chakirou18/final-project-AIzoomcamp-2026/issues/10). Branch `feature/t10-alerting`, exact validated T09 parent `b76b6dbabb57215fcac06f93907c935b9fabb4a6`. T09 PR #23 remains open/unmerged. Authorization covers implementation and local validation only: **no commit, push, PR, Issue comment, independent audit, merge or closure**. No T11 agent, public deployment or purchase.

The recovered working tree already contained the four rules, private receiver, Compose wiring, and T10 tests. The last completed run before the Codex CLI interruption was the five-case live suite, which passed in 308.89s. The preceding backend run passed 422 cases, including PostgreSQL integration. Both reports and all T09 evidence were preserved.

## Contract and architecture

The live Issue requires an acknowledged pause followed by a genuine assignment/outbox commit, notification absent from the recipient inbox for more than 60 seconds, and a queue-delay alert delivered to an authenticated labeled receiver within 110 seconds. Empty queue stays quiet; scrape/database/missing-signal rules fire; controls deny non-demo/nonoperator access. Killed-container remediation is excluded.

Reuse the existing synthetic `fieldops-t09` stack, PostgreSQL database `fieldops_t09_demo_test`, subnet `10.254.9.0/24`, web/Grafana/Jaeger ports 18009/13009/16689. No second monitoring stack is created. T09 source/evidence and backups remain intact. PostgreSQL/telemetry volumes are reused; only three new dedicated volumes are added for webhook credentials, reader credentials and receiver evidence. No application migration or dependency change is required.

Real assignment -> transactional PostgreSQL outbox -> paused delivery -> web-owned PostgreSQL snapshot metrics -> Prometheus pending/firing rule -> Alertmanager grouping -> authenticated private receiver -> durable test receipt. The receiver has **no application DB credentials, operator/recovery/session keys, Docker socket, host process control or remediation client**. Its service has no host port, runs UID 10001 with read-only root, dropped capabilities, no-new-privileges, 128MiB/0.5 CPU caps, 8MiB tmpfs and rotated Docker logs.

Receiver evidence uses SQLite solely as a separate append-only test sink (not as a substitute for PostgreSQL business/locking tests). WAL, full SQLite default synchronous durability, parameterized statements and a single short `BEGIN IMMEDIATE` protect a batch plus capacity check. The persistent evidence volume survives receiver replacement. At 10,000 receipts new writes fail closed with 507; storage failure returns 503 so Alertmanager can retry. There is no automatic data deletion. Operators must inspect capacity; indefinite/high-volume retention is not claimed.

## Alert definitions and timing

Rules: `observability/notification-rules.yml`. Existing T09 metrics retain their names/semantics. Aggregate alerts expose only **alertname, severity, service=fieldops-web, environment=local**: no event/user/trace/run IDs or instance labels. The local one-company/one-web-target assumption is explicit; a future multi-environment deployment needs environment-specific configuration, not this local receiver allowlist.

| Alert | Condition | Pending period | Severity |
|---|---|---:|---|
| NotificationQueueDelayed | max oldest undelivered age >60 AND undelivered count >0 AND DB-up=1 AND scrape-up=1 | 30s | warning |
| NotificationMetricsMissing | required queue count/age or DB availability series absent, with successful scrape; DB explicitly down is handled separately | 15s | critical |
| NotificationScrapeFailure | failed scrape (`up=0`) or target `up` absent | 15s | critical |
| NotificationDatabaseUnavailable | successful scrape but DB snapshot flag=0 | 15s | critical |

Scrape/evaluation/group interval **5s**, scrape timeout **4s**, Alertmanager **group_wait 5s**, repeat **1h**, webhook timeout **3s**, send_resolved enabled. Budget after assignment: >60s age + <=5s scrape alignment + <=5s evaluation alignment +30s pending +5s grouping + delivery/polling margin <=110s under healthy monitoring. This is a measured local acceptance deadline, not a guarantee during unavailable monitoring/network/resource exhaustion.

The timed test starts `time.monotonic()` **before the assignment HTTP request**, after pause acknowledgement. This is stricter than starting at committed outbox creation. It ends when the authorized inspection observes the durably stored firing receipt. UTC request start, DB `created_at`, Prometheus `activeAt`, Alertmanager state, receiver `received_at`, pause effective time and final delivery timestamp are retained. Polls every 0.5–1s inspect actual state; no timestamps or metric values are rewritten. Timeouts fail rather than extending the 110s deadline. A 240s auto-expiring pause bounds failed-test impact; `finally` performs an explicit generation-checked manual resume and verifies the same event exactly once.

## Receiver and security

`fieldops/alert_receiver.py` exposes private POST `/internal/alerts` (webhook Bearer only), GET `/internal/receipts?after_id=N&limit=100` (distinct read Bearer only), and a minimal storage readiness endpoint. Generated random keys are separate from all app credentials. Only the webhook volume is mounted into Alertmanager; only initializer/receiver have the reader volume. Keys never enter Git, Prometheus labels, traces or test artifacts. Authentication precedes request-body reading. No session cookie can grant receiver/control authority.

JSON body capped at 64KiB, one to twenty alerts, version/receiver/status/timestamps validated, exactly four allowlisted label keys/values. Unknown fields are denied; Alertmanager 0.35's bounded `routeLabels`/`notification_reason` envelope fields are supported explicitly. Annotations, external/generator URLs, route labels and notification reason are not persisted or executed. Schema diagnostics log only bounded error types/known schema paths, never values. Receipt uniqueness is canonical bounded labels + UTC startsAt + status; repeated firing retries do not create new evidence, and resolved is a separate state of the same episode. SQL/read/storage errors never echo credentials or payloads.

The T07 DB lock gate, CSRF, operator authentication, generation checks, idempotent recovery Bearer, rate limits and expiry apply. Both pause routes require `environment=local` and DEMO_MODE. The dashboard uses the same predicate to decide whether to show the HTML form. The recovered production guard covered only JSON. Resumption extended it to HTML and verified 404 responses for both routes with a real PostgreSQL-backed operator session and DEMO_MODE enabled in production settings. The dashboard returned 200 with the pause form absent. Chromium also confirmed the authorized operator sees the form in local demo mode.

## Detection versus recovery

1. Detection: Prometheus rule pending/firing is evidence of impact/missing monitoring.
2. Generation: the evaluated firing alert exists in Prometheus and Alertmanager.
3. Delivery: receiver commits a receipt and returns 202.
4. Acknowledgement: 202 acknowledges only durable transport receipt; there is **no human incident acknowledgement workflow** or incident record in T10.
5. Recovery: the test's separate authorized manual cleanup resumes the gate, then independently checks the exact inbox row and correlated trace. An Alertmanager resolved message is not proof of inbox delivery. No autonomous remediation or T11 success is claimed.

## Commands

Use consistent existing project overrides for every Compose command:

```powershell
$env:COMPOSE_PROJECT_NAME='fieldops-t09'
$env:FIELDOPS_SUBNET='10.254.9.0/24'
$env:FIELDOPS_PORT='18009'
$env:FIELDOPS_GRAFANA_PORT='13009'
$env:FIELDOPS_JAEGER_PORT='16689'
$env:POSTGRES_DB='fieldops_t09_demo_test'
# For a new environment, the single profile startup orders credential initialization/readiness.
docker compose --profile observability up --build --wait --wait-timeout 240
# Existing healthy stack: initialize only new keys/evidence, then update only changed services.
docker compose --profile observability up --build --no-deps --wait alert-credentials
docker compose --profile observability up --build --no-deps --wait alert-receiver prometheus alertmanager web worker
docker compose --profile observability exec -T prometheus promtool check config /etc/prometheus/prometheus.yml
docker compose --profile observability exec -T prometheus promtool test rules /etc/prometheus/notification-rules-tests.yml
docker compose --profile observability exec -T alertmanager amtool check-config /etc/alertmanager/alertmanager.yml
$env:FIELDOPS_RUN_ALERTING_TESTS='1'
.venv/Scripts/python.exe -m pytest alerting_tests -v -s -p no:cacheprovider --tb=short --junitxml=artifacts/t10-alerting-final.xml
.venv/Scripts/python.exe -m pytest tests/test_t10.py -m 'not integration' -p no:cacheprovider --junitxml=artifacts/t10-unit.xml
```

T10's live missing-signal tests temporarily **drop a real metric during collection** or configure a nonexistent scrape path. They never generate artificial app metrics or crash PostgreSQL. An assignment still delivers during both faults; `finally` restores the exact Prometheus configuration bytes and SIGHUP reloads only Prometheus. The DB-up=0 rule is evaluated by promtool; the unchanged T09 PostgreSQL-outage test provides real database-contract regression coverage. Killed-worker lifecycle cases are not rerun under the owner's current prohibition; previous T09 evidence remains separately labeled.

Backend runner uses `COMPOSE_PROJECT_NAME=fieldops-t09-regression`, `FIELDOPS_TEST_SUBNET=10.254.10.0/24`, `FIELDOPS_BROWSER_SUBNET=10.254.11.0/24`, then `docker compose --profile test run --build --rm tests`. Only its fresh run-owned test databases are finalized by the existing T08 guard. Historical/application databases are never restored/overwritten/deleted.

## Development failures and corrections

- First real attempt: **two passed / one failed**, 243.97s, `artifacts/t10-alerting-first.xml`. Queue alert reached the receiver but returned 422 because the strict schema omitted Alertmanager 0.35 `routeLabels` and `notification_reason`. No receipt was accepted within 110s. Cleanup resumed/delivered but the reused trace helper attempted an uncreated evidence directory. Fixed the actual envelope schema and routed trace evidence into the T10 directory; label restrictions and timing assertions were not relaxed.
- The second five-case attempt was disrupted by a receiver diagnostic rebuild while running: **two passed / three failed**, 100.67s, `artifacts/t10-alerting-complete.xml`. This was an implementation sequencing error; final acceptance runs use stable dependencies without concurrent mutation.
- Focused pre-fix missing-signal probe failed at its bounded 60s deadline with the same schema rejection: `artifacts/t10-missing-diagnostic.xml`. After the schema fix, **both live missing-metric/failed-scrape cases passed**, 72.87s, `artifacts/t10-missing-fixed.xml`; data under `artifacts/t10-alerting-bdd9022ccbfd4ade95df4e447f333ac5/`.
- First backend run: **421 passed / one failed / four Docker deselected**, 95.74s, `artifacts/t08-backend-9a5208d32be743c895c6d996c6863806/`. Extending the generic demo guard unintentionally denied the existing nonlocal secure-cookie login test. Narrowed the restriction to the pause endpoint; shared login semantics and old test assertions remain unchanged. Cleanup/shutdown passed even on this failing run. Final rerun is recorded below.

## Resumption and verification commands

The earlier five-case T10 pass is in [t10-alerting-final.xml](../artifacts/t10-alerting-final.xml). The resumed session first reproduced all five cases in 297.11s. In that run, a firing receipt was observed at **100.578s**, the oldest pending event was **98.996283s** at the final inbox check, and the same event produced one inbox row after manual cleanup. The live suite was run again against the rebuilt web service after the HTML authorization fix. The production probe initially used a runtime credential configuration with a fixture that submits its own synthetic operator credential and got 403 at login. The corrected probe and the unchanged PostgreSQL fixture setup both passed.

```powershell
. ./artifacts/t10-env.ps1
docker compose --profile observability up --build --no-deps --wait --wait-timeout 120 web
docker compose --profile observability --profile test --profile browser config --quiet
docker compose --profile observability exec -T prometheus promtool check config /etc/prometheus/prometheus.yml
docker compose --profile observability exec -T prometheus promtool check rules /etc/prometheus/notification-rules.yml
docker compose --profile observability exec -T prometheus promtool test rules /etc/prometheus/notification-rules-tests.yml
docker compose --profile observability exec -T alertmanager amtool check-config /etc/alertmanager/alertmanager.yml
$env:FIELDOPS_RUN_ALERTING_TESTS='1'
.venv/Scripts/python.exe -m pytest alerting_tests -v -s -p no:cacheprovider --tb=short --junitxml=artifacts/t10-post-fix-live.xml
$env:FIELDOPS_RUN_OBSERVABILITY_TESTS='1'
.venv/Scripts/python.exe -m pytest observability_tests -k 'not retry_keeps and not malformed_context and not worker_stop' -v -s -p no:cacheprovider --tb=short --junitxml=artifacts/t10-resumed-t09.xml
$p='artifacts/t10-unit-temp-'+[guid]::NewGuid()
.venv/Scripts/python.exe -m pytest tests/test_t10.py -m 'not integration' --basetemp $p -p no:cacheprovider --junitxml=artifacts/t10-resumed-unit-passed.xml
$p='artifacts/t10-post-fix-unit-temp-'+[guid]::NewGuid()
.venv/Scripts/python.exe -m pytest tests -m 'not integration and not container' --basetemp $p -p no:cacheprovider --tb=short --junitxml=artifacts/t10-post-fix-backend-unit.xml
powershell -NoProfile -File artifacts/t10-retained-postgres.ps1
$env:FIELDOPS_RUN_CONTAINER_TESTS='1'
$p='artifacts/t10-lifecycle-temp-'+[guid]::NewGuid()
.venv/Scripts/python.exe -m pytest tests/test_container_lifecycle.py -k 'startup_and_persistence or real_database_outage' --basetemp $p -v -p no:cacheprovider --tb=short --junitxml=artifacts/t10-resumed-lifecycle.xml
$env:PYTHONPATH=(Get-Location).Path
.venv/Scripts/python.exe artifacts/t10-browser-smoke.py
.venv/Scripts/ruff.exe check .
.venv/Scripts/ruff.exe format --check .
$env:UV_CACHE_DIR=Join-Path $PWD 'artifacts/uv-cache-t10'
uv lock --check --offline
git diff --check
```

The focused PostgreSQL launcher ran existing tests against `fieldops-t09-regression` with only the fixture cleanup callback replaced. The callback retained all nine test-created databases and did not change test setup or assertions. This kept the full runner's database deletion behavior outside the resumption. The first dedicated unit launch could not access the Windows pytest temp directory and reported 18 setup errors. A unique workspace `--basetemp` fixed the setup and all 18 cases passed.

| Suite | Status | Evidence and scope |
|---|---|---|
| Dedicated T10 unit | PASSED | 18 passed, one PostgreSQL case deselected. [JUnit](../artifacts/t10-resumed-unit-passed.xml) |
| Prometheus rules | PASSED | Four rules loaded. Twelve rule-test groups and 27 assertions passed, including threshold/pending, empty, missing, scrape, DB-down and clearing. |
| Real alert delivery | PASSED | Five passed on the rebuilt web service in 287.02s. [JUnit](../artifacts/t10-post-fix-live.xml) |
| Live database-unavailability alert | PASSED | One supplemental probe. Alert received after 33.171s, then a separate assignment delivered once after PostgreSQL restarted. [Evidence](../artifacts/t10-db-alert-live.json) |
| Backend unit regression | PASSED | 158 passed on final source. Includes the 18 dedicated T10 unit cases. [JUnit](../artifacts/t10-post-fix-backend-unit.xml) |
| Focused PostgreSQL integration | PASSED | Eight passed on final source, including production JSON/HTML denial, HTML CSRF, expired/revoked operator sessions, the acknowledged gate and pause/resume idempotency. [JUnit](../artifacts/t10-retained-postgres.xml) |
| Full backend/PostgreSQL rerun | NOT EXECUTED | Recovered T10 run passed 422 before the shared guard fix, including 264 integration cases and four Docker deselections. Its standard runner deletes owned fixtures. [Recovered JUnit](../artifacts/t08-backend-e814966b8e6e4b86b58bc9d92c4ad6a6/pytest.xml) |
| Docker lifecycle | PASSED | Two passed, covering startup/recreation persistence and actual DB outage/recovery in a disposable stack. Its volume was retained. [JUnit](../artifacts/t10-resumed-lifecycle.xml) |
| Docker lifecycle worker-stop cases | NOT EXECUTED | Two deselected under current scope. [Retained T09 evidence](t09-validation.md) |
| FieldOps Chromium | PASSED | One focused local operator login/dashboard smoke on final source. The full 18-case browser suite was not rerun. [Smoke](../artifacts/t10-resumed-browser.json) |
| T09 observability regression | PASSED | Ten passed, three worker-stop cases deselected, 70.13s. Includes Grafana desktop/mobile, both stored backlog snapshots through Grafana-to-Jaeger, trace/log correlation, label bounds, and business delivery through three telemetry outages. [JUnit](../artifacts/t10-resumed-t09.xml), [browser link evidence](../artifacts/t09-stack-6d655670e6cf4840aa0f03cb36bdbb71/browser-link-snapshots.json) |
| T09 worker-stop observability cases | NOT EXECUTED | Retry, malformed-context setup and combined worker/DB outage use real worker stops. [Retained T09 evidence](t09-validation.md) |

## Real alert on the rebuilt web service

The worker reported a fresh heartbeat before pause and continued reporting fresh heartbeats while paused. The operator received HTTP 200 with generation 13 and an effective timestamp. A subsequent PostgreSQL read confirmed the committed gate before the assignment began. The assignment committed outbox event `088322aa-f54e-4a66-b043-966cf6ae35ed` for the intended technician. PostgreSQL and the technician's authenticated API both showed the event's notification absent with zero delivery attempts. The final inbox check saw **99.877487s** of undelivered age. Before the pause, the empty queue stayed quiet for **101.812s**.

| Event | UTC, 2026-11-10 |
|---|---|
| Pause became effective, as returned in the acknowledgement | 22:16:58.412422 |
| Assignment HTTP request started | 22:16:59.314969 |
| Persisted outbox creation timestamp, read after commit | 22:16:59.422202 |
| Prometheus pending `activeAt` | 22:18:03.622564128 |
| Prometheus firing `starts_at` | 22:18:33.622000 |
| Alertmanager active record `updatedAt` | 22:18:33.625000 |
| Private receiver firing receipt | 22:18:38.628787 |
| Inbox delivery after separately authorized manual resume | 22:18:43.268984 |
| Receiver resolved receipt for the same episode | 22:18:48.630768 |

The monotonic measurement from immediately before the assignment HTTP request to observation of the persisted firing receipt was **101.187s**, **8.813s inside the 110s limit**. The receiver UTC timestamp was **99.206585s** after outbox creation and **100.216365s** after the pause became effective. UTC differences are supporting measurements. The acceptance test uses the monotonic clock and includes request and polling overhead.

The receiver retained the following fields from the authenticated delivery. Bearer values and raw annotations were excluded from the record.

```json
{
  "id": 17,
  "status": "firing",
  "labels": {
    "alertname": "NotificationQueueDelayed",
    "environment": "local",
    "service": "fieldops-web",
    "severity": "warning"
  },
  "starts_at": "2026-11-10T22:18:33.622000+00:00",
  "received_at": "2026-11-10T22:18:38.628787+00:00"
}
```

The test separately issued a generation-checked manual resume in cleanup. PostgreSQL recorded exactly one inbox row, `f6dd9b81-0c46-474d-b366-133dd9006223`, and one delivery attempt for the same event. Jaeger stored 19 spans across web and worker on trace `5b0d461f6482102e821b134e23baf060`. Its delivery span references the persisted enqueue span, and both process logs correlate with the event. [Timed run](../artifacts/t10-alerting-aa9ac70a0a4448288a60331969f37866/real-alert.json), [cleanup](../artifacts/t10-alerting-aa9ac70a0a4448288a60331969f37866/cleanup.json), [correlated trace and logs](../artifacts/t10-alerting-aa9ac70a0a4448288a60331969f37866/088322aa-f54e-4a66-b043-966cf6ae35ed.json).

## Acceptance matrix

| Criterion | Test | Evidence | Verdict |
|---|---|---|---|
| Healthy worker and acknowledged operator pause before assignment | Dashboard heartbeat, HTTP pause, PostgreSQL gate read | Generation 13 committed before assignment start | PASS |
| Real committed assignment and durable outbox, no recipient inbox notification for >60s | PostgreSQL recipient/history/outbox plus authenticated technician API | Same pending event and zero inbox rows at 99.877487s age | PASS |
| Queue alert reaches the authenticated labeled receiver within 110s | Real Prometheus firing, Alertmanager active dispatch, durable firing receipt | Receipt 17 observed after 101.187s monotonic | PASS |
| Empty queue stays quiet | Live sampling plus stale-age/zero-count rule case | 101.812s quiet before pause and matching promtool assertion | PASS |
| Missing application metrics and failed scrape trigger distinct alerts | Real metric drop and bad scrape path, plus rule tests | Missing metrics received at 22:19:18.674575Z, observed after 29.203s. Scrape failure received at 22:19:48.628380Z, observed after 25.078s. Business delivery succeeded in both cases. | PASS |
| DB-down signal has its own rule and reaches the receiver | Promtool DB-up=0 case, graceful synthetic DB outage and receiver observation | Receipt 23 at 22:23:08.674905Z, observed after 33.171s. Liveness stayed 200, readiness returned 503, and metrics omitted queue series with DB-up=0. | PASS |
| Bad webhook authentication is denied | Live missing, invalid and wrong-scope tokens for both APIs | Six 401 responses, valid-auth malformed payload 422, unchanged receipt set | PASS |
| Anonymous, technician, manager and invalid operator requests are denied | Live JSON tests and PostgreSQL HTML/JSON controls tests | Wrong roles, missing/invalid CSRF, expired/revoked operator and wrong resume keys denied | PASS |
| Fault simulation is limited to local demo mode | Real PostgreSQL-backed sessions with DEMO_MODE false and with production plus DEMO_MODE true | Both pause routes deny production, dashboard omits form, local browser renders form | PASS |
| Pause/resume idempotency | PostgreSQL repeated/stale pause, concurrent resume and changed replay binding | Deadline preserved, one effective resume, identical replay result | PASS |
| Independent delivery verification after explicit manual cleanup | Same outbox ID, inbox uniqueness and correlated trace | One delivery attempt and one inbox row after authorized resume | PASS |
| Threshold/for/empty/missing executable rule coverage | Pinned promtool | Twelve groups, 27 assertions | PASS |

The separate database probe ran with `$env:PYTHONPATH=(Get-Location).Path; .venv/Scripts/python.exe artifacts/t10-db-alert-live.py`. It gracefully stopped only the synthetic PostgreSQL service and restarted it in a `finally` block. The first attempt called a metrics helper that tried to log in during the outage and failed before checking alert delivery. Cleanup restored readiness. The corrected probe used its already authenticated client. After the successful run, the worker had a fresh heartbeat and an empty queue, and a new assignment produced one inbox row. [DB alert evidence](../artifacts/t10-db-alert-live.json)

## Security and resource checks

- Ruff lint, Ruff format check (91 Python files), offline dependency lock check (52 resolved packages), all-profile Compose config, Prometheus config and rule checks, Alertmanager config and `git diff --check` passed. Git emitted only working-copy line-ending conversion notices.
- Source review confirmed separate random file-backed bearer keys, capped payload and batch size, strict low-cardinality alert labels, bounded receipt reads and storage, no receiver control credentials, and no published receiver port. The private Docker network carries the local HTTP webhook. The receiver is a local test service with no public ingress or production TLS claim.
- `.venv/Scripts/python.exe artifacts/t10-security-probe.py artifacts/t10-alerting-aa9ac70a0a4448288a60331969f37866` confirmed four actual runtime bearer/control keys absent from all 17 changed files, captured web/worker/Alertmanager/receiver logs and nine evidence JSON files. The T09 synthetic sentinel was absent from those logs and evidence. The scan output contains no keys. [Security probe result](../artifacts/t10-security-probe.log)
- The receiver's fixed 10,000-row cap rejects writes with 507 at capacity. Tests verified no partial batch, duplicate suppression and no acknowledgement on storage failure. No sustained-load, disk-full or high-availability exercise was performed.

Final sample at **2026-11-10 22:23:39 UTC**, from `docker stats --no-stream`, `docker inspect` and `du -sk` inside the three services. All three were running without OOM termination or published ports. The receiver ran as UID/GID 10001 with a read-only root. [Raw sample](../artifacts/t10-resumed-resources.log)

| Service | CPU | Memory / limit | Data directory |
|---|---:|---:|---:|
| Alert receiver | 0.16% | 52.54 / 128 MiB | 228 KiB |
| Prometheus | 2.56% | 37.45 / 192 MiB | 4,272 KiB |
| Alertmanager | 0.00% | 27.42 / 64 MiB | 8 KiB |

## Handoff

**GO for independent T10 audit, pending owner authorization.** Local `HEAD` and `feature/t09-observability` both point to `b76b6dbabb57215fcac06f93907c935b9fabb4a6`. Read-only GitHub verification confirmed the same head on open PR #23. The T09 validation documents and observability tests have no working-tree diff from that baseline.

The recovered implementation added `fieldops/alert_receiver.py`, `observability/notification-rules.yml`, `observability/notification-rules-tests.yml`, `tests/test_t10.py`, `alerting_tests/test_alerting.py` and this validation record. T10 modifies `AGENTS.md`, `README.md`, `docker-compose.yml`, `docs/architecture.md`, `docs/backlog.md`, `fieldops/auth.py`, `fieldops/routes/controls.py`, `fieldops/web.py`, `fieldops/templates/dashboard.html`, `observability/alertmanager.yml` and `observability/prometheus.yml`. The resumption's application fix is confined to the shared pause guard and dashboard form visibility. The validation artifacts remain local under the ignored `artifacts/` directory.

The full backend and application browser suites, worker-stop cases, sustained load and hosted operation remain outside the fresh evidence. Existing volumes, application data and T09 evidence were preserved. All source changes remain local and unstaged.

References checked: [Alertmanager configuration/webhook contract](https://prometheus.io/docs/alerting/latest/configuration/), [current template.Data fields](https://github.com/prometheus/alertmanager/blob/main/template/template.go), [promtool rule test syntax](https://prometheus.io/docs/prometheus/latest/configuration/unit_testing_rules/). Actual pinned binary behavior is verified by integration, not assumed from current docs alone.
