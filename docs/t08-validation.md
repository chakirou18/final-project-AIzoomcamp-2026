# T08 reproducible tests and N03 performance validation

Task: [Issue #8](https://github.com/chakirou18/final-project-AIzoomcamp-2026/issues/8). Branch `feature/t08-testing`, based on unchanged published T07 `96de71dc2cbd15e69c7d90f130c211be998172eb`. Owner authorization now permits T08 feature-branch publication only: one commit, non-force push, PR against T07 and Issue #8 progress comment. No merge, Issue closure, T09+ implementation, deployment, purchase, application-volume deletion or global pruning.

Independent audit (2026-11-10): **PASS after corrections - 403 distinct tests: 124 unit, 257 real PostgreSQL, four Docker lifecycle and 18 Chromium; zero final failures/errors/skips. Independent clean-source N03: p50 42.186 ms, p95 59.375 ms, maximum 63.113 ms, 0% errors. GO for owner-approved T08 publication. No commit or publication performed.** The independent audit section below supersedes the historical implementation counts.

Historical pre-audit implementation verdict: **PASS — 401 distinct passing tests: 122 unit, 257 real PostgreSQL, four Docker lifecycle and 18 Chromium. Zero final normal-suite failures/errors/skips. N03 clean-source p95 54.16 ms (<1 second). GO for independent T08 audit; publication is not authorized.** Historical failures and deliberate negative probes are listed separately below.

## Architecture and ownership

The two specified commands remain compatible:

```sh
docker compose --profile test run --build --rm tests
docker compose --profile browser run --build --rm browser-tests
```

Both use the committed uv lock and digest-pinned Python/PostgreSQL base images. Playwright installs its matching Chromium revision and system libraries in a separate cached dependency layer. No host Python/venv, copied environment settings or existing application fixtures are needed. Test-only PostgreSQL passwords are explicit public synthetic values on internal networks; no production credentials are used.

The profiles depend only on their respective healthy `test-db`/`browser-db`, not the application's credential initializer or data volumes. Each service has a separate internal network, no host ports, and 512MiB data tmpfs. Default test CIDRs are explicit and overridable because this host's automatic Docker address pools are exhausted. Separate Compose projects need separate free CIDRs; simultaneous runs in the same project share the service safely through unique database/run IDs.

The browser runner supervises real Uvicorn and worker subprocesses in its isolated runner namespace. It waits for real HTTP/database readiness and uses fresh migrated/seeded databases. Its test-only restart adapter signals its supervisor; existing SQL evidence probes execute read-only SQL against that run's database. This replaces Docker-CLI assumptions inside browser tests without mounting a Docker socket or adding application/runtime-agent controls. The four actual Docker lifecycle cases remain a separate opt-in host gate.

`test_support/database.py` registers generated UUID database names with a unique run ownership comment. Function finalizers remove case databases; session finalizers remove the run root/module database. Cleanup requires both the strict generated name and exact current-run marker. A tampered/unrelated marker is rejected, not deleted. A supervisor fallback queries only its marker after pytest exits, so failed probes can be cleaned without touching another run. SIGTERM/SIGINT stop children and clean owned databases; SIGKILL/daemon failure cannot guarantee finalization. Bounded tmpfs limits damage in that case; no application database/volume is a cleanup target.

## Coverage inventory

| Requirement / risk | Existing or added evidence |
|---|---|
| Create/edit/assign/reassign, no-op version check | T04 domain/HTTP matrices, T05 PostgreSQL adapters and four desktop/mobile JS/fallback journeys |
| Technician start/complete, required resolution | T04 transition matrix and T05 live manager/technician browser journey |
| Cancellation and history | T04 raw/HTTP timestamp assertions; new T08 mobile browser cancellation, reload, matching history and closed timestamp with JS on/off |
| Permissions, cross-technician, CSRF, invalid/expired sessions | T03–T07 direct HTTP negatives; historical reassignment inbox browser checks; new T08 unauthenticated direct URL denial |
| Optimistic concurrency / 409 | T04 simultaneous assignment tests; T05 actual two-page stale-edit browser conflict |
| Transactional history/outbox and rollback | T04 statement/COMMIT failure injection and authorization-lock races |
| Retry limit, stale lease, duplicate delivery, crashes | T06 real PostgreSQL concurrent workers, five-attempt exhaustion and pre/post-commit process crashes |
| Worker/database outage and restart, persistence | Four real Docker lifecycle cases, plus T06 connection termination/recovery tests |
| Persistent inbox/read scope | T06 SQL/HTTP uniqueness/read tests and T05 live inbox/mark-read workflows |
| Dashboard and pause/resume safety | T07 real counts/failed-oldest/empty-zero cases, lock barriers, CAS replay/rollback and one-minute Chromium recovery demo |
| Cleanup/isolation | New T08 generated-name rejection and live ownership-tamper protection; repeated/parallel runs and negative cleanup probes |
| N03 | Actual HTTP benchmark after browser suite: separate fresh database with exactly 1,000 synthetic jobs |
| N07 | Desktop/375px, associated labels, no overflow, real keyboard focus, JS enabled and disabled full-page forms |

No new business workflow was introduced. Existing tests were integrated rather than rewritten/duplicated. Intentional failure probes are explicit files outside normal discovery and are not counted as ordinary passing tests.

## Benchmark methodology

`test_support/performance.py` creates exactly 1,000 interventions through the existing domain service in a separate owned, migrated database and asserts the persisted count. It restarts the real API/worker on that database. Five independent clients each authenticate with their own cookie jar, issue one list and one detail warmup, then synchronize on a barrier. Authentication, seed time and ten warmups are excluded from measurement.

Each client performs ten sequential requests: five JSON list requests (25-item pages distributed across the 1,000 jobs) alternating with five JSON detail requests to known IDs. Total: **25 list + 25 detail = 50 measured requests**, closed-loop concurrency five. `perf_counter` spans HTTP open, complete response/JSON read and payload validation. List total must be 1,000 with 25 items; detail ID must match. Errors remain in the sample/error count; no slow samples are discarded. p50 is the median; p95 uses nearest rank (sorted sample 48 of 50); maximum is the slowest measured request. Duration is first measured start through last response validation; RPS is 50/duration. The gate requires 50 valid responses, zero errors and **p95 <1 second**.

Configuration: one Uvicorn process, SQLAlchemy pool five/overflow zero, PostgreSQL 17 with a two-second statement timeout and 512MiB tmpfs, one worker polling every two seconds with no assignment backlog. HTTP is loopback inside the Linux runner; PostgreSQL crosses its isolated Compose network. It excludes public proxy/TLS/WAN overhead and is a local N03 check, not a production capacity claim. Raw timing samples and environment metadata are written to `n03-performance.json`; host/Docker resources and observed results are recorded below after execution.

## Executions and failures observed so far

- Initial combined startup failed because Docker automatic address pools were exhausted; explicit overridable internal test/browser CIDRs fixed startup without pruning.
- First combined run: **372 passed, four deselected, zero failures/skips, 64.83s**, cleanup PASS, no fallback databases left. Run `2a67b4d6217847f0beabe572188bc10d`.
- Expanded combined run: **379 passed, four deselected, zero failures/skips, 77.15s**, cleanup PASS. Run `d2636b7fd82e4a898e7528575aaa89c7`.
- Unit selection: **122 passed, 261 deselected, zero failures/skips, 1.77s**. The deselections are real PostgreSQL plus the four separately executed Docker cases.
- Two simultaneous seven-case runs passed with distinct run IDs `127043076f41485cb46304153d41cad7` and `7edc47e2a5df40ec820bb0e3040a0cce` (0.82s/0.80s pytest time), both cleanup PASS. No artifact/database naming collision.
- Backend intentional failure probe: **one expected failure**, exit **1**, supervisor fallback removed exactly one owned database; run `554fa4ce45fb454da5fa30262f8d121f`. This verifies nonzero failure propagation and fallback, not an ordinary passing test.
- The first browser image failed to start the Playwright driver because `libatomic.so.1` was missing. Installing `libatomic1` before Playwright's system-dependency installer fixed the build.
- First browser execution: **15 passed, three failed, 117.85s**, exit 1 and cleanup PASS (one owned database removed). The existing HTMX test used string-form `wait_for_function`, which the locked Linux Chromium rejected under the application's CSP. It now supplies a function predicate; CSP was not weakened. Two new cancellation assertions incorrectly expected a `cancelled` event type; they now assert the published `transitioned` event plus exact status/closed-time changes. These failures were test-harness assumptions, not hidden application fixes. Benchmark was correctly not executed after the failed suite.
- Four Docker lifecycle tests: **four passed**, zero failures/skips/deselections, **119.13s**. Real stale heartbeat, retained pause during database outage, restart and exact delivery persistence passed. Normal-delivery regression benchmark: 20/20, max DB 1.949078s, max HTTP observed 2.031s, total 2.235s; one worker, two-second polling.

## Evidence and limitations

Every runner writes `artifacts/t08-<suite>-<run-id>/pytest.xml` and `summary.json`; browser runs also write redacted web/worker JSONL, screenshots, synthetic fault IDs/timestamps and N03 JSON. Password inputs are masked in failure screenshots. Raw traces, HAR, storage-state/cookie dumps and HTML forms containing CSRF values are not persisted. All artifacts are ignored and remain local.

Known boundaries: first builds need registry/Debian/Playwright network access; OS repository patch packages are not a bit-for-bit frozen snapshot. No screen-reader/full-WCAG or non-Chromium certification is implied. Docker lifecycle tests preserve their own synthetic persistence volumes for inspection and require a Docker-capable host; the socket-free combined runner intentionally deselects them. Hard daemon failure/SIGKILL may leave only its dedicated test-service databases until owner review; it never authorizes global cleanup. Earlier T07 retained test databases and application volumes are preserved.

## Interruption recovery and completion

The session resumed from the existing local T08 branch and worktree, without resetting or recreating the branch. AGENTS.md, the live Issue #8, specification/architecture and tracked/untracked changes were inspected. The last completed operation before interruption was the successful browser runner `057d4b4b28ee4c5e802de01bcbecefeb`: **18 passed in 120.703s**, N03 benchmark passed, exit zero, cleanup PASS with its two browser/benchmark databases removed. The clean-source backend run `f6dc88b597dc46fa9b78837b430ba5ac` had also passed **379 in 69.934s**, four deselected, cleanup PASS.

JUnit files, summary JSON and all 50 raw benchmark samples were recovered and checked. Recomputing median, nearest-rank p95 and maximum reproduced the recorded values. A SHA-256 manifest confirmed that the 106 exported source files matched the local worktree at resumption; valid backend/unit/Docker evidence was reused instead of rerunning full suites.

After resumption:

- Ran the remaining exact browser command from the already-created clean-source export, against a new browser service/database. All 18 cases and N03 passed.
- Ran the intentional browser failure probe. It returned nonzero and cleaned its database, but exposed a real diagnostics gap: the screenshot hook captured `browser.new_context()` contexts but missed implicit contexts created by `browser.new_page()`.
- Corrected only that screenshot bookkeeping hook, then reran the short failure probe. It saved an actual masked PNG before Playwright closed the page, returned exit 1 and removed exactly its one owned database. The PNG was opened and inspected: the operator credential input is fully covered by a mask.
- Verified completed-run database inventories, bounded tmpfs, source/artifact safety, lint, format, lock, Compose configuration and Git whitespace/status. Updated current-task authorization/status notes without changing application behavior or migrations.

The normal browser suite's application code, assertions, runner and benchmark did not change during recovery. Its clean-source execution predates only the final failure-screenshot bookkeeping correction; that isolated correction was verified by the targeted probe rather than another expensive normal-suite run. The original export and manifest were preserved as evidence, not overwritten.

## Exact execution commands and clean-source proof

Before interruption, commands used the isolated project `fieldops-t08`:

```powershell
docker compose --project-name fieldops-t08 --profile test run --build --rm tests
docker compose --project-name fieldops-t08 --profile browser run --build --rm browser-tests
docker compose --project-name fieldops-t08 --profile test run --build --rm tests python -m test_support.runner backend --failure-probe
# Invoked twice simultaneously; each selected seven real guard/percentile cases:
docker compose --project-name fieldops-t08 --profile test run --rm tests python -m test_support.runner backend --pytest-target tests/test_t08_support.py

.venv/Scripts/python.exe -m pytest -m "not integration and not container" -p no:cacheprovider --basetemp=artifacts/t08-unit --junitxml=artifacts/t08-unit.xml
$env:FIELDOPS_RUN_CONTAINER_TESTS='1'
.venv/Scripts/python.exe -m pytest tests/test_container_lifecycle.py -v -s -p no:cacheprovider --junitxml=artifacts/t08-container.xml --tb=short
```

To verify checkout independence while T08 remains uncommitted, a clean source export was created at `artifacts/t08-clean-source/` from Git-listed tracked and untracked source paths. It contains **106 source files and no `.git`, `.venv`, `.env` or prior `artifacts/`**. Hashes were saved in `artifacts/t08-clean-source-manifest.json`. This was a clean export of the unpublished working tree, not a claim that a remote T08 commit already exists. Docker build contexts exclude virtualenvs, credentials, caches and generated artifacts. The host virtualenv was used only to prepare/inspect evidence; neither required runner uses it.

Both required command lines were executed unchanged from that export. Environment overrides avoid collisions with retained projects on this particular host:

```powershell
# Working directory: artifacts/t08-clean-source
$env:COMPOSE_PROJECT_NAME='fieldops-t08-clean'
$env:FIELDOPS_TEST_SUBNET='10.252.0.0/24'
$env:FIELDOPS_BROWSER_SUBNET='10.252.1.0/24'
docker compose --profile test run --build --rm tests
docker compose --profile browser run --build --rm browser-tests
```

The backend command ran before interruption; the browser command completed after resumption. These do not start application services, mount existing application volumes, require host Python or need pre-existing seed data. A fresh healthy profile database and each run's unique migrated/seeded root are created automatically. Docker layer cache was available; this is checkout independence, not a claim of a new empty Docker host or a cache-disabled image rebuild. Earlier browser dependency installation was actually downloaded and executed, as recorded in the build failure/correction above.

Post-resumption negative probe commands:

```powershell
docker compose --project-name fieldops-t08 --profile browser run --rm browser-tests python -m test_support.runner browser --failure-probe
# After correcting implicit-page screenshot capture:
docker compose --project-name fieldops-t08 --profile browser run --build --rm browser-tests python -m test_support.runner browser --failure-probe
```

The first browser probe (`a34f35177efc4194805ab9e351ba7f1e`) intentionally failed once in 0.840s, exit 1, cleanup PASS, no screenshot. The corrected probe (`ee4471b4870340cfa53e1fed2d108069`) intentionally failed once in 1.05s, exit 1, cleanup PASS and one masked screenshot. These are repetitions of one explicit negative probe, excluded from normal distinct totals. Together with the backend probe they verify both required runners' failure propagation and cleanup.

## Pre-audit test accounting

| Gate | Passed | Failed/errors | Skipped | Deselected | Result |
|---|---:|---:|---:|---:|---|
| Host unit selection (recovered) | 122 | 0 | 0 | 261 | PASS; 257 PostgreSQL + four Docker cases executed by other gates |
| Combined backend (clean export) | 379 | 0 | 0 | 4 | PASS; 122 unit + 257 PostgreSQL, 69.934s |
| Docker lifecycle (recovered) | 4 | 0 | 0 | 0 | PASS, 119.127s |
| Chromium (clean export, resumed) | 18 | 0 | 0 | 0 | PASS, 118.58s |
| N03 benchmark (not a pytest case) | 50 valid HTTP responses | 0 | 0 | 0 | PASS; not added to test totals |

**Distinct tests: 401 = 122 unit + 257 PostgreSQL + four Docker + 18 Chromium.** Repeated combined, parallel seven-case, standalone unit and browser executions are not counted twice. All intended normal tests ran; none were silently skipped. Initial browser failures (15 passed/three failed) were corrected before the final normal run. Explicit negative probe failures are expected diagnostics checks and are not described as ordinary passing tests. Full WCAG/screen-reader certification, non-Chromium and hard SIGKILL/daemon-failure finalization remain **NOT TESTED**.

## N03 actual measurements

| Measurement | Recovered successful run | Resumed clean-source run |
|---|---:|---:|
| Persisted synthetic records | 1,000 | 1,000 |
| Concurrent independent clients | 5 | 5 |
| Measured requests | 50 | 50 |
| p50 | 34.440 ms | **42.765 ms** |
| p95 | 49.056 ms | **54.159 ms** |
| Maximum | 52.245 ms | **56.247 ms** |
| Error rate | 0/50 (0%) | **0/50 (0%)** |
| Requests/second | 140.753 | **116.419** |
| Measured duration | 0.355232s | **0.429484s** |
| p95 <1 second | PASS | **PASS** |

Recovered report: `artifacts/t08-browser-057d4b4b28ee4c5e802de01bcbecefeb/n03-performance.json`.

Clean-source report: `artifacts/t08-clean-source/artifacts/t08-browser-db8c38aff1804ea4ac3997d5b2708406/n03-performance.json`.

Both include all 50 raw timing/error samples, verified client/mix counts and the methodology above. Host conditions: Windows Docker Desktop/WSL2, **12 visible CPUs**, **7,978,242,048 bytes Docker RAM**; Linux `6.18.33.2-microsoft-standard-WSL2`, Python **3.12.16**, PostgreSQL **17**, Chromium **158.0.8127.18 / revision 1254** installed by the lockfile-selected Playwright. Earlier unrelated application/audit projects were retained; no global cleanup or claim of an otherwise empty host. No scoped performance correction was necessary because both benchmarks met the target. The short closed-loop sample demonstrates the specified N03 workload, not sustained throughput or a general production SLO.

## Cleanup, browser and security evidence

All completed normal and probe summaries report cleanup PASS. Read-only queries against `fieldops-t08` test/browser services and `fieldops-t08-clean` test/browser services returned **zero** databases whose ownership comment matched `fieldops-t08:%`. Test tmpfs returned to **62 MiB used / 512 MiB total**, approximately 451 MiB available, after repeated runs. Docker inspection showed no development/application data mounts on either profile's database. Application data/credential volume definitions remain unchanged. Historical T07 retained databases were not cleaned.

Verification queries/commands executed:

```powershell
docker compose --project-name fieldops-t08 exec -T test-db psql -U fieldops_test -d fieldops_test -At -c "SELECT count(*) FROM pg_database WHERE shobj_description(oid,'pg_database') LIKE 'fieldops-t08:%';"
docker compose --project-name fieldops-t08 exec -T browser-db psql -U fieldops_test -d fieldops_test -At -c "SELECT count(*) FROM pg_database WHERE shobj_description(oid,'pg_database') LIKE 'fieldops-t08:%';"
docker compose --project-name fieldops-t08-clean exec -T test-db psql -U fieldops_test -d fieldops_test -At -c "SELECT count(*) FROM pg_database WHERE shobj_description(oid,'pg_database') LIKE 'fieldops-t08:%';"
docker compose --project-name fieldops-t08-clean exec -T browser-db psql -U fieldops_test -d fieldops_test -At -c "SELECT count(*) FROM pg_database WHERE shobj_description(oid,'pg_database') LIKE 'fieldops-t08:%';"
docker compose --project-name fieldops-t08 exec -T test-db df -h /var/lib/postgresql/data
docker inspect fieldops-t08-test-db-1 --format '{{json .Mounts}}'
docker inspect fieldops-t08-browser-db-1 --format '{{json .Mounts}}'
```

Desktop completed-work, 375px dashboard with JavaScript disabled, new mobile pagination/cancellation and the masked failure screenshot were opened and visually inspected. Figures/cards stay within the viewport, keyboard focus is visible and synthetic content is readable. Normal browser assertions cover persisted state, inbox event identity, CSRF/role denial, history changes and full-page forms, rather than just screenshots/status codes.

Useful local paths:

- `artifacts/t08-clean-source/artifacts/t08-backend-f6dc88b597dc46fa9b78837b430ba5ac/{pytest.xml,summary.json}`.
- `artifacts/t08-clean-source/artifacts/t08-browser-db8c38aff1804ea4ac3997d5b2708406/{pytest.xml,summary.json,n03-performance.json}`.
- Under that browser run's `browser/artifacts/`: `t05-1440-js-True.png`, `t07-dashboard-375-js-False.png`, `t08-pagination-js-False.png` and real pause/recovery evidence.
- `artifacts/t08-browser-ee4471b4870340cfa53e1fed2d108069/browser/artifacts/failures/browser_tests_failure_probe_py__test_intentional_browser_failure_with_masked_operator_input-0-0.png`.

## Pre-audit acceptance and handoff

| Issue #8 acceptance requirement | Verdict | Evidence |
|---|---|---|
| Core browser lifecycle, cancellation, permissions, optimistic concurrency | PASS | 18 real Chromium cases plus T03–T07 direct PostgreSQL/HTTP regressions |
| Retries, worker recovery and persistence | PASS | Real PostgreSQL lease/crash/rollback tests and four Docker outage/restart/recreation cases |
| 1,000 jobs / five clients / 50 HTTP requests, p95 <1 second | PASS | Two complete raw-sample reports; resumed p95 54.159 ms, zero errors |
| Combined unit/integration command works from clean source | PASS | Exact command, exported tree without host env/venv/data, 379 tests passed |
| Browser command works from clean source | PASS | Exact command, isolated real API/worker/PostgreSQL, 18 tests plus N03 passed |
| Separate disposable DBs, readiness, artifacts, meaningful failure exit | PASS | 512MiB services, run ownership checks, parallel runs, nonzero probes and masked screenshot |
| Width, keyboard and no-HTMX/full-page forms | PASS | Desktop/375px and JavaScript-disabled cases; actual screenshot inspection |

Historical pre-audit handoff: GO for independent T08 audit. No business-service/model/migration change was needed. Changed files are the Docker/Compose runners, test-only `test_support/`, owned PostgreSQL fixtures in existing tests, browser diagnostics/adapters/cancellation coverage, T08 guard tests and current-task documentation. No commit or publication has been performed. Remaining risks are the documented host CIDR overrides, initial build network access/OS package drift, short local benchmark scope, and inability to finalize after SIGKILL/daemon failure; none justify deleting unrelated data or weakening tests.

Final quality checks after resumption:

```powershell
.venv/Scripts/ruff.exe check .
.venv/Scripts/ruff.exe format --check .
uv lock --check
docker compose --profile test --profile browser config --quiet
git diff --check
git status --short
git diff --cached --stat
git rev-parse HEAD
git merge-base HEAD feature/t07-dashboard-controls
```

Observed: Ruff PASS; **80 Python files** already formatted; lock consistency PASS (**38 packages**, unchanged lockfile); Compose profiles valid; whitespace PASS (only LF/CRLF conversion notices). All untracked source files also passed a separate whitespace check. A source scan of **106 tracked/untracked paths** found no sensitive runtime filenames, private-key/token patterns or tracked artifacts. The intentional screenshot was visually masked, and no raw cookie/session/HTML-state dump was generated. These checks do not claim an exhaustive production secret audit. Index is empty; the worktree contains only local T08 changes. HEAD and T07 merge base remain `96de71dc2cbd15e69c7d90f130c211be998172eb`.

New files: `test_support/{__init__,database,runner,managed,performance,failure_probe}.py`, `browser_tests/{conftest,failure_probe,test_t08_journeys}.py`, `tests/test_t08_support.py`, and this document. Modified files: `AGENTS.md`, `Dockerfile`, `README.md`, `docker-compose.yml`, `docs/{architecture,backlog}.md`, `tests/{conftest,test_audit,test_t03_postgresql,test_t04_review,test_t05_web,test_t06_postgresql}.py`, and `browser_tests/{test_t05_review,test_t07_dashboard}.py`.

## Independent audit — 2026-11-10

**Verdict: PASS after isolated corrections. GO for owner-approved T08 publication.** Repository/branch were confirmed as `chakirou18/final-project-AIzoomcamp-2026`, `feature/t08-testing`. HEAD, T07 branch and merge base remain `96de71dc2cbd15e69c7d90f130c211be998172eb`. The index is empty. No previous commit was changed; application Python, assets, models, migrations, dependency manifest and lockfile have no T08 diff. All 25 changed/new source paths belong to test infrastructure, coverage or its documentation. Live Issue #8 and dependency Issues #5/#6/#7 were read, together with AGENTS, specification, architecture and the existing evidence. No remote write was performed.

### Corrections and test-quality findings

1. **Browser order dependency:** each new cancellation/pagination case previously created only one intervention but expected a second page supplied by earlier tests. Each now creates its own second persisted intervention and asserts that page two contains a different record. Both JavaScript variants passed individually against separate fresh databases: run `1ad26e21cacf430ca4aaf531a5636182` (1.77s) and `4b75283312b14180a3095bc6cf12a971` (1.59s). Browser `--pytest-target` selection now supports such focused checks.
2. **Cleanup bypass:** an exception stopping a child process could skip database cleanup and `summary.json`. Shutdown now attempts every child; finalization independently attempts cleanup, writes shutdown/cleanup status and returns nonzero for either failure. Two new unit cases verify failure reporting. A separate real-PostgreSQL probe verified both shutdown failure with successful removal, and an unreachable cleanup connection with a retained database, reported failure, then successful removal using the restored connection. Only the probe's own marked database was removed.
3. Documentation now distinguishes historical implementation results from independent evidence, updates the local T08 backlog state and replaces obsolete proposed-only descriptions of the implemented runners.

Coverage review found substantive persisted-state assertions: complete HTTP transition matrix; failed-commit triggers and row counts; real PostgreSQL lock observations; three independent worker processes with disjoint claims and unique inbox mappings; stale fencing/five-attempt exhaustion; session/CSRF/cross-technician denial; exact resume replay and rollback. Mocks are used for policy and OS-error unit checks, with PostgreSQL/process/HTTP evidence for critical persistence behavior. The fixed new browser case no longer depends on earlier cases for pagination.

Some older tests share a module/session database and rely on fixture restoration or per-record assertions; browser cases run sequentially within a fresh runner database. This audit verifies concurrent **runners**, not pytest-xdist execution of every case. Bounded polling observes persisted state; the deliberate 61-second browser hold measures a real delayed-notification scenario. Tight lock deadlines and free-port/subnet selection can still be sensitive to a heavily loaded or concurrently changing Docker host.

### Independent commands and final accounting

A new export at `artifacts/t08-audit-source-final/` copied all **106 Git-listed tracked/untracked source files**, preserving the existing worktree. Its SHA-256 manifest is `artifacts/t08-audit-source-final-manifest.json`. Before execution it contained no `.git`, virtualenv, local `.env`, databases or prior artifacts; `.env.example` contains placeholders only. It is a clean export of unpublished source, not a remote T08 checkout. Only documentation changed afterward: every executed Python, Docker, Compose and dependency file still matches the manifest. Cached image layers were available; dependency installation remains `uv sync --frozen` and Chromium is selected by the locked Playwright version.

```powershell
# Original workspace: standalone unit and actual Docker gates.
.venv/Scripts/python.exe -m pytest -m "not integration and not container" -p no:cacheprovider --basetemp=artifacts/t08-audit-unit --junitxml=artifacts/t08-audit-unit.xml
$env:FIELDOPS_RUN_CONTAINER_TESTS='1'
.venv/Scripts/python.exe -m pytest tests/test_container_lifecycle.py -v -s -p no:cacheprovider --junitxml=artifacts/t08-audit-container.xml --tb=short

# Working directory: artifacts/t08-audit-source-final.
# Use the SAME project/configuration/subnet overrides for every command in this project.
$env:COMPOSE_PROJECT_NAME='fieldops-t08-audit'
$env:FIELDOPS_TEST_SUBNET='10.253.0.0/24'
$env:FIELDOPS_BROWSER_SUBNET='10.253.1.0/24'
docker compose --profile test run --build --rm tests
docker compose --profile browser run --build --rm browser-tests

# Two simultaneous invocations, each a distinct UUID-owned database/artifact directory:
docker compose --profile test run --rm tests python -m test_support.runner backend --pytest-target tests/test_t08_support.py

# Expected-negative probes, excluded from ordinary totals:
docker compose --profile test run --rm tests python -m test_support.runner backend --failure-probe
docker compose --profile browser run --rm browser-tests python -m test_support.runner browser --failure-probe
docker compose --profile test run --rm -e PYTHONPATH=/app tests python artifacts/t08-audit-finalizer-probe.py
```

Focused browser checks were executed from the original workspace:

```powershell
docker compose --project-name fieldops-t08 --profile browser run --build --rm browser-tests python -m test_support.runner browser --pytest-target '/app/browser_tests/test_t08_journeys.py::test_cancel_and_paginate_persisted_jobs_with_direct_session_denial[True]'
docker compose --project-name fieldops-t08 --profile browser run --rm browser-tests python -m test_support.runner browser --pytest-target '/app/browser_tests/test_t08_journeys.py::test_cancel_and_paginate_persisted_jobs_with_direct_session_denial[False]'
```

| Final gate | Passed | Failed | Errors | Skipped | Deselected | Evidence/time |
|---|---:|---:|---:|---:|---:|---|
| Standalone unit | 124 | 0 | 0 | 0 | 261 | `artifacts/t08-audit-unit.xml`, 2.150s |
| Combined clean-source | 381 | 0 | 0 | 0 | 4 | `t08-backend-73cfaa8c4f994ceb8c0fa99219f8bd2b`, 83.422s |
| Docker lifecycle | 4 | 0 | 0 | 0 | 0 | `artifacts/t08-audit-container.xml`, 126.378s |
| Chromium clean-source | 18 | 0 | 0 | 0 | 0 | `t08-browser-8cd7c03758af4a1bbd6b3f76653a26ed`, 122.909s |

**403 distinct passing tests = 124 unit + 257 real PostgreSQL + four Docker + 18 Chromium.** The 381 combined cases include the 124 unit cases; repeats and diagnostic probes are not added to the distinct total. Four Docker deselections are intentional because the container runner has no Docker socket; all four executed separately. No intended final normal test remains unexecuted or skipped.

Additional observed executions:

- Initial independent pre-correction backend: 379 passed/four deselected, 67.34s, cleanup PASS (`32e3d90f0de9468ebbcf78811ed51238`).
- Parallel nine-case runs: `3d6d8b00a0424b8dbe71de0d6eb1e5bc` and `c4caa12146e54530a0d4d2bd54c9a4ea`; nine passed each in 0.99s/0.87s, cleanup PASS, no collision.
- Backend negative probe `7bb0d85aba3041dda414544753e5019e`: one intentional failure, exit 1, cleanup PASS, one database removed. Browser negative probe `4ee87b672de1482a82e9bcabd46de1d7`: one intentional failure, exit 1, cleanup PASS, one database removed and an inspected masked PNG.
- Real finalizer probe `t08-audit-finalizer-7ee8e6b6ef2c4112af2e62fd458877e9`: shutdown failure recorded exit 1 and removed one database; cleanup connection failure recorded exit 1 and preserved its database until recovery removed it. Final matching database count zero. The diagnostic script exits zero only after verifying both expected failures and recovery.
- **Audit execution error, retained transparently:** a probe was mistakenly run under the audit project name from a different Compose source/network configuration. Compose stopped only the isolated test database while the combined suite was active. Run `e24e6c92f97d434eb6477ea4a5dd1cc2` ended with 350 passed, two failed, 77 setup/teardown errors, four deselected and cleanup FAIL. JUnit phase/error accounting is not a distinct-test total. This run is invalid acceptance evidence. The service was restored from the original export with `docker compose --profile test up -d --wait test-db`, and the exact combined command reran successfully as recorded above. No application resource was stopped or deleted. All concurrent invocations must use consistent project configuration; unique database IDs cannot protect a service deliberately reconfigured by Compose.
- Preparation failures: the first export safety guard rejected the placeholder `.env.example` (corrected to allow that template); the first standalone diagnostic script invocation lacked `PYTHONPATH=/app` and performed no database operations. Neither is represented as a passing suite. The sandbox initially denied uv's existing user cache; the authorized cache-access retry passed.

### Independent N03 measurement

Report: `artifacts/t08-audit-source-final/artifacts/t08-browser-8cd7c03758af4a1bbd6b3f76653a26ed/n03-performance.json`.

| Measurement | Observed |
|---|---:|
| Persisted jobs / independent clients / measured requests | 1,000 / 5 / 50 |
| Excluded warmup requests | 10 |
| Mix | 25 list + 25 detail |
| p50 | **42.186 ms** |
| p95, nearest rank 48/50 | **59.375 ms** |
| Maximum | **63.113 ms** |
| Errors | **0/50 (0%)** |
| Throughput | **111.151 requests/second** |
| Measured duration | **0.449839 seconds** |
| p95 <1 second | **PASS** |

All 50 raw samples were independently recomputed: ten per client, exactly 25 of each request kind, median, sorted sample 48, maximum, error count and elapsed-boundary throughput agree with the report. Exactly 1,000 rows are checked in PostgreSQL; all measured responses are actually read and validated against expected totals/IDs. No mocked HTTP response or seeded production data is used. The previously reported 42.765/54.159/56.247 ms values are supported by the older clean-export report but are not substituted for this audit's new measurement.

Host: Docker Desktop/WSL2, Docker Engine **29.9.3**, **12 CPUs**, **7,978,242,048 bytes RAM**; Linux kernel **6.18.33.2**, container Python **3.12.16**, PostgreSQL **17**, locked Chromium **158.0.8127.18/revision 1254**. One Uvicorn/worker, pool five/overflow zero, 512MiB PostgreSQL tmpfs, two-second polling and statement timeout, loopback HTTP/private-network PostgreSQL as described above. Retained unrelated projects remained present. The Docker and backend gates had finished before the principal benchmark; this is not a dedicated quiet-machine capacity test.

The two focused cancellation checks also triggered the runner's automatic benchmark (p95 51.344/47.194 ms, zero errors). A later focused visual probe triggered another benchmark (p95 97.545 ms, max 105.491 ms, zero errors). These additional successful measurements are retained, not averaged into or counted beyond the specified 50-request principal audit sample. No performance target was weakened.

### Isolation, failure recovery and security

Both profiles start only their healthy PostgreSQL dependency, migrate/seed run-owned databases, and run real processes without host Python or a Docker socket. SQL names require a generated UUID form and the exact run ownership comment before teardown. The tampered-marker integration case refuses deletion, verifies the database survives, then restores only its own marker and cleans it. Ordinary pytest failures were cleaned by the parent fallback; cleanup failure is visible/nonzero rather than silently reported successful. Simultaneous run IDs, data and artifacts are separate. Tmpfs bounds storage even after an uncatchable process/daemon failure; it does not guarantee recovery from every hardware or SQL-DDL interruption.

Final read-only inventory queries against both audit services returned **zero** databases marked `fieldops-t08:%`. Both have **512MiB tmpfs**, no application/credential volume mounts, and no published ports; usage returned to **62MiB / 512MiB**, approximately 451MiB free. The four Docker tests preserve their separate synthetic persistence volumes. Historical retained test databases and development/application volumes were not removed. No global cleanup was run.

```powershell
docker compose --project-name fieldops-t08-audit exec -T test-db psql -U fieldops_test -d fieldops_test -At -c "SELECT count(*) FROM pg_database WHERE shobj_description(oid,'pg_database') LIKE 'fieldops-t08:%';"
docker compose --project-name fieldops-t08-audit exec -T browser-db psql -U fieldops_test -d fieldops_test -At -c "SELECT count(*) FROM pg_database WHERE shobj_description(oid,'pg_database') LIKE 'fieldops-t08:%';"
docker compose --project-name fieldops-t08-audit exec -T browser-db df -h /var/lib/postgresql/data
docker inspect fieldops-t08-audit-test-db-1 fieldops-t08-audit-browser-db-1 --format '{{.Name}} tmpfs={{json .HostConfig.Tmpfs}} mounts={{json .Mounts}} ports={{json .HostConfig.PortBindings}}'
```

The browser recovery case preserved exact event identity: outbox `8c6a44ca-4ffd-48dd-a9ec-ded5657a3f7b`, created **06:17:21.270806 UTC**, held pending/attempts zero with fresh heartbeat and increasing age **0.039417 → 61.083789 seconds**. Generation-one authorized resume was recorded at **06:18:22.587085 UTC**; inbox delivery of that same event at **06:18:23.446082 UTC** (**0.858997 seconds** later). Replay returned the recorded action; backlog and empty age returned to zero. The PostgreSQL result is recorded in `browser/artifacts/t07-failure-evidence.json`. This is manually authorized recovery, not a T10 alert or autonomous T11 agent. The separate Docker delivery regression observed 20/20 notifications, maximum persisted latency 2.146636s and maximum HTTP-observed latency 2.203s, including restart/outage checks.

### Chromium, visual inspection and final gates

All 18 scenarios were reviewed and executed: four manager/technician journeys, four boundary/reassignment/stale-edit variants, HTMX storage/revocation, two empty/focus layouts, four dashboard variants, the real pause/restart/recovery and two cancellation/pagination variants. Desktop and 375px, JavaScript enabled/disabled, keyboard form submission/disclosure/focus, labels, errors, notification visibility and unauthorized URLs have actual assertions. API/SQL checks verify persisted status, history, inbox and audit effects.

Opened and inspected, under the main audit browser run's `browser/artifacts/`:

- `t05-1440-js-True.png`: completed manager view, real history and resolution.
- `t07-dashboard-375-js-False.png`: responsive metrics, worker state and visible keyboard focus.
- `t08-pagination-js-False.png`: mobile native page-two result and controls.
- `t05-audit-conflict-375-True.png`: visible stale-edit error, retained user input and reload action.

No static overflow/rendering defect was found in these inspected screens. The first dashboard PNG caught Bootstrap's focus color transition; an additional isolated Chromium probe captured settled styling with animations disabled: white text on `rgb(220,53,69)`, solid visible outline. Its inspected PNG is `t08-browser-ff6c601c61314426985ab4c65c1d8a4f/browser/artifacts/t08-dashboard-settled-focus.png`. This diagnostic probe is not added as a new normal test.

The intentional browser-failure PNG was also opened: `t08-browser-4ee87b672de1482a82e9bcabd46de1d7/browser/artifacts/failures/browser_tests_failure_probe_py__test_intentional_browser_failure_with_masked_operator_input-0-0.png`. The credential input is completely masked. Source and audit JSON/XML/JSONL scans found no private-key/token patterns, credential assignments, tracked runtime settings/database files or raw cookie/HAR/storage-state/HTML dumps. Screens contain synthetic data only. Test passwords are explicitly public, isolated values. Demo persona/operator authentication remains unsuitable for production. This is a scoped artifact inspection, not a universal secret-detection or full accessibility certification.

Final quality commands:

```powershell
.venv/Scripts/ruff.exe check .
.venv/Scripts/ruff.exe format --check .
uv lock --check
docker compose --profile test --profile browser config --quiet
git diff --check
git status --short --untracked-files=all
git diff --cached --stat
git rev-parse HEAD
git merge-base HEAD feature/t07-dashboard-controls
```

Observed: Ruff PASS, **80 Python files** formatted; lock PASS (**38 packages**, manifest/lock unchanged); Compose PASS; Git and all untracked whitespace PASS, apart from informational LF/CRLF conversion warnings. All 106 source paths were inspected/scanned; no staged files or runtime artifacts. Test results were cross-checked against JUnit and summary JSON, not just prior prose.

### Independent acceptance verdicts and limits

| Live Issue #8 criterion | Verdict | Independent evidence |
|---|---|---|
| Core browser lifecycle, cancellation, permissions, optimistic concurrency | PASS | 18 Chromium; real reload/API/history assertions and T03–T07 HTTP/PG negatives |
| Retry behavior and persistence | PASS | 257 PG + four Docker; leases, crash/commit rollback, restart/outage and inbox identity |
| 1,000 jobs / five clients / 50 requests, report p95 against <1 second | PASS | 50 real validated responses; p95 59.375ms; raw calculations verified |
| Exact combined command works from clean source | PASS | Independent 106-file export; 381 passed, four separately executed Docker deselections |
| Exact browser command works from clean source | PASS | Same export; 18 passed plus N03; no host venv or demo data |
| Separate disposable databases, readiness, artifacts, nonzero failure exits | PASS | Bounded internal services, owned cleanup/tamper test, simultaneous runners and actual negative probes |
| Width, keyboard and full-page/no-HTMX fallback | PASS | Desktop/375px JS-on/off and keyboard assertions; inspected actual screenshots |

**NOT TESTED:** every case under pytest-xdist, hard SIGKILL/daemon-failure finalization, a cache-disabled build on an otherwise empty Docker host, non-Chromium browsers, screen readers/full WCAG certification and sustained/public-network load. These are not claimed as passes. Remaining operational limits are explicit free CIDRs/consistent per-project overrides, 512MiB shared capacity during concurrent large suites, registry/OS-package availability and patch drift, rare interrupted CREATE/ownership-comment DDL, and short local benchmark scope. They do not justify global pruning or touching unrelated data.

No major architectural/security defect remains identified in this T08 scope. Stop for owner review: **no commit, push, merge, Issue closure, deployment or future-phase implementation was performed.**

## Publication preflight - 2026-11-10

The owner authorized publication after the independent audit. Pre-publication checks confirmed branch `feature/t08-testing` starts at unchanged published T07 `96de71dc2cbd15e69c7d90f130c211be998172eb`. The 106-file audit manifest still matches every executable, test and configuration file; only task-status documentation differs. JUnit reports confirm 124 unit, 257 PostgreSQL, four Docker and 18 Chromium cases (403 distinct, zero final failures/errors/skips). Both clean-source runner summaries report exit zero and cleanup PASS. All 50 benchmark samples were rechecked: p50 42.186ms, p95 59.375ms, maximum 63.113ms, zero errors, 111.151 requests/second. No expensive suite was rerun because its code and evidence are unchanged.

Only the 25 T08 source/documentation paths are publication candidates. Runtime credentials, local settings, databases, screenshots and generated reports remain excluded/ignored; previous synthetic artifact inspection and current source scans are recorded above. Development volume definitions and application code/migrations are unchanged. This publication performs no Docker mutation or cleanup. The commit uses the owner-specified message, with the final SHA and PR URL recorded in the public Issue #8 progress comment. Publication does not authorize merging, Issue closure or T09 implementation.
