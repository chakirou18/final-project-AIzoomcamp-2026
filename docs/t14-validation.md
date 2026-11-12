# T14 demonstration and evidence package: local validation

Task is [Issue #14](https://github.com/chakirou18/final-project-AIzoomcamp-2026/issues/14). Its dependency T13 is **not accepted** (no hosting), so T14 can only deliver the reproducible walkthrough, the recorded local incident evidence, the requirement-to-evidence mapping and the submission checklist. **No video was recorded.** CI/deploy links do not exist and are not claimed.

## Delivered

| Deliverable | Location | Status |
|---|---|---|
| Reproducible reviewer walkthrough and incident scenario | [demo-script.md](demo-script.md) | Written from the recorded local run; every step names its command and evidence |
| Real agent diagnosis and recovery evidence | `artifacts/t11-real-5bd8899d1d424a9ab234acf3b3f405a1/evidence.json`, `real-agent.log`, trace JSON | Recorded 2026-11-11 09:22 UTC with llama3.2:3b |
| Architecture diagrams | [architecture.md](architecture.md), state machine in [t11-validation.md](t11-validation.md) | Existing Mermaid diagrams |
| Alerting and tracing evidence | T09/T10 validation, `artifacts/claude/t09-regression.xml`, `t10-regression.xml` | Reran after the final rebuild (see T15) |
| Test reports | JUnit files under `artifacts/` and `artifacts/claude/` | Listed in [t15-final-review.md](t15-final-review.md) |
| CI/CD evidence | [t12-validation.md](t12-validation.md): actionlint, isolation, gate tests, real `pr-validation` runs on PR #26 | PR checks ACTUAL; deployment runs BLOCKED |
| Deployment and rollback evidence | [t13-validation.md](t13-validation.md): dry runs | Local only; remote BLOCKED |
| Video storyboard and narration | demo-script.md sections 5–6 (timestamped script, pre-recording checklist, secret-hygiene rules, post-recording steps) | Plan only; **no recording** (owner action) |
| Requirement-to-evidence mapping (F01–F10, N01–N07) | [evidence-index.md](evidence-index.md) | Complete; blocked items stated |
| Rubric status | [rubric-evidence.md](rubric-evidence.md) retained; 24-point mapping preserved, 41-point alternative kept separate | Unchanged |
| Submission checklist | [final-release-checklist.md](final-release-checklist.md) | Written |
| Reviewer and submission guide | [submission-guide.md](submission-guide.md) | Written: purpose, features, agent architecture, technologies, installation, demo credentials handling, workflow and incident reproduction, verification queries, tests, monitoring, CI/CD, deployment, rollback, limitations, links |

## Tests required by Issue #14

| Required | Result |
|---|---|
| Repeat the seeded demo from baseline | The mock live scenario was repeated on the rebuilt stack during the T15 final validation (`artifacts/claude/t11-mock-live.xml`); the real-model scenario was run once (budget 1) and is not repeated without owner approval of further calls |
| Verify artifact links and measured timings | Links in this package were checked for existence; timings are copied verbatim from the evidence JSON files |
| Scan exported evidence for secrets | `scripts/ci/secret_scan.py` over tracked files: 0 findings; the T11 live credential scan (`artifacts/t11-secret-scan.py`) was executed by Codex against eight runtime credentials, and the new evidence directories contain no credential values by construction (the agent log prints only typed event names) |

## Acceptance

Issue #14 acceptance requires a successful full incident recording and current rubric status (both delivered locally) and a short video with CI/deploy links (**not delivered**). Verdict: **NO-GO for Issue #14 closure**, deliverables ready for the owner to record the video once T13 hosting exists or, if the owner accepts a local-only submission, to record the local walkthrough from the demo script.
