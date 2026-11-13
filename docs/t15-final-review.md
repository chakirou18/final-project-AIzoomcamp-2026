# T15 final independent review

Task is [Issue #15](https://github.com/chakirou18/final-project-AIzoomcamp-2026/issues/15). This review covers the published feature chain T11–T14 (PRs #25–#28) and this T15 branch as of 2026-11-12. The dependency chain is incomplete by external constraints (no hosting and no production approval record; a demo video was later published on 2026-11-13 as release v1.0.0-demo), so this is a conditional review: every missing item is named and nothing historical is presented as freshly rerun.

## Test ledger

Fresh runs are dated. Runs from 2026-11-11 were executed on images rebuilt from the final T11 source (`315b449`) and remain valid for the application code, which has not changed since; T12/T13 changed only pipeline, deployment and documentation files. The Docker Desktop engine was stopped on 2026-11-12 and was not restarted (owner policy), so Docker-backed suites were not rerun locally today; the GitHub-hosted runs below exercised them remotely on the published branch.

| Suite | Result | Date / where | Evidence |
|---|---:|---|---|
| Backend unit (mock model), incl. T11 audit (10) and T12 pipeline (10) cases | 207 passed, 0 failed | 2026-11-12 local; 2026-11-12 GitHub run 43200242540 (job pass) | `artifacts/claude/t11-audit-unit.xml` |
| T12 pipeline checks (promotion gate, secret scan, isolation render) | 10 passed | 2026-11-12 local | `artifacts/claude/t12-pipeline-unit.xml` |
| PostgreSQL integration (mock model) | 284 passed, 1 skipped (+2 audit regressions) | 2026-11-11 local retained DB; 2026-11-12 GitHub run 43200242540 (job pass) | `artifacts/claude/t11-audit-full-postgres.xml`, `…processing-postgres.xml` |
| Chromium journey + N03 benchmark | 18 passed (p95 50.4 ms) | 2026-11-11 local; GitHub runs 43199314066 and 43200242540 attempt 2 (job pass); attempt 1 of 43200242540 had one Playwright protocol-error failure (17 passed) that passed on the failed-job rerun without test changes | `artifacts/t08-browser-a18676f0…/pytest.xml` |
| T10 live alerting (receipt 101.672 s) | 5 passed | 2026-11-11 local | `artifacts/claude/t10-regression.xml` |
| T09 observability | 10 passed | 2026-11-11 local | `artifacts/claude/t09-regression.xml` |
| T11 mock live (rebuilt images) | 1 passed | 2026-11-11 local | `artifacts/claude/t11-mock-live.xml` |
| T11 real-model live (llama3.2:3b) | 1 passed | 2026-11-11 local | `artifacts/t11-real-model-live.xml` |
| Prometheus rules (promtool) + Alertmanager config | 4 rules / 27 assertions | 2026-11-12 GitHub run 43200242540 (job pass); 2026-11-11 Codex local | rules job log |
| Dependency audit (pip-audit 2.10.1) | no known vulnerabilities | 2026-11-12 local and GitHub | security job log |
| Safe Docker lifecycle (startup/persistence, DB outage) | 2 passed | 2026-11-11 Codex local (not rerun) | `artifacts/t11-lifecycle.xml` |

**528 distinct passing pytest cases** (unique class/name pairs across the 2026-11-11/12 local JUnit files; historical T08–T10 ledgers not re-added). Not executed under the preservation rule: five worker-stop cases and one database-deletion assertion. Static gates: ruff lint/format, `uv lock --check`, Compose render (all profiles, hosted and proxy overlays), `git diff --check`, actionlint 1.7.12, secret scan (163 tracked files, 0 findings).

## Audit dimensions

| # | Dimension | Finding |
|---|---|---|
| 1–2 | Functional correctness, database integrity | PostgreSQL suite and live runs pass; integrity probe after the final rebuild: 244 outbox = 244 inbox, zero undelivered/missing/duplicate/wrong-recipient rows |
| 3–6 | Authentication, authorization, CSRF, input validation | Session/CSRF tests, role tests, T11 grant tests; bounded pydantic contracts throughout; operator secret never in documents |
| 7–9 | Notification idempotency, outbox/inbox consistency, worker reliability | Leased worker, idempotent inbox, injected-failure tests; verified again by the integrity probe |
| 10–11 | Monitoring accuracy, alert latency | Real alert receipts at 100.7–103.8 s against the 110 s requirement across T10/T11 runs |
| 12–15 | Provider integration, structured diagnosis, prompt-injection resistance, execution policy | Real llama3.2:3b run; schema-validated output; injected log text never reaches the model; counterfactual outputs denied by `policy()`; model cannot choose tools |
| 16–18 | Operator approval, recovery safety, resolution invariants | Per-incident/generation grant, scoped bearer, execution guard, DB trigger requiring action + delivery evidence; audit fixes for freshness anchoring and budget ordering |
| 19 | Restart persistence | Lifecycle test and the live VERIFYING-restart case (Codex) retained; real incident preserved across service recreation |
| 20 | CI/CD workflow security | SHA-pinned actions, least-privilege permissions, env-only secret/input handling, no `pull_request_target`, verify jobs without environments; real PR runs confirm the gate executes |
| 21–23 | Environment isolation, deployment safety, secret handling | Isolation render ok; digest-only releases; backups before migration; no secrets in git (scan clean); hosted override and edge render correctly |
| 24 | Resource stability | Agent 57 MiB / 192 MiB; host memory pressure interrupted one local simulation (resource event, not a defect) |
| 25 | Rollback correctness | Automatic and manual rollback paths implemented; dry-run only; no remote rehearsal |
| 26–29 | Documentation accuracy, evidence completeness, reproducibility, reviewer usability | Validation/audit documents per task, evidence index with ACTUAL/HISTORICAL/PLANNED/BLOCKED classes, submission guide, demo script |
| 30 | Rubric coverage | All F/N requirements have local evidence; N06 remote deployment part and F09 hosted exposure check remain blocked ([evidence index](evidence-index.md)) |

## Defects found during T12–T15 and their resolution

| Severity | Defect | Resolution |
|---|---|---|
| MEDIUM | Workflow-level database variables leaked into the unit job and into the isolation render on the first real PR run (unit job error, security job failure). | Scoped to the integration job; confirmed by run 43200242540 (both jobs pass). |
| MEDIUM | Hosted override relied on YAML anchors for `build: !reset null`; the runner's Compose kept the build definitions. | Services spelled out without anchors; isolation render passes remotely. |
| LOW | Secret-scan test fixtures tripped the CI lint gate once tracked. | Synthetic markers on the fixture source lines; lint job passes remotely. |
| LOW | One Chromium case failed on the hosted runner with a Playwright protocol error after passing locally and on the previous remote run. | Failed-job rerun passed (all seven PR checks green on `51464b5`); no assertion weakened; recorded as runner flakiness to watch. |
| MEDIUM | The T13 Caddyfile used `exclude request>headers>…` inside `log`; Caddy's `exclude` takes logger names, so the edge could refuse to start. | Replaced with a `format filter` that deletes the Cookie and Authorization fields; CI now runs `caddy validate` with the pinned image in the rules job (this PR). |
| LOW | `FIELDOPS_PUBLIC_HTTPS` in the hosted override was a no-op, and the T13 document claimed it controlled Secure cookies. | Removed; documentation now states the real control: cookies are Secure whenever the environment is not `local` (`fieldops/auth.py`). |

| HIGH | `deploy.sh` pulled images and then ran `up --no-build`. The seven observability services are built locally from digest-pinned vendor images, so the first release on a fresh host would have failed. | `deploy.sh` now runs `pull --ignore-buildable`, then `build`, before `up`. Found by rendering the full hosted stack. |
| MEDIUM | There was no way to give hosted environments a real model without exposing Ollama. | Added `docker-compose.model.yml`: a private Ollama runtime on an internal network with no published port. `docker-compose.model-client.yml` attaches only the agent. `deploy.sh` applies the overlays and refuses to release without the network. |
| MEDIUM | The README lacked CI/CD, deployment, security, limitations and evidence sections, and its status line was stale. | Sections added, status updated. |
| LOW | Earlier documents said Azure was "signed in". The cached token had expired after 90 days of inactivity. | Corrected in the hosting proposal; Azure inventory requires the owner to run `az login`. |

No critical or high defect is open; the high-severity deployment defect above is fixed and verified by dry run.

## GitHub publication state

| Task | Branch | Head | PR | CI |
|---|---|---|---|---|
| T11 | `feature/t11-oncall-agent` | `315b449` | [#25](https://github.com/chakirou18/final-project-AIzoomcamp-2026/pull/25) → T10 | predates the workflows |
| T12 | `feature/t12-ci-cd` | `07ea7b5` | [#26](https://github.com/chakirou18/final-project-AIzoomcamp-2026/pull/26) → T11 | all 7 jobs pass ([43262717139](https://github.com/chakirou18/final-project-AIzoomcamp-2026/actions/runs/43262717139)) |
| T13 | `feature/t13-deployment` | `9f07bd5` | [#27](https://github.com/chakirou18/final-project-AIzoomcamp-2026/pull/27) → T12 | all 7 jobs pass ([43262801348](https://github.com/chakirou18/final-project-AIzoomcamp-2026/actions/runs/43262801348)) |
| T14 | `feature/t14-evidence` | `7dfe09c` | [#28](https://github.com/chakirou18/final-project-AIzoomcamp-2026/pull/28) → T13 | all 7 jobs pass ([43262890336](https://github.com/chakirou18/final-project-AIzoomcamp-2026/actions/runs/43262890336)) |
| T15 | `feature/t15-final-review` | this branch | → T14 | runs on this PR |

Update 2026-11-13: `feature/t15-final-review` was merged into `main` by the owner (PR #30), followed by the public-demo boundary (PR #31). Issues #11–#15 remain open. No hosted deployment exists.

## Security scan of the release set

`scripts/ci/secret_scan.py` over all tracked files: 0 findings. Six live runtime credential values were absent from the T11 publication set; environment templates contain placeholders only; evidence directories under `artifacts/` are git-ignored and were not published; no personal data beyond the owner's public GitHub handle appears in the documentation.

## Release readiness additions (2026-11-12, later pass)

- [GitHub release readiness](github-release-readiness.md) documents the merge plan:
  - The chain is linear, conflict-free and `MERGEABLE`/`CLEAN` from T01 to T15.
  - The recommended path is one merge-commit integration PR `feature/t15-final-review` → `main`; never squash or rebase the chain.
  - It also contains a ruleset proposal (seven required checks, no force-push, no deletion, PR required) and the environment and secret setup commands.
- [T13 hosting proposal](t13-hosting-proposal.md) gives verified prices:
  - The full target, two environments plus the private model, needs about 8 GB and 4 vCPU. It cannot run for €5/month.
  - Recommended: Hetzner CX33, €8.99/month excl. VAT, currently listed unavailable. Available fallback: CPX32 Helsinki, €30.49.
  - Azure costs more for the same capacity.
- Today's local reruns: unit tests 207 passed; isolation render ok; Compose config ok for all profiles; full hosted-stack render with both overlays; `deploy.sh` dry runs for both environments. Docker-backed suites were not rerun because the Docker engine was stopped.

## Remaining risks and blocked evidence

Remote: automatic main→development deployment, production approval gate with a real reviewer, promotion of an identical digest, production smoke, backup verification and rollback rehearsal, permanent public HTTPS hosting and exposure scan (a temporary Quick Tunnel demo passed 37/37 checks on 2026-11-13), a video of a live agent recovery (a 1 min 33 s demo video is published as release v1.0.0-demo). Local: Docker-backed suites were not rerun on 2026-11-12 (engine stopped); the Chromium suite shows runner-side flakiness in one mobile JS-disabled case.

## Verdict

**CONDITIONAL GO.** The application, agent and pipeline are locally complete and audited; the PR validation gate demonstrably executes on GitHub. Exact missing requirements for GO: (1) branch protection on `main` and the `development`/`production` environments with required reviewers, (2) approved hosting with DNS/TLS and deployment secrets, (3) one real main→development automatic run, one production promotion with approval record, smoke results in both environments and one rollback rehearsal, (4) a demonstration video — **now published** as release v1.0.0-demo (2026-11-13), covering the web interface, interventions, Grafana and previously validated alerting evidence, without a live agent run. Until then the project status is **LOCALLY COMPLETE — EXTERNAL ACCEPTANCE PENDING**.
