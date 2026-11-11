# T10 independent audit

Publication authorization was granted by the owner on 2026-11-11 for the audited commit, normal push, one PR against feature/t09-observability and one Issue #10 progress comment. The historical authorization and working-tree statements below describe their validation sessions. Raw artifacts and retained databases remain local. The committed documents publish redacted measurements and results.


Scope is the local `feature/t10-alerting` working tree at T09 baseline `b76b6dbabb57215fcac06f93907c935b9fabb4a6`. The audit used the live acceptance text and its dependency, the project specification and architecture, current source, and previous evidence. The existing worktree and baseline were preserved. [Issue #10](https://github.com/chakirou18/final-project-AIzoomcamp-2026/issues/10), [Issue #9](https://github.com/chakirou18/final-project-AIzoomcamp-2026/issues/9), [prior validation](t10-validation.md)

## Findings

| Severity | Finding and reproduction | Correction and verification |
|---|---|---|
| MEDIUM | The timed test could accept a new receipt solely by alert name and status while separately finding a firing alert. It never compared the Alertmanager episode start to the persisted receipt. A mistaken receipt association could produce a false timing pass. | The test matches exact bounded labels, Alertmanager start time and receiver route. It checks the same Prometheus firing alert against its pending timestamp, requires one undelivered event and rejects a firing timestamp preceding outbox creation. The timed poll reads only receipts newer than its saved cursor. |
| MEDIUM | A webhook with a timezone-aware year-one timestamp that underflows UTC returned HTTP 500. An authenticated reader cursor greater than SQLite's signed 64-bit maximum also returned 500. | Normalize both webhook timestamps during validation and cap the cursor at SQLite's integer limit. Added three tests for the invalid inputs and maximum valid cursor. |
| LOW | The malformed-request probe left the SQLite file open when Python attempted to remove its temporary directory on Windows. Receipt writes also performed synchronous SQLite locking on the async request loop. | Close receiver connections explicitly and run write transactions in the threadpool. The timestamp for an inserted row is sampled after acquiring the writer lock. The API observes a commit before returning 202. |
| LOW | The alert test opt-in did not enforce the synthetic project and database naming guards already used by T09. | The fixture now rejects an unexpected project or database name before starting fault tests. |

There were no confirmed critical or high findings. A persistent receiver outage or exhausted receipt store can cause repeated Alertmanager delivery attempts while the alert remains active. Each HTTP request has a three-second timeout. The receiver has no retry loop, and repeats of accepted episodes cannot grow the receipt store. The 10,000-row cap is a local capacity limit. No finite lifetime limit for Alertmanager attempts during a persistent outage was demonstrated.

## Prior timing challenge

The previous 101.187s was monotonic from immediately before the assignment request to an authenticated read of the durable receipt. It includes the assignment and polling overhead. The persisted receiver timestamp is 99.206585s after the outbox creation timestamp and 100.216365s after the effective pause timestamp. Those UTC differences use wall clocks. The PostgreSQL `created_at` is an insert timestamp read after commit, rather than the exact commit instant. Recomputing the old evidence found a single active Alertmanager alert with exactly the persisted labels and firing start, and a Prometheus pending-to-firing interval of 29.999436s after timestamp precision conversion. The stored run supports the previous result despite the weaker original assertion. [Prior live evidence](../artifacts/t10-alerting-aa9ac70a0a4448288a60331969f37866/real-alert.json)

## Executed checks

```powershell
git status --short --branch
git rev-parse HEAD feature/t09-observability
gh issue view 10 --repo chakirou18/final-project-AIzoomcamp-2026
gh issue view 9 --repo chakirou18/final-project-AIzoomcamp-2026
. ./artifacts/t10-env.ps1
docker compose --profile observability up --build --no-deps --wait --wait-timeout 120 alert-receiver
docker compose --profile observability --profile test --profile browser config --quiet
docker compose --profile observability exec -T prometheus promtool check config /etc/prometheus/prometheus.yml
docker compose --profile observability exec -T prometheus promtool check rules /etc/prometheus/notification-rules.yml
docker compose --profile observability exec -T prometheus promtool test rules /etc/prometheus/notification-rules-tests.yml
docker compose --profile observability exec -T alertmanager amtool check-config /etc/alertmanager/alertmanager.yml
$p='artifacts/t10-audit-unit-'+[guid]::NewGuid()
.venv/Scripts/python.exe -m pytest tests -m 'not integration and not container' --basetemp $p -p no:cacheprovider --tb=short --junitxml=artifacts/t10-audit-unit.xml
$env:FIELDOPS_RUN_ALERTING_TESTS='1'
.venv/Scripts/python.exe -m pytest alerting_tests -v -s -p no:cacheprovider --tb=short --junitxml=artifacts/t10-audit-live.xml
$env:FIELDOPS_RUN_OBSERVABILITY_TESTS='1'
.venv/Scripts/python.exe -m pytest observability_tests -k 'not retry_keeps and not malformed_context and not worker_stop' -v -s -p no:cacheprovider --tb=short --junitxml=artifacts/t10-audit-t09.xml
powershell -NoProfile -File artifacts/t10-audit-integration.ps1
powershell -NoProfile -File artifacts/t10-audit-browser.ps1
$env:FIELDOPS_RUN_CONTAINER_TESTS='1'
$p='artifacts/t10-audit-lifecycle-'+[guid]::NewGuid()
.venv/Scripts/python.exe -m pytest tests/test_container_lifecycle.py -k 'startup_and_persistence or real_database_outage' --basetemp $p -v -p no:cacheprovider --tb=short --junitxml=artifacts/t10-audit-lifecycle.xml
$env:PYTHONPATH=(Get-Location).Path
.venv/Scripts/python.exe artifacts/t10-audit-db-alert.py
.venv/Scripts/python.exe artifacts/t10-audit-integrity.py
.venv/Scripts/python.exe artifacts/t10-security-probe.py artifacts/t10-alerting-9c41d9d5eabc4b2e957d1515c3006d16
.venv/Scripts/ruff.exe check .
.venv/Scripts/ruff.exe format --check .
$env:UV_CACHE_DIR=Join-Path $PWD 'artifacts/uv-cache-t10'
uv lock --check --offline
git diff --check
```

The initial Ruff format check flagged two wrapped conditions in the strengthened test. Running Ruff format on that file corrected them, and the final lint and format checks passed. The backend unit run passed 161 cases, including all 21 T10 unit cases. Pinned promtool validated four rules and passed 27 assertions in 12 groups. The lock and Compose, Prometheus, Alertmanager and Git whitespace checks passed.

## Fresh timing and receiver evidence

All times below are UTC on 2026-11-10. The paused outbox event was `a0c59480-31a5-4412-b02c-e0cc8c99f624`. The timed test used the existing synthetic stack and made no valid webhook POST. Its authenticated write probe in a separate case sent only malformed input and verified that the receipt set stayed unchanged.

| Event | UTC |
|---|---|
| Acknowledged gate effective | 22:30:39.719008 |
| Assignment request began | 22:30:41.085515 |
| Outbox created, read after commit | 22:30:41.142334 |
| Prometheus pending | 22:31:48.622564128 |
| Prometheus firing | 22:32:18.622000 |
| Alertmanager last update | 22:32:18.626000 |
| Durable firing receipt recorded | 22:32:23.630572 |
| Same event delivered after separate authorized resume | 22:32:26.732084 |
| Same alert episode resolved receipt | 22:32:33.631347 |

The durable receipt was observed at **103.797s monotonic**, **6.203s below the 110s limit**. The UTC differences were 102.488238s from outbox creation and 103.911564s from the effective pause. The final paused queue age was **102.611567s** with zero inbox rows and one pending event. Before the pause, the empty queue stayed quiet for **101.125s**. PostgreSQL recorded one inbox row and one attempt after authorized cleanup. [Timed evidence](../artifacts/t10-alerting-9c41d9d5eabc4b2e957d1515c3006d16/real-alert.json), [manual cleanup](../artifacts/t10-alerting-9c41d9d5eabc4b2e957d1515c3006d16/cleanup.json)

```json
{
  "id": 25,
  "status": "firing",
  "labels": {
    "alertname": "NotificationQueueDelayed",
    "environment": "local",
    "service": "fieldops-web",
    "severity": "warning"
  },
  "starts_at": "2026-11-10T22:32:18.622000+00:00",
  "received_at": "2026-11-10T22:32:23.630572+00:00"
}
```

## Acceptance matrix

| Criterion | Test and evidence | Verdict |
|---|---|---|
| Authorized pause acknowledged | Fresh heartbeat, HTTP acknowledgement, separate PostgreSQL gate read before assignment | PASS |
| Real intervention assignment persisted | Manager API returned updated version and PostgreSQL outbox/history mapped to the intended technician | PASS |
| Transactional outbox committed | Independent PostgreSQL read saw the pending event and matching history | PASS |
| No corresponding inbox notification for >60s | PostgreSQL and technician API absence during the pause, through 102.611567s of queue age | PASS |
| Real delay alert fired | Prometheus pending and firing evidence matched the configured 30s pending period | PASS |
| Authenticated labeled receiver within 110s | Alertmanager route and firing start matched receipt 25, observed at 103.797s | PASS |
| Empty queue stays quiet | 101.125s live observation and stale-age/zero-count rule test | PASS |
| Scrape failure | Real failed scrape alert received after 30.531s. A separate assignment delivered. | PASS |
| Missing application metrics | Real dropped series alert received after 29.266s. A separate assignment delivered. | PASS |
| Database unavailable | Graceful synthetic DB outage exposed DB-up=0 and omitted queue series. Receipt 31 arrived at 22:36:08.628682Z and was observed after 29.500s. A separate assignment delivered once after DB restart. [Evidence](../artifacts/t10-audit-db-alert.json) | PASS |
| Unauthorized fault controls denied | Live anonymous/wrong-role/wrong-key/CSRF checks and PostgreSQL session/role tests | PASS |
| Production fault controls denied | PostgreSQL-backed session with DEMO_MODE enabled and production environment. JSON and HTML refused the command, and the form was absent. | PASS |
| Bad webhook authentication rejected | Missing, invalid and read-scoped credentials rejected. No receipt was created. | PASS |
| Recovery claim scoped to manual cleanup | Authorized generation-checked resume, one matching inbox row, and separate resolved receipt | PASS |

## Fresh and retained coverage

| Suite | Fresh result | Scope and evidence |
|---|---:|---|
| Backend unit | 161 passed | Includes the 21 T10 unit cases. [JUnit](../artifacts/t10-audit-unit.xml) |
| Backend PostgreSQL integration | 263 passed | One database-deletion assertion deselected. The isolated launcher retained 115 databases in the dedicated `fieldops-t10-audit-pg` volume, about 1.4 GiB. [JUnit](../artifacts/t10-audit-integration.xml) |
| Chromium application | 18 passed | Full existing suite, including desktop/mobile and JS-disabled dashboard, authentication, and the browser pause scenario. The graceful restart affected only a test-runner child. The launcher retained both fixture databases and disabled forced process termination. [JUnit](../artifacts/t08-browser-e797d199b1b04ec39d33c3f1bfdeac49/pytest.xml) |
| Live T10 | 5 passed | Hardened episode matching, bad-auth, quiet queue and real scrape/missing-data coverage. [JUnit](../artifacts/t10-audit-live.xml) |
| T09 observability | 10 passed | Real trace/log correlation, dashboard-to-Jaeger navigation, label bounds and delivery through telemetry outages. Three worker-stop cases deselected. [JUnit](../artifacts/t10-audit-t09.xml) |
| Docker lifecycle | 2 passed | Startup, recreation persistence and real database outage in disposable scope. Two worker-stop cases deselected. [JUnit](../artifacts/t10-audit-lifecycle.xml) |
| Prometheus | 27 assertions passed | Twelve groups, four loaded rules. Reported separately from pytest totals. |

**459 distinct fresh pytest cases passed**, plus one supplemental live DB-alert probe. The full Chromium suite and 263 PostgreSQL cases extend the earlier focused coverage. The integration launcher ran the existing tests with only fixture teardown retention substituted. The browser launcher similarly substituted retention and used graceful-only subprocess shutdown. The cleanup-deletion case exercises the harness's `DROP DATABASE` behavior and was excluded to honor data preservation. The three T09 and two lifecycle cases with worker stops remain historical, as recorded in [T09 validation](t09-validation.md). These six exclusions do not block the T10 feature publication because they exercise unchanged behavior and the T10 live path keeps the worker running.

## Security review

Both pause routes enforce local DEMO_MODE, authenticated operator authority and CSRF. Session tests exercised expired and revoked sessions. The receiver has separate read and write bearer scopes, a bounded body and batch, a fixed label schema, an indexed replay key, and a capped receipt store. The outbox worker's business retries have a five-attempt cap. Replay concurrency, capacity rejection and atomic batch rollback passed. The webhook uses HTTP on the private Compose network, and public ingress and sustained outage behavior remain outside the audited deployment scope.

Four live credentials were absent from the 18 changed files, sampled stdout/stderr logs and nine fresh alert evidence JSON files. The T09 sentinel was also absent from the sampled logs and evidence. Docker inspection showed no published port, all Linux capabilities dropped, a read-only receiver root and UID/GID 10001. The receiver's only mounts were webhook credential, reader credential and receipt storage. [Resource and Docker sample](../artifacts/t10-audit-resources.log)

## Integrity and release verdict

At 22:36:58Z the health-checked services were healthy. The worker reported a fresh heartbeat and an unpaused gate. PostgreSQL contained 211 outbox rows and 211 inbox rows with zero undelivered events, missing inbox rows, duplicate inbox rows or recipient mismatches. Its migration revision was `0003_t07_controls`. Receiver SQLite `quick_check` returned `ok` with 32 receipts. The receiver used 44 MiB of its 128 MiB memory limit, 0.15% CPU and 28 KiB of receipt-directory space at the final sample. No receiver OOM termination was recorded. [Integrity](../artifacts/t10-audit-integrity.json), [resource sample](../artifacts/t10-audit-resources.log)

**GO for T10 feature publication after explicit owner approval.** All live Issue #10 acceptance criteria passed and no critical or high finding remains. The result applies to the private synthetic deployment and the measured timing conditions. Five worker-stop tests and one database-deletion test remain unexecuted in this audit. Persistent receiver outages, capacity exhaustion under sustained load and public deployment are outside the verified scope. The active synthetic worker was preserved. The separate integration database container was stopped gracefully and its audit volume retained. The T09 baseline and evidence remain unchanged, and all T10 changes are local and unstaged.
