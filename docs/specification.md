# Product specification

Status: proposed T01 baseline, 2026-11-09. Requirement IDs are stable references for backlog tasks, tests and evidence. All acceptance criteria below are targets, not completed results.

T03 implementation note: persistence, synthetic identities, session/CSRF infrastructure and draft lifecycle schemas exist locally; full F01 through F05/F10 workflows remain future T04 through T06 work. [T03 contracts](t03-contracts.md) records the implemented boundary and [validation](t03-validation.md) records actual evidence.

## Users, assumptions and boundaries

Dispatchers manage jobs; technicians work assigned jobs; operators run the reliability demonstration. Assume one company per environment, distinct development/production deployments, fewer than 20 technicians and at most 1,000 interventions in each demonstration dataset. Use synthetic addresses and descriptions only. Seeded personas with signed sessions and server-side role checks replace account registration; this is a demonstration access model, not production identity management.

Owner decision, 2026-11-09: managers use the dispatcher role and a separate demo identity from technicians; all demonstration data is synthetic. The paused-worker scenario and authenticated/audited allowlisted On-Call actions are approved. This does not authorize application development, provisioning or purchasing model access.

One intervention has at most one current technician. Reassignment creates a new assignment version and notification; old notifications remain historical and clearly show their assignment version. An in-app notification is delivered when its inbox row is committed. It is read only after a separate user action. All timestamps use database-generated UTC and render with an explicit timezone.

## Functional requirements and acceptance criteria

| ID | User story / requirement | Measurable acceptance criteria |
| --- | --- | --- |
| F01 | As a dispatcher, register, list, view and edit jobs. | Title (1–160 characters), description (max 4,000), site (1–250), priority and optional technician persist across restart. Invalid input returns 422 with field feedback. Unknown IDs return 404. List supports pagination (25 default, 100 maximum) and status, priority and technician filters. |
| F02 | As a dispatcher, assign or reassign work. | Only active technicians are accepted. Assignment to an open job changes status to assigned. Reassignment of assigned work changes its version; in-progress and terminal jobs cannot be reassigned. Each effective assignment atomically writes job, history and exactly one outbox event. Repeating the same current assignment is a no-op. |
| F03 | As a technician, start and close work. | Allowed transitions: open → assigned or cancelled; assigned → in_progress or cancelled; in_progress → completed or cancelled. completed and cancelled are terminal. Completion requires a nonblank resolution (max 4,000). Unlisted transitions return 409 without mutations. No reopen or unassign operation. |
| F04 | As a dispatcher, prioritize work and inspect history. | Priorities are low, medium, high, urgent (default medium). Every creation, effective edit, assignment and status transition has one append-only history record with actor, UTC time and changed fields. created_at, updated_at, started_at and closed_at reflect the corresponding operations. Stale version updates return 409. |
| F05 | As a technician, receive persistent assignment notifications. | A successful assignment response implies durable outbox persistence, even during worker pause. Inbox is scoped to its recipient. Delivered items survive process restarts. Mark-read is idempotent. Existing unread items remain visible during worker failure. |
| F06 | As an operator, see status and delivery impact. | Dashboard shows counts for all five statuses, unfinished total (open + assigned + in_progress), undelivered outbox total and oldest undelivered age, including pending, processing and failed rows. Counts match database fixtures. A notification older than 60 seconds is labeled delayed. Empty queue age is zero. |
| F07 | As an operator, detect delivery delay automatically. | Prometheus evaluates oldest undelivered age >60 seconds with undelivered count >0 for 30 seconds; scrape/evaluation interval 5 seconds. With monitoring healthy, a paused-worker assignment reaches the authenticated alert receiver within 110 seconds. HTTP liveness alone never represents delivery success. |
| F08 | As an operator, recover safely and review the incident. | Demo pause produces a real queue delay; Alertmanager webhook creates/deduplicates an incident. Agent gathers telemetry, identifies paused worker, requests one bounded resume action, then verifies the incident's pending event IDs were delivered and backlog drains. Replayed webhook/action produces no duplicate effect. Verification has a 120-second deadline and records unresolved failures for human review. |
| F09 | As a reviewer, inspect API and health contracts. | OpenAPI documents JSON endpoints and errors; /health/live reports process availability; /health/ready fails when PostgreSQL is unavailable. Worker heartbeat is visible separately. Sensitive metrics, control endpoints and telemetry are inaccessible to public clients. |
| F10 | As a user, see only permitted operations. | Dispatcher creates/edits/assigns/cancels; technician sees own assigned jobs and inbox and starts/completes own jobs; operator sees dashboard/incidents and demo controls. Wrong-role requests return 403. No unauthenticated mutation; HTML forms use CSRF protection. |

## Contract clarifications

