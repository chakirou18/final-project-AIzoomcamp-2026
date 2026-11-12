#!/usr/bin/env bash
# External exposure check for a deployment host. Run on the host (or against it with
# EXPOSURE_TARGET=<ip> when nmap is available). Prints every listening TCP socket bound to a
# non-loopback address and fails when anything other than SSH (22), HTTP (80) and HTTPS (443)
# is reachable from outside. Does not change any state.
set -euo pipefail

ALLOWED="${EXPOSURE_ALLOWED:-22 80 443}"
TARGET="${EXPOSURE_TARGET:-}"

if [[ -n "$TARGET" ]] && command -v nmap >/dev/null 2>&1; then
  OPEN="$(nmap -sT -Pn -p- --open -oG - "$TARGET" | awk -F'Ports: ' '/Ports:/{print $2}' | tr ',' '\n' | awk -F/ '$2=="open"{print $1}' | tr -d ' ')"
else
  # Host-local view: sockets bound to 0.0.0.0, :: or a public interface address.
  OPEN="$(ss -Hltn 2>/dev/null | awk '{print $4}' | grep -vE '^(127\.|\[::1\]|::1)' | sed -E 's/.*:([0-9]+)$/\1/' | sort -un)"
fi

STATUS=0
for port in $OPEN; do
  if grep -qw -- "$port" <<<"$ALLOWED"; then
    echo "allowed  $port"
  else
    echo "EXPOSED  $port"
    STATUS=1
  fi
done
echo "loopback-only services (expected): $(ss -Hltn 2>/dev/null | awk '{print $4}' | grep -cE '^(127\.|\[::1\])' || true)"
exit $STATUS
