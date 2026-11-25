#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# Vortexen Estimator — Atomic Production Deployment Script
# Installed at: /usr/local/sbin/vortexen-deploy
#
# Usage:
#   CI artifact mode : sudo /usr/local/sbin/vortexen-deploy <git_sha>
#   Direct build mode: sudo /usr/local/sbin/vortexen-deploy --build <repo_dir>
# ==============================================================================

if [[ "$(id -u)" -ne 0 ]]; then
  echo "ERROR: Run vortexen-deploy via sudo or as root." >&2
  exit 1
fi

BASE_DIR="/opt/vortexen-estimator"
ENV_FILE="${BASE_DIR}/.env"
CURRENT_LINK="${BASE_DIR}/current"
PREV_FILE="${BASE_DIR}/previous_release"
LOCK_FILE="/var/lock/vortexen-deploy.lock"
PROJECT_NAME="vortexen-estimator"

exec 9>"${LOCK_FILE}"
if ! flock -n 9; then
  echo "ERROR: Another Vortexen deployment is already running." >&2
  exit 1
fi

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "ERROR: Missing ${ENV_FILE}. Run setup_vortexen.sh and populate .env first." >&2
  exit 1
fi

if grep -q "CHANGE_ME" "${ENV_FILE}"; then
  echo "ERROR: ${ENV_FILE} still contains CHANGE_ME placeholder values." >&2
  exit 1
fi

set -a
# shellcheck source=/dev/null
source "${ENV_FILE}"
set +a

MODE="tarball"
TARGET_TAG=""
REPO_DIR=""

