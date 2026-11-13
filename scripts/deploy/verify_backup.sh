#!/usr/bin/env bash
# Verify a pg_dump custom-format backup without restoring it anywhere.
#
#   verify_backup.sh <backup.dump> [compose args...]
#
# Checks the file is non-empty, that pg_restore can list its table of contents, that the
# application tables appear in it, and prints its size and SHA-256. When Compose arguments are
# given (project directory, env file, compose files) the listing runs inside that environment's
# own `db` container, so no PostgreSQL client is needed on the host. Never restores data.
set -euo pipefail

BACKUP="${1:?backup file}"
shift || true
test -s "$BACKUP" || { echo "backup missing or empty: $BACKUP" >&2; exit 2; }

if [[ $# -gt 0 ]]; then
  LIST="$(docker compose "$@" exec -T db pg_restore --list < "$BACKUP")"
else
  LIST="$(pg_restore --list "$BACKUP")"
fi

REQUIRED=(users interventions intervention_history notification_outbox notifications worker_control worker_resume_actions incidents incident_events incident_grants incident_actions alembic_version)
MISSING=()
for table in "${REQUIRED[@]}"; do
  grep -qE "TABLE DATA public ${table} " <<<"$LIST" || MISSING+=("$table")
done

SIZE="$(stat -c %s "$BACKUP" 2>/dev/null || stat -f %z "$BACKUP")"
SHA="$(sha256sum "$BACKUP" | awk '{print $1}')"
ENTRIES="$(grep -c '^[0-9]' <<<"$LIST" || true)"
printf '{"backup":"%s","bytes":%s,"sha256":"%s","toc_entries":%s,"missing_tables":%s}\n' \
  "$BACKUP" "$SIZE" "$SHA" "$ENTRIES" "$(printf '%s\n' "${MISSING[@]:-}" | grep -v '^$' | sed 's/.*/"&"/' | paste -sd, | sed 's/^/[/;s/$/]/')"
[[ ${#MISSING[@]} -eq 0 ]]
