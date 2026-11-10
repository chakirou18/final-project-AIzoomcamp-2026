# T07 dashboard and worker controls validation

> Publication authorization (2026-11-10): the owner authorized final checks, one feature-branch commit/push, a PR against T05 and an Issue #7 progress comment. Historical local-only/audit statements below describe earlier phases. No merge, Issue closure, T08 or later work or deployment is authorized.

> Independent audit (2026-11-10): **PASS — 392 distinct tests passed after corrections: 116 unit, 256 PostgreSQL, four Docker lifecycle and 16 Chromium. Zero final failures/errors/skips. GO for owner-authorized feature-branch publication.** The final audit section below supersedes the original implementation report and its 380-test total. Earlier results are retained as historical evidence, not reused as audit proof. No publication action was performed.

Task: [Issue #7](https://github.com/chakirou18/final-project-AIzoomcamp-2026/issues/7), F06/F09/F10. Local implementation/testing only on `feature/t07-dashboard-controls`, based on published T05 `6460870d68e81699d5bd4eee23b2715d6240b064`. No commit, push, merge, Issue closure, deployment or volume deletion was performed. T09 telemetry, T10 alerts and the T11 model-driven agent remain unimplemented.

Final implementation gate (2026-11-10): **PASS — 380 distinct tests passed, zero final failures or skips** (114 unit, 247 real PostgreSQL, 3 Docker lifecycle, 16 Chromium). All five live Issue #7 acceptance criteria have execution evidence. GO for independent audit/owner review before any separately authorized publication.

## Components and contracts

- `fieldops/services/controls.py` shares PostgreSQL control logic between JSON and HTML adapters. Dashboard counts use a repeatable-read snapshot and database time. All five intervention statuses and all four outbox states are represented. Undelivered means **pending + processing + failed**. Its oldest age uses the oldest creation timestamp, is clamped at zero, and equals zero for an empty queue. Age above 60 seconds displays a delivery-delay warning; this is not an alerting implementation.
- `0003_t07_controls` adds `worker_control`, `worker_heartbeats`, `worker_control_audit` and `worker_resume_actions`. Constraints bound pause duration to 600 seconds and validate generations/results. PostgreSQL triggers reject ordinary updates/deletes of audit and action records. The singleton gate is initialized by migration. No previous migration was edited.
- Each worker process has a new UUID and persists heartbeat/observed generation during polling, including while paused. Freshness is 15 seconds with the existing default two-second polling interval. Gate state and process freshness are separate: a paused worker can be fresh; an enabled gate can have no live worker. Recent heartbeats are observations, not an instantaneous process guarantee. API readiness remains a database check.
- Worker claims and deliveries hold a shared row lock on the control singleton until transaction completion. Pause acquires an exclusive lock, waits for those transactions, then commits the new generation, effective time, deadline and audit together. A successful acknowledgement therefore cannot precede an active delivery commit. Subsequent claims/deliveries see the closed gate. Nothing stops Docker or kills a process to activate pause.
- Pause requires explicit demo mode, an active operator session and CSRF. It requires the current expected generation, rejects an already paused generation, and permits at most one successful pause per ten seconds. Duration is 1–600 seconds. Authenticated command denials and successful changes are durably audited. Authentication/CSRF failures are rejected before mutation and appear in redacted HTTP logs; they are not represented as committed control actions.
- Expiration is reconciled under the exclusive gate on worker polling or an authorized dashboard/status read. This also works when the worker is absent without manufacturing a heartbeat. It is recorded as `auto_expired/system/externally_recovered`, never as agent success. Database unavailability delays reconciliation until access recovers.
- Resume uses a distinct internal bearer, expected-generation compare-and-set and a durable UUID idempotency key bound to the incident correlation UUID and expected generation. Identical replays return the recorded result, even after a newer pause. Rebinding a key is HTTP 409. Wrong generation/not paused are recorded unsuccessful results (409). State change, result and audit commit atomically. Both statement-time and deferred commit-time failures roll everything back.

`incident_id` is correlation metadata only in T07: no incident diagnosis, incident workflow or incident foreign key is implemented. Future T11 must bind these fixed actions to its authenticated incident lifecycle.

## Routes and authorization

| Route | Boundary |
|---|---|
| `GET /app/operator`, `POST /app/operator/login` | Demo operator-secret activation, existing signed/revocable session and login CSRF |
| `GET /app/dashboard`, `GET /api/v1/dashboard` | Active operator session; manager/technician access denied |
| `POST /app/worker/pause`, `POST /demo/worker/pause` | Demo mode, operator session, CSRF, expected generation and bounded duration |
| `GET /internal/worker/status` | Recovery bearer only |
| `POST /internal/worker/resume` | Recovery bearer only; fixed resume operation |

Operator secrets/cookies, unrelated webhook credentials and recovery bearer authority are not interchangeable. A bearer does not grant UI or pause access. `/internal/alerts` does not exist. Missing/invalid internal credentials receive 401. OpenAPI documents the resume 409 union: a recorded unsuccessful `ResumeResult` or a standard idempotency-conflict `ErrorResponse`. Existing application validation/error envelopes remain in use.

Compose generates distinct random operator/recovery keys in a separate `control_credentials` volume. Only the initializer and web service mount it; the worker has no control-key mount. Keys are loaded from files, never rendered into HTML. Configuration rejects weak recovery keys, an explicitly empty key and operator/recovery key reuse. No production credentials were introduced.

## Executed verification

Python 3.12.10, pytest 9.2.0; real PostgreSQL 17 in Docker Desktop on Windows, Chromium via Playwright. Tests use isolated, explicitly named test databases; migration rollback never targets the application database. Test databases and existing volumes are retained.

Commands executed from the repository root (PowerShell):

```powershell
# Backend unit + PostgreSQL regression gate inside the test profile:
docker compose --project-name fieldops-t07 --profile test run --build --rm tests

# Local unit selection:
.venv/Scripts/python.exe -m pytest -m "not integration and not container" -p no:cacheprovider --basetemp=artifacts/t07-unit-release

$env:FIELDOPS_RUN_CONTAINER_TESTS='1'
.venv/Scripts/python.exe -m pytest tests/test_container_lifecycle.py -v -s -p no:cacheprovider --junitxml=artifacts/t07-container.xml --tb=short

$env:FIELDOPS_PORT='18007'
$env:FIELDOPS_SUBNET='10.248.0.0/24'
docker compose --project-name fieldops-t07 up --build --wait

$env:FIELDOPS_BROWSER_URL='http://127.0.0.1:18007'
$env:FIELDOPS_BROWSER_PROJECT='fieldops-t07'
.venv/Scripts/python.exe -m pytest browser_tests -v -s -p no:cacheprovider --tb=short --junitxml=artifacts/t07-browser.xml

.venv/Scripts/ruff.exe check .
.venv/Scripts/ruff.exe format --check .
uv lock --check
docker compose --project-name fieldops-t07 config --quiet
git diff --check
git status --short
```

The final backend execution passed **361 tests, 3 deselected, zero failures/skips, 88.03 seconds**: 114 unit and 247 PostgreSQL. The three deselections are the separately executed opt-in Docker tests, not untested cases. There are 37 new T07 backend cases (13 unit, 24 PostgreSQL); the preceding backend regression cases remain present.

The final Docker run passed **3 tests, zero failures/skips/deselections, 119.34 seconds**. It verified Compose build/startup, persistence across restart/recreation, liveness during PostgreSQL outage, readiness/dashboard/internal-status unavailability during outage, recovery, worker restart and control-volume isolation. The existing delivery benchmark delivered 20/20: maximum database latency 3.506613 seconds, maximum HTTP-observed latency 3.625 seconds, total observed 4.031 seconds, one worker with two-second polling. This is a local regression measurement, not a production performance guarantee.

The final Chromium execution passed **16 tests, zero failures/skips/deselections, 133.16 seconds**: 11 T05 regressions and five T07 cases. The earlier complete browser execution passed 16/16 in 131.93 seconds; it is superseded by the final rebuild run, not counted twice.

The final standalone unit selection passed 114, deselected 250, zero failures/skips in 2.78 seconds. Those deselections are 247 PostgreSQL and three Docker cases executed by the other gates. Ruff lint passed; Ruff formatting passed for 68 Python files. `uv lock --check` resolved 38 packages without changes. Its first sandboxed invocation could not access the existing uv cache (Windows access denied); the approved retry passed. Compose configuration and whitespace checks passed; Git emitted only existing LF-to-CRLF conversion notices. No dependencies or lockfile were changed.

### PostgreSQL evidence and negative cases

- Correct counts include failed and processing rows; a failed oldest event still drives queue age. An empty queue reports exactly zero age. Fresh, stale and missing heartbeat cases are separate from API readiness.
- A deterministic barrier blocks an actual inbox INSERT after acquiring the shared gate; another connection observes pause waiting on a PostgreSQL lock. Pause cannot acknowledge until the delivery transaction is released and commits. Timestamp ordering is asserted.
- Concurrent identical resume requests produce one action record and one effect, with identical results. Replays across later generations cannot resume the new pause. Stale and repeated pause commands do not extend the deadline or advance generation and generate denied-action audit records.
- Six failure-injection cases exercise pause audit, resume action and resume audit insertion, both immediately and using deferred constraint triggers at COMMIT. Persisted gate/action/audit state remains unchanged after each failure.
- Terminating a real PostgreSQL connection during a control transaction rolls back state and audit; a following request succeeds. Real Docker database outage returns 503 for dashboard and authenticated status instead of invented healthy state, while liveness remains available.
- One-second pause deadlines test automatic expiry by worker polling and by status reconciliation with no heartbeat. Expiry creates one external-recovery audit. Invalid duration, wrong generation, reused keys, credential substitution and agent/operator privilege confusion are rejected.
- Migration down to `0002_t03_review`, upgrade to head and schema comparison pass in an isolated database; pre-existing intervention data survives. Audit/action update/delete attempts are rejected by PostgreSQL.
- Existing T06 concurrency, fencing, five-attempt exhaustion, transaction rollback, restart, crash-recovery and inbox recipient-scope tests still pass. Existing T02–T05 lifecycle, session/CSRF, historical-notification and UI regressions are retained.

### Corrections during implementation

An initial unit run had one failure: an explicitly empty `SecretStr` bypassed a truthiness-based configuration check. The check now tests presence explicitly and rejects the empty value; subsequent gates passed. Review also added expiry reconciliation without a live worker, documented both 409 response forms in OpenAPI, separated current control credentials from worker mounts, and corrected operator navigation. No final assertions were weakened to hide failures.

## Browser, responsive and accessibility evidence

Dashboard presentation is tested at 1440px and 375px with JavaScript enabled and disabled. Core navigation, login and pause are native full-page forms. Tests assert associated labels, visible content, snapshot/freshness messages, no horizontal overflow and no control credentials in HTML. Existing Chromium regressions cover manager/technician journeys, keyboard interaction, visible focus, CSRF/session denial, escaping, historical inbox scope and mobile layouts.

Local ignored artifacts, reproducible with the browser command above:

- `artifacts/t07-dashboard-1440-js-True.png` and `artifacts/t07-dashboard-1440-js-False.png`
- `artifacts/t07-dashboard-375-js-True.png` and `artifacts/t07-dashboard-375-js-False.png`
- `artifacts/t07-paused-delivery.png`, `artifacts/t07-recovered-delivery.png`
- `artifacts/t07-failure-evidence.json`, `artifacts/t07-browser.xml`, `artifacts/t07-container.xml`

Screenshots show operational data and synthetic identities, without credential values. Full WCAG certification, screen-reader testing and non-Chromium engines are NOT TESTED.

Actual screenshots were opened and inspected: desktop and 375px no-JavaScript layouts keep all cards/labels in the viewport; the paused image distinguishes a fresh heartbeat from the closed gate and shows the delayed backlog, and the recovered image shows zero backlog. A read-only scan of 94 tracked/untracked source paths found no sensitive filenames or credential patterns. The four current generated credential values were compared in memory against Compose logs and the three T07 JSON/XML reports: no matches; values were never printed.

### Real controlled failure/recovery demonstration

Final run used the real Compose application at `http://127.0.0.1:18007`, PostgreSQL, worker and separate Chromium operator/manager/technician sessions. The preflight normal assignment was delivered and both backlog count and age were zero. Native browser pause acknowledged generation **2** effective at **2026-11-10T02:12:47.178228Z**, with deadline **02:22:47.178228Z**. A separate restart reliability check changed worker instance from `a4a77f1b-5f15-4300-9cf0-aeb0977e8e99` to `d68c85c2-56ba-4a2c-9c32-420ce591b3b2` while preserving the pause generation/deadline. Restart was test-only; the pause endpoint itself never restarts a container.

- Affected synthetic intervention: `a0a099ea-3215-4a36-8310-c874d84ae4b6`.
- Outbox event: `433ba3db-d73c-472a-abe9-5425a1b629bc`, created **02:12:51.792925Z**; SQL confirmed pending, attempts zero. Recipient inbox had no matching notification.
- Initial age: **0.333292 seconds**. After an actual 61-second wait, dashboard backlog remained one and oldest age was **61.412556 seconds**, heartbeat fresh, gate paused, notification still absent. No row timestamps were rewritten.
- Authorized resume key `6a4b1b34-ce3c-40f8-98aa-143ee78cd617` committed `resumed/success` for generation 2 at **02:13:53.740627Z**. Immediate replay returned the identical stored result. SQL confirmed the persisted action.
- Inbox notification `0aca7813-7879-413f-802d-3d71dc529ab4` mapped to that exact event and intervention, delivered at **02:13:54.646163Z** (0.905536 seconds after recorded resume). Dashboard then showed undelivered zero and oldest age zero.

IDs/timestamps, heartbeat snapshots and the successful action are retained in the ignored JSON evidence file. This demonstrates the controlled fault and fixed authenticated recovery action; it does not demonstrate T10 alerting or autonomous T11 recovery.

Final read-only SQL inspection (`docker compose --project-name fieldops-t07 exec -T db psql -U fieldops -d fieldops -At -c ...`) executed:

```sql
SELECT 'revision', version_num FROM alembic_version;
SELECT 'control', generation::text, paused::text FROM worker_control;
SELECT 'audit', event_type, generation::text, outcome
FROM worker_control_audit WHERE generation=2 ORDER BY created_at;
SELECT 'delivery', o.status, count(n.id)::text
FROM notification_outbox o LEFT JOIN notifications n ON n.outbox_id=o.id
WHERE o.id='433ba3db-d73c-472a-abe9-5425a1b629bc' GROUP BY o.status;
```

Observed: revision `0003_t07_controls`; control `2/false`; audit `pause/2/effective` and `resume/2/resumed`; delivery `delivered/1`. Final Git whitespace check passed and status contained only the 25 local T07 paths below (16 modified, nine new), with no staged files.

## Change inventory

New files: `fieldops/control_schemas.py`, `fieldops/services/controls.py`, `fieldops/routes/controls.py`, `fieldops/templates/dashboard.html`, `fieldops/templates/operator.html`, `migrations/versions/0003_t07_controls.py`, `tests/test_t07.py`, `browser_tests/test_t07_dashboard.py` and this document.

Modified files: `.env.example`, `AGENTS.md`, `README.md`, `docker-compose.yml`, `docs/architecture.md`, `docs/backlog.md`, `fieldops/bootstrap.py`, `fieldops/contracts.py`, `fieldops/main.py`, `fieldops/models.py`, `fieldops/settings.py`, `fieldops/templates/base.html`, `fieldops/templates/login.html`, `fieldops/web.py`, `fieldops/worker.py`, `tests/test_container_lifecycle.py`. Existing commits remain unchanged; HEAD and merge base with T05 both equal the baseline SHA. The index remains empty and the working tree intentionally contains these local T07 changes.

## Acceptance criteria

| Issue #7 acceptance criterion | Result | Evidence |
|---|---|---|
| Dashboard includes pending, processing and failed undelivered rows and age | PASS | Real PostgreSQL aggregate assertions; browser backlog demo |
| Empty undelivered queue age equals zero | PASS | Real database empty case and post-resume HTTP assertion |
| Pause acknowledgement waits for active delivery completion | PASS | Shared/exclusive row-lock synchronization and committed timestamp ordering |
| Resume compare-and-set and recorded result are atomic | PASS | Concurrent requests, durable replay and six statement/COMMIT rollback cases |
| Operator, webhook and agent credentials are isolated | PASS | Direct HTTP negative tests, separate secrets, no worker control-volume mount |

## Remaining limitations and review boundary

- Authentication remains a synthetic demo. Production TLS, proxy/network isolation of internal routes, rotation, least-privilege database roles and hardened account login are not implemented or certified. Existing local application processes retain database-owner privileges; append-only triggers are not protection against a malicious owner.
- Every worker must run the new gate-aware binary. Mixed old/new worker deployments are not certified; perform a coordinated migration/restart. A two-second database statement timeout may deny acknowledgement for an unusually long transaction; it must never be treated as an effective pause.
- Heartbeat freshness has a 15-second grace period; old instance rows remain for evidence, so recently stopped instances may briefly count as fresh. Expiration is reconciled when PostgreSQL becomes available and a worker/read occurs, not by a real-time external watchdog.
- Claims committed just before pause may retain processing leases. Resume/expiry follows existing fenced lease and five-attempt behavior; attempts are never reset. Failed rows remain visible and are not automatically replayed.
- The bearer has only the fixed status/resume capability, but T11 incident existence, eligibility and agent decision permissions are future work. T07 correlation UUIDs do not prove an eligible incident.
- Earlier local credential-volume development files were retained rather than deleted. Current control keys use the new volume; obsolete files are not current control authority. Existing database/session credential mounts are still a local-demo trust boundary.
- No Grafana/OTel stack, alert webhook, model-driven action, arbitrary shell command, Docker socket control, incident diagnosis or production deployment was added.

Publication remains unauthorized. Final GO/NO-GO applies to readiness for owner review and a subsequent independent audit, not permission to publish.

## Independent T07 audit — 2026-11-10

Scope: fresh code/schema/security review and actual execution requested by the owner, without commit/push/publication. Live Issue #7 was fetched through the GitHub connector; its five acceptance criteria and required tests match the table above. `origin` is `https://github.com/chakirou18/final-project-AIzoomcamp-2026.git`; branch is `feature/t07-dashboard-controls`. HEAD and merge base with T05 remain `6460870d68e81699d5bd4eee23b2715d6240b064`. All tracked diffs and untracked T07 files were inspected; no unrelated changes were identified. No earlier commits/migrations were rewritten.

### Findings and corrections

1. **Test capacity/reproducibility limitation:** the first audit run against the retained `fieldops-t07` test service ended with **310 passed, 51 setup errors, three deselected, zero assertion failures/skips** in 58.25 seconds. PostgreSQL logged `No space left on device` while creating isolated databases; `df -h /var/lib/postgresql/data` showed its 3.8 GiB tmpfs at 100%. Fixtures retain a new database per case, so repeated full runs eventually exhaust that service. No data/volumes were deleted or reset. A fresh Compose project (`fieldops-t07-audit`, subnet `10.249.0.0/24`) restored test isolation/capacity. README now explicitly documents a fresh project/subnet for repeated audits. This limitation remains; the failed initial run is not hidden or counted as a pass.
2. **Minor configuration defect corrected:** `Settings.validate_control_credentials` treated an explicitly empty inline secret as absent when a file was also configured. It silently selected the file, contradicting the documented one-source rule. It now rejects any simultaneous inline/file source, including the empty inline value. Two unit cases cover operator and recovery sources. This is a configuration ambiguity correction, not evidence that invalid credentials could authenticate.
3. **Audit coverage strengthened:** seven PostgreSQL cases in `tests/test_t07_review.py` cover concurrent distinct resume keys (one success, one durable `not_paused`), wrong-generation HTTP 409 replay, expired/revoked operator denial through both HTML and JSON, HTML CSRF/unexpected-field denial, and actual UPDATE rejection on existing audit/action rows. Existing DELETE rejection, deferred-COMMIT rollback, shared-lock synchronization, role denial and migration tests remain intact.
4. **Real process coverage added:** a fourth Docker test stops the isolated worker and waits for actual heartbeat expiry without rewriting timestamps; verifies pause generation/deadline survive a real PostgreSQL outage; restarts the worker and observes a new fresh instance with the same paused state; then performs authorized resume. The browser presentation cases now traverse the real Tab order, expand the pause disclosure with Space and verify the focused button has a visible outline, with JavaScript on and off.
5. **Minor generation validation defect reproduced and corrected:** a direct authenticated HTTP request with `expected_generation=2**63` returned 500 because PostgreSQL could not store the oversized integer in the durable resume action. No successful action was recorded, but this was the wrong error classification. Pause/resume generation contracts now cap input at PostgreSQL INTEGER maximum `2147483647`. Two additional real PostgreSQL/HTTP cases assert 422 and no control/action/audit writes. A direct probe against the rebuilt application independently confirmed 422 with `validation_error`.

No significant application authorization, transactional or concurrency defect was identified. No extensive architectural change or future-phase implementation was made. This audit reused existing fixtures but independently inspected their assertions and database effects; it did not rely on reported test totals.

### Commands and observed audit results

```powershell
# Initial retained-project run: 310 passed, 51 PostgreSQL setup errors, 3 deselected.
docker compose --project-name fieldops-t07 --profile test run --build --rm tests
docker compose --project-name fieldops-t07 logs --tail 12 test-db
docker system df
docker compose --project-name fieldops-t07 exec -T test-db df -h /var/lib/postgresql/data

# Fresh isolated run, then final rerun after the credential-source correction:
$env:FIELDOPS_SUBNET='10.249.0.0/24'
docker compose --project-name fieldops-t07-audit --profile test run --build --rm tests

.venv/Scripts/python.exe -m pytest -m "not integration and not container" -p no:cacheprovider --basetemp=artifacts/t07-audit-unit-final --junitxml=artifacts/t07-audit-unit-final.xml

$env:FIELDOPS_RUN_CONTAINER_TESTS='1'
.venv/Scripts/python.exe -m pytest tests/test_container_lifecycle.py -v -s -p no:cacheprovider --junitxml=artifacts/t07-audit-container.xml --tb=short

$env:FIELDOPS_PORT='18017'
$env:FIELDOPS_SUBNET='10.249.0.0/24'
docker compose --project-name fieldops-t07-audit up --build --wait
$env:FIELDOPS_BROWSER_URL='http://127.0.0.1:18017'
$env:FIELDOPS_BROWSER_PROJECT='fieldops-t07-audit'
.venv/Scripts/python.exe -m pytest browser_tests -v -s -p no:cacheprovider --tb=short --junitxml=artifacts/t07-audit-browser.xml

.venv/Scripts/ruff.exe check .
.venv/Scripts/ruff.exe format --check .
uv lock --check
docker compose --project-name fieldops-t07-audit config --quiet
git diff --check
git status --short
```

The first fresh backend run passed **368**, deselected four, in **65.88 seconds**. After the two added unit cases and configuration correction, the next backend gate passed **370**, deselected four, in **66.56 seconds**. After correcting the independently reproduced generation boundary error, the final full backend gate passed **372**, deselected **four**, in **67.47 seconds**: **116 unit + 256 PostgreSQL**, zero final failures/errors/skips. The standalone unit selection before the last two PostgreSQL cases passed **116**, deselected **258** (then 254 PostgreSQL + four Docker), in **1.55 seconds**; these repeat executions are not added to the distinct total.

Ruff lint passed and all **69 Python files** passed formatting. Lock verification resolved **38 packages** without modification. The source correction does not change dependencies.

The Docker lifecycle suite passed **four**, zero failures/errors/skips/deselections, in **120.79 seconds**. Its new actual process-death test took 22.315 seconds; the stale heartbeat was `2026-11-10T02:26:20.057783Z`, restarted instance `1847de01-3fc0-4a4e-a182-9389aa2ad74d`, pause generation 1 retained through database outage and restart. Actual elapsed time, not a rewritten heartbeat timestamp, produced stale state. API readiness remained 200 after worker stop while PostgreSQL was available. Its benchmark delivered 20/20 with one worker, two-second polling: maximum database latency **1.941593 seconds**, maximum HTTP-observed latency **2.016 seconds**, total observed **2.219 seconds**.

All **16 Chromium scenarios** passed in **117.35 seconds**, zero failures/skips/deselections. This includes the 11 prior T05 journeys and four enhanced T07 keyboard/presentation variants plus the delayed-delivery demonstration. The first audit recovery event was `9a598e5b-3fab-45ee-ac8a-b78a5802ceeb`, delayed age **61.353481 seconds**, delivered at **2026-11-10T02:30:46.492347Z**. These artifacts were preserved in `artifacts/t07-audit-first-recovery/`; original implementation artifacts were preserved in `artifacts/t07-implementation-snapshot/`. Following the generation-bound correction, the application was rebuilt and the five T07 browser cases were repeated using:

```powershell
$env:FIELDOPS_BROWSER_URL='http://127.0.0.1:18017'
$env:FIELDOPS_BROWSER_PROJECT='fieldops-t07-audit'
.venv/Scripts/python.exe -m pytest browser_tests/test_t07_dashboard.py -v -s -p no:cacheprovider --tb=short --junitxml=artifacts/t07-audit-browser-final.xml
```

The repeated five cases are already included in the 16 distinct browser cases and must not be counted twice. Docker reports **12 CPUs and 7,978,242,048 bytes RAM** available to its Linux environment on Windows Docker Desktop. No production load or non-Chromium browser certification is implied.

### Database and security review conclusions

The real PostgreSQL suite revalidated counts for each intervention state, every outbox state, failed-oldest age and empty zero age. Dashboard snapshots use `REPEATABLE READ` and database time; manager/technician HTTP reads receive 403. Heartbeat missing/stale/fresh values are independent of readiness and the pause flag. Status reads can reconcile expiry but cannot manufacture heartbeats.

Claims/deliveries acquire the shared singleton row lock before outbox access and retain it through transaction completion. Pause acquires the exclusive lock, samples effective time after acquisition and acknowledges only after commit. The synchronized actual-INSERT test observes a PostgreSQL lock waiter and verifies pause remains blocked until delivery commits. Once paused, both new claims and previously claimed deliveries are denied. Five-attempt/lease-token behavior remains unchanged.

Resume locks the same gate, checks the durable key/body binding and commits compare-and-set, result and audit together. Identical keys are replayed exactly; distinct simultaneous keys cannot both succeed. Wrong generation receives a persisted unsuccessful 409. Existing six immediate/deferred-COMMIT failure injections leave gate and audit/action counts unchanged. Migration rollback/reapplication in an isolated database preserves pre-existing business data and metadata comparison finds no drift. PostgreSQL rejects audit/action UPDATE and DELETE, as well as a pause beyond 600 seconds.

Operator session plus CSRF is required for demo pause; internal bearer authentication alone grants neither browser access nor pause authority. Operator cookie/secret and an unrelated webhook token cannot replace the recovery bearer. Direct HTTP tests reject invalid/expired/revoked sessions, role substitution, missing CSRF and unexpected action targets. No application shell/subprocess/Docker-socket capability was found. The `agent` audit principal identifies the internal credential boundary; manually invoked recovery in this audit is not autonomous-agent evidence.

### Final browser evidence and persisted recovery

After the last correction, the repeated **five T07 Chromium cases passed in 74.32 seconds**, zero failures/errors/skips/deselections. Thus the distinct audit total is **392 = 116 unit + 256 PostgreSQL + four Docker + 16 Chromium**. The full backend gate's four deselections were all run separately; the standalone unit selection's other cases were covered by the full gate and Docker run. Repeated browser/unit/backend executions are not additional distinct tests. The initial 51 setup errors and the reproduced negative HTTP 500 are historical failures corrected/isolated above, not part of a claim that every audit execution passed.

Final real run at `http://127.0.0.1:18017` used operator, dispatcher and technician browser sessions with synthetic data:

| Evidence | Observed value |
|---|---|
| Normal-delivery preflight | Recipient inbox populated; undelivered count and age both zero |
| Pause | Generation 2, effective **2026-11-10T02:32:02.456037Z**, deadline **02:42:02.456037Z** |
| Restart while paused | Old instance `60e6c97a-0edc-43ed-b711-cc4437e897aa`; new `89db50b5-1b8d-4e30-900e-bc4249b334c1`; same generation/deadline, fresh heartbeat |
| Affected intervention | `3456a9db-183f-4156-a016-806dd494be71` |
| Outbox event | `c2a7d4df-b046-4114-9af9-77bc34f8c398`, created **02:32:05.298304Z**, pending, attempts zero |
| Initial and delayed age | **0.240647 → 61.297756 seconds**, one undelivered event, no matching inbox row, heartbeat fresh throughout |
| Manually authorized resume | Key `25106221-988e-4550-8d3c-c1915d2778d0`, generation 2, `success/resumed` recorded **02:33:06.954410Z**; exact replay identical |
| Inbox delivery | `90c3d8fc-aea1-4e92-b370-2dc33e93e47b`, matching exact event/intervention, delivered **02:33:07.607130Z**, **0.652720 seconds** after recorded resume |
| Recovery state | Gate enabled, backlog count zero, oldest age zero; SQL confirmed one inbox row and durable pause/resume audit entries |

The new event stayed absent for an actual elapsed minute; neither its timestamp nor dashboard age was fabricated. This is a manually authorized fixed recovery operation, not T10 alerting or autonomous T11 repair.

Read-only final SQL was executed through `docker compose --project-name fieldops-t07-audit exec -T db psql -U fieldops -d fieldops -At -c ...`:

```sql
SELECT version_num FROM alembic_version;
SELECT generation, paused FROM worker_control;
SELECT event_type, generation, principal, outcome, created_at
FROM worker_control_audit WHERE generation=2 ORDER BY created_at;
SELECT o.id, o.status, o.created_at, o.delivered_at, count(n.id)
FROM notification_outbox o LEFT JOIN notifications n ON n.outbox_id=o.id
WHERE o.id='c2a7d4df-b046-4114-9af9-77bc34f8c398' GROUP BY o.id;
SELECT count(*), min(created_at) FROM notification_outbox
WHERE status IN ('pending','processing','failed');
```

Observed: revision `0003_t07_controls`; control `2/false`; audit `pause/2/operator/effective` and `resume/2/agent/resumed`; exact event `delivered` with inbox count one; undelivered count zero and no oldest timestamp. Audit `created_at` uses PostgreSQL transaction-start time; control `effective_at` and action `recorded_at` are the explicit post-lock operational timestamps.

The four current desktop/mobile/paused/recovered PNGs were opened and visually inspected after the final rerun. Desktop and 375px no-JavaScript screenshots show readable cards, contained long instance IDs, clearly visible keyboard focus on the pause button and no horizontal overflow. Paused/fresh and enabled/fresh states are distinct; delayed warning and zero recovery figures match the database. Artifact paths are listed above; final report XML is `artifacts/t07-audit-browser-final.xml`, with the full 16-case run in `artifacts/t07-audit-browser.xml`. JSON contains synthetic IDs/timestamps only. A final source scan inspected **95 tracked/untracked paths**, found no credential patterns or sensitive runtime filenames and checked untracked whitespace. Current database/session/operator/recovery values were compared in memory against service logs and eight completed JSON/XML reports with no matches; values were never printed. No staged secrets or runtime data exist.

### Final acceptance and recommendation

| Live Issue #7 criterion | Independent audit | Actual evidence |
|---|---|---|
| Include pending, processing and failed in undelivered count/age | PASS | PostgreSQL fixture has one of each, delivered excluded; failed row is oldest; real paused-event HTTP/UI evidence |
| Empty queue age is zero | PASS | Isolated empty fixture and both real post-recovery HTTP snapshots |
| Pause acknowledgement waits for active transaction | PASS | Actual inbox INSERT held by a barrier, PostgreSQL lock waiter observed, pause completes only after delivery transaction; subsequent claims/delivery denied |
| Resume CAS and action result commit atomically | PASS | Same-key and different-key races, persistent replay, wrong-generation HTTP 409, six statement/deferred-COMMIT rollback cases |
| Isolate operator/webhook/agent credentials | PASS | Direct HTTP substitution/CSRF/session negatives; distinct generated control keys; worker lacks control-key volume |

Remaining limitations: demo identities and shared database-owner trust are unsuitable for production; TLS/private proxy restrictions, rotation and least-privilege database roles are not certified. All deployed workers must understand the gate; mixed-version rollout is not certified. Heartbeat has a 15-second grace period; automatic expiration reconciles on the next worker/status access after PostgreSQL recovery, not through an external real-time watchdog. Failed events stay visible and are not automatically replayed. Test database retention can exhaust tmpfs on repeated runs; use fresh isolated projects and retain earlier evidence without deleting application volumes. Full WCAG/screen-reader certification, non-Chromium browsers and production load are **NOT TESTED**. The incident correlation UUID is not an implemented T11 eligibility policy; there is no alert receiver or model-driven agent.

**Verdict: PASS for T07's authorized local/demo scope after two isolated corrections. Recommendation: GO for feature-branch publication only after owner authorization.** Audit changes are limited to `fieldops/settings.py`, `fieldops/control_schemas.py`, `tests/test_t07.py`, new `tests/test_t07_review.py`, `tests/test_container_lifecycle.py`, `browser_tests/test_t07_dashboard.py`, `README.md` and this document. Final working tree retains the 26 local T07 paths (16 modified and ten new), with nothing staged. No commit/push/merge/Issue closure, future phase, deployment, purchase or volume deletion was performed.


## Pre-publication check ? 2026-11-10

Repository/branch and unchanged T05 baseline were reconfirmed; live Issue #7 remains open. The two audited corrections and static migration were reviewed. No application changes were made after the audit. Re-ran `.venv/Scripts/python.exe -m pytest -m "not integration and not container" -p no:cacheprovider --basetemp=artifacts/t07-publication-unit`: **116 passed, 260 deselected, zero failures/skips, 1.34 seconds**. Deselected PostgreSQL/Docker cases remain covered by the recorded 392-test audit; this publication check does not claim a new full-suite run. Ruff lint and formatting passed (69 files). Git whitespace checks passed. Only T07 application, migration, test, configuration and documentation paths are eligible for staging; ignored screenshots, reports, runtime credentials and databases remain local.
