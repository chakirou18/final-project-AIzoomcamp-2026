# T13 rollback procedure

Applies to the hosted development and production environments described in [T13 deployment](t13-deployment.md). Rollback redeploys a previously successful **immutable image digest** for every application process of one environment. It never downgrades the database schema, never restores a backup and never touches the other environment. This procedure is **prepared and locally rehearsed only**; no hosted environment exists yet, so no remote rollback has been executed. See [T13 validation](t13-validation.md) for what was actually run.

## What every release records before it changes anything

`scripts/deploy/deploy.sh <environment> <image@sha256:...>` runs on the host and, before switching the digest:

1. Reads the currently pinned digest from the environment's host-only `.env` (`previous`).
2. Takes a `pg_dump -Fc` backup of that environment's own database into `<root>/<environment>/backups/<utc-stamp>-<environment>.dump` when the database container is running.
3. Writes an append-only release record `<root>/<environment>/releases/<utc-stamp>-<environment>.json` containing `previous`, `next`, `migration_version`, `backup` and the running services after the switch.

The GitHub deployment record created by the workflow carries the same `previous` digest and migration version, so the rollback target is discoverable from the repository without host access.

## Automatic rollback on failed smoke

Both `main-release.yml` (development) and `promote-production.yml` (production) run the API-to-inbox smoke after the host release. If the smoke fails and a `previous` digest exists, the workflow immediately redeploys that digest with the same `deploy.sh`, reruns the smoke, marks the GitHub deployment `failure` with the rollback target in its description and uploads `host-rollback.json` plus both smoke reports. If no previous digest exists (first bootstrap), the run is marked failed with an explicit operator-intervention error and nothing is redeployed.

## Manual production rollback

`rollback-production.yml` is a `workflow_dispatch` that accepts one input: a digest that previously completed a **successful production deployment** (`scripts/deploy/verify_digest.py <digest> production`). Unknown, failed or development-only digests are rejected before any host access. The job then requires the protected `production` environment approval, redeploys the digest through `deploy.sh`, runs the smoke, and records a production deployment whose payload has `rollback: true`. The same concurrency group as promotion serializes the two workflows.

## Schema compatibility rule

Migrations are expand-only (T03–T11 add tables and columns; migration 0004 refuses downgrade when incidents exist). A rolled-back image therefore runs against a newer schema it does not know about, which is compatible by construction. A rollback across a future **contracting** migration would require a separate owner-approved backup restoration, which this workflow deliberately cannot do.

## Rehearsal commands (host)

```bash
# Dry run: validates the environment file, renders the Compose configuration and prints the
# previous/next digests without pulling, migrating or restarting anything.
FIELDOPS_DRY_RUN=1 sudo /srv/fieldops/bin/deploy.sh production ghcr.io/<owner>/<repo>@sha256:<previous>
# Real rollback (same approval boundary as promotion when run from GitHub Actions).
sudo /srv/fieldops/bin/deploy.sh production ghcr.io/<owner>/<repo>@sha256:<previous>
python3 scripts/smoke/smoke.py --base-url https://<production-host> --environment production --output smoke-rollback.json
```

## Backup verification before and after rollback

`scripts/deploy/verify_backup.sh <dump> --project-directory <repo> --env-file <env> -f docker-compose.yml -f docker-compose.deploy.yml` lists the dump's table of contents inside the environment's own `db` container, asserts every application table is present and prints the size and SHA-256 that go into the release record. It never restores. Restoration remains a separate, owner-approved, documented operation.

## Evidence required before T13 can be accepted

- Release record and GitHub deployment showing `previous` and `next` digests for one real production promotion.
- A real rollback run URL (automatic or manual) redeploying the previous digest with a passing smoke report.
- Backup file size and `pg_restore --list` verification output for the pre-migration backup of that release.
- Restart persistence evidence: inbox and history rows unchanged across `docker compose restart` of the rolled-back stack.
