#!/usr/bin/env bash
#
# Creates a batch of AndroidWorld containers, one per port in a range.
#
# Each container maps its port to the container's server port (5000):
#   -p <PORT>:5000
#
# Usage:
#   ./scripts/create_containers.sh <START_PORT> <END_PORT>
#   ./scripts/create_containers.sh 5001 5064     # 64 containers, ports 5001..5064
#
# Options (env vars):
#   IMAGE_NAME   image to run (default: android_world:latest)
#   CONTAINER_PREFIX  container name prefix (default: android_world)
#   DRY_RUN=1    print docker commands without executing them
#
# Examples:
#   IMAGE_NAME=android_world:dev ./scripts/create_containers.sh 5001 5004
#   DRY_RUN=1 ./scripts/create_containers.sh 5001 5004

set -euo pipefail

IMAGE_NAME="${IMAGE_NAME:-android_world:latest}"
CONTAINER_PREFIX="${CONTAINER_PREFIX:-android_world}"
DRY_RUN="${DRY_RUN:-0}"

START_PORT="${1:-}"
END_PORT="${2:-}"

if [[ -z "${START_PORT}" || -z "${END_PORT}" ]]; then
  echo "Usage: $0 <START_PORT> <END_PORT>" >&2
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

if ! command -v docker >/dev/null 2>&1; then
  echo "Error: docker CLI not found in PATH." >&2
  exit 1
fi

echo "==> Image: ${IMAGE_NAME}"
echo "==> Port range: ${START_PORT}..${END_PORT} ($(( END_PORT - START_PORT + 1 )) containers)"
echo "==> Container prefix: ${CONTAINER_PREFIX}"

for (( port = START_PORT; port <= END_PORT; port++ )); do
  name="${CONTAINER_PREFIX}_${port}"
  if docker ps -a --format '{{.Names}}' | grep -qx "${name}"; then
    echo "==> Skipping ${name}: container already exists."
    continue
  fi
  cmd=(docker run -d --name "${name}" --privileged -p "${port}:5000" "${IMAGE_NAME}")
  echo "==> Creating ${name} (host port ${port} -> container 5000)"
  if [[ "${DRY_RUN}" == "1" ]]; then
    echo "    (dry-run) ${cmd[*]}"
  else
    "${cmd[@]}"
  fi
done

echo "==> Done. To check status: docker ps --filter name=${CONTAINER_PREFIX}_"