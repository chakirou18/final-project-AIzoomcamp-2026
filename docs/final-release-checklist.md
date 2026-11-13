# Final release checklist

Status as of the Claude handover session on 2026-11-11 (local, unpublished). Each line states the actual result; "BLOCKED" items need an owner action or approval and are not claimed. Counts and links are in [T15 final review](t15-final-review.md).

## Code and tests

- [x] Working tree on `feature/t11-oncall-agent` from published T10 `7b6889c`; Codex work preserved and checkpointed; T09/T10 sources untouched except the audited T11 changes.
- [x] Ruff lint and format clean; `uv lock --check --offline` clean; `docker compose … config --quiet` clean for all profiles; `git diff --check` clean.
- [x] Backend unit suite passed (mock model).
- [x] Complete PostgreSQL integration suite passed on the retained isolated database (one database-deletion assertion deselected, as in T10/T11).
- [x] Chromium suite passed (18 cases, N03 p95 50.4 ms).
- [x] T11 audit regressions added and passing (freshness anchor, budget ordering, provider bounds and failure codes).
- [x] T09 observability (10) and T10 alerting (5, receipt 101.672 s) regressions rerun on the rebuilt images.
- [x] Mock live incident rerun on the rebuilt images (RESOLVED, intake 101.61 s).
- [x] Integrity probe: 244/244 outbox/inbox, zero anomalies, agent role privileges unchanged, 37 container source files equal the workspace.

## Real-model acceptance (Issue #11)

- [x] Genuine model invocation (llama3.2:3b via the owner's local Ollama, zero spend, one durable reservation) diagnosed the real paused-delivery incident; operator grant; one allowlisted resume; delivery verified; RESOLVED. Evidence `artifacts/t11-real-5bd8899d1d424a9ab234acf3b3f405a1/`.
- [x] Counterfactual model outputs were denied by the deterministic policy (pre-flight probes).
- [x] Owner confirmed the local Ollama/llama3.2 provider as the approved existing provider (2026-11-11).
- [ ] Owner decides whether further real calls are permitted (`FIELDOPS_ONCALL_MAX_CALLS` is 1 and consumed in the synthetic database).

## Publication (requires explicit owner authorization; none performed)

- [x] T11 committed (`315b449`), pushed, PR #25 → `feature/t10-alerting`, Issue #11 progress comment (2026-11-11).
- [x] T13 PR #27, T14 PR #28 published after local review; T15 PR from `feature/t15-final-review`.
- [ ] No merge, no deployment.

## CI/CD and hosting (T12/T13) — remote deployment BLOCKED

- [x] Workflows pass actionlint; gates, smoke, isolation and deploy scripts verified locally.
- [x] T12 published: `feature/t12-ci-cd` (`04f3b49`, `9e61a79`, `51464b5`), PR #26 → `feature/t11-oncall-agent`, Issue #12 comment.
- [x] Real `pr-validation` runs on PR #26: lint, unit, PostgreSQL integration, dependency audit + isolation, rules, image jobs pass on `51464b5` (run 43200242540); Chromium passed on run 43199314066, flaked once on attempt 1 of 43200242540 (see T12 validation for the rerun).
- [x] T13 tooling: HTTPS edge overlay, exposure/backup/capacity scripts, environment variables documented; rendered and syntax-checked locally.
- [ ] Branch protection on `main` requiring the `checks` jobs.
- [ ] GitHub environments `development` (no reviewers) and `production` (required reviewers).
- [ ] Repository variables/secrets for the deployment hosts; approved hosting with DNS and TLS.
- [ ] First real PR run, main→development run, blocked production gate, failed-check denial (Issue #12 evidence).
- [ ] Production promotion, smoke, backup verification and rollback rehearsal run URLs (Issue #13 evidence).

## Demonstration and submission (T14) — partially BLOCKED

- [x] Reviewer walkthrough, incident scenario, evidence index and rubric mapping written.
- [x] Demo video published 2026-11-13: [release v1.0.0-demo](https://github.com/chakirou18/final-project-AIzoomcamp-2026/releases/tag/v1.0.0-demo) (web interface, interventions, Grafana, previously validated alerting evidence; no live agent run).
- [ ] CI/deploy links (none exist).

## Housekeeping

- [ ] Owner may repair the Ollama folder ACL (`icacls C:\Users\chaki\.ollama /grant "chaki:(OI)(CI)F" /T`) so the primary instance works; the second instance started by Claude on port 11435 was stopped by the host for memory pressure and holds no state.
- [ ] The retained integration database container `fieldops-t11-test-db` can be stopped gracefully after review (volume retained; no deletion authorized).

## Release readiness pass (2026-11-12)

- [x] PR chain #16–#29 verified linear, conflict-free, MERGEABLE/CLEAN; merge plan in `docs/github-release-readiness.md`.
- [x] Ruleset, environments, secrets and variables proposal prepared (not applied).
- [x] Hosting options costed from verified sources; approval request in `docs/t13-hosting-proposal.md` (no spending).
- [x] Private model runtime overlay and deploy.sh build fix; dry runs for both environments.
- [x] README reviewer sections; recording package in `docs/demo-script.md` section 6.
- [ ] Owner: approve and apply the integration merge, ruleset and environments.
- [ ] Owner: choose hosting and a monthly ceiling; provide DNS; `az login` if Azure should be reconsidered.
- [x] Owner: recorded and published the demo video (release v1.0.0-demo).
