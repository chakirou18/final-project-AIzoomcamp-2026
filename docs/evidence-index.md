# Evidence index: requirements, rubric and artifacts

Maps every functional (F01–F10) and non-functional (N01–N07) requirement from the [specification](specification.md) to actual artifacts produced locally. "Local" means verified on the developer machine against synthetic data; "BLOCKED" means the required remote/hosted evidence does not exist and is not claimed. The supplied 24-point rubric mapping is preserved from [rubric evidence](rubric-evidence.md); the provisional 41-point alternative stays separate and is not used for any claim here.

## Requirement to evidence

| Requirement | Evidence | Status |
|---|---|---|
| F01 Jobs CRUD, validation, pagination | `tests/test_t04*.py`, `test_t05_web.py`; PostgreSQL suite `artifacts/claude/t11-audit-full-postgres.xml` | PASS local |
| F02 Assignment with atomic history + outbox | `tests/test_t06_postgresql.py`; smoke `artifacts/claude/smoke-local.json` | PASS local |
| F03 Technician transitions | `tests/test_t04.py`, browser suite | PASS local |
| F04 Priorities, history, stale version | `tests/test_t04.py`, `test_t04_review.py` | PASS local |
| F05 Durable notifications, inbox scope, restart survival | T06 suite; lifecycle `artifacts/t11-lifecycle.xml` | PASS local |
| F06 Dashboard counts, delayed label | T07 suite; live dashboard reads in T09–T11 evidence | PASS local |
| F07 Automatic delay detection ≤ 110 s | `artifacts/t10-alerting-*/real-alert.json` (103.797 s), T11 real run 100.719 s, four rules / 27 promtool assertions | PASS local |
| F08 Safe recovery and incident review | `artifacts/t11-real-5bd8899d1d424a9ab234acf3b3f405a1/evidence.json` (real model), `artifacts/t11-live-a50f4cf158114cdd8359a8c69d0aa2bd/evidence.json` (mock), `tests/test_t11*.py` | PASS local |
| F09 OpenAPI, health, private metrics | `tests/test_contracts.py`, `test_health.py`; smoke private-path check (hosted) | PASS local; hosted exposure BLOCKED |
| F10 Role permissions, CSRF | `tests/test_sessions.py`, T05/T07 reviews, T11 grant tests | PASS local |
| N01 Reliability (rollback, crash after inbox insert) | T06 PostgreSQL injected-failure tests | PASS local |
| N02 Delivery SLO (20 assignments ≤ 10 s each) | T06/T08 measured results in `docs/t08-validation.md` | PASS local |
| N03 Performance p95 < 1 s | browser benchmark (T11 rerun p95 85.262 ms; audit rerun in `artifacts/claude/browser.log`) | PASS local |
| N04 Security (secrets, roles, bounded agent) | `scripts/ci/secret_scan.py` (0 findings), T11 audit security review, role privilege probe | PASS local |
| N05 Operability (trace correlation, incident records) | T09 evidence, `artifacts/claude/t09-regression.xml`, incident events | PASS local |
| N06 Reproducibility (four Compose workflows, CI before deployment) | README commands verified through T11; `.github/workflows/*` validated by actionlint and by real `pr-validation` runs on PR #26; automatic development deployment | Local PASS; PR CI ACTUAL; deployment BLOCKED |
| N07 Usability (375 px, keyboard, fallbacks) | browser suite desktop/mobile cases | PASS local |

## Task evidence

| Task | Validation | Audit | Key artifacts |
|---|---|---|---|
| T09 | [t09-validation](t09-validation.md) | — | trace/log correlation, Grafana views |
| T10 | [t10-validation](t10-validation.md) | [t10-audit](t10-audit.md) | real alert 103.797 s |
| T11 | [t11-validation](t11-validation.md) | [t11-audit](t11-audit.md) | real-model incident `cfa129e9…`, PostgreSQL 284 + 2 audit cases, unit 207 |
| T12 | [t12-validation](t12-validation.md) | [t12-audit](t12-audit.md) | actionlint, isolation report, smoke, gate tests |
| T13 | [t13-validation](t13-validation.md) | — | deployment/rollback procedures, dry runs |
| T14 | [t14-validation](t14-validation.md) | — | this index, [demo script](demo-script.md) |
| T15 | [t15-final-review](t15-final-review.md) | [final release checklist](final-release-checklist.md) | final verdict |

