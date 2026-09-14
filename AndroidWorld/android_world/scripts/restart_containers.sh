#!/usr/bin/env bash
#
# Restarts AndroidWorld containers for the given ports: removes each container,
# then recreates it with the same port mapping.
#
# Usage:
#   ./scripts/restart_containers.sh <PORT> [PORT ...]
#   ./scripts/restart_containers.sh 5001 5003 5007 5010
#
# Options (env vars):
#   IMAGE_NAME   image to run (default: android_world:latest)
#   CONTAINER_PREFIX  container name prefix (default: android_world)
#   DRY_RUN=1    print docker commands without executing them
#
# Examples:
#   ./scripts/restart_containers.sh 5001
#   ./scripts/restart_containers.sh 5001 5003 5007

set -euo pipefail

IMAGE_NAME="${IMAGE_NAME:-android_world:latest}"
CONTAINER_PREFIX="${CONTAINER_PREFIX:-android_world}"
DRY_RUN="${DRY_RUN:-0}"

PORTS=("$@")

if [[ ${#PORTS[@]} -eq 0 ]]; then
  echo "Usage: $0 <PORT> [PORT ...]" >&2
  echo "Example: $0 5001 5003 5007 5010" >&2
  exit 1
fi

for port in "${PORTS[@]}"; do
  if ! [[ "${port}" =~ ^[0-9]+$ ]]; then
    echo "Error: port must be an integer, got: ${port}" >&2
    exit 1
  fi
done

if ! command -v docker >/dev/null 2>&1; then
  echo "Error: docker CLI not found in PATH." >&2
  exit 1
fi

echo "==> Image: ${IMAGE_NAME}"
echo "==> Ports: ${PORTS[*]} (${#PORTS[@]} containers)"
echo "==> Container prefix: ${CONTAINER_PREFIX}"

for port in "${PORTS[@]}"; do
  name="${CONTAINER_PREFIX}_${port}"

  # Stop and remove the old container if it exists.
  if docker ps -a --format '{{.Names}}' | grep -qx "${name}"; then
    echo "==> Removing ${name}"
    if [[ "${DRY_RUN}" == "1" ]]; then
      echo "    (dry-run) docker rm -f ${name}"
    else
      docker rm -f "${name}" >/dev/null
    fi
  else
    echo "==> ${name} does not exist, skipping removal."
  fi

  # Recreate the container.
  cmd=(docker run -d --name "${name}" --privileged -p "${port}:5000" "${IMAGE_NAME}")
  echo "==> Creating ${name} (host port ${port} -> container 5000)"
  if [[ "${DRY_RUN}" == "1" ]]; then
    echo "    (dry-run) ${cmd[*]}"
  else
    "${cmd[@]}"
  fi
done

echo "==> Done. To check status: docker ps --filter name=${CONTAINER_PREFIX}_"