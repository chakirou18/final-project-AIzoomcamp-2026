# T13 deployment: preparation and local validation

Task is [Issue #13](https://github.com/chakirou18/final-project-AIzoomcamp-2026/issues/13). **Remote acceptance is BLOCKED**: no hosting, public DNS/TLS, GitHub environments, deployment secrets or owner deployment approval exist. No public URL, deployment run, approval record, production smoke, backup or rollback run is claimed. This record lists what was prepared and what was verified locally without touching any remote system. See [T13 deployment](t13-deployment.md) and [T13 rollback](t13-rollback.md) for the procedures.

## Prepared deliverables

| Deliverable | Location | Local verification |
|---|---|---|
| Hosted Compose override (digest-pinned, loopback-only ports, environment-scoped settings) | `docker-compose.deploy.yml` | Rendered for both environments by `scripts/deploy/check_isolation.py`: ok, zero problems ([report](../artifacts/claude/isolation.json)) |
| Per-environment configuration templates | `deploy/environments/*.env.example` | Distinct project, database, user, ports, subnets; placeholders only; secret scan clean |
| Host release/rollback script with backup and release records | `scripts/deploy/deploy.sh` | Dry run for development and production renders and records previous/next digests; tag references and unknown environments are rejected with exit 2 |
| Public smoke (HTTPS readiness, private-path denial, cookie flags, API→inbox journey, history) | `scripts/smoke/smoke.py` | Passed against the local synthetic stack in 0.969 s with the loopback-only private-path exemption ([report](../artifacts/claude/smoke-local.json)) |
| Promotion of the identical tested digest with approval gate; manual rollback workflow | `.github/workflows/promote-production.yml`, `rollback-production.yml` | actionlint 1.7.12 clean; gate logic unit-tested (`tests/test_t12_pipeline.py`) |
| Environment isolation and restart persistence | T02 lifecycle test `startup_and_persistence` (local Compose), isolation renderer | Retained T11 evidence: 2 safe lifecycle cases passed (`artifacts/t11-lifecycle.xml`); isolation ok |
| Backup verification procedure | `deploy.sh` (`pg_dump -Fc` before migration), rollback doc | Not exercised remotely; the T11 pre-migration backup (`artifacts/t11-pre-migration-t10.dump`, SHA256 `75718e3d…`) demonstrates the same command locally |
| Capacity and exposure checks | `scripts/deploy/check_capacity.sh`, `scripts/deploy/check_exposure.sh` | Syntax-checked; not executed (Linux host and Docker engine required); local resource samples only (agent 57.55 MiB / 192 MiB during the real-model run) |
| Public HTTPS edge | `docker-compose.proxy.yml`, `deploy/proxy/Caddyfile` | Rendered locally (digest-pinned Caddy, 80/443 only on the proxy); TLS issuance and edge deny rules not exercised |
| Backup verification | `scripts/deploy/verify_backup.sh` | Syntax-checked; not executed against a dump (Docker engine stopped) |

## Acceptance matrix

| Issue #13 criterion | Status |
|---|---|
| Public synthetic-data journey works over HTTPS | BLOCKED (no hosting); journey verified locally over loopback HTTP |
| Internal services remain private | Prepared (loopback-only ports, proxy deny rules, smoke assertion); BLOCKED remotely |
| Development changes cannot mutate production data | PASS locally by configuration rendering (distinct projects, databases, users, volumes, subnets) |
| Manual dispatch plus production approval promotes the exact development digest | Implemented; BLOCKED remotely |
| Both environments pass assignment/inbox smoke | Smoke verified locally; BLOCKED remotely |
| Restart preserves inbox/history | PASS locally (retained lifecycle evidence) |
| Backups verified | Procedure prepared; BLOCKED remotely |
| Previous compatible digest rollback passes smoke | Implemented (automatic and manual); dry run only |
| Concurrent environments within measured resources | BLOCKED (no host) |
| No destructive restore without approval | By design: no restore path exists in the workflows |

## Session note (2026-11-12)

The Docker Desktop engine was stopped when this validation pass ran and the owner's policy forbids restarting it; every Docker-backed local check listed as "not executed" is therefore BLOCKED on an owner action, not failed. An enabled Azure subscription exists on the development machine and is the candidate hosting path; using it needs explicit approval because it costs money. See the hosting evaluation in [T13 deployment](t13-deployment.md).

## Owner approvals required

Hosting budget/access, DNS + TLS, GitHub environment and secret configuration, a validated main branch, and explicit authorization to deploy. The two environments must never share a database; a shared host requires the capacity check in the deployment document before production is promoted.
