#!/usr/bin/env bash
# Docker pull command with temporary authentication token for accessing private registry images.

set +x

TMPDIR="$(mktemp -d)"
DOCKER_IMAGE="$1"
DOCKER_REGISTRY_NAME="$2"
DOCKER_REGISTRY_AUTH="$3"

# store to temp file and fork process to allow longer pull to take as much time as needed
echo "{\"auths\": { \"${DOCKER_REGISTRY_NAME}\": { \"auth\": \"${DOCKER_REGISTRY_AUTH}\"}}}" > "${TMPDIR}/config.json"
docker --config "${TMPDIR}" pull "${DOCKER_IMAGE}" &

# give just enough time for docker to read the tmp config before deleting it
# this way, even if docker fails or takes long to pull, the duration tokens are present is minimized
sleep 5
rm -f "${TMPDIR}/config.json"
rmdir "${TMPDIR}"

# wait until forked docker pull completes
wait
