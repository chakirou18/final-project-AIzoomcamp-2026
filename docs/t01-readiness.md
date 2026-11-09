# Final T01 readiness summary

Status: owner authorized **T01 documentation and public tracker publication**, subject to final Git validation (2026-11-09). **GO for T02 planning readiness; execution remains on hold until the owner authorizes application development.** No runtime acceptance check or rubric score is claimed. This summary supersedes historical audit authorization/readiness statements, not its unimplemented-test warnings.

Approved: separate manager (dispatcher) and technician demo identities, synthetic demonstration data, controlled paused delivery loop and authenticated/audited allowlisted recovery. Prohibited: paid infrastructure provisioning and API purchases. Preserve the supplied 24-point mapping and provisional 41-point flag. Publication authorization covers documentation commits/pushes on feature/t01-project-specification and duplicate-safe T01–T15 Issue creation; no force push, main merge, Issue closure or deployment is authorized.

## Corrections completed

- CI/CD now matches the supplied 3-point band: automatic PR tests, automatic deployment after validated merge to main to an isolated development environment/DB, then manual GitHub Actions promotion with a production approval gate. Promote the same digest; smoke and rollback both environments.
- Trace contract is explicit: inject W3C context during enqueue, persist traceparent/tracestate in PostgreSQL, extract an empty-context worker parent, and preserve one trace ID through inbox insert. A proposed automated test checks parentage, structured logs, concurrent events/retries and safe metric labels. Log-derived dashboard links are required; exemplars are optional.
- Four single-command Compose workflows are specified for core, complete stack, combined unit/integration and browser tests. **All are proposed and unverified**; no Compose/workflow code exists yet.
- Fifteen Issue bodies have dependencies, acceptance criteria, responsible roles, tests and evidence. Order is acyclic; public tracker publication is now authorized. Implementation and closure remain separate gates.
- Agent success requires real recipient-visible delayed delivery, an actual received alert, evidence-based diagnosis, successful authorized resume, verification of affected notification IDs and persistent incident/action records. MVP repairs a paused delivery loop; killed containers escalate. Explanation-only or spontaneous recovery never qualifies.

## Revised remaining effort and resources

Most likely **62 planned engineering hours + 16 contingency = 78 hours**. Planning range **58–117 hours** including contingency; already-spent T01 time is unmeasured and additional. Includes real PostgreSQL concurrency/failure tests, browser tests, telemetry/Alertmanager, model-assisted recovery, two deployment environments, public HTTPS, smoke and rollback evidence. Coverage takes priority over the superseded 20-hour limit. See [backlog](backlog.md) for task ranges and assumptions.

Resource envelopes are unmeasured: core 2 vCPU/4 GiB; full environment 4 vCPU/8–12 GiB; two concurrent full environments may require 8 vCPU/16–24 GiB and 80–120 GiB disk. Measure in T09/T13 before selecting hosting. These are hypotheses, not purchased resources or verified minima.

## Remaining decisions

| Decision | Owner / gate |
| --- | --- |
| Authorize T02 implementation against the revised estimate | Project owner; T01 publication and separate manager/technician identities are already approved |
| Confirm authoritative cohort dashboard rubric/version | Project owner before maximum-score assurance/final scope freeze; supplied 12/24 stays mapped separately from provisional 19/41 |
| Select existing/no-purchase model access and approved credentials | Owner before T11; paused-loop scenario approved, no API purchase permitted |
| Confirm accelerated 60-second/30-second delay thresholds and 110-second receipt budget | Owner/SRE before T10; production objectives require workload evidence |
| Select development host/DB/access and authorize automatic CD; choose production required reviewer/self-approval policy | Owner/SRE before T12 remote execution |
| Approve production hosting, DNS/TLS, isolation/capacity, access and costs | Owner/SRE before T13; no provisioning authorized |
| Public T01 documentation commits/pushes and T01–T15 Issue creation | Authorized now; implementation commits/pushes, main merge and Issue closure are not implied |

Development and production may share hardware only with separate DB containers/users/volumes/secrets/networks and measured capacity. Exact provider and cost remain open. The authenticated dashboard was not accessed; no missing 41-point criteria have been invented.

## Validation status

Final documentation checks and exact commands are recorded in the [audit addendum](t01-audit.md). They cover all tracked/untracked Markdown, local links, task ordering, Issue fields, requirements and estimate arithmetic. Runtime commands, workflows, trace tests and recovery demonstration remain **NOT RUN**.
