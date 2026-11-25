#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# Vortexen Estimator — Rollback Script
# Installed at: /usr/local/sbin/vortexen-rollback
# ==============================================================================

if [[ "$(id -u)" -ne 0 ]]; then
  echo "ERROR: Run vortexen-rollback via sudo or as root." >&2
  exit 1
fi

BASE_DIR="/opt/vortexen-estimator"
ENV_FILE="${BASE_DIR}/.env"
CURRENT_LINK="${BASE_DIR}/current"
PREV_FILE="${BASE_DIR}/previous_release"
PROJECT_NAME="vortexen-estimator"

TARGET_TAG="${1:-}"
if [[ -z "${TARGET_TAG}" && -f "${PREV_FILE}" ]]; then
  TARGET_TAG="$(tr -d '[:space:]' < "${PREV_FILE}")"
fi

if [[ -z "${TARGET_TAG}" ]]; then
  echo "ERROR: No target release tag provided and ${PREV_FILE} does not exist." >&2
  exit 1
fi

RELEASE_DIR="${BASE_DIR}/releases/${TARGET_TAG}"
COMPOSE_FILE="${RELEASE_DIR}/docker-compose.production.yml"

if [[ ! -f "${COMPOSE_FILE}" ]]; then
  echo "ERROR: Release compose manifest missing: ${COMPOSE_FILE}" >&2
  exit 1
fi

if ! docker image inspect "vortexen-backend:${TARGET_TAG}" >/dev/null 2>&1 || \
   ! docker image inspect "vortexen-frontend:${TARGET_TAG}" >/dev/null 2>&1; then
  echo "ERROR: Docker images for release '${TARGET_TAG}' are not present locally." >&2
  exit 1
fi

if grep -q '^IMAGE_TAG=' "${ENV_FILE}"; then
  sed -i "s|^IMAGE_TAG=.*|IMAGE_TAG=${TARGET_TAG}|" "${ENV_FILE}"
else
  echo "IMAGE_TAG=${TARGET_TAG}" >> "${ENV_FILE}"
fi

ln -sfn "${RELEASE_DIR}" "${CURRENT_LINK}"

echo "==> Rolling back Vortexen Estimator to ${TARGET_TAG}..."
docker compose --project-name "${PROJECT_NAME}" --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" up -d --remove-orphans

/usr/local/sbin/vortexen-health
echo "==> Rollback to ${TARGET_TAG} verified healthy."
