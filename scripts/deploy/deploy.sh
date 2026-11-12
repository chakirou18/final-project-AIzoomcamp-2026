#!/usr/bin/env bash
# Host-side release job for one hosted environment. Runs on the deployment host over SSH.
#
#   deploy.sh <development|production> <registry/image@sha256:digest>
#
# Layout per environment (never shared between environments):
#   $FIELDOPS_DEPLOY_ROOT/<env>/.env       host-only Compose variables and distinct project name
#   $FIELDOPS_DEPLOY_ROOT/<env>/repo       checkout of the Compose files at the released commit
#   $FIELDOPS_DEPLOY_ROOT/<env>/releases   append-only JSON release/rollback records
#   $FIELDOPS_DEPLOY_ROOT/<env>/backups    pg_dump custom-format backups taken before migration
#
# The script records the previous digest, backs up that environment's database, switches the
# pinned digest, runs the explicit migration and idempotent seed release jobs, starts the
# stack and prints one JSON line. It never builds images, never downgrades schema, never
# restores data and never touches another environment's project, volumes or secrets.
set -euo pipefail

ENVIRONMENT="${1:?environment}"
IMAGE="${2:?image@sha256:digest}"
case "$ENVIRONMENT" in development | production) ;; *) echo "unknown environment" >&2; exit 2 ;; esac
[[ "$IMAGE" =~ ^[a-z0-9./_-]+@sha256:[0-9a-f]{64}$ ]] || { echo "immutable digest required" >&2; exit 2; }

ROOT="${FIELDOPS_DEPLOY_ROOT:-/srv/fieldops}"
ENV_DIR="$ROOT/$ENVIRONMENT"
ENV_FILE="$ENV_DIR/.env"
REPO="$ENV_DIR/repo"
test -f "$ENV_FILE" || { echo "missing $ENV_FILE" >&2; exit 2; }
test -f "$REPO/docker-compose.yml" || { echo "missing $REPO/docker-compose.yml" >&2; exit 2; }
mkdir -p "$ENV_DIR/releases" "$ENV_DIR/backups"

# shellcheck disable=SC1090
set -a; source "$ENV_FILE"; set +a
[[ "${FIELDOPS_ENVIRONMENT:-}" == "$ENVIRONMENT" ]] || { echo "env file belongs to another environment" >&2; exit 2; }
[[ "${COMPOSE_PROJECT_NAME:-}" == "fieldops-$ENVIRONMENT" ]] || { echo "unexpected project name" >&2; exit 2; }

# Optional overlays: the HTTPS edge when a public host is configured, the private model network
# when the environment selects the Ollama provider. Both are no-ops when not configured.
OVERLAYS=()
if [[ -n "${FIELDOPS_PUBLIC_HOST:-}" && -f "$REPO/docker-compose.proxy.yml" ]]; then
  OVERLAYS+=(-f "$REPO/docker-compose.proxy.yml")
fi
if [[ "${FIELDOPS_ONCALL_PROVIDER:-unconfigured}" == "ollama" && -f "$REPO/docker-compose.model-client.yml" ]]; then
  OVERLAYS+=(-f "$REPO/docker-compose.model-client.yml")
fi

compose() {
  docker compose --project-directory "$REPO" --env-file "$ENV_FILE" \
    -f "$REPO/docker-compose.yml" -f "$REPO/docker-compose.deploy.yml" "${OVERLAYS[@]}" \
    --profile observability --profile incident "$@"
}

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
PREVIOUS="$(grep -E '^FIELDOPS_IMAGE=' "$ENV_FILE" | cut -d= -f2- || true)"
BACKUP=""
if compose ps --status running --services 2>/dev/null | grep -qx db; then
  BACKUP="$ENV_DIR/backups/$STAMP-$ENVIRONMENT.dump"
  compose exec -T db pg_dump -Fc -U "$POSTGRES_USER" "$POSTGRES_DB" > "$BACKUP"
  test -s "$BACKUP"
fi

sed -i "s#^FIELDOPS_IMAGE=.*#FIELDOPS_IMAGE=$IMAGE#" "$ENV_FILE"
if [[ "${FIELDOPS_DRY_RUN:-}" == "1" ]]; then
  compose config --quiet
  printf '{"environment":"%s","previous":"%s","next":"%s","backup":"%s","overlays":"%s","dry_run":true}\n' \
    "$ENVIRONMENT" "$PREVIOUS" "$IMAGE" "$BACKUP" "${OVERLAYS[*]:-}"
  exit 0
fi

if [[ "${OVERLAYS[*]:-}" == *docker-compose.model-client.yml* ]]; then
  docker network inspect fieldops-model >/dev/null 2>&1 \
    || { echo "start the private model runtime first: docker compose -f docker-compose.model.yml up -d --wait" >&2; exit 2; }
fi
compose pull --quiet --ignore-buildable
# Observability services wrap digest-pinned vendor images with a static probe binary
# (observability/Dockerfile.probe); build them on the host. Application services have no build.
compose build --quiet
# Explicit release jobs: expand-only migration, then idempotent synthetic personas.
compose run --rm --no-deps bootstrap python -m fieldops.bootstrap migrate
compose run --rm --no-deps bootstrap python -m fieldops.bootstrap seed --allow-nonlocal
compose up -d --no-build --wait --wait-timeout 180
MIGRATION="$(compose exec -T db psql -At -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c 'SELECT version_num FROM alembic_version')"
RUNNING="$(compose ps --status running --services | sort | tr '\n' ' ')"
RECORD="$ENV_DIR/releases/$STAMP-$ENVIRONMENT.json"
printf '{"environment":"%s","previous":"%s","next":"%s","migration_version":"%s","backup":"%s","running":"%s","at":"%s"}\n' \
  "$ENVIRONMENT" "$PREVIOUS" "$IMAGE" "$MIGRATION" "$BACKUP" "$RUNNING" "$STAMP" | tee "$RECORD"
