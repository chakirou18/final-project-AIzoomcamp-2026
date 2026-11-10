# T05 web interface validation

> Publication authorization (2026-11-10): the owner authorized one T05 commit, non-force feature
> push, a PR against `feature/t06-notification-worker` and an Issue #6 progress comment. Historical
> local-only authorization notes below describe earlier phases. No merge, Issue closure or T07+
> implementation is authorized.

> Independent audit: **PASS — 338 distinct passing tests**, zero final failures/skips (2026-11-10).
> The final audit section below supersedes the original
> implementation handoff. Review found and corrected long-text overflow, private HTMX history
> retention, error-heading duplication and out-of-range empty-page feedback. Publication remains
> unauthorized; all work is local.

Task: [Issue #6 — intervention UI and technician inbox](https://github.com/chakirou18/final-project-AIzoomcamp-2026/issues/6).
Requirements: F01–F05, F10, N07. Local implementation and testing only, 2026-11-10.
Branch: `feature/t05-web-interface`, created from published T06
`1253faaedd5b39aa9ee9da0330645e1b5667119b`. HEAD and merge-base remain that commit.
Read AGENTS.md, live Issue #6 and its dependency Issues #4/#5, specification, architecture,
contracts, intervention/inbox/session services and existing tests before implementation.
Initial working tree was clean. Earlier commits and feature PRs remain unchanged/unmerged.

## Architecture and screens

`fieldops/web.py` adapts the existing transaction-owning `InterventionService` and `InboxService`.
No duplicated lifecycle, authorization, delivery or persistence logic is implemented in templates.
Existing JSON APIs, schema, migrations and notification worker are unchanged.

| Route | Screen or behavior |
| --- | --- |
| GET / | 303 to the demo identity page |
| GET/POST /app/login | Labeled synthetic manager/technician selector; existing signed session activation and login CSRF |
| POST /app/logout | Existing database session revocation and cookie clearing; 303 to login |
| GET /app/interventions | Manager queue or currently assigned technician work, status/priority/technician filters, pagination |
| GET/POST /app/interventions/new | Manager create, optional initial assignment, visible field feedback |
| GET /app/interventions/{id} | Scoped details, UTC timestamps, paginated append-only history, permitted actions |
| GET/POST /app/interventions/{id}/edit | Manager edit with version check and retained values on failure |
| POST /app/interventions/{id}/assignment | Manager assignment/reassignment, including current-version same-assignee no-op |
| POST /app/interventions/{id}/transition | Technician start/complete; manager cancellation, using shared lifecycle rules |
| GET /app/inbox | Persistent recipient inbox, read/unread state, refresh and pagination |
| POST /app/inbox/{id}/read | Scoped, idempotent mark-read; full-page 303 redirect |

Eight Jinja templates provide a shared header/navigation, responsive card list, create/edit form,
detail/history/action screen, inbox, login, error page and pagination. Priority and status have
text labels in addition to color. Completion requires a nonblank resolution, maximum 4000 characters.
Cancellation requires an explicit confirmation button inside native `details`; no hard delete exists.
Historical inbox entries retain their immutable event summary but omit the job link; direct stale
URLs are still checked by the service. Missing or inaccessible references return visible 404/403.

HTMX boosts navigation links only. Forms always submit ordinary URL-encoded requests and work
without JavaScript. Error responses during boosted navigation are swapped into view, including
expired/revoked sessions. Mutations validate CSRF and then invoke the same services as JSON.
Form parsing is bounded to 65,536 bytes/12 fields, rejects duplicates and wrong content types,
and explicitly converts version strings before applying strict shared Pydantic contracts.

Bootstrap 5.3.8 CSS and HTMX 2.0.8 JavaScript are served from `/static/vendor`; licenses, source URLs
and SHA-256 values are recorded in its README. There is no runtime CDN or frontend build.
Jinja2 3.1.6 is locked as a runtime dependency; Playwright 1.65.0 is development-only.

## Executed commands and results

PowerShell, repository root, Python 3.12.10 on Windows; Docker Linux Python 3.12.16/PostgreSQL 17.
Chromium installed by the locked Playwright package. All database tests use real PostgreSQL.

```powershell
uv --cache-dir .cache/uv add "jinja2>=3.1.6,<4"
uv --cache-dir .cache/uv add --dev "playwright>=1.56,<2"
.venv/Scripts/python.exe -m playwright install chromium

$env:FIELDOPS_PORT='18005'
$env:FIELDOPS_SUBNET='10.246.0.0/24'
docker compose --project-name fieldops-t05 up --build --wait
docker compose --project-name fieldops-t05 config --quiet

.venv/Scripts/python.exe -m pytest -m 'not integration and not container' -q --basetemp=artifacts/t05-unit
# 101 passed, 211 deselected, 1.86s; one Windows pytest-cache permission warning.

docker compose --project-name fieldops-t05 --profile test run --build --rm tests
# Final combined run: 309 passed, 3 deselected, 71.67s.
# Breakdown: 101 unit + 208 PostgreSQL; the three Docker tests are separate.

$env:FIELDOPS_RUN_CONTAINER_TESTS='1'
.venv/Scripts/python.exe -m pytest tests/test_container_lifecycle.py -v -s -p no:cacheprovider --junitxml=artifacts/t05-container.xml --tb=short
# 3 passed, 111.58s. Persistence, DB outage/recovery, worker restart and delivery.

.venv/Scripts/python.exe -m pytest browser_tests -v -s -p no:cacheprovider --junitxml=artifacts/t05-browser.xml --tb=short
# See final browser results below.

.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m ruff format --check .
uv --cache-dir .cache/uv lock --check
git diff --check
git status --short
```

Lint passed; format check passed; lock verification resolved 38 locked packages; whitespace check
passed. No unit/PostgreSQL failures or skips in the final combined run. All previous 290 tests
remain present and passed in their applicable suites. T05 adds five unit and seventeen PostgreSQL
tests, plus four browser cases. Deselected suite counts are separate from skipped tests.
Browser tests live outside default `testpaths` and must be explicitly run with `pytest browser_tests`.

Each T05 PostgreSQL case creates a UUID-named `_test` database, migrates and seeds it, and retains
it afterward. It does not drain the shared regression queue, reset an application database or
drop any volume/database. The Compose test database is separately configured. Browser cases
create retained synthetic jobs through HTTP against the isolated `fieldops-t05` application.

### Failures and corrections during development

These are historical failures, not passing results:

- Initial T05 run: 11 failed/4 passed (6.62s). A template string containing an unescaped apostrophe
  failed compilation; a unit assertion assumed every version rejection was a domain exception.
  Corrected template and accepted the shared Pydantic validation exception where appropriate.
- Next T05 run: 1 failed/14 passed (3.50s). Invalid-cookie test added a second differently scoped
  cookie rather than replacing the real one. Clearing the cookie jar makes the denial test genuine.
- Initial browser run: 2 failed/2 passed (88.20s), while the first app revision was being replaced.
  Next browser run: 2 failed/2 passed (14.50s): it inspected job links before boosted inbox navigation
  finished. Explicitly waiting for the inbox heading resolves the asynchronous test assumption.
- Combined run: 1 failed/301 passed/3 deselected (66.70s). Shared outbox fixtures could put the new
  HTML journey outside the next twenty-event claim. T05 cases now use separate databases.
- Expanded combined run: 1 failed/308 passed/3 deselected (77.15s), and targeted reproduction
  1 failed (1.95s). Completion conflict discarded the proposed resolution. The template now keeps
  escaped submitted text; targeted T05 run subsequently passed all 22 tests (7.93s).
- Review also corrected a conflict reload link pointing at a POST-only command URL, history
  pagination with a success notice, readable UTC formatting, and visible HTMX authentication errors.
- Initial lint findings were formatting/import/line-length issues; final lint and format checks pass.

## Browser, responsiveness and accessibility

Four live Chromium cases cover 1440×960 and 375×960, each with JavaScript enabled and disabled.
Each selects the manager, submits invalid creation and sees feedback with retained site, creates,
edits, assigns A, waits for the real worker inbox, marks read, starts/completes as A, and verifies
the manager's completed detail and JSON HTTP 200 response/resolution. Separate browser contexts
keep manager and technician sessions independent. With JavaScript enabled the test observes an
actual `HX-Request: true` navigation. Revoking the technician session through HTTP and then using
navigation must visibly show the authentication error in both enhanced and full-page modes.

Keyboard checks exercise the skip link, Tab from title to site, keyboard text entry and Enter
submission. Layout checks assert no document-level horizontal overflow and exactly one associated
label for every visible input/select/textarea on the tested screens. Focus outlines, semantic
headings/main/nav, status text, alert summaries, required markers, field feedback and native details
remain available without JavaScript. Error fields use accessible descriptions and invalid state.

Screenshots are generated in ignored `artifacts/`:

- `t05-create-{1440|375}-js-{True|False}.png`
- `t05-inbox-{1440|375}-js-{True|False}.png`
- `t05-{1440|375}-js-{True|False}.png` (completed detail)

Desktop create and mobile inbox screenshots were visually inspected. This is a bounded Chromium
usability check, not WCAG certification. Screen-reader testing, automated axe analysis, Firefox,
Safari, browser zoom and the full range of assistive technology are **NOT TESTED**.

## Real local demonstration and persistence

The browser journey executes the requested nine-step manager → assignment → actual worker → inbox
→ technician completion → manager status flow. No frontend notification fixtures or direct database
delivery insertions are used in that demonstration. This is executed browser automation rather than
a claim of a human-operated manual demonstration. Reproduce manually at `http://127.0.0.1:18005/`:
choose Synthetic Dispatcher, create/edit an intervention, save its technician assignment, open a
separate browser profile as Synthetic Technician A, refresh Inbox, mark read, open/start/complete
the job with a resolution, and refresh the manager detail.

Read-only verification command:

```powershell
docker compose --project-name fieldops-t05 exec -T db psql -U fieldops -d fieldops -c "WITH jobs AS (SELECT * FROM interventions WHERE title LIKE 'Browser %' ORDER BY created_at DESC LIMIT 4) SELECT j.id,j.status,j.row_version,(SELECT count(*) FROM intervention_history h WHERE h.intervention_id=j.id) AS history,(SELECT count(*) FROM notification_outbox o WHERE o.intervention_id=j.id AND o.status='delivered') AS delivered,(SELECT count(*) FROM notifications n WHERE n.intervention_id=j.id AND n.read_at IS NOT NULL) AS read_inbox FROM jobs j;"
```

The four verified jobs each had `completed`, row_version 5, five history records, one delivered
outbox and one read inbox record. Their IDs were b023d6ac-4b9f-471e-a75c-ad296e8d4238,
be479868-9b6d-42c7-ab9f-301acb25f5b0, cec6454d-153f-4d1c-a7b4-21dd09096cc0 and
67e442b3-ba74-4b8c-ac57-39b681b71228. Subsequent browser reruns create additional retained jobs.
Docker lifecycle regression independently verified persistence after restart/recreation and retained
volumes. Its twenty-notification benchmark delivered 20/20, all API-visible in 3.313s.

## Security and remaining limitations

- Existing eight-hour signed/database-revocable sessions, active-user checks and role restrictions
  are reused. Missing/invalid/expired/revoked identities receive visible 401; wrong-role/cross-user
  reads and mutations receive 403. Missing/wrong CSRF denies mutations before service calls.
- Direct HTML tests verify cross-technician detail/start denial, cross-recipient read denial,
  post-reassignment history-link suppression and stale direct-link denial, manager-only forms,
  stale edit/command 409 and invalid fields 422. Existing JSON/security/transaction regressions pass.
- Jinja autoescaping renders submitted HTML as text. No raw-safe filter is used for user data.
  Success notices are selected from a fixed mapping. Error feedback never renders exception inputs
  or SQL. Runtime CSRF tokens intentionally appear in hidden forms; session signing keys and raw
  session cookies do not. HTML responses are no-store with Cookie variation, CSP restricting
  scripts/styles/forms to self, frame denial, nosniff and same-origin referrer policy.
- Source scan of 82 nonignored files before this validation file found no private-key/token patterns
  or runtime environment/database files. Runtime checks captured web/worker logs in memory and
  verified the generated database password and signing key were absent without printing either.
- Demo persona selection is explicitly labeled unsuitable for production identity authentication.
  Anyone can select public synthetic personas. Existing local DB-owner/shared credential-volume
  limitations remain; production authorization hardening/penetration testing is **NOT TESTED**.
- Inbox refresh is explicit, not realtime push. Live pagination can shift under writes. A link can
  become stale after rendering; its request is authorized again and safely denied. Existing worker
  lease/retry limitations remain as documented in T06; no worker controls or monitoring were added.
- Test databases, generated volumes, screenshots and synthetic jobs remain local. Browser tests are
  intended for a separately configured local demo, never production. Parallel runner behavior and
  production load are **NOT TESTED**. Existing application volumes were preserved.

## Issue #6 acceptance

| Acceptance criterion | Verdict | Evidence |
| --- | --- | --- |
| Dispatcher CRUD/assignment works | PASS | HTML create/edit/detail/list/assignment/reassignment/cancel adapters; shared domain regressions; browser create/edit/assign; no hard delete in contract |
| Technician inbox/start/complete works | PASS | Real worker delivery in browser; scoped persisted read and completion; PostgreSQL verification |
| Errors are visible | PASS | Browser invalid creation; HTML field, CSRF, session, 409 and completion negative cases; enhanced authentication error handling |
| Historical notifications cannot expose unassigned job details | PASS | No historical job link, direct stale URL 403, cross-technician denial |
| Desktop and 375px remain usable | PASS | Chromium journeys, associated labels, keyboard actions, overflow assertions and screenshots |
| Full-page fallback remains usable | PASS | Both viewport journeys with JavaScript disabled, ordinary forms and redirects |

## Final results and handoff

Final live browser run: **4 passed in 22.41s**, zero failed/skipped/deselected. Includes the
new revoked-session error visibility check during HTMX navigation and ordinary navigation.
Final unit rerun with `-p no:cacheprovider --basetemp=artifacts/t05-unit-final`:
101 passed, 211 deselected in 2.34s, no warning. Final source scan: 83 nonignored files,
no credential/runtime-file findings; the Git index remains empty.
Observed assignment-to-inbox visibility (including sign-in/navigation time, not a worker-only SLO):

| Viewport | JavaScript | Inbox visibility |
| --- | --- | --- |
| 1440×960 | Enabled | 0.922s |
| 375×960 | Enabled | 0.610s |
| 1440×960 | Disabled | 2.375s |
| 375×960 | Disabled | 2.000s |

| Suite | Passed | Failed | Skipped | Deselected in that invocation |
| --- | --- | --- | --- | --- |
| Standalone unit selection | 101 | 0 | 0 | 211 |
| Combined unit/PostgreSQL | 309 (101 + 208) | 0 | 0 | 3 |
| Docker lifecycle | 3 | 0 | 0 | 0 |
| Chromium browser | 4 | 0 | 0 | 0 |
| Distinct total (unit counted once) | **316** | **0** | **0** | Suite selection only |

The prior 290 tests are preserved and passed. `git diff --check`, Ruff lint/format and frozen lock
verification passed. The work remains uncommitted and unstaged on the T05 branch, with T06 HEAD
unchanged. No commit, push, merge, Issue closure, deployment, paid infrastructure or volume deletion
was performed. Local review URL: `http://127.0.0.1:18005/`.

Files: HTML adapter and main router/error/static integration; eight templates; custom CSS and
licensed pinned local assets; T05 HTTP/PostgreSQL tests and explicit browser suite; Jinja2/Playwright
manifest and lock additions; AGENTS, README, architecture, backlog, contract handoff and this evidence.
No model/migration/worker/business-service modifications were required.

Recommendation: **GO for independent review and subsequently owner-authorized T05 publication**
within the documented synthetic demo scope. Full accessibility certification and production
authentication/security are not claimed. Stop here for owner review; publication is not authorized.

## Independent end-to-end audit — 2026-11-10

Reviewed live [Issue #6](https://github.com/chakirou18/final-project-AIzoomcamp-2026/issues/6),
AGENTS.md, F01–F05/F10/N07, architecture, all eight templates, HTML adapters, local CSS/vendor
assets/licenses/hashes, manifest/lock changes, existing browser and PostgreSQL tests, and tracked
and untracked files. Branch is `feature/t05-web-interface`; HEAD and merge-base remain published
T06 `1253faaedd5b39aa9ee9da0330645e1b5667119b`. No earlier commit was rewritten. Auth, models,
migrations, worker and shared business-service files have no diff against T06.

### Actual execution and environment failure

Independent initial unit run: **101 passed, 211 deselected in 2.26s**. Original four browser cases
independently passed in **26.39s** on a separate `fieldops-t05-audit` stack (port 18015, subnet
10.247.0.0/24). No inference was made from the previous 316-test claim.

The initial combined regression run was interrupted when Docker Desktop/WSL became unresponsive.
Even `docker ps`, application liveness and WSL diagnostics stalled. Five added browser cases then
failed navigation before reaching their audit assertions (**5 failed, 159.05s**). That run provides
no layout/security acceptance evidence. The interrupted PostgreSQL run is **NOT COMPLETED**, not
counted as passing. `docker desktop restart` recovered the runtime; it interrupted local stacks
but preserved named volumes. Existing stacks resumed healthy. No volumes were deleted. The cause
of this local Docker/WSL outage was not established; it is not attributed to an application defect.
Completed suites after recovery were run sequentially to reduce local runner interference.

### Reproduced defects and isolated corrections

1. **Valid text overflow:** 160-character unbroken titles and 250-character sites overflowed detail
   and list layouts. A standalone CSS probe measured a 375px viewport expanding to 2,954px; this
   was only a diagnostic, not database evidence. Real PostgreSQL-backed browser cases subsequently
   reproduced overflow at both viewport sizes, with JavaScript on/off. `main { overflow-wrap:
   anywhere }` now keeps those valid values inside the viewport. Real boundary journeys pass.
2. **Private client history:** pinned HTMX 2.0.8 uses `sessionStorage` for its history snapshots
   (not the localStorage named in current upstream documentation). Authenticated HTML, including
   hidden form tokens, could persist in that cache and be redisplayed by Back after revocation.
   A browser assertion returning only a boolean reproduced the cache retention in **1 failed,
   1.79s** against the preserved pre-correction image. Disabled snapshots with `hx-history="false"`
   and `historyCacheSize: 0`; `refreshOnHistoryMiss: true` makes Back re-request a full authenticated
   page. Verified no HTMX snapshots in either storage and visible 401 after revocation plus Back.
   See [HTMX history guidance](https://htmx.org/attributes/hx-history/) and
   [configuration](https://htmx.org/docs/#config); the pinned asset was inspected directly.
3. **Error semantics:** standalone error pages duplicated the same text as an H2 before H1.
   They now render one H1 within an alert; ordinary field-error summaries remain intact.
4. **Empty-page feedback:** requesting a page beyond existing results implied no work or no inbox
   notifications existed. It now explicitly says no items are on this page and provides a first-page
   link that preserves filters. Zero-match filters retain their genuine empty-state explanation.

The recovered pre-correction reproduction run had **5 failed in 13.93s**: four overflow assertions
and one Back-after-revocation assertion. A first cache check examined localStorage alone and missed
the pinned version's sessionStorage; source inspection corrected this test assumption. The final
cache test waits deterministically for `htmx:afterSettle`, inspects both stores as booleans, and never
serializes cached HTML/tokens into reports. Minor import/format lint findings in new tests were fixed.
No lifecycle, permission, transaction, database schema or future-task functionality was added.

### Exact final commands

```powershell
$env:FIELDOPS_PORT='18015'
$env:FIELDOPS_SUBNET='10.247.0.0/24'
docker compose --project-name fieldops-t05-audit up --build --wait
docker compose --project-name fieldops-t05-audit config --quiet

$env:FIELDOPS_BROWSER_URL='http://127.0.0.1:18015'
.venv/Scripts/python.exe -m pytest browser_tests -v -s -p no:cacheprovider --tb=short --junitxml=artifacts/t05-audit-browser.xml
# 11 passed in 53.76s; 0 failed/skipped/deselected.

docker compose --project-name fieldops-t05-audit --profile test run --build --rm tests
# 324 passed (101 unit + 223 real PostgreSQL), 3 deselected in 81.88s.
# 0 failed/skipped. The 3 Docker tests run separately below.

$env:FIELDOPS_RUN_CONTAINER_TESTS='1'
.venv/Scripts/python.exe -m pytest tests/test_container_lifecycle.py -v -s -p no:cacheprovider --junitxml=artifacts/t05-audit-container.xml --tb=short
# 3 passed in 107.28s; 0 failed/skipped/deselected.

.venv/Scripts/python.exe -m pytest -m 'not integration and not container' -q -p no:cacheprovider --basetemp=artifacts/t05-audit-unit-corrected
# 101 passed, 226 deselected in 1.89s; unit tests also passed in the combined run.
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m ruff format --check .
uv --cache-dir .cache/uv lock --check
git diff --check
git status --short
```

Lint, formatting and 38-package lock consistency passed. No previous test was removed or weakened.
Fifteen additional PostgreSQL tests exercise direct HTML role/scope denials, missing/wrong/other-session
CSRF, and unauthenticated mutations, comparing complete intervention snapshots and exact history/
outbox counts before and after. Test data remains in separate UUID-named `_test` databases. No SQLite
or mocked delivery substitutes for PostgreSQL evidence. Lifecycle fixtures retain volumes and select
free host ports/subnets; a short free-port selection race and host-network dependencies remain.

### Browser journeys and actual persisted state

Seven new browser cases augment the original four:

- Four boundary-field journeys (1440×960/375×960, JavaScript enabled/disabled) create and edit work,
  assert escaped HTML, submit a second stale edit tab and see HTTP 409 with retained values, assign A,
  repeat the same assignment without changing the JSON snapshot/version, wait for real delivery,
  mark read twice/reload with an unchanged read timestamp, reassign B, verify A's historical item has
  no job link, deny A's direct detail/start requests, then start/complete as B and verify the manager's
  HTTP 200 completed detail. Filters and one-item pagination remain usable.
- One synchronized history-cache/revocation/Back check verifies both client storage and visible 401.
- Two viewport cases check zero-match filters, out-of-range page recovery, one H1/main, English
  document language and a keyboard-focused skip link with an actual solid 3px outline.

All eleven final cases passed. Overflow assertions cover long valid values, not just short fixtures.
The original four still exercise invalid creation feedback, keyboard Tab/text/Enter submission,
real worker inbox delivery, completion, enhanced HX requests and full-page no-JavaScript fallbacks.
Cards replace wide tables; no horizontal document overflow was observed on tested pages.

Read-only SQL was executed using:

```powershell
docker compose --project-name fieldops-t05-audit exec -T db psql -U fieldops -d fieldops -c "WITH jobs AS (SELECT * FROM interventions WHERE title LIKE 'Audit-%' AND status='completed' ORDER BY created_at DESC LIMIT 4) SELECT j.id,j.status,j.row_version,(SELECT count(*) FROM intervention_history h WHERE h.intervention_id=j.id) AS history,(SELECT count(*) FROM notification_outbox o WHERE o.intervention_id=j.id AND o.status='delivered') AS delivered,(SELECT count(*) FROM notifications n WHERE n.intervention_id=j.id) AS inbox,(SELECT count(DISTINCT n.outbox_id) FROM notifications n WHERE n.intervention_id=j.id) AS unique_events,(SELECT count(*) FROM notifications n WHERE n.intervention_id=j.id AND n.read_at IS NOT NULL) AS read_inbox FROM jobs j;"
```

All four rows were completed/version 6, history 6, delivered events 2, inbox 2, unique originating
events 2, read inbox 1. IDs: `6c2107c0-dfe2-4dc9-ba5b-f5f4b679de82`,
`a15b8525-3e7f-4941-b51c-2482d2810e3f`, `e2b2fae0-dd0c-4122-bfca-5ecd1c9771f4`,
`16df061e-314b-4bcb-ba48-211486a20ddc`. Creation, edit, two effective assignments, start and
completion explain the six events; the same-assignee no-op added none. Inbox uniqueness was verified
in SQL, in the UI and by the retained T06 PostgreSQL regressions.

### Screenshots, accessibility and data safety

Generated ignored evidence, visually inspected during this audit:

- `artifacts/t05-audit-boundary-375-True.png`: long title/site wrap, escaped HTML text, all controls fit.
- `artifacts/t05-audit-conflict-1440-True.png`: visible 409 summary, recovery link and retained form.
- `artifacts/t05-audit-historical-inbox-375-True.png`: historical read notifications lack job links.
- `artifacts/t05-audit-empty-focus-375.png`: mobile filters, empty state and visible skip-link outline.

Other viewport/JavaScript variants use the same filename prefixes; `t05-audit-filtered-*` captures
the final filtered queue. Original create/inbox/completed screenshots were freshly regenerated too.
Reproduce with the exact browser command above against a local demo; it creates retained synthetic
jobs. No human-operated demonstration is claimed beyond inspecting the executed browser screenshots.

HTML labels, required markers, alert feedback, semantic navigation, native controls/details,
keyboard actions and focus were checked. This is not full WCAG certification: screen-reader,
axe, Firefox/Safari, zoom, exhaustive contrast and assistive-technology combinations remain
**NOT TESTED**. Native long input values scroll inside their controls while the page stays contained.

Token-safe in-memory checks used a standard-library cookie jar to log into port 18015, captured the
generated prelogin/session cookies and CSRF, and read the generated DB password/signing key through
`docker compose ... exec -T web cat /run/fieldops/{db_password,session_key}` without printing values.
None appeared in captured `docker compose ... logs --no-color web worker`; keys and cookie values
were absent from rendered HTML (CSRF is intentionally in hidden inputs). Five audit XML files were
scanned for those values and serialized hidden CSRF inputs: clean. Reports expose only synthetic
IDs and boolean cache results, not storage contents. Screenshots show synthetic personas/data only.
The 85-file nonignored source scan found no private-key/GitHub-token/AWS-key patterns or runtime
`.env`/database/key files. No credentials or runtime data are staged; index remains empty.

### Acceptance after independent audit

| Issue #6 criterion | Verdict | Actual evidence |
| --- | --- | --- |
| Dispatcher CRUD/assignment works | PASS | Real browser create/edit/assign/reassign; stale 409/no-op; PostgreSQL history/outbox checks; cancellation HTTP regression. No hard delete exists in the specification. |
| Technician inbox/start/complete works | PASS | Independent A/B contexts, actual worker, persistent read, B completion and manager refresh/API check |
| Errors are visible | PASS | Browser invalid creation, stale edit, revoked session and Back; HTTP 401/403/409/422 negative suites |
| Historical notifications cannot expose unassigned details | PASS | No historical link, direct A detail/start denied after B reassignment; correct persisted recipient mappings |
| Desktop and 375px usable | PASS | Real Chromium screenshots, valid boundary text, keyboard/focus/semantics/empty states and overflow assertions |
| Full-page fallback usable | PASS | Both original and reassignment journeys at both sizes with JavaScript disabled |

Remaining limits: synthetic demo authentication, local DB-owner/shared credential-volume design,
explicit inbox refresh, shifting live pagination, local runner/network reliability and inherited
worker lease/retry limits. Production security/load, complete accessibility, and browser-native
cache behavior across every browser/device are **NOT TESTED**. An already executing request or
an already displayed page is not retroactively erased by logout; further requests are authorized.
No T07/T08 or later implementation, commit, push, merge, Issue closure, deployment, purchase or
Docker volume deletion was performed.

### Final audit result

| Final verification | Passed | Failed | Skipped | Deselected |
| --- | --- | --- | --- | --- |
| Standalone unit selection | 101 | 0 | 0 | 226 |
| Combined unit + PostgreSQL | 324 (101 + 223) | 0 | 0 | 3 |
| Docker lifecycle | 3 | 0 | 0 | 0 |
| Chromium browser | 11 | 0 | 0 | 0 |
| Distinct total, counting units once | **338** | **0** | **0** | Complementary suite selections only |

Docker lifecycle: **3 passed in 107.28s**. Its real-network worker benchmark delivered 20/20,
all recipient-API-visible in **3.297s**, maximum per-assignment HTTP-observed latency **3.062s**,
maximum DB-recorded latency **2.945867s**, one worker polling every two seconds.
The earlier focused Back/revocation reproduction also failed in 7.23s before the cache test was
corrected to inspect both storage locations; its final successor passes with the other browser cases.

Final Ruff lint, format (61 discovered Python files), lock consistency, Compose configuration and
`git diff --check` passed. Generated evidence remains ignored. Git index is empty; all T05 work
is uncommitted, including the preexisting implementation. T06 HEAD/merge-base remain unchanged.

Audit corrections affect `fieldops/web.py`, `fieldops/static/app.css`, base/error/list/inbox templates,
new `tests/test_t05_review.py` and `browser_tests/test_t05_review.py`, and this validation file.
No earlier implementation work was discarded. Private browser history tests use fresh contexts;
old pre-correction demo tabs/storage were not remotely purged. Close those tabs or clear their
site storage before reviewing the new build. No browser cache is a substitute for server authorization.

**Audit verdict: PASS. GO for separately owner-authorized T05 publication within the documented
demo scope.** No unresolved T05 authorization or workflow defect was found after corrections.
Review the corrected local stack at `http://127.0.0.1:18015/`; the prior port-18005 stack was
preserved and was used only for pre-correction reproduction. Stop for owner approval; do not commit
or publish on the authority of this audit.

## Pre-publication verification — 2026-11-10

Read AGENTS.md and live Issue #6; confirmed repository, clean index before staging, T05 branch,
HEAD/merge-base at T06 `1253faaedd5b39aa9ee9da0330645e1b5667119b`, and matching published remote
T06 HEAD. No remote T05 branch/PR existed before publication. Reviewed all 28 required changed/new
files, including local asset licenses/hashes and both browser suites. No application/test change
was made during publication preparation; only current authorization/handoff documentation and
one trailing blank line in CSS changed.

Fresh commands:

```powershell
.venv/Scripts/python.exe -m pytest -m 'not integration and not container' -q -p no:cacheprovider --basetemp=artifacts/t05-publication-unit
# 101 passed, 226 deselected in 2.45s; zero failures/skips.
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m ruff format --check .
uv --cache-dir .cache/uv lock --check
git diff --check
git status --short
```

All quality checks passed (61 Python files formatted; 38 locked packages). The complete independently
executed audit remains **338 distinct passing tests: 101 unit, 223 PostgreSQL, 3 Docker, 11 Chromium**;
the fresh unit rerun is not counted again. PostgreSQL/Docker/browser evidence and limitations above
remain applicable to the unchanged implementation. No claim of a second full-suite run is made.

Repeated source scan: 85 nonignored files, no credential/private-key/runtime-file findings. Vendor
SHA-256 values still match. Six audit XML reports passed the hidden-token check. Re-inspected the
mobile focus screenshot: only synthetic identities/data are visible. Prior audit checked the generated
keys/cookies/CSRF against captured logs and report contents without printing values. Screenshots,
XML, caches and local environment/database data remain ignored and excluded from the commit.

Staged whitespace review found one extra blank line at the end of the new CSS file; removed it.
This was invisible to the earlier unstaged check because that file was still untracked.
