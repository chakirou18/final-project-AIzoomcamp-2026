# FieldOps repository instructions

Current authorization: **T05 / GitHub Issue #6 feature-branch publication only**, on feature/t05-web-interface from published T06 commit 1253faaedd5b39aa9ee9da0330645e1b5667119b. On 2026-11-10 the owner authorized final checks, one T05 commit, a non-force push, a PR targeting feature/t06-notification-worker and an Issue #6 progress comment. Preserve earlier commits and existing data. No merge, main modification, Issue closure, T07 or later implementation, deployment, spending or Docker volume deletion is authorized. Record evidence in [T05 validation](docs/t05-validation.md) and stop after publication for owner review.

## Scope and current state

FieldOps is a single-company technical maintenance MVP prioritizing verifiable rubric coverage. The former 20-hour target is superseded by the T01 remaining-work estimate in the backlog (78 hours including contingency; uncertain range 58–117 hours, not actual time spent). Current phase is audited T05 feature-branch publication for owner review. Implement only authorized tasks; do not create remote Issues, commit or push beyond the owner's current authorization. Preserve existing user files and inspect git status before editing. All project documentation is English.

Historical T01 publication authorization (2026-11-09): validate/publish T01 documentation on feature/t01-project-specification and create T01–T15 public Issues. Those actions are complete; current permissions are defined at the top of this file. Approved product decisions remain separate manager (dispatcher)/technician demo identities, synthetic data, a controlled paused delivery loop and authenticated/audited allowlisted On-Call operations. Keep the supplied 24-point mapping and provisional 41-point flag separate.

## Context map

- [README](README.md): purpose, journeys and entry point.
- [Specification](docs/specification.md): authoritative behavior, stable Fxx/Nxx requirements and boundaries.
- [Architecture](docs/architecture.md): contracts, data, reliability and decision register.
- [Agent team](docs/agent-team.md): responsibilities and development/runtime separation.
- [Backlog](docs/backlog.md): task order, dependencies, proposed Issues and estimates.
- [Rubric evidence](docs/rubric-evidence.md): scoring baseline and reviewer evidence.
- [T01 audit](docs/t01-audit.md): findings, validation and readiness gates.
- [Issue drafts](docs/github-issue-drafts.md): reviewed bodies for the authorized public tracker publication.
- [Final readiness](docs/t01-readiness.md): current T01 verdict and remaining decisions; supersedes historical audit estimates.
- [T03 validation](docs/t03-validation.md): current schema, contracts, permissions and test handoff.
- [T02 foundation validation](docs/t02-validation.md): runnable commands, actual results and review status for Issue #2.

Read only the relevant modules after this file; use task summaries and linked evidence to restore context. Record assumptions and unresolved choices explicitly. Do not treat planned functionality or test commands as verified results. Update affected documents when contracts change.

## Conventions and responsibilities

Use Python/FastAPI, server-rendered Jinja2/HTMX, PostgreSQL and a separate Python worker as proposed in the architecture. Future code should separate routes/templates, business services, persistence, worker and runtime agent concerns. Share business rules between HTML and JSON handlers; keep transactions and authorization out of templates. Use snake_case Python names, explicit schemas, UTC timestamps, migrations and environment configuration. Pin dependencies when implementation is authorized; never commit credentials or real customer data.

The integration lead owns shared contracts and release review. Backend owns data/invariants, frontend owns user flows, QA owns independent verification, and SRE owns delivery/telemetry/recovery. These roles do not authorize parallel sub-agents; obtain owner authorization before delegating. Runtime agent privileges are strictly separate from development privileges.

## Development and review process

1. Select a ready Txx task and check dependencies, requirements and working-tree changes.
2. State intended behavior and affected files; resolve contract conflicts before dependent changes.
3. Make the smallest coherent change and add risk-based verification. Do not expand scope without recording why.
4. Run relevant checks and record exact commands, outcomes, limitations and evidence links. T02 foundation tests exist; browser, business workflow, notification and agent suites remain future work.
5. Review for requirement coverage, input validation, permissions, migrations, transaction boundaries, concurrency, secrets and operational consequences. An independent QA/review role should challenge the evidence when available.
6. Update task status and handoff; request owner review before any unauthorized commit, push or public change.

T02 commands: `uv sync --frozen` (Python 3.12); `uv run pytest -m "not container and not integration"`; `docker compose config`; `docker compose up --build --wait`; `docker compose --profile test run --build --rm tests`. Opt-in container lifecycle tests need local Docker access and FIELDOPS_RUN_CONTAINER_TESTS=1; see validation notes for PowerShell/POSIX examples and disposable-project safeguards. No worker, persona schema or business tables belong to T02.

Codex must read the public tracker and real dependency Issues before authorized implementation, reference its Issue URL/number in task summaries, report progress/validation evidence, and link any authorized commit/PR to the Issue. Follow [agent-team.md](docs/agent-team.md) for fields and closure rules. Close an Issue only when acceptance criteria have evidence and closure is authorized. T02 publication is historical and complete. T03 publication is historical and complete. T04 publication is historical and complete. T06 publication is historical and complete. Current authorization permits T05 feature-branch publication and the Issue #6 progress comment only; do not merge or close any task. Core/test commands are documented in README; future stack/browser commands remain proposed.

## Testing and safety rules

Use Pytest unit tests for state transitions, authorization and recovery policy; PostgreSQL integration tests for constraints, rollback, leases, deduplication and crash recovery; Playwright for the main dispatcher/technician journey. SQLite is not an adequate substitute for PostgreSQL locking tests. Mock model calls in deterministic CI and separately record a bounded real-provider recovery demo. Test denied actions, replayed alerts, stale generations, verification timeout and malicious telemetry text. Validate alert rules and the actual delayed-delivery scenario.

Run targeted tests during development and the complete required CI gate before release. A passing health check cannot prove inbox delivery. Never weaken assertions to hide defects. Report failed/unrun checks plainly. Agent recovery must remain allowlisted, authenticated, idempotent and auditable with no unrestricted shell or Docker socket. Destructive database operations, production backup restoration and purchases need explicit owner approval.
