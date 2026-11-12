# T12 CI/CD pipeline: implementation and local validation

Task is [Issue #12](https://github.com/chakirou18/final-project-AIzoomcamp-2026/issues/12), requirement N06 and the architecture's delivery contract. Work is local on `feature/t11-oncall-agent` (T12 shares the branch until the owner authorizes publication; a separate `feature/t12-ci-cd` branch can be cut after T11 is committed). **No workflow has run on GitHub**, no image was published, no environment was deployed and no branch protection, environment or secret was configured: remote operations remain unauthorized. Every claim below is a local, non-destructive verification of configuration and scripts. Remote CI/CD acceptance is **BLOCKED** until the owner authorizes a push and provides hosting.

## Workflows

| File | Trigger | Purpose |
|---|---|---|
| `.github/workflows/checks.yml` | `workflow_call` | Reusable gate: lint/format/lock/secret scan; unit tests (mock model); PostgreSQL integration tests on a `postgres:17` service with migration smoke; dependency audit (`pip-audit` 2.10.1) plus Compose/isolation rendering; promtool/amtool checks of the four alert rules and Alertmanager config; Chromium journey through the committed `browser` profile; runtime image build and import check. Untrusted PR jobs reference no secrets. |
| `.github/workflows/pr-validation.yml` | `pull_request` to `main` and `feature/**` | Calls the reusable checks; cancels superseded runs per PR. Branch protection must require every job. |
| `.github/workflows/main-release.yml` | `push` to `main` | Reruns the checks on the merged commit, builds once with `docker buildx`, pushes `ghcr.io/<repo>:sha-<commit>`, records the registry digest (`release.json` artifact), then the `development` environment job skips stale commits, releases the digest over SSH, records a GitHub deployment with digest/previous/migration, runs the API-to-inbox smoke, and rolls back on failure. Serialized by `concurrency: deploy-development`. Enabled only when the repository variable `DEVELOPMENT_DEPLOY_ENABLED` is `true`. |
| `.github/workflows/promote-production.yml` | `workflow_dispatch` (digest input) | `verify_digest.py` rejects any digest without a successful development deployment; `docker manifest inspect` proves it exists; the `production` environment (required reviewers) gates secrets; the identical digest is released, smoke-tested without pausing delivery, recorded, rolled back on failure. Serialized by `concurrency: deploy-production`. |
| `.github/workflows/rollback-production.yml` | `workflow_dispatch` (digest input) | Same approval and concurrency boundary; accepts only a previously successful production digest. |

Actions are pinned by commit SHA (`actions/checkout` v5.0.0 `08c6903…`, `actions/upload-artifact` v4.6.2 `ea165f8…`); uv is pinned to 0.12.19; the PostgreSQL service image is the same digest as the repository's Compose file.

## Supporting files

- `docker-compose.deploy.yml`: hosted override that replaces every application service's build with `${FIELDOPS_IMAGE}` (registry digest, `pull_policy: always`), forces `FIELDOPS_ENVIRONMENT`/`FIELDOPS_DEMO_MODE` from the environment file, keeps every published port on `127.0.0.1`.
- `deploy/environments/development.env.example`, `production.env.example`: distinct project names, databases, users, ports and subnets; placeholders only.
- `scripts/deploy/deploy.sh`: host release job (previous digest, `pg_dump` backup, digest switch, explicit `migrate` and idempotent `seed --allow-nonlocal` release jobs, `up --wait`, append-only release record; `FIELDOPS_DRY_RUN=1` renders only).
- `scripts/deploy/verify_digest.py`: promotion/rollback gate over GitHub deployment records (pure function unit-tested).
- `scripts/deploy/check_isolation.py`: renders both environments with `docker compose config` and fails on any shared project/database/user/port/subnet/volume, unpinned image, build definition or non-loopback port.
- `scripts/smoke/smoke.py`: readiness, private-path denial, cookie flags, dispatcher login, uniquely marked job, assignment, technician inbox polling for the exact outbox-backed notification, history check; bounded, never pauses delivery, never writes to the database directly.
- `scripts/ci/secret_scan.py`: deterministic credential-pattern scan with documented synthetic allowances.
- `tests/test_t12_pipeline.py`: unit tests for the promotion gate (unknown/failed/in-progress/wrong-environment/tag/branch/malformed digests rejected; JSON-string payloads accepted; rollback requires a production success), the secret scan, and a `pipeline`-marked rendering test.

## Local verification performed

```powershell
docker run --rm -v "${PWD}:/repo:ro" -w /repo rhysd/actionlint:1.7.12 -color      # exit 0, no findings
.venv/Scripts/python.exe scripts/deploy/check_isolation.py --output artifacts/claude/isolation.json   # {"ok": true, "problems": []}
.venv/Scripts/python.exe scripts/ci/secret_scan.py                                 # scanned 130 files, 0 findings
. ./artifacts/t10-env.ps1
.venv/Scripts/python.exe scripts/smoke/smoke.py --base-url http://127.0.0.1:18009 --environment local --allow-http --skip-private-path-check --output artifacts/claude/smoke-local.json   # passed in 0.969 s
.venv/Scripts/python.exe -m pytest tests/test_t12_pipeline.py -p no:cacheprovider   # 10 passed
FIELDOPS_DEPLOY_ROOT=<scratch> FIELDOPS_DRY_RUN=1 bash scripts/deploy/deploy.sh development ghcr.io/…@sha256:<digest>   # renders, records previous/next
FIELDOPS_DEPLOY_ROOT=<scratch> FIELDOPS_DRY_RUN=1 bash scripts/deploy/deploy.sh production ghcr.io/…@sha256:<digest>
bash scripts/deploy/deploy.sh production ghcr.io/x:latest    # rejected: immutable digest required
bash scripts/deploy/deploy.sh staging ghcr.io/x@sha256:…     # rejected: unknown environment
```

The smoke journey against the running synthetic stack created a marked job, assigned it, and saw the exact notification in the technician inbox 0.67 s after assignment ([report](../artifacts/claude/smoke-local.json)). The private-path check was skipped locally because the local web service intentionally serves `/metrics` on loopback; hosted proxies must deny it and the smoke enforces that by default.

### Second pass on `feature/t12-ci-cd` (2026-11-12)

```powershell
git switch -c feature/t12-ci-cd 315b4491e40a19f52ae4ec06dc4de4877792cda4
docker run --rm -v "${PWD}:/repo:ro" -w /repo rhysd/actionlint:1.7.12 -color          # exit 0 after the hardening edits
uv export --frozen --no-dev --no-hashes --format requirements-txt -o requirements-ci.txt
uvx --from "pip-audit==2.10.1" pip-audit -r requirements-ci.txt --strict --progress-spinner off   # No known vulnerabilities found
docker build --target runtime --tag fieldops-ci:local . ; docker run --rm fieldops-ci:local python -c "import fieldops.main, fieldops.worker, fieldops.oncall.runtime"   # import ok
.venv/Scripts/python.exe -m pytest tests/test_t12_pipeline.py -p no:cacheprovider      # 10 passed (also without a Docker daemon)
.venv/Scripts/python.exe scripts/ci/secret_scan.py                                      # 147 files, 0 findings
# CI integration job simulated from the host against a disposable loopback postgres:17 (same digest/env as checks.yml):
#   migrate ×2 + seed passed; 175 integration cases passed with no failure, then the process was stopped by the host for memory pressure (interrupted, not failed).
```

| Workflow | Audit verdict |
|---|---|
| checks.yml | 7 jobs, no secrets, SHA-pinned actions, pipx-installed pinned uv, mock providers only |
| pr-validation.yml | calls checks; cancels superseded PR runs; `contents: read` |
| main-release.yml | checks → publish (buildx push, digest recorded) → development (stale skip, SSH release, deployment record, smoke, auto-rollback); all secrets/outputs via `env:` |
| promote-production.yml | verify (no environment) rejects untested digests and missing manifests → production environment job (approval) → identical digest, smoke, record with the verified commit, auto-rollback |
| rollback-production.yml | same gate against previous production successes; same approval and concurrency boundary |

### Gates not executed before publication (2026-11-12)

On resume the Docker Desktop engine and WSL were found stopped and the owner's policy forbids restarting them without approval. Two local gates therefore remain **NOT EXECUTED**: the promtool/amtool rules-job commands (their rule files are unchanged since T10 and passed 27 promtool assertions there) and the host-side rerun of the CI integration job (175 of the 284 cases had passed with no failure before the earlier interruption; the same 284 passed inside the containerized runner on 2026-11-11). The smoke script was not modified after its last local pass, so that evidence stands. These gates are recorded as **BLOCKED (Docker engine stopped)**, not as failures, and must be rerun before Issue #12 acceptance.

## Real GitHub Actions evidence (PR #26, 2026-11-12)

Opening PR #26 against `feature/t11-oncall-agent` (a `feature/**` base) triggered the `pr-validation` workflow for real. These are genuine hosted runs, not local simulations.

| Run | Commit | Outcome |
|---|---|---|
| [43199177767](https://github.com/chakirou18/final-project-AIzoomcamp-2026/actions/runs/43199177767) | `04f3b49` | lint **failed** on the scanner's own test fixtures (defect caught by the pre-publication scan, fixed in `9e61a79`); remaining jobs cancelled by the superseding run |
| [43199314066](https://github.com/chakirou18/final-project-AIzoomcamp-2026/actions/runs/43199314066) | `9e61a79` | lint, image, Prometheus/Alertmanager rules, PostgreSQL integration (284 cases on the hosted service) and Chromium (18 cases) **passed**; unit and security **failed** because workflow-level database variables leaked into every job (unit fixture tried to reach PostgreSQL; `FIELDOPS_ENVIRONMENT=local` overrode the environment files) and the anchored `build: !reset null` was ignored by the runner's Compose |
| [43200242540](https://github.com/chakirou18/final-project-AIzoomcamp-2026/actions/runs/43200242540) | `51464b5` | attempt 1: lint, unit, PostgreSQL integration, dependency audit + isolation, rules, image **passed**; Chromium **failed** one mobile JS-disabled case (`Page.reload: Not attached to an active page`, 17 passed) — runner-side Playwright instability; attempt 2 (failed-job rerun, no test change): Chromium **passed** — all seven jobs green |

What these runs prove: the PR gate executes automatically on GitHub-hosted runners with pinned actions and no secrets; the mock-model unit and real-PostgreSQL integration suites, the dependency audit, the rule tests, the isolation render and the image build pass remotely. What they do not prove: merge blocking (no branch protection yet), the main→development automatic deployment, digest publication, the production approval gate or any hosted smoke — those remain BLOCKED.

## Tests required by Issue #12 and their status

| Required test | Status |
|---|---|
| PR passing/failing gates | **ACTUAL**: three real `pr-validation` runs on PR #26 show failing gates (lint on `04f3b49`, unit/security on `9e61a79`) and passing gates on `51464b5`. Merge blocking itself needs branch protection (owner setting) — BLOCKED. |
| Merge-to-main automatic development deployment with API→inbox smoke | Workflow and smoke script implemented; smoke exercised locally; remote run BLOCKED (no hosting). |
| Rendered development/production DSN/volume separation | PASS locally (`check_isolation.py`, `test_hosted_environments_render_isolated_and_digest_pinned`). |
| Unknown/failed-development digest promotion rejection | PASS locally (`test_only_a_successful_development_tested_digest_is_promotable`, `test_tags_branches_and_malformed_digests_are_rejected`). |
| Manual approval enforcement | Implemented through the `production` environment; the reviewer policy is a repository setting the owner must configure; remote evidence BLOCKED. |
| Stale-run prevention | Implemented (`origin/main` head comparison before release); remote evidence BLOCKED. |
| Mock model in CI; no production pause | Integration/unit jobs use the deterministic providers; smoke never pauses. |
| Rules job (promtool/amtool) and integration job | **ACTUAL** on GitHub (runs 43199314066 and 43200242540: both jobs pass); local reruns remain blocked by the stopped Docker engine. |

## Owner decisions and prerequisites

Repository variables `DEVELOPMENT_DEPLOY_ENABLED`, `DEVELOPMENT_URL`, `PRODUCTION_URL`; secrets `DEVELOPMENT_SSH_HOST/USER/KEY/KNOWN_HOSTS` and `PRODUCTION_SSH_*`; GitHub environments `development` (no reviewers) and `production` (required reviewers, restricted to `main`); branch protection on `main` requiring the `checks` jobs; GHCR package visibility; and hosting (procedure prepared for T13). None of these can be created from this session.