- Creation without a technician yields open status and assignment_version=0. Creation with a technician uses the same assignment service inside the creation transaction, yields assigned/version=1, and writes a creation history record plus an assignment history record and one outbox event. Each records its distinct event type.
- PATCH edits title, description, site and priority only, and only on open/assigned jobs. Assignment/status use dedicated commands; all edits to in_progress/completed/cancelled jobs return 409. Assignment to the same technician is a no-op only after the supplied row_version passes its concurrency check.
- open requires no technician; assigned/in_progress/completed require a technician. Cancellation preserves the prior technician if present. started_at is set once on start; closed_at is set once on completion/cancellation. Cancellation does not require a resolution. No hard delete endpoint exists.
- Technicians retain their own historical inbox notifications after reassignment but cannot open or mutate jobs no longer assigned to them; those inbox entries show a historical summary and unavailable job link. Dispatcher can view all jobs/history; technician can view history only for a currently assigned job. Operator has global dashboard/incident access, not dispatcher mutation privileges.
- All business reads require a session. Seeded persona selection is a demo convenience, not proof of a person's identity; signing a cookie does not change that limitation. Operator persona activation requires an environment-configured operator secret and is not offered by the unrestricted persona selector. Public technician/dispatcher data remains synthetic. Cookies are HttpOnly, Secure over HTTPS and SameSite=Lax; logout invalidates the session, with an 8-hour maximum lifetime. F10 permission tests cover direct JSON and HTML requests, not just hidden buttons.
- A resolved incident requires a recorded successful authorized recovery action for its pause generation **and** delivery verification. A model explanation, spontaneous drain, pause auto-expiry or Alertmanager resolved message is insufficient; record externally_recovered/escalated instead, with no autonomous recovery credit.

The owner-approved incident demonstration intentionally stops the worker's delivery loop through a controlled pause. It does not terminate the process/container; that distinct failure is diagnostic/escalation coverage only. It must cause genuine user-visible impact: after successful assignment, the recipient's inbox lacks the affected notification for more than 60 seconds while the durable outbox event remains undelivered. Browser/API evidence must show that absence before repair and the same event's inbox notification after repair. Fabricated latency, a simulated explanation and spontaneous recovery never count as a successful agent repair.

## Nonfunctional requirements

| ID | Target and verification |
| --- | --- |
| N01 Reliability | Assignment rollback leaves neither history nor outbox fragments; crash after inbox insertion produces one visible notification after retry. Prove using PostgreSQL integration tests and injected failures. |
| N02 Delivery | With one worker polling every 2 seconds and no injected fault, all 20 assignments in a local test become visible within 10 seconds each. Report host and measured results; this is a demo SLO, not a production guarantee. |
| N03 Performance | On a documented single-host configuration with 1,000 seeded jobs and five concurrent clients, list/detail p95 <1 second over 50 requests, excluding external model calls. |
| N04 Security | Secrets come from environment/CI secret storage, never git or logs. Parameterized database access, escaped templates, role checks, CSRF and bounded input apply. Agent has no shell, filesystem, Docker socket or arbitrary URL tool. |
| N05 Operability | Persist W3C traceparent/tracestate with the assignment outbox event; worker extracts that parent so HTTP, outbox insert, delivery and inbox insert spans share one trace ID. T09's correlated-journey test checks parentage and structured web/worker logs; no trace IDs appear as metric labels. Queue gauges and incident records support investigation. Telemetry failures cannot block assignment commits. |
| N06 Reproducibility | Clean checkout has the four proposed single-command Compose workflows in README, implemented and verified for application, full stack, combined unit/integration tests and browser tests. Startup orders readiness, migrations and idempotent synthetic seed. CI runs unit, PostgreSQL integration and browser checks before automatic development deployment on validated main; production promotion is manual with an approval gate and separate DB. |
| N07 Usability | Key journeys work at desktop and 375px width with labels, keyboard-operable forms and visible errors. HTMX actions retain usable full-page form fallbacks. |

## Scope and release gate

MVP includes only the requirements above, a seeded persona login, one notification channel, a controlled paused-worker incident with real delayed delivery, one bounded recovery action and a single-host Compose deployment model per environment. Development and production are distinct environments with separate databases/credentials/volumes; they may share one suitably sized host, subject to measured capacity and isolation. Release requires positive and negative permission tests, transactional outbox tests, the create→assign→start→complete browser journey, a correlated trace journey, automatic development deployment evidence, manual production promotion evidence, deployed persistence smoke test and a recorded successful recovery.

Excluded: real customer data, multi-tenancy, customer portal, payments, scheduling optimization, geolocation/maps, attachments, mobile app, external messaging, password reset, SSO, high availability, autoscaling, Kubernetes, arbitrary remediation, autonomous code deployment and unrestricted agent execution. No chat assistant is required for intervention CRUD.

## Unresolved product decisions

- P01: owner must confirm the applicable course rubric version; supplied 24-point scope is the planning baseline.
- P02: approved separate manager/technician demo identities and synthetic disposable data. Operator-secret, session and route-level access checks remain required implementation criteria; real production authentication is outside MVP.
- P03: confirm hosting budget, hostname and provider before deployment; no purchase is authorized.
- P04: identify an already available/no-purchase model provider and approved credentials before T11; API purchases are prohibited. The runtime agent must perform real constrained model-assisted diagnosis; deterministic tests alone are not evidence. If existing access is unavailable, record a blocker rather than purchase access or claim a simulated repair.
- P05: latency thresholds are accelerated demonstration values; production service objectives need real workload data.