## Evidence classes

| Class | Meaning | Examples |
|---|---|---|
| ACTUAL | produced in this project and re-verifiable now | demo video [release v1.0.0-demo](https://github.com/chakirou18/final-project-AIzoomcamp-2026/releases/tag/v1.0.0-demo) (1 min 33 s, published 2026-11-13; web interface, interventions, Grafana, previously validated alerting evidence), source and PRs #21–#26, `artifacts/claude/*.xml` JUnit files, `artifacts/t11-real-5bd8899d…/evidence.json`, real GitHub Actions runs on PR #26 |
| HISTORICAL | produced by an earlier validated session and not rerun since | T08–T10 measurements quoted in their validation documents, Codex's 507-case T11 ledger |
| PLANNED | designed and documented, execution depends on an owner action | public deployment, production promotion with approval, rollback rehearsal, a video of a live On-Call agent recovery |
| BLOCKED | cannot be produced from this machine or session | hosted smoke results, approval records, public URLs, main→development automatic run (no main merge, no hosting) |

## GitHub publication state (2026-11-12)

| Task | Branch | Commit(s) | PR | Status |
|---|---|---|---|---|
| T11 | `feature/t11-oncall-agent` | `315b4491…` | [#25](https://github.com/chakirou18/final-project-AIzoomcamp-2026/pull/25) → `feature/t10-alerting` | open, unmerged |
| T12 | `feature/t12-ci-cd` | `04f3b497…`, `9e61a791…`, `51464b52…`, `07ea7b54…` | [#26](https://github.com/chakirou18/final-project-AIzoomcamp-2026/pull/26) → `feature/t11-oncall-agent` | open, unmerged; real `pr-validation` runs: [43199314066](https://github.com/chakirou18/final-project-AIzoomcamp-2026/actions/runs/43199314066) (lint, image, rules, PostgreSQL integration, Chromium passed; unit and security failed on a workflow env leak), [43200242540](https://github.com/chakirou18/final-project-AIzoomcamp-2026/actions/runs/43200242540) (all seven jobs green after one Chromium failed-job rerun) |
| T13 | `feature/t13-deployment` | `9f07bd5a…` | [#27](https://github.com/chakirou18/final-project-AIzoomcamp-2026/pull/27) → `feature/t12-ci-cd` | open, unmerged; tooling only, no public deployment |
| T14 | `feature/t14-evidence` | `7dfe09c2…` | [#28](https://github.com/chakirou18/final-project-AIzoomcamp-2026/pull/28) → `feature/t13-deployment` | merged to `main` via #30; documentation; demo video published separately as release v1.0.0-demo |
| T15 | `feature/t15-final-review` | see PR | → `feature/t14-evidence` | final review documents, edge-config correction |

Issues #11 and #12 carry progress comments; no Issue is closed; no PR is merged.

## Not available (stated plainly)

- No video of a live On-Call agent recovery or of a new live alert. The published [demo video](https://github.com/chakirou18/final-project-AIzoomcamp-2026/releases/tag/v1.0.0-demo) covers the web interface, interventions, Grafana monitoring and previously validated alerting test evidence; the live agent evidence is the recorded T11 real-model run (`artifacts/t11-real-5bd8899d…/evidence.json`, quoted in [T11 audit](t11-audit.md)).
- No public URL, hosted deployment, GitHub Actions run, production approval record or remote rollback.
- No cloud model provider; the real model is the owner's local llama3.2:3b. Model output quality on counterfactuals is weak and documented.
- Five worker-stop lifecycle cases and one database-deletion assertion remain unexecuted under the data-preservation constraint, as in T09–T11.
