> T06 local implementation update: all published intervention, technician-list and JSON notification inbox/read contracts below now have handlers. The inbox is recipient-scoped, mark-read is idempotent, and historical ID/version summaries do not confer job access. HTML inbox UI remains unimplemented. See [T06 validation](t06-validation.md). Historical T03 implementation-status claims below describe that baseline.

# T03 schema, session and API contracts

Task: [Issue #3](https://github.com/chakirou18/final-project-AIzoomcamp-2026/issues/3); requirements F01–F05/F09/F10 and N01/N04/N06. T03 defines persistence and future workflow contracts. It implements session infrastructure only; no intervention CRUD, transition service, inbox delivery or worker endpoint exists.

## Persistence

`fieldops/models.py` defines six tables: users, interventions, intervention_history, notification_outbox, notifications and persona_sessions. Static revision `0001_t03.py` establishes the tables; corrective revision `0002_t03_review.py` rejects whitespace-only required text, including tabs/newlines. Neither imports mutable application metadata. Existing valid data is retained; invalid preexisting rows cause migration failure without automatic rewriting. `migrations/env.py` supplies metadata for structural drift checks; CHECK rules and triggers are verified separately.

- User role values are dispatcher, technician and operator. Manager is a product name for dispatcher. persona_key is unique; stable UUIDs identify four synthetic personas. Seed inserts missing identities and never silently reactivates or overwrites existing ones.
- Interventions have bounded title/site/description/resolution; four priority and five status values; positive row_version, nonnegative assignment_version; status/assignee/start/close/completion consistency checks. Composite user/role FKs restrict assignees to technicians. Database timestamps use timestamptz with database defaults and UTC connection settings.
- History requires valid intervention/actor FKs and an object-valued JSONB changes record. A PostgreSQL trigger rejects updates/deletes. This is application audit protection, not tamper-proof storage against the database owner.
- Outbox uniqueness is intervention_id + assignment_version + event_type. Event type is assignment. Recipient must be a technician. Attempts are 0–5; processing requires a lease token/deadline and a consumed attempt; nonprocessing states clear leases; delivered state requires delivered_at. Trace context fields are persisted for T09, without claiming tracing is implemented.
- Inbox outbox_id is unique. A composite FK binds recipient, intervention and assignment version to the originating outbox event, so another recipient cannot be substituted. Historical rows can survive reassignment. No cascade deletion is configured.
- Sessions store only a SHA-256 digest of the random cookie token, a user FK, CSRF token, creation/expiry and optional revocation timestamp. Signing keys and raw cookie tokens are not stored in the database. Session and CSRF values are runtime data, never source fixtures.

Active-technician checks at assignment time, legal transitions, concurrency/version increments, and atomic job/history/outbox writes are T04 service responsibilities. Schema constraints cannot prove that an assignment wrote all required rows atomically. Inbox materialization, fencing and worker retry behavior remain T06. No worker-control/incident/recovery tables were added.

## Executable lifecycle contract

GET `/contracts/openapi.json` returns generated OpenAPI with Pydantic request/response/error schemas and JSON examples. It explicitly declares x-implementation-status=contracts-only and marks every operation x-implemented=false. It is separate from the live `/openapi.json` and `/docs`, which describe available health/session/contract routes. T03 does not register the draft lifecycle handlers.

| Contract | Fields / behavior |
| --- | --- |
| Create | title trimmed 1–160; site trimmed 1–250; description default empty, max 4000; priority low/medium/high/urgent, default medium; optional UUID technician_id. Extra/server-owned fields rejected. |
| Edit | Required strict integer expected_version >=1, plus at least one nonnull title/description/site/priority. Explicit empty description is allowed; null/empty edit and technician/status fields are rejected. |
| Assignment | Required UUID technician_id and strict expected_version >=1. T04 validates active technician and eligibility; same-assignee no-op follows version check. |
| Transition | Required expected_version and target_status in_progress/completed/cancelled. Completion requires nonblank resolution <=4000; resolution rejected on other commands. T04 checks role, current state and assignment. |
| Intervention response | UUID id, title/description/site, priority/status, technician_id, assignment_version, row_version, resolution, aware created_at/updated_at/started_at/closed_at. Server controls state/versions/timestamps. |
| History | UUID id/intervention_id/optional actor_id, event_type, changed_fields object, aware created_at. Append-only and currently-assigned scope. |
| Inbox | UUID id/outbox_id/intervention_id, assignment_version, historical_assignment, summary, aware created_at/delivered_at/read_at. Historical summary does not confer access to a reassigned intervention. |
| Pagination | page >=1, default 1; page_size 1–100, default 25; response items/page/page_size/total. Intervention filters: status, priority, technician_id. Scope before pagination; created_at DESC, id DESC. |

| Draft operation | Success | Permission |
| --- | --- | --- |
| GET /api/v1/interventions and /interventions/{id} | 200 | Dispatcher all; technician currently assigned only |
| POST /api/v1/interventions | 201 | Dispatcher |
| PATCH /api/v1/interventions/{id} | 200 | Dispatcher, open/assigned |
| POST /api/v1/interventions/{id}/assignment | 200, including no-op | Dispatcher, open/assigned |
| POST /api/v1/interventions/{id}/transitions | 200 | Technician starts/completes own job; dispatcher cancels |
| GET /api/v1/interventions/{id}/history | 200 paginated | Dispatcher or currently assigned technician |
| GET /api/v1/technicians | 200 | Dispatcher; active technicians only |
| GET /api/v1/notifications | 200 paginated | Technician, recipient only |
| POST /api/v1/notifications/{id}/read | 204 | Technician, recipient only; idempotent |

All business reads require a valid session. JSON mutations require session AND X-CSRF-Token, explicitly represented as a combined OpenAPI security requirement. Planned failures: 401 missing/expired/revoked identity; 403 role/scope/CSRF; 404 unknown resource; 409 stale version/illegal lifecycle operation; 422 invalid input; 503 unavailable database. No hard-delete/reopen/unassign operation exists.

Errors use `{"error":{"code":"validation_error","message":"Invalid request fields","fields":{"body.persona_id":["Invalid value"]}}}`. Available routes adapt validation errors without echoing invalid input, exception context or secrets. Future T04 errors must use the same envelope. Text is trimmed/length-validated but HTML escaping remains the renderer's responsibility.

## Session and authorization boundary

Available routes:

| Route | Behavior |
| --- | --- |
| GET /auth/personas | Demo-enabled only; active dispatcher/technician identities, never operator |
| GET /auth/csrf | Demo-enabled only; returns login token and signed HttpOnly prelogin cookie (10-minute browser max-age) |
| POST /auth/login | JSON persona_id and optional operator_secret; signed prelogin cookie plus matching X-CSRF-Token required; returns persona and session CSRF token |
| GET /auth/session | Requires signed, unexpired, unrevoked session and active user; returns persona + CSRF token |
| POST /auth/logout | Session + CSRF header; 204, database revocation and cookie deletion |
| GET /session | Minimal authenticated HTML identity/logout form; no application UI |
| POST /session/login | URL-encoded persona_id, optional operator_secret and csrf_token; same service/gates, 303 |
| POST /session/logout | URL-encoded csrf_token; same revocation service, 303 |

Cookies are HttpOnly, SameSite=Lax, path=/, host-only. Session max-age is 8 hours; server checks expiry, age, revocation and active user on every authenticated request. HTTPS requests and all nonlocal environments set Secure; local HTTP is a deliberate development exception. Identity rotation revokes the previous valid session. Authentication/session responses use Cache-Control: no-store. HTML mutation parsing is bounded to 4096 bytes and rejects duplicate fields; database work runs off the event loop.

Operator activation requires a configured FIELDOPS_OPERATOR_SECRET of at least 32 characters, compared in constant time; missing, weak or wrong values deny access. Demo login is opt-in via FIELDOPS_DEMO_MODE (enabled in local Compose); outside that configuration it is disabled by default. Signing key comes from one FIELDOPS_SESSION_SECRET or FIELDOPS_SESSION_SECRET_FILE source, minimum 32 characters. Compose generates/reuses a separate random session_key file alongside its database password. A shared protected volume is local bootstrap storage, not production secret management.

The unrestricted synthetic persona selector is intentionally not proof of a person's identity. Anyone using that demo can select another public demo persona. Authorization means enforcing the selected session's role/recipient scope; this is not production account authentication. Operator cannot bypass its separate secret gate.

`fieldops/permissions.py` shares deny-by-default role and query-scope helpers. Dispatcher can read interventions; technicians can read currently assigned interventions and their own inbox. Operators cannot use dispatcher/technician business privileges. Real PostgreSQL tests verify that A retains its historical inbox after reassignment to B but loses job access. Direct JSON/HTML role denials are tested through test-only adapters using the shared dependencies; these adapters are not shipped application routes. Real business-route checks remain T04/T05 acceptance work.

Local `bootstrap all` migrates and idempotently seeds identities. Nonlocal `all` migrates only; `seed` refuses nonlocal settings unless explicitly invoked with `--allow-nonlocal`. This flag is not authorization to seed any actual production database. No jobs, notifications, business data or passwords are seeded.

Audit clarification: live OpenAPI documents the enforced cookie/header pairs and HTML form inputs. Draft command JSON schemas express nonnull edits, permitted transition targets and conditional completion resolution. Internal model-validation bugs produce 500; malformed client forms/JSON produce the sanitized 422 envelope. No lifecycle endpoint was added.
