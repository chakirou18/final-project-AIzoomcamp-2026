# Development agent team

Status: proposed collaboration model. These are responsibilities for future development, not claims that multiple agents have already worked on the repository. T01 documentation was prepared by a single assistant. Do not launch parallel agents unless the owner authorizes delegation.

| Role | Responsibility and deliverable | Required handoff |
| --- | --- | --- |
| Product/specification agent | Maintain requirement IDs, scope, acceptance criteria, assumptions and proposed Issues. | Approved task with behavior, exclusions, dependencies and reviewer evidence. |
| Backend agent | Business rules, OpenAPI, migrations, transactions, outbox and authorization. | Contract examples, migration impact, relevant unit/integration results and error behavior. |
| Frontend agent | Jinja2/HTMX views, shared service integration, usable forms and responsive journeys. | Screenshots, keyboard checks, loading/error states and browser journey results. |
| QA/testing agent | Risk-based tests, PostgreSQL failure injection, browser checks and acceptance traceability. | Reproduction commands, observed results and defects linked to requirements. |
| DevOps/SRE agent | Compose, CI/CD, deployment, telemetry, alert rules and bounded recovery infrastructure. | Runbooks, dashboards, alert test results, deploy/rollback evidence and incident transcript. |
| Integration/review lead | Resolve cross-boundary decisions, review diffs, enforce scope and assemble evidence. | Integrated acceptance check and explicit owner approval before commit/push/public changes. |

## Collaboration and task tracker

Use [backlog.md](backlog.md) as the local source of truth until remote Issues are explicitly authorized. Each Txx task contains a proposed public Issue title, dependency, timebox, acceptance criteria and evidence. Later copy those fields into a GitHub Issue and record its actual URL; never invent Issue numbers. States: proposed → ready → in_progress → review → done, or blocked with a named reason. Current state: T01 in review; every other task proposed.

Before starting, read [AGENTS.md](../AGENTS.md), the relevant specification/architecture section and dependency handoffs. Claim one task, name intended files and record assumptions. If parallel work is authorized, allocate disjoint files or isolated worktrees and one owner per shared contract. Schema/API changes must be agreed before dependent UI work. The integration lead reconciles changes and runs cross-component checks.

Task handoff template: task/Issue ID; requirement IDs; files changed; contract/migration impact; commands and actual outcomes; evidence links; remaining risks/decisions. Save concise, redacted summaries in task updates; do not rely on chat memory or copy secret-bearing transcripts. Update documentation when behavior changes. Review generated code as ordinary code, including failures and unsupported assumptions. Do not mark done until acceptance evidence exists.

### Public tracker evidence protocol for Codex

The owner authorized T01 documentation and public tracker preparation on 2026-11-09. Create Issues from the reviewed drafts in topological order without duplicates and map each Txx to its actual public URL in backlog.md. Include real dependency URLs, responsible role, requirement IDs, acceptance criteria, tests and expected evidence. Do not use guessed Issue numbers. This authorization does not start application development or permit Issue closure; progress updates below apply to subsequent authorized implementation.

Codex reads the Issue and dependencies before starting, references `Txx / #actual-number` in its task summary, and posts a short start update naming scope/files/role. During implementation, post updates at meaningful task milestones or blockers with checked acceptance items, exact commands/results, CI/artifact links, actual time and changed decisions. Update the Issue checklist and local tracker together. PR title/body references the Issue (`Refs #actual-number`; use `Closes` only when closure is authorized) and explains behavior, validation and remaining risks. Commits reference the Issue only after commit permission exists.

At review, post a handoff containing the tested commit/digest, test results, screenshots/traces, development-deployment run and relevant failure evidence. Do not post secrets or private credentials. Integration/review lead confirms acceptance, then closes an Issue only with authorized closure and reviewer-visible evidence; automated `Closes` must not bypass review. If publishing is not authorized, retain the same update locally as a draft. Record actual agents/tools used honestly; role definitions alone are not execution evidence.

## Runtime On-Call Agent is a separate system

Development agents help build and review the repository. They may propose source changes under owner supervision. The runtime On-Call Agent is a deployed application component receiving authenticated alerts. It can read bounded telemetry, request one allowlisted worker-resume action and append incident audit records. It cannot edit code, deploy releases, open Issues, execute shell commands or obtain development-agent credentials. Its policies, real-provider demonstration and adversarial/failure tests are implementation deliverables, not powers granted to the development team.
