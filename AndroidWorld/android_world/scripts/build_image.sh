#!/usr/bin/env bash
docker build -t "${IMAGE_NAME:-android_world:latest}" "$@" "$(dirname "$(realpath "$0")")/.."