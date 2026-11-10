> T07 publication update: independent audit PASS (392 distinct tests). Owner authorized feature-branch commit/push, PR against T05 and Issue #7 progress comment only. No merge, closure, T08 or later work or deployment is authorized. See [T07 validation](t07-validation.md).

> T07 current local implementation: PostgreSQL-backed operator dashboard, generation-scoped shared/exclusive worker gate, separate heartbeats and append-only pause/resume audit/results are implemented. Local testing only from T05 `6460870`; no commit/push, future phases or deployment authorized. See [T07 validation](t07-validation.md). Historical status notes below describe earlier baselines.

> Current task: **T05 / Issue #6 feature-branch publication only**, based on published T06 `1253faa`. The owner authorized one commit, non-force push, a PR targeting feature/t06-notification-worker and an Issue #6 progress comment. No merge, Issue closure, T07 or later implementation, deployment, spending or volume deletion is authorized. See [T05 validation](t05-validation.md). Historical status notes below describe earlier phases.

> Current authorization (2026-11-10): T06 / [Issue #5](https://github.com/chakirou18/final-project-AIzoomcamp-2026/issues/5) feature-branch publication only, based on published T04 f272f5c. The owner authorized one commit, non-force push, a PR targeting feature/t04-intervention-lifecycle and an Issue #5 progress comment. No merge, Issue closure, T05 or later implementation, deployment, spending or volume deletion is authorized. [T06 validation](t06-validation.md) supersedes historical task-status snapshots below.

# Delivery backlog and proposed GitHub Issues

Current task update: **T03 / [Issue #3](https://github.com/chakirou18/final-project-AIzoomcamp-2026/issues/3) passed independent audit; feature-branch publication is authorized**, with a PR from feature/t03-schema-contracts to feature/t02-foundation and an Issue progress comment. [T03 validation](t03-validation.md) records 112 passing tests. T02 PR #16 remains open/unmerged. Historical authorization/status snapshots below are superseded; no T04 implementation, merge, Issue closure, deployment, spending or Docker volume deletion is authorized.

Publication authorization, 2026-11-09: owner approved T01 documentation commit/push and duplicate-safe creation of T01–T15 Issues. Manager/technician identity separation, synthetic data, paused-loop incident and authenticated/audited recovery are decided. Historical approval warnings below remain phase gates for implementation/deployment, not a request to reconfirm this publication. No T02 implementation, deployment, paid provisioning or API purchase is authorized. Public Issue URLs are indexed below; task IDs are never assumed to equal Issue numbers.

Revised estimate: **62 engineering hours of remaining planned work + 16 hours contingency = 78 hours**, with a planning range of **58–117 hours including contingency**. This supersedes the former 19.5-hour allocation/20-hour constraint. Already-spent T01 time is unmeasured and must be added separately to report total project effort; T01 below has zero estimated remaining execution hours after this correction, pending final review. Maximum rubric coverage is the priority. Estimates are not completed time or promises. All 15 reviewed Issues have been published and verified OPEN; none is automatically complete merely because it exists. Reference requirement IDs in [specification.md](specification.md).

Audit history: [T01 review](t01-audit.md); current [readiness summary](t01-readiness.md); detailed local [Issue drafts](github-issue-drafts.md). The historical audit's 20-hour statements are superseded, not evidence of actual time. T01 remains in review; all other tasks remain proposed. Hours below are most-likely remaining estimates, excluding the separate contingency reserve.

## Public Issue index

Verified 2026-11-09: 15 unique OPEN Issues in the public repository, with exact draft titles/bodies, real dependency links and immutable published-document references. T01 remains open for acceptance review; T02–T15 have not started. GitHub numbering differs for T05/T06 because the worker dependency was published first.

| Local task | Public Issue | State |
| --- | --- | --- |
| T01 | [#1](https://github.com/chakirou18/final-project-AIzoomcamp-2026/issues/1) | OPEN — documentation published, acceptance review pending |
| T02 | [#2](https://github.com/chakirou18/final-project-AIzoomcamp-2026/issues/2) | OPEN — published at 24bde69; PR #16 open/unmerged |
| T03 | [#3](https://github.com/chakirou18/final-project-AIzoomcamp-2026/issues/3) | OPEN - audit PASS; publication authorized; PR review pending |
| T04 | [#4](https://github.com/chakirou18/final-project-AIzoomcamp-2026/issues/4) | OPEN — not started |
| T06 | [#5](https://github.com/chakirou18/final-project-AIzoomcamp-2026/issues/5) | OPEN — not started |
| T05 | [#6](https://github.com/chakirou18/final-project-AIzoomcamp-2026/issues/6) | OPEN — not started |
| T07 | [#7](https://github.com/chakirou18/final-project-AIzoomcamp-2026/issues/7) | OPEN — not started |
| T08 | [#8](https://github.com/chakirou18/final-project-AIzoomcamp-2026/issues/8) | OPEN — not started |
| T09 | [#9](https://github.com/chakirou18/final-project-AIzoomcamp-2026/issues/9) | OPEN — not started |
| T10 | [#10](https://github.com/chakirou18/final-project-AIzoomcamp-2026/issues/10) | OPEN — not started |
| T11 | [#11](https://github.com/chakirou18/final-project-AIzoomcamp-2026/issues/11) | OPEN — not started |
| T12 | [#12](https://github.com/chakirou18/final-project-AIzoomcamp-2026/issues/12) | OPEN — not started |
| T13 | [#13](https://github.com/chakirou18/final-project-AIzoomcamp-2026/issues/13) | OPEN — not started |
| T14 | [#14](https://github.com/chakirou18/final-project-AIzoomcamp-2026/issues/14) | OPEN — not started |
| T15 | [#15](https://github.com/chakirou18/final-project-AIzoomcamp-2026/issues/15) | OPEN — not started |

## Implementation plan

| Phase / task | Proposed Issue title | Hours | Depends on | Measurable acceptance criteria | Expected reviewer evidence |
| --- | --- | ---: | --- | --- | --- |
| Planning T01 | Specify FieldOps MVP, architecture and evidence plan | 0 | — | Original requested docs, audit, drafts and final summary exist and agree. Owner review pending; past effort unmeasured. | Documentation diff and decision register. |
| Foundation T02 | Add reproducible FastAPI and PostgreSQL skeleton | 3 | T01 approval | Proposed base Compose command builds and waits for healthy web/DB with bootstrap dependency; readiness fails without DB. Business schema/seed land in T03. | Clean-checkout command output and restart check. |
| Foundation T03 | Define schema, API contracts and persona permissions | 4 | T02 | Migrations and idempotent synthetic seed run in local bootstrap; OpenAPI agrees with F01–F05/F10; role/session guards and version schemas tested. | Schema, OpenAPI, seed rerun and permission results. |
| Core T04 | Implement intervention lifecycle and transactional assignment | 5 | T03 | F01–F04 pass with atomic history/outbox, four priorities/five statuses and stale update rejection. | Unit/PostgreSQL rollback/concurrency tests and API examples. |
| Reliability T06 | Implement leased outbox worker and inbox persistence | 5 | T04 | F05/N01/N02 pass with actual PostgreSQL concurrent workers/crashes; one inbox row per event; persisted trace context fields preserved for T09 instrumentation. | Failure-injection results and 20-event timing report. |
| Core T05 | Deliver intervention UI and technician inbox | 4 | T04, T06 | Dispatcher/technician journeys work with errors, filters, role scope, keyboard/full-page fallback and 375px layout. | Screenshots, browser results and usability checklist. |
| Reliability T07 | Add dashboard, worker controls and health indicators | 3 | T05, T06 | F06/F09 counts include every undelivered state; generation-scoped pause/resume, atomic action audit and private access pass tests. | Fixture assertions, dashboard and negative API checks. |
| Quality T08 | Add critical unit, integration and browser coverage | 5 | T05, T06, T07 | Combined unit/integration and separate browser single-command runners pass; lifecycle, retry/restart, N03 benchmark and N07 checks recorded. | Runner commands/results, benchmark and browser artifacts. |
| Operations T09 | Wire metrics, logs, traces and Grafana | 6 | T07 | Full observability profile works; HTTP→outbox→worker→inbox has one trace ID with extracted parentage; logs correlate; metric/stream labels exclude trace IDs; resource/redaction tests pass. | Trace JSON, log excerpts, dashboard links and resource report. |
| Operations T10 | Alert on delayed notifications and simulate failure | 3 | T09 | Real assignment notification remains absent from recipient inbox >60s while durable event waits; F07 receipt <=110s; promtool tests pass using labeled test receiver. | Before-delivery inbox/outbox evidence, real metric/alert timestamps and receiver payload. |
| Operations T11 | Implement bounded model-assisted On-Call recovery | 7 | T10 | Real agent receives alert, diagnoses pause, executes authorized action, verifies affected IDs and persists evidence; replay/failure tests pass; killed-container case escalates. | Real-provider action/verification audit and negative/idempotency tests; no explanation-only repair claim. |
| Delivery T12 | Build gated GitHub Actions test and release pipeline | 5 | T08, T10, T11 | Automatic PR checks; validated main automatically deploys to development DB/environment; manual production dispatch + approval promotes same digest; smoke and rollback paths tested. | PR/main auto-CD run, distinct environment/DB proof, promotion/approval and gate-failure evidence. |
| Delivery T13 | Deploy public demo and rehearse rollback | 5 | T11, T12, hosting decision | Development and production HTTPS/isolation/persistence verified; both smoke checks pass; failed deploy restores compatible digest; promotion uses development-tested digest. | Live URLs, environment-isolation checks, auto-dev/manual-prod runs and rollback report. |
| Review T14 | Capture incident demonstration and complete evidence index | 3 | T13 | F01–F10/N01–N07 and supplied rubric indexed; real delayed inbox→alert→diagnosis→successful action→same IDs delivered→audit recorded. | Video, trace/log links, CI/CD runs and incident IDs. |
| Hardening T15 | Resolve integration defects and verify release gate | 4 | T14 | Critical defects fixed, required checks rerun, no unsupported acceptance claim remains. This is planned final regression work, not contingency. | Final checklist and remaining limitations. |

## Estimate basis, uncertainty and contingency

| Task | Low hours | Most likely hours | High hours | Cost driver |
| --- | ---: | ---: | ---: | --- |
| T02 | 2 | 3 | 4 | Compose health/bootstrap and image setup |
| T03 | 3 | 4 | 6 | Schema, auth/session, seed and OpenAPI |
| T04 | 4 | 5 | 7 | Transaction rules, permissions and conflicts |
| T06 | 4 | 5 | 8 | Real PostgreSQL locking/crash/retry tests |
| T05 | 3 | 4 | 6 | Forms, inbox and responsive behavior |
| T07 | 2 | 3 | 4 | Dashboard, control/audit correctness |
| T08 | 4 | 5 | 8 | Browser harness, combined test runner, benchmark |
| T09 | 4 | 6 | 9 | Telemetry services, propagation, logs/dashboard, resource checks |
| T10 | 2 | 3 | 5 | Alertmanager, rule/no-data tests and real timing |
| T11 | 5 | 7 | 10 | Model/provider integration and durable safe recovery tests |
| T12 | 4 | 5 | 8 | PR CI, automatic dev CD, manual approved production promotion |
| T13 | 4 | 5 | 8 | Two environments/DBs, TLS, public deployment and rollback |
| T14 | 2 | 3 | 4 | Repeatable recording and evidence curation |
| T15 | 3 | 4 | 6 | Final regressions and review |
| **Planned work subtotal** | **46** | **62** | **93** | T01 historical time excluded |
| **Contingency, approximately 25% rounded up** | **12** | **16** | **24** | Integration surprises, flaky CI, provider/network/debugging |
| **Remaining effort including contingency** | **58** | **78** | **117** | Engineering hours; not elapsed delivery dates |

Assume an experienced developer, existing tool familiarity, available Docker host, ready accounts/credentials and minimal visual polish. Test writing near each feature is included in its task; T08 integrates runners and covers gaps rather than duplicating all test effort. T15 is explicit final verification; contingency is a separate reserve. Owner approvals, external provisioning wait time and learning unfamiliar services add calendar delay; they are not hidden engineering-hours estimates. Additional authoritative rubric requirements, if confirmed, require a separate estimate. Actual time tracking begins with authorized implementation; no past hours are fabricated.

## Execution rules

T03 establishes contracts before implementation diverges. Add focused tests with each behavior; T08 integrates and fills gaps rather than postponing all testing. T09 configurations should be prepared from known minimal examples; avoid dashboard polish. T12 is finalized after all service/check inputs exist; local verification remains required before it.

At each task boundary record actual time, reserve consumed and blockers; re-estimate after T06 and the T09 telemetry resource spike. Protect transactional correctness, safe recovery, tests and reviewer reproducibility. Cut optional visual polish and extra dashboards before required evidence. Additional rubric requirements or overruns require an explicit revised estimate rather than silent omissions.

## Pre-implementation decisions

Before T02: obtain explicit foundation implementation authorization; identity separation/synthetic data are already approved. Record rubric verification as unresolved if dashboard evidence is unavailable; no maximum-score assurance follows. Before T11: select existing/no-purchase model access and approved credentials; the pause scenario is already approved. Before T12 remote execution: authorize implementation push/merge policy and automatic development deployments; arrange approved development host/access/DB and production reviewer policy without dependency on T13. Before T13: authorize deployment and resolve hosting/access/rubric scope; paid provisioning remains prohibited. T01 documentation commit/push and Issue preparation are authorized now; no implementation or deployment is authorized.
