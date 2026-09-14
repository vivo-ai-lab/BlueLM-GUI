#!/usr/bin/env bash
#
# Removes AndroidWorld containers created by create_containers.sh.
#
# Usage:
#   ./scripts/remove_containers.sh <START_PORT> <END_PORT>   # remove by port range
#   ./scripts/remove_containers.sh --all                      # remove ALL containers with the prefix
#
# Options (env vars):
#   CONTAINER_PREFIX  container name prefix (default: android_world)
#   DRY_RUN=1         print docker commands without executing them
#
# Examples:
#   ./scripts/remove_containers.sh 5001 5064
#   ./scripts/remove_containers.sh --all
#   DRY_RUN=1 ./scripts/remove_containers.sh 5001 5004

set -euo pipefail

CONTAINER_PREFIX="${CONTAINER_PREFIX:-android_world}"
DRY_RUN="${DRY_RUN:-0}"

if ! command -v docker >/dev/null 2>&1; then
  echo "Error: docker CLI not found in PATH." >&2
  exit 1
fi

MODE="${1:-}"

remove_container() {
  local name="$1"
  if ! docker ps -a --format '{{.Names}}' | grep -qx "${name}"; then
    echo "==> Skipping ${name}: not found."
    return
  fi
  echo "==> Removing ${name}"
  if [[ "${DRY_RUN}" == "1" ]]; then
    echo "    (dry-run) docker rm -f ${name}"
  else
    docker rm -f "${name}" >/dev/null
  fi
}

if [[ "${MODE}" == "--all" ]]; then
  echo "==> Removing ALL containers with prefix '${CONTAINER_PREFIX}_'"
  names=$(docker ps -a --format '{{.Names}}' | grep "^${CONTAINER_PREFIX}_" || true)
  if [[ -z "${names}" ]]; then
    echo "==> No containers found."
    exit 0
  fi
  while IFS= read -r name; do
    remove_container "${name}"
  done <<< "${names}"
  echo "==> Done."
  exit 0
fi

START_PORT="${1:-}"
END_PORT="${2:-}"

if [[ -z "${START_PORT}" || -z "${END_PORT}" ]]; then
  echo "Usage: $0 <START_PORT> <END_PORT> | --all" >&2
  echo "Example: $0 5001 5064" >&2
  exit 1
fi

if ! [[ "${START_PORT}" =~ ^[0-9]+$ ]] || ! [[ "${END_PORT}" =~ ^[0-9]+$ ]]; then
  echo "Error: ports must be integers." >&2
  exit 1
fi

if (( START_PORT > END_PORT )); then
  echo "Error: START_PORT (${START_PORT}) must be <= END_PORT (${END_PORT})." >&2
  exit 1
fi

echo "==> Removing containers for port range ${START_PORT}..${END_PORT}"
for (( port = START_PORT; port <= END_PORT; port++ )); do
  remove_container "${CONTAINER_PREFIX}_${port}"
done

echo "==> Done."