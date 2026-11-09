# Rubric coverage and reviewer evidence

Status: **planning only; no implementation points claimed**. The supplied target has 12 criteria totaling **24 points**. Every criterion below uses the owner's supplied maximum. The owner subsequently clarified the 3-point CI/CD band: automatic test CI, automatic development CD, manual production deployment. Other exact score-band descriptors were not supplied and are not invented here.

Publication decision, 2026-11-09: owner authorized T01 documentation commit/push and public Issue creation, approved separate manager/technician demo identities, synthetic data and authenticated/audited paused-loop recovery. This settles scenario/identity choices, not runtime evidence or authenticated rubric confirmation. Paid provisioning/API purchases remain prohibited.

## Source discrepancy and scoring baseline

Checked 2026-11-09: the [official course project page](https://datatalksclub.github.io/docs/courses/ai-dev-tools-zoomcamp/project/) points learners to current project requirements. The [official course FAQ](https://datatalksclub.github.io/faq/ai-dev-tools-zoomcamp.html) currently describes a draft 2026 rubric with 19 criteria, 41 available points and 24 points required to pass. This differs from the requested 24-point maximum. Treat the table below as complete coverage of the **supplied baseline**, not verified coverage of every criterion in the current course rubric. Resolve P01 using the cohort's authoritative rubric/version before freezing scope; attach its permalink or dated copy and reconcile every additional criterion. A 24/24 course-maximum claim is currently unsupported.

Audit verification: these are **two different versions**, not a 24-point rubric plus inferred extra criteria. The 12 names/weights and subsequently supplied CI/CD band were checked against the owner's supplied text. No separate user-provided rubric README exists in this checkout; the original repository README was only a title. Public FAQ wording was rechecked on 2026-11-09; the authenticated course dashboard was **not accessed**. Owner must confirm its Project outcomes/rubric version. No missing 41-point criteria are invented or mapped.

## Supplied criterion mapping

| Criterion | Supplied highest score | Implementation plan / tasks | Required reviewer-visible evidence | Full-score risk |
| --- | ---: | --- | --- | --- |
| Problem Description | 2 | README explains maintenance workflow, missed assignments, users and journeys; T01. | README and concrete assignment-delay scenario. | Vague claims without a reproducible user journey. |
| Product Specification | 2 | F01–F10/N01–N07, scope exclusions and decision register; T01. | Specification, acceptance criteria and implemented-behavior cross-check. | Unresolved identity or delivery semantics drift during implementation. |
| Agent Team Specification | 2 | Document role boundaries, task tracker, handoffs and review; T01 plus task execution. | agent-team.md and honest task/handoff records; distinguish planned roles from actual use. | A role list alone may not satisfy execution-related score bands. |
| Context Management | 2 | Modular docs, AGENTS.md, stable requirement/task IDs and concise handoffs; T01–T15. | Instruction file, linked modules, decision updates and selected redacted context/handoff examples. | Instructions exist but development does not follow/update them. |
| Application | 2 | Functional UI, JSON API and PostgreSQL persistence; T02–T07. | Live demo, OpenAPI, create/assign/start/complete journey and restart persistence proof. | Backend-only demo, broken permissions or missing closure/history. |
| Testing | 2 | Unit, real PostgreSQL integration, browser and recovery tests; T04–T11. | Runnable commands, passing CI run, failure-injection tests and critical journey output. | Mock-only database/model evidence or happy-path-only tests. |
| Containerization | 2 | One app image reused by web/worker/agent plus Compose dependencies; T02/T09. | Dockerfile, pinned Compose config, clean-start and persistence evidence. | Unpinned images or undocumented host prerequisites. |
| Deployment | 2 | Public HTTPS single-host demo, persistent volume, deployment and rollback runbook; T13. | Working URL, demo access, restart and rollback smoke evidence. | Hosting not funded/available; full telemetry exceeds VM resources. |
| CI/CD | 3 | Automatic PR/main test CI; automatic development deployment after validated main merge to its own DB; manual GitHub Actions production dispatch + approval, same digest, smoke/rollback; T12–T13. | PR check run; automatic main→development deploy run with no manual dispatch/approval; distinct DB/volume targets; manual production dispatch + approval record; matching image digest, smoke and rollback output. | Missing automatic development CD cannot satisfy supplied 3-point band; workflow YAML alone is insufficient. |
| Observability | 2 | OTel W3C context persisted in outbox and extracted as worker parent; HTTP→outbox→worker→inbox same trace ID, structured logs and safe dashboard correlation; T09. | Correlated-journey trace JSON with parentage, web/worker JSON logs, Grafana→Loki→Jaeger links, no high-cardinality metric labels and resource/redaction checks. | Link-only separate traces, missing export or leaked context across events would fail planned evidence. |
| Alerting on User Impact | 1 | Undelivered assignment age threshold, not just process uptime; T10. | Alert rule test and real timing from assignment through Alertmanager webhook. | Worker emits its own backlog metric and disappears during failure; missing-data blind spot. |
| On-Call Agent | 2 | Genuine recipient-visible delay, real alert/model diagnosis, authorized pause-loop resume, affected-ID delivery verification and durable audit; T11/T14. | Inbox absent >60s then delivered for same IDs; real-provider diagnosis/action/verification transcript; incident rows and replay/denial tests. Explanation or spontaneous recovery gets no repair credit. | Killed-container repair is outside MVP; paused-loop variant must meet authoritative score bands. |
| **Total supplied baseline** | **24** | **Revised 78-hour remaining estimate including contingency; see backlog** | **Actual artifacts required before score claims** | **Official rubric reconciliation remains blocking for maximum-score assurance.** |

## Evidence collection and release review

### Per-criterion documentation status and remaining verification

PASS below applies only to an inspectable documentation property; PARTIAL means a plan exists without full acceptance evidence. None of these statuses awards course points or passes runtime behavior.

| Supplied criterion | Documentation status and support | Required test / demonstration | Remaining work |
| --- | --- | --- | --- |
| Problem Description | PASS: README problem, users and journeys | Demonstrate missed assignment impact and normal journey | T04–T07/T14: running walkthrough |
| Product Specification | PASS: specification F01–F10/N01–N07 and clarified contracts | Execute requirement acceptance checks | T03–T15: implement and index results |
| Agent Team Specification | PASS: agent-team roles, handoffs and tracker states | Show actual reviewed handoffs, without inventing multi-agent use | Record development collaboration as it happens |
| Context Management | PASS: AGENTS links and modular context | Follow one task from instructions through decision/handoff | T02–T15: maintain real context records |
| Application | PARTIAL: connected UI/services/database design | Browser lifecycle, API errors, restart persistence | T02–T08: all implementation |
| Testing | PARTIAL: risk-based strategy and drafted tests | Run unit, PostgreSQL, browser and fault tests | T04–T12: runnable suites and passing results |
| Containerization | PARTIAL: shared image/base/profile plan | Clean checkout Compose startup/restart | T02/T09: Dockerfile/config and proof |
| Deployment | PARTIAL: HTTPS, backup and rollback concept | Public access, persistence and prior-image rollback | T13: hosting decision and measured rehearsal |
| CI/CD | PARTIAL: automatic PR/main tests + automatic development CD + manual approved production promotion explicitly planned | Automatic dev deployment, distinct DB, manual dispatch/approval, failed gate, both smoke tests and rollback | T12–T13: real run/approval links and tested digest identity |
| Observability | PARTIAL: exact persisted W3C parent extraction and log correlation specified | Same-trace/parentage journey, concurrent/retry isolation, metric label and sentinel-secret scan | T09/T14: actual trace/log artifacts and measured resources |
| Alerting on User Impact | PARTIAL: undelivered age/count and timing defined | promtool and real authenticated receipt within 110s | T10/T11: tests and timestamps |
| On-Call Agent | PARTIAL: policy, action, retry, verification and audit design | Successful real-provider action plus verified delivery; replay/denial/failure tests | T11/T14: implementation and complete incident evidence |

Required implementation and reviewer artifact details remain in the supplied criterion mapping above; the [Issue drafts](github-issue-drafts.md) define test ownership and dependencies.

During implementation, add an evidence index here with actual repository paths, commit-relative links, public CI/deployment run URLs and video timestamps. Do not create fabricated logs, screenshots, scores or Issue links. Each entry should name requirement/task, environment, command/action, expected result, observed result and date. Redact credentials and customer data. Keep the public demo seeded and accessible through peer review.

Suggested final walkthrough: identify dispatcher/technician personas; create and assign a job; show normal inbox delivery and history; pause worker and assign another job; show pending age and firing alert; show agent diagnosis, policy decision and resume result; verify the specific inbox event and incident audit; complete the job; show passing tests, deployment run and correlated telemetry.

## Risk priorities

1. Rubric mismatch: obtain authoritative cohort score bands before promising the maximum; any newly confirmed requirements need a separate estimate. The old 20-hour constraint is superseded.
2. Time and resource pressure: the full telemetry stack plus runtime model integration is the largest implementation risk. Use minimal stock configurations, one dashboard and the buffer; re-estimate rather than omit evidence silently.
3. External prerequisites: hosting, DNS/TLS, CI credentials and model budget must be available before delivery tasks start. No paid provisioning is currently authorized.
4. Correctness under failure: leases, transaction atomicity, replay handling and verification need real PostgreSQL tests; a visually successful demo is insufficient.
5. Public access and agent safety: separate manager/technician synthetic personas are approved; operator controls remain secret-gated. Keep control/telemetry private, enforce role checks and prove denied actions.

Recommended next step after authorized T01 publication/tracker preparation: obtain T02 implementation authorization. P01 remains open until authenticated dashboard confirmation; P03/P04 block deployment/model integration respectively. No deployment, paid provisioning or model-access purchase is authorized.
