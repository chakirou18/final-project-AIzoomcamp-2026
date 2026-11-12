#!/usr/bin/env bash
# Measure whether the host can run the requested environments side by side. Read-only.
#
#   check_capacity.sh [compose-project-name ...]
#
# Prints host memory, swap, disk and load, then the live memory of every container in the
# named Compose projects together with the sum of their configured limits. Fails when free
# memory after the configured limits would drop under FIELDOPS_MIN_FREE_MIB (default 2048) or
# when free disk is under FIELDOPS_MIN_FREE_DISK_GIB (default 10).
set -euo pipefail

MIN_FREE_MIB="${FIELDOPS_MIN_FREE_MIB:-2048}"
MIN_FREE_DISK_GIB="${FIELDOPS_MIN_FREE_DISK_GIB:-10}"

read -r TOTAL_KIB AVAIL_KIB < <(awk '/MemTotal/{t=$2} /MemAvailable/{a=$2} END{print t, a}' /proc/meminfo)
read -r SWAP_TOTAL_KIB SWAP_FREE_KIB < <(awk '/SwapTotal/{t=$2} /SwapFree/{f=$2} END{print t, f}' /proc/meminfo)
DISK_FREE_GIB="$(df -BG --output=avail / | tail -1 | tr -dc '0-9')"
LOAD="$(cut -d' ' -f1-3 /proc/loadavg)"
echo "host: total=$((TOTAL_KIB/1024))MiB available=$((AVAIL_KIB/1024))MiB swap_used=$(((SWAP_TOTAL_KIB-SWAP_FREE_KIB)/1024))MiB disk_free=${DISK_FREE_GIB}GiB load=${LOAD}"

LIMIT_SUM=0
for project in "$@"; do
  while IFS=$'\t' read -r name used limit; do
    [[ -z "$name" ]] && continue
    echo "container: $name used=$used limit=$limit"
    case "$limit" in
      *GiB) LIMIT_SUM=$((LIMIT_SUM + ${limit%GiB} * 1024)) ;;
      *MiB) LIMIT_SUM=$((LIMIT_SUM + ${limit%MiB})) ;;
    esac
  done < <(docker ps --filter "label=com.docker.compose.project=${project}" --format '{{.ID}}' \
           | xargs -r docker stats --no-stream --format '{{.Name}}\t{{.MemUsage}}' \
           | awk -F'\t' '{split($2,a," / "); print $1"\t"a[1]"\t"a[2]}')
done
echo "configured limits of listed projects: ${LIMIT_SUM}MiB (unlimited services excluded)"

STATUS=0
if (( AVAIL_KIB/1024 - LIMIT_SUM < MIN_FREE_MIB )); then echo "FAIL: less than ${MIN_FREE_MIB}MiB would remain free"; STATUS=1; fi
if (( DISK_FREE_GIB < MIN_FREE_DISK_GIB )); then echo "FAIL: less than ${MIN_FREE_DISK_GIB}GiB disk free"; STATUS=1; fi
[[ $STATUS -eq 0 ]] && echo "capacity ok"
exit $STATUS
