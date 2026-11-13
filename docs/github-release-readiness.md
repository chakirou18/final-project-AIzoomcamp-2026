# GitHub release readiness

State verified 2026-11-12. Nothing in this document has been applied: merging, ruleset creation, environment creation and secret creation all need explicit owner approval.

## PR chain

`main` contains only the initial commit (`9dbb22a`). The feature branches form one strictly linear chain. Every branch contains its predecessor, and every PR reports `MERGEABLE` / `CLEAN`:

`main` → `t01` (2 commits; no PR) → #16 `t02` → #17 `t03` → #18 `t04` → #19 `t06` → #20 `t05` → #21 `t07` → #22 `t08` → #23 `t09` → #24 `t10` → #25 `t11` → #26 `t12` → #27 `t13` → #28 `t14` → #29 `t15` (`eaa8016`).

T06 precedes T05 in the chain by design (the web interface was built on the worker). Latest PR validation: all seven jobs pass on T12 `07ea7b5`, T13 `9f07bd5`, T14 `7dfe09c` and T15 `eaa8016`. T11 and earlier predate the workflows.

## Safest integration into `main`

**Recommended: one integration PR `feature/t15-final-review` → `main`, merged with "Create a merge commit".**

- Main is an ancestor of the whole chain, so this lands all 19 feature commits exactly once, with their original SHAs, plus one merge commit. Nothing is duplicated and nothing unrelated is added.
- The stacked PRs #16–#29 then contain no new changes relative to `main`. Close each with a comment pointing to the integration PR. GitHub does not mark them merged automatically, because their bases are feature branches.
- Do **not** use squash or rebase merges anywhere in the chain. Both rewrite SHAs, so every later stacked PR would show the earlier work again as duplicate changes.
- Alternative: merge bottom-up. Retarget #16's chain base to `main` after creating a `feature/t01` → `main` PR, then retarget each next PR to `main` after its predecessor merges, always with merge commits. This gives 15 separate reviews and 15 merge commits. Same end state, more steps.

Consequences of the first push to `main`:

- `main-release.yml` runs the full checks on the merged commit.
- It then builds and pushes `ghcr.io/chakirou18/final-project-aizoomcamp-2026:sha-<commit>` and records its digest. This is a real registry publication; check the package visibility after the first run.
- `deploy-development` is skipped while the repository variable `DEVELOPMENT_DEPLOY_ENABLED` is unset. No deployment can happen accidentally.

## Branch protection proposal (repository ruleset; supported on this public repository)

The repository is public, so rulesets and required reviewers for environments are available on the free plan. Current state: 0 rulesets, no classic branch protection, 0 environments. Workflow token default is `read`, and Actions cannot approve PRs.

Proposed ruleset `protect-main`. The owner applies it with `gh api -X POST repos/chakirou18/final-project-AIzoomcamp-2026/rulesets --input ruleset.json` after the integration merge, or before it if the integration PR should already be gated:

```json
{
  "name": "protect-main",
  "target": "branch",
  "enforcement": "active",
  "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
  "bypass_actors": [],
  "rules": [
    {"type": "deletion"},
    {"type": "non_fast_forward"},
    {"type": "pull_request", "parameters": {
      "required_approving_review_count": 0,
      "dismiss_stale_reviews_on_push": true,
      "require_code_owner_review": false,
      "require_last_push_approval": false,
      "required_review_thread_resolution": true
    }},
    {"type": "required_status_checks", "parameters": {
      "strict_required_status_checks_policy": true,
      "required_status_checks": [
        {"context": "checks / Lint, format, lock and secret scan"},
        {"context": "checks / Backend unit tests (mock model)"},
        {"context": "checks / PostgreSQL integration tests (mock model)"},
        {"context": "checks / Dependency audit and configuration checks"},
        {"context": "checks / Prometheus rules and Alertmanager configuration"},
        {"context": "checks / Chromium journey and performance benchmark"},
        {"context": "checks / Build runtime image (not published)"}
      ]
    }}
  ]
}
```

Notes on the ruleset:

- **Approvals:** `required_approving_review_count` is 0 because the owner is the only maintainer and GitHub does not let an author approve their own PR. With a second reviewer, set it to 1. Every change still has to go through a PR with all seven checks passing, with no force pushes and no deletion.
- **Bypass:** the empty `bypass_actors` means the owner can no longer push to `main` directly. To keep an emergency path, add the repository-admin role in bypass mode `pull_request` only.

## GitHub environments (proposal)

| Environment | Protection | Variables | Secrets |
|---|---|---|---|
| `development` | deployment branches: `main` only; no reviewers (automatic deployment) | `DEVELOPMENT_URL` (repository variable), `DEVELOPMENT_DEPLOY_ENABLED=true` (repository variable, set only when the host exists) | `DEVELOPMENT_SSH_HOST`, `DEVELOPMENT_SSH_USER`, `DEVELOPMENT_SSH_KEY`, `DEVELOPMENT_SSH_KNOWN_HOSTS` |
| `production` | deployment branches: `main` only; **required reviewers: owner**; optional wait timer 0 | `PRODUCTION_URL` (repository variable) | `PRODUCTION_SSH_HOST`, `PRODUCTION_SSH_USER`, `PRODUCTION_SSH_KEY`, `PRODUCTION_SSH_KNOWN_HOSTS` |

Commands for the owner to run themselves. Secret values are entered into the `gh` prompt or read from a local file, never pasted into a chat:

```bash
gh api -X PUT repos/chakirou18/final-project-AIzoomcamp-2026/environments/development \
  -F 'deployment_branch_policy[protected_branches]=false' -F 'deployment_branch_policy[custom_branch_policies]=true'
gh api -X POST repos/chakirou18/final-project-AIzoomcamp-2026/environments/development/deployment-branch-policies -f name=main
gh api -X PUT repos/chakirou18/final-project-AIzoomcamp-2026/environments/production \
  -F "reviewers[][type]=User" -F "reviewers[][id]=$(gh api user --jq .id)" \
  -F 'deployment_branch_policy[protected_branches]=false' -F 'deployment_branch_policy[custom_branch_policies]=true'
gh api -X POST repos/chakirou18/final-project-AIzoomcamp-2026/environments/production/deployment-branch-policies -f name=main
gh secret set DEVELOPMENT_SSH_KEY --env development < ~/.ssh/fieldops_dev_deploy     # repeat for each secret
gh variable set DEVELOPMENT_URL --body https://dev.fieldops.<domain>
```

## Acceptance evidence still required (Issue #12)

1. **Merge blocking:** a PR with a failing check shown as blocked by the ruleset.
2. **Development deployment:** a `main-release` run on the merged commit that publishes a digest and deploys development without a manual step.
3. **Production gate:** a `promote-production` run waiting for the required reviewer, then approved, deploying the identical digest.
4. **Digest rejection:** a promotion attempt with an unknown digest rejected by the `verify` job.