if [[ $# -eq 1 && "$1" != "--build" ]]; then
  MODE="tarball"
  TARGET_TAG="$1"
elif [[ $# -eq 2 && "$1" == "--build" ]]; then
  MODE="build"
  REPO_DIR="$2"
else
  echo "Usage: $0 <git_sha> | --build <repo_dir>" >&2
  exit 1
fi

PREV_TAG="${IMAGE_TAG:-}"
RELEASE_DIR=""
COMPOSE_FILE=""

if [[ "${MODE}" == "tarball" ]]; then
  if [[ ! "${TARGET_TAG}" =~ ^[a-zA-Z0-9._-]+$ ]]; then
    echo "ERROR: Invalid deployment tag '${TARGET_TAG}'." >&2
    exit 1
  fi
  INCOMING_DIR="${BASE_DIR}/incoming/${TARGET_TAG}"
  if [[ ! -d "${INCOMING_DIR}" ]]; then
    echo "ERROR: Incoming directory not found: ${INCOMING_DIR}" >&2
    exit 1
  fi
  echo "==> Verifying SHA-256 checksums in ${INCOMING_DIR}..."
  (cd "${INCOMING_DIR}" && sha256sum -c SHA256SUMS)

  echo "==> Loading immutable Docker images for tag ${TARGET_TAG}..."
  docker load -i "${INCOMING_DIR}/vortexen-backend-${TARGET_TAG}.tar.gz"
  docker load -i "${INCOMING_DIR}/vortexen-frontend-${TARGET_TAG}.tar.gz"

  RELEASE_DIR="${BASE_DIR}/releases/${TARGET_TAG}"
  install -d -m 0755 -o root -g root "${RELEASE_DIR}"
  cp "${INCOMING_DIR}/docker-compose.production.yml" "${RELEASE_DIR}/docker-compose.production.yml"
  sed -i 's/\r$//' "${RELEASE_DIR}/docker-compose.production.yml"
else
  if [[ ! -d "${REPO_DIR}/backend" || ! -d "${REPO_DIR}/frontend" ]]; then
    echo "ERROR: '${REPO_DIR}' does not look like the Vortexen Estimator repository root." >&2
    exit 1
  fi
  if command -v git >/dev/null 2>&1 && [[ -d "${REPO_DIR}/.git" ]]; then
    TARGET_TAG="$(git -C "${REPO_DIR}" rev-parse --short HEAD)"
  else
    TARGET_TAG="$(date -u +%Y%m%d%H%M%S)"
  fi
  echo "==> Building Docker images directly from ${REPO_DIR} (tag: ${TARGET_TAG})..."
  docker build -t "vortexen-backend:${TARGET_TAG}" -f "${REPO_DIR}/backend/Dockerfile" "${REPO_DIR}"
  docker build \
    --build-arg "NEXT_PUBLIC_API_BASE_URL=/api/v1" \
    -t "vortexen-frontend:${TARGET_TAG}" \
    -f "${REPO_DIR}/frontend/Dockerfile" \
    "${REPO_DIR}/frontend"

  RELEASE_DIR="${BASE_DIR}/releases/${TARGET_TAG}"
  install -d -m 0755 -o root -g root "${RELEASE_DIR}"
  cp "${REPO_DIR}/deploy/hostinger/docker-compose.production.yml" "${RELEASE_DIR}/docker-compose.production.yml"
  sed -i 's/\r$//' "${RELEASE_DIR}/docker-compose.production.yml"
fi

COMPOSE_FILE="${RELEASE_DIR}/docker-compose.production.yml"

if [[ -L "${CURRENT_LINK}" ]]; then
  CURRENT_RESOLVED="$(basename "$(readlink -f "${CURRENT_LINK}")")"
  if [[ -n "${CURRENT_RESOLVED}" && "${CURRENT_RESOLVED}" != "${TARGET_TAG}" ]]; then
    echo "${CURRENT_RESOLVED}" > "${PREV_FILE}"
    PREV_TAG="${CURRENT_RESOLVED}"
  fi
elif [[ -n "${PREV_TAG}" && "${PREV_TAG}" != "latest" && "${PREV_TAG}" != "${TARGET_TAG}" ]]; then
  echo "${PREV_TAG}" > "${PREV_FILE}"
fi

# Pre-deploy DB backup if vortexen-db is already running
if docker ps --format '{{.Names}}' | grep -qx "vortexen-db"; then
  echo "==> Creating pre-deploy PostgreSQL backup..."
  /usr/local/sbin/vortexen-backup
fi

update_env_image_tag() {
  local new_tag="$1"
  if grep -q '^IMAGE_TAG=' "${ENV_FILE}"; then
    sed -i "s|^IMAGE_TAG=.*|IMAGE_TAG=${new_tag}|" "${ENV_FILE}"
  else
    echo "IMAGE_TAG=${new_tag}" >> "${ENV_FILE}"
  fi
}

update_env_image_tag "${TARGET_TAG}"
export IMAGE_TAG="${TARGET_TAG}"

compose_cmd() {
  docker compose --project-name "${PROJECT_NAME}" --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" "$@"
}

echo "==> Starting PostgreSQL and Redis..."
compose_cmd up -d vortexen-db vortexen-redis

echo "==> Waiting for database and Redis healthchecks..."
for _ in $(seq 1 30); do
  db_ok="$(docker inspect -f '{{.State.Health.Status}}' vortexen-db 2>/dev/null || echo starting)"
  redis_ok="$(docker inspect -f '{{.State.Health.Status}}' vortexen-redis 2>/dev/null || echo starting)"
  if [[ "${db_ok}" == "healthy" && "${redis_ok}" == "healthy" ]]; then
    break
  fi
  sleep 2
done

if [[ "$(docker inspect -f '{{.State.Health.Status}}' vortexen-db 2>/dev/null || true)" != "healthy" ]]; then
  echo "ERROR: vortexen-db failed to become healthy." >&2
  exit 1
fi

echo "==> Running Django production deploy checks, migrations, and static collection..."
compose_cmd run --rm --no-deps vortexen-api python manage.py check --deploy
compose_cmd run --rm --no-deps vortexen-api python manage.py migrate --noinput
compose_cmd run --rm --no-deps vortexen-api python manage.py collectstatic --noinput

ln -sfn "${RELEASE_DIR}" "${CURRENT_LINK}"

echo "==> Starting application containers (api, worker, web)..."
compose_cmd up -d --remove-orphans

echo "==> Running post-deploy health verification..."
if ! /usr/local/sbin/vortexen-health; then
  echo "ERROR: Health verification failed for ${TARGET_TAG}." >&2
  if [[ -n "${PREV_TAG}" && "${PREV_TAG}" != "${TARGET_TAG}" && -d "${BASE_DIR}/releases/${PREV_TAG}" ]]; then
    echo "==> Attempting automatic rollback to ${PREV_TAG}..." >&2
    /usr/local/sbin/vortexen-rollback "${PREV_TAG}" || true
  fi
  exit 1
fi

if [[ "${MODE}" == "tarball" && -d "${BASE_DIR}/incoming/${TARGET_TAG}" ]]; then
  rm -rf "${BASE_DIR}/incoming/${TARGET_TAG}"
fi

# Retain last 5 release directories cleanly
if [[ -d "${BASE_DIR}/releases" ]]; then
  ls -1dt "${BASE_DIR}/releases"/* 2>/dev/null | tail -n +6 | xargs -r rm -rf || true
fi

# Prune older unused vortexen-* images only (keep latest 5 tags, never touch Market Intel DB)
for repo in vortexen-backend vortexen-frontend; do
  docker image ls "${repo}" --format '{{.Tag}}' \
    | grep -v '^<none>$' \
    | grep -v "^${TARGET_TAG}$" \
    | tail -n +6 \
    | xargs -r -I{} docker image rm "${repo}:{}" >/dev/null 2>&1 || true
done

echo "==> Vortexen Estimator deployed successfully (release: ${TARGET_TAG})."
