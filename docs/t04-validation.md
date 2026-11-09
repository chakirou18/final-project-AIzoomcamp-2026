# T04 intervention lifecycle validation

> Latest independent audit: **PASS after two corrections; 229 distinct passing tests**
> (73 unit, 154 real PostgreSQL integration, 2 Docker lifecycle), zero final failures/skips.
> The independent audit section below supersedes the earlier implementation-run totals.

Task: [Issue #4](https://github.com/chakirou18/final-project-AIzoomcamp-2026/issues/4).
Implementation/audit snapshot, 2026-11-09. Branch: `feature/t04-intervention-lifecycle`.
Baseline: `c4e83e38fcd6b45e422b32772e1934a40c3f0aa9` on published
`feature/t03-schema-contracts` (PR #17 remains unmerged). Subsequent feature-branch publication
authorization and checks are recorded below; earlier local-only statements are historical snapshots.

## Implementation and contracts

Shared `InterventionService` owns transactions and resolves active identity/role within them.
JSON adapters delegate business rules; future HTML adapters can reuse the service.
No schema changes or new migrations: T03 revisions `0001_t03` and `0002_t03_review` remain intact.

| Method | Path | Permission and behavior |
| --- | --- | --- |
| POST | `/api/v1/interventions` | Dispatcher; 201; optional active technician |
| GET | `/api/v1/interventions` | Dispatcher all; technician current assignments only |
| GET | `/api/v1/interventions/{id}` | Dispatcher or currently assigned technician |
| PATCH | `/api/v1/interventions/{id}` | Dispatcher; open/assigned; editable fields only |
| POST | `/api/v1/interventions/{id}/assignment` | Dispatcher; open/assigned; active technician |
| POST | `/api/v1/interventions/{id}/transitions` | Own technician starts/completes; dispatcher cancels |
| GET | `/api/v1/interventions/{id}/history` | Same current scope as detail; append-only |
| GET | `/api/v1/technicians` | Dispatcher; active technicians only |

All mutations require signed, persisted demo session plus matching `X-CSRF-Token`.
Operators have no business permissions. JSON errors use `error.code/message/fields`;
401 identity, 403 role/scope/CSRF, 404 missing job, 409 stale version/illegal lifecycle,
422 invalid fields/assignee, 503 unavailable database, sanitized 500 unexpected failure.
Live OpenAPI includes role descriptions, errors and cookie AND CSRF requirements.
`/contracts/openapi.json` marks implemented lifecycle operations; notification paths remain draft.

Example bodies (keep login cookies and session CSRF token):

```json
{"title":"Synthetic inspection","site":"Demo Site","priority":"high"}
```

PATCH body: `{"expected_version":1,"priority":"urgent"}`.
Assignment body: `{"expected_version":2,"technician_id":"<active-technician-uuid>"}`.
Start body: `{"expected_version":3,"target_status":"in_progress"}`.
Complete body: `{"expected_version":4,"target_status":"completed","resolution":"Synthetic repair"}`.
Cancel body: `{"expected_version":3,"target_status":"cancelled"}`.

Published field lengths, normalization and low/medium/high/urgent priorities are reused.
Open -> assigned/cancelled; assigned -> in_progress/cancelled;
in_progress -> completed/cancelled; terminal states have no exits.
Assignment is the only route to assigned; no reopen/unassign/delete operations exist.
Only title, description, site and priority can be edited, while open/assigned.
Completion requires nonblank resolution; other transitions reject resolution.
Cancellation sets closed_at and retains assignee/start information; completion closes once.
Clock timestamps are sampled after acquiring the row lock, in UTC, bounded below by prior timestamps.

Each mutation locks the intervention, then checks expected_version. Effective changes increment
row_version once. Same-assignee with current version returns unchanged, with no history/outbox;
stale same-assignee returns 409. Identical field edits are also checked no-ops.
Creation keeps row_version=1; optional assignment sets assignment_version=1 and assigned state.
Creation and initial assignment have separate history entries. Subsequent assignments increment
assignment_version. Every effective assignment appends history and one unique pending outbox row
in the same transaction as the intervention update. Any insertion/commit failure rolls back all.
The database history trigger prevents UPDATE/DELETE; the API exposes only history reads.

Lists support status, priority and technician_id filters; scope applies before count/pagination.
Page starts at 1, page_size defaults 25 and is bounded 1..100. Sort is created_at DESC, id DESC.
Very large page values return empty items without overflowing PostgreSQL OFFSET.
Counts/pages are live READ COMMITTED views, not a stable snapshot across requests.

## Actual execution

PowerShell from repository root, Python 3.12; Docker uses real PostgreSQL 17.

```powershell
.venv/Scripts/python.exe -m pytest -m 'not integration and not container' -q -p no:cacheprovider --basetemp=artifacts/t04-unit-final
$env:FIELDOPS_SUBNET='10.242.0.0/24'
docker compose --project-name fieldops-t04-validation --profile test run --build --rm tests
$env:FIELDOPS_RUN_CONTAINER_TESTS='1'
.venv/Scripts/python.exe -m pytest tests/test_container_lifecycle.py -v --junitxml=artifacts/t04-container.xml
$env:FIELDOPS_PORT='18004'
docker compose --project-name fieldops-t04-validation config --quiet
docker compose --project-name fieldops-t04-validation up --build --wait
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m ruff format --check .
uv --cache-dir .cache/uv lock --check
git diff --check
git status --short
```

- Unit: **73 passed, 96 deselected**, 1.59s.
- PostgreSQL plus unit gate: **167 passed, 2 container tests deselected**, final rerun 18.53s;
  **94 real PostgreSQL integration tests**, including previous T02/T03 suites.
- Separate Docker lifecycle: **2 passed**, 51.76s; startup, restart/recreation persistence,
  database outage readiness 503 with liveness 200, recovery readiness 200.
- **169 distinct passing tests; 0 final failures; 0 skips.** Deselections above separate the gates.
- Compose configuration, image build, migration/seed bootstrap and healthy startup: PASS.
- Real network HTTP smoke on `127.0.0.1:18004` with Python urllib cookie jar:
  health live/ready 200; login dispatcher; create assigned 201; login own technician;
  start 200; complete 200; retrieve history 200 with four events, row_version=3.
- Ruff lint/format, frozen lock resolution (36 packages), whitespace: PASS.
- Final tracked/untracked review covered 56 nonignored files: no credential patterns, local
  environment files, private keys or generated databases found. Synthetic test signing keys and
  `.env.example` placeholders are intentional. Index is empty; HEAD remains the T03 baseline.
- Initial unit collection failed on a method-name/type annotation collision (`list`);
  fixed with postponed annotations, then reran successfully. Intermediate lint/format errors
  and a test-block insertion syntax error were corrected before final execution.
- Earlier full gates passed 146 and 163 tests before coverage expansion; do not sum repeated runs.

Transaction tests inject failures at actual SQL INSERT boundaries (history/outbox), verify from
new sessions that job/history/outbox remain unchanged, then retry successfully. Create-with-assignee
outbox failure leaves no intervention. Two independent PostgreSQL sessions race on the same
expected version: exactly one succeeds and one reports stale_version; only one assignment event
is appended. Policy tests cover all 25 status pairs; database tests cover all 15 schema-accepted
transition commands, including terminal states and scope checks. Direct HTTP tests exercise missing
sessions, missing CSRF, invalid fields/priorities, cross-technician detail/history, unauthorized
creation, stale edits, forbidden completion, completion resolution, history mutation denial and
pagination bounds. Separate tests cover all priorities, reassignment/no-op, cancellation from all
eligible states, filtering/order/pages, invalid assignee and manager/technician/operator boundaries.

All destructive migration checks run in isolated test databases. No application volume was deleted.
The T04 Compose project, its local HTTP service and synthetic data remain for inspection; lifecycle
tests retain their generated volumes. PostgreSQL is not exposed on a host port.

## Acceptance and limitations

| Issue #4 criterion | Result | Evidence |
| --- | --- | --- |
| Valid lifecycle and all priorities persist | PASS | Real DB lifecycle/matrix and priority tests |
| Optional assignee creation is atomic | PASS | Separate history, outbox and injected create failure |
| Forbidden edits/transitions fail | PASS | Policy/DB matrix, role and HTTP checks |
| Same-assignee checked no-op | PASS | Unchanged DTO/history/outbox; stale version rejected |
| Stale updates return 409 | PASS | Direct HTTP stale edit and concurrent DB assignments |
| Field limits, filters and pagination | PASS | Existing schema negatives; scoped pages/order/filter tests |
| T02/T03 regression gate | PASS | All prior test cases retained; obsolete no-live-route assertion updated |

Demo persona selection remains demo authentication, not production identity proof. Existing local
database owner privileges are not a production least-privilege deployment. No HTML business UI,
inbox handler, delivery worker, notification delivery evidence, tracing propagation, browser tests,
load benchmark or production deployment is provided (T05/T06/T08/T09+ remain deferred). Assignment
success proves durable pending outbox insertion, not technician notification delivery. SQL lock waits
are bounded by the existing statement timeout and return sanitized 503 on operational failure;
clients must refresh before retrying an uncertain response. No automatic command retry/idempotency
key is added beyond the published same-assignee/version contract. READ COMMITTED pagination may
shift during concurrent writes. No external security scanner or production penetration test was run.

Recommendation: **GO for independent T04 review and subsequent owner-authorized publication**.
No commit, push, PR, merge or Issue closure performed. Owner approval remains required for publication.

## Independent backend, database and security audit

Audit date: 2026-11-09. Live Issue #4 was read and remains OPEN. Repository origin and expected
branch were confirmed. HEAD and `feature/t03-schema-contracts` both remain exactly
`c4e83e38fcd6b45e422b32772e1934a40c3f0aa9`; their merge-base is the same commit.
Models, migrations, manifest and lockfile have no differences from that baseline. Existing
tracked/untracked implementation changes were preserved; the index remains empty.

### Reproduced defects and corrections

1. **History authorization race:** `list_history` checked the assignee, then counted/read history
   under READ COMMITTED without holding an intervention lock. A second real PostgreSQL connection
   successfully changed the assignee in this gap. A technician could consequently read history
   committed after reassignment. The service now holds `FOR SHARE` on the intervention through
   authorization, count and page materialization. A deterministic SQL hook attempts a competing
   reassignment at that precise boundary and now receives PostgreSQL lock timeout `55P03`.
   After the read transaction finishes, normal reassignment remains supported.
2. **Assignment timestamp inconsistency:** outbox `created_at`/`available_at` inherited transaction
   `now()`, preceding the actual post-lock assignment time. A PostgreSQL probe reproduced this.
   Assignment history, outbox creation and availability now use one database `clock_timestamp()`
   sample after locking/validation. Effective assignment also uses it for intervention updated_at;
   initial assigned creation retains its documented creation timestamp and row_version=1.

Both new probes failed against the original implementation: **2 failed, 39 deselected**, 1.84s.
After correction the first audit-only gate passed **41/41**, 12.47s. Coverage was then expanded
to **60 audit integration cases**, included in the final full gate below. These earlier failures
are recorded rather than counted as final failures or hidden by weaker assertions.

Minor documentation fixes: served lifecycle contract title no longer says unimplemented;
schema module description reflects T04; architecture records the locking/timestamp boundary;
AGENTS removes a contradictory historical T03 publication authorization. The OpenAPI regression
now also compares all shared generated schemas between draft and live documents.

### Commands and final observed results

PowerShell, repository root. This audit uses a separate Compose project/subnet and retained,
uniquely named audit databases; it never clears an existing application database.

```powershell
# Reproduction before the two service corrections:
$env:FIELDOPS_SUBNET='10.243.0.0/24'
docker compose --project-name fieldops-t04-audit --profile test run --build --rm tests .venv/bin/pytest tests/test_t04_review.py -k 'scope_locked or timestamp_reflects' -v
# First corrected audit-only gate:
docker compose --project-name fieldops-t04-audit --profile test run --build --rm tests .venv/bin/pytest tests/test_t04_review.py -v
# Final unit gate:
.venv/Scripts/python.exe -m pytest -m 'not integration and not container' -q -p no:cacheprovider --basetemp=artifacts/t04-audit-unit-final
# Final complete unit + PostgreSQL gate:
docker compose --project-name fieldops-t04-audit --profile test run --build --rm tests
# Separate real Docker lifecycle gate:
$env:FIELDOPS_RUN_CONTAINER_TESTS='1'
.venv/Scripts/python.exe -m pytest tests/test_container_lifecycle.py -v --junitxml=artifacts/t04-audit-container.xml
# Local network HTTP and business-data persistence:
$env:FIELDOPS_PORT='18014'
docker compose --project-name fieldops-t04-audit config --quiet
docker compose --project-name fieldops-t04-audit up --build --wait
$env:PYTHONPATH='.'
.venv/Scripts/python.exe artifacts/t04-audit-network.py
# Final quality/baseline checks:
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m ruff format --check .
uv --cache-dir .cache/uv lock --check
git merge-base HEAD feature/t03-schema-contracts
git diff HEAD -- migrations fieldops/models.py uv.lock pyproject.toml
git diff --cached --stat
git diff --check
git status --short
```

| Final gate | Passed | Failed | Skipped | Deselected | Observed time |
| --- | ---: | ---: | ---: | ---: | --- |
| Unit only | 73 | 0 | 0 | 156 | 1.87s |
| Unit + real PostgreSQL | 227 | 0 | 0 | 2 container | 40.44s |
| Docker lifecycle | 2 | 0 | 0 | 0 | 49.41s |
| Distinct across full gates | **229** | **0** | **0** | **0 left unrun** | Unit-only repeats excluded |

The 227-test gate comprises **73 unit and 154 PostgreSQL integration cases**. All original
169 tests are retained; 60 audit integration cases were added. All T02/T03 regression cases,
including migration upgrade/downgrade/reapplication, retained data and SQL history protection,
passed. Ruff lint and formatting (46 Python files), lock resolution (36 packages), Compose config,
build/bootstrap/health and whitespace checks passed. No dependency changes were required.

### Transaction, lifecycle and permission evidence

- Seven **database constraint triggers**, DEFERRABLE INITIALLY DEFERRED, reject COMMIT with
  SQLSTATE P0001 after SQLAlchemy flush has succeeded. Cases cover unassigned creation/history,
  assigned creation/history and outbox, assignment/history and outbox, edit/history and start/history.
  New sessions confirm identical intervention/history/outbox counts and unchanged original state.
  Only the temporary triggers/functions in the unique audit DB are removed afterward; no data or
  database/volume is dropped. This supplements the original pre-INSERT Python failure injection.
- Independent HTTP clients race with the same expected_version over separate database connections:
  exactly one 200 and one 409 `stale_version`. The winning recipient/version matches exactly one
  pending outbox row and one assignment history entry. A current-version repeat returns the identical
  response without any row-count change; a stale repeat returns 409 with no changes.
- All 25 source/target status pairs run through real application HTTP handlers. Open/assigned targets
  are rejected with 422 by the published T03 request schema; those cannot bypass the assignment
  command. Schema-valid but illegal source transitions return 409, after role/current-scope checks.
  The separate database assignment eligibility matrix covers open -> assigned and forbidden
  reassignment from in-progress/terminal states. No new transitions were introduced.
- HTTP edit/assignment eligibility is checked in every state. Cancellation tests verify retained
  technician, assignment_version and started_at, closed_at=updated_at, actor and exact history diff.
  Completion rejects null, empty, whitespace-only and 4001-character resolution; accepts 4000.
  Exact title/site/description limits accept 160/250/4000 and reject the next character with 422.
  Priorities, list sorting, filters, page bounds, huge page offsets and scoped counts pass existing
  tests. History UPDATE/DELETE is rejected by the real PostgreSQL trigger; no mutation route exists.
- Direct business-route HTTP tests deny manager mutations for both technicians and operator, deny
  manager start, deny technician B starting/reading A's job/history, and deny operator business reads.
  Missing, tampered and revoked sessions produce 401. Missing, wrong and another session's CSRF
  token produce 403 for every mutation type. Invalid/nontechnician/inactive assignees return 422;
  missing job gives 404, invalid UUID 422, technician listing is dispatcher-only. Requests denied
  for role/scope/CSRF leave database state/counts unchanged.
- Live and T03 contract documents have matching shared request/response schemas, success/error
  status sets, role descriptions and cookie AND CSRF requirements. Notification routes remain
  absent from live OpenAPI. Error envelope and sanitized validation behavior remain consistent.

### Real network, persistence and secret evidence

The ignored local harness `artifacts/t04-audit-network.py` uses Python urllib with separate cookie
jars against **127.0.0.1:18014**, not just ASGI TestClient. It verified unauthenticated 401, missing
CSRF 403, create 201, concurrent assignment 200/409, checked no-op, cross-technician 403,
start/completion 200 and resolution validation 422. The completed job has row_version=4,
four history events and exactly one outbox row.

The harness executed `docker compose --project-name fieldops-t04-audit restart db web` and
`docker compose --project-name fieldops-t04-audit up -d --no-deps --force-recreate db web`.
After each, the same authenticated technician retrieved the identical completed job and four
history events. The final PostgreSQL outbox count was one, proving job/history/outbox/session
persistence across both restart and container recreation. Separate lifecycle tests verified actual
DB outage: liveness stays 200, readiness becomes 503, recovery returns readiness 200.

Generated DB password and session signing key were read into memory only; the harness checked
them, all four clients' signed cookies and CSRF tokens against service logs and the business
response. No matches occurred. No runtime secret was printed or written to source. Final source
review/scanning covered **57 tracked and untracked nonignored files**: no private-key/token patterns,
local environment files or generated databases found. `.env.example` and synthetic test keys are
intentional. The harness and lifecycle XML are ignored artifacts, not publication candidates.

### Test quality and remaining limits

The original suite was not sufficient to rule out the reproduced history race or timestamp defect.
Its concurrent service test did not prove the HTTP 409 adapter; its create rollback test counted
only interventions; and SQLAlchemy pre-INSERT hooks did not demonstrate a database COMMIT failure.
The added HTTP race, aggregate row-count checks and PostgreSQL deferred triggers close those gaps.
No existing assertion was weakened. Existing broad exception assertions also check status codes;
unexpected exceptions without those codes fail rather than pass. Pure policy tests are supplemented
by real DB and HTTP matrices; mocks are not the only transaction evidence.

Audit databases are isolated from application data and retained. Some original tests commit synthetic
rows into the disposable test database and list assertions assume serial execution. Audit DDL-trigger
tests also assume serial execution; xdist/parallel suite execution is **NOT TESTED**. Docker lifecycle
tests choose a free fixed host port before startup and inspect Docker subnet overlap, avoiding port-0
changes after restart. A small port-allocation race and host/VPN route conflicts remain environmental
risks; failures are surfaced, not converted to passes. Test volumes accumulate by design.

Demo persona selection is still not production authentication. Database-owner tampering, production
least privilege, penetration testing, browser/UI behavior, notification delivery and load SLOs are
outside this audit and **NOT TESTED**. The DB owner can disable audit triggers; ordinary application
operations cannot edit/delete history. Request authentication is checked on entry; revoking a session
does not cancel already-running requests. Pagination uses live READ COMMITTED queries and can shift
under writes. Lock contention remains bounded by existing DB/pool timeouts and may return 503;
there is no automatic retry. No T05/T06 implementation was added.

### Issue #4 acceptance after independent audit

| Acceptance criterion | Verdict | Verified evidence |
| --- | --- | --- |
| Valid lifecycle and all priorities persist | PASS | Policy/DB/HTTP matrix, four priorities, real restart/recreation |
| Optional-assignee creation is atomic | PASS | History+outbox graph and deferred DB COMMIT failures |
| Forbidden edits/transitions fail | PASS | Every source state, role/scope denials and unchanged state |
| Same-assignee command is a checked no-op | PASS | HTTP identical response/counts; stale repeat 409 |
| Stale updates return 409 | PASS | Independent ASGI and network HTTP races; exactly one pending event |
| Field limits/filter/pagination contract implemented | PASS | Boundary HTTP validation, scoped pages/order/filter regressions |

Audit verdict: **PASS after corrections; GO for owner-authorized T04 publication**. No critical
unresolved defect was found within T04 scope. Changes remain local and unstaged. The audit stack
is running locally on port 18014 and all existing volumes remain intact. No commit, push, PR merge,
Issue closure, public deployment or infrastructure purchase was performed. Stop for owner approval.

## Authorized feature-branch publication checks

After the independent audit, the owner authorized one T04 commit, a non-force push of
`feature/t04-intervention-lifecycle`, a PR targeting `feature/t03-schema-contracts` and a progress
comment on Issue #4. No merge, Issue closure, later-task implementation, deployment, purchase or
volume deletion is authorized. AGENTS and current-status notes reflect this authorization.

Pre-publication checks confirmed the branch, repository, unchanged T03 baseline and live Issue #4.
`git ls-remote --heads origin feature/t03-schema-contracts feature/t04-intervention-lifecycle`
confirmed published T03 at `c4e83e38fcd6b45e422b32772e1934a40c3f0aa9`; no T04 remote branch existed
before publication. Tracked and untracked changes were inspected. A fresh scan of all 57
nonignored files found no credential patterns, local environment files or generated databases.
Only synthetic test keys and example placeholders are included. Ignored runtime artifacts and
container volumes are excluded from staging.

Fresh commands and results:

```powershell
.venv/Scripts/python.exe -m pytest -m 'not integration and not container' -q -p no:cacheprovider --basetemp=artifacts/t04-publication-unit
$env:FIELDOPS_SUBNET='10.243.0.0/24'
docker compose --project-name fieldops-t04-audit --profile test run --build --rm tests
$env:FIELDOPS_RUN_CONTAINER_TESTS='1'
.venv/Scripts/python.exe -m pytest tests/test_container_lifecycle.py -v --junitxml=artifacts/t04-publication-container.xml
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m ruff format --check .
uv --cache-dir .cache/uv lock --check
git diff --check
```

- Unit: **73 passed, 0 failed, 0 skipped, 156 deselected**, 1.95s.
- Unit/PostgreSQL gate: **227 passed, 0 failed, 0 skipped, 2 container tests deselected**, 40.31s.
- Docker lifecycle: **2 passed, 0 failed, 0 skipped, 0 deselected**, 51.77s.
- **229 distinct passing tests: 73 unit + 154 real PostgreSQL + 2 Docker lifecycle.**
- Both corrected concurrency/timestamp regressions passed; no application/test code changed
  during publication preparation. Ruff, formatting, frozen lock and whitespace checks passed.

The release commit/PR and Issue progress comment provide publication identifiers. The publication
gate does not add notification delivery, HTML workflows or production authentication claims.
