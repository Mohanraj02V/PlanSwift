#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# Vortexen Estimator — PostgreSQL Restore Script
# Installed at: /usr/local/sbin/vortexen-restore
# Usage: sudo /usr/local/sbin/vortexen-restore /opt/vortexen-estimator/backups/vortexen_db_<stamp>.dump
# ==============================================================================

if [[ "$(id -u)" -ne 0 ]]; then
  echo "ERROR: Run vortexen-restore as root." >&2
  exit 1
fi

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <backup_file(.dump|.dump.gpg)>" >&2
  exit 1
fi

BACKUP_FILE="$1"
if [[ ! -f "${BACKUP_FILE}" ]]; then
  echo "ERROR: Backup file not found: ${BACKUP_FILE}" >&2
  exit 1
fi

BASE_DIR="/opt/vortexen-estimator"
ENV_FILE="${BASE_DIR}/.env"
COMPOSE_FILE="${BASE_DIR}/current/deploy/hostinger/docker-compose.production.yml"
if [[ ! -f "${COMPOSE_FILE}" ]]; then
  COMPOSE_FILE="${BASE_DIR}/deploy/docker-compose.production.yml"
fi
PROJECT_NAME="vortexen-estimator"

set -a
# shellcheck source=/dev/null
source "${ENV_FILE}"
set +a

if [[ -f "${BACKUP_FILE}.sha256" ]]; then
  echo "==> Verifying backup checksum..."
  (cd "$(dirname "${BACKUP_FILE}")" && sha256sum -c "$(basename "${BACKUP_FILE}").sha256")
fi

TMP_DUMP=""
DUMP_SOURCE="${BACKUP_FILE}"
cleanup() {
  if [[ -n "${TMP_DUMP}" && -f "${TMP_DUMP}" ]]; then
    rm -f "${TMP_DUMP}"
  fi
}
trap cleanup EXIT

if [[ "${BACKUP_FILE}" == *.gpg ]]; then
  if [[ -z "${BACKUP_ENCRYPTION_PASSPHRASE:-}" ]]; then
    echo "ERROR: BACKUP_ENCRYPTION_PASSPHRASE must be set in ${ENV_FILE} to restore .gpg backup." >&2
    exit 1
  fi
  TMP_DUMP="$(mktemp /tmp/vortexen-restore-XXXXXX.dump)"
  printf '%s' "${BACKUP_ENCRYPTION_PASSPHRASE}" \
    | gpg --batch --yes --passphrase-fd 0 -d -o "${TMP_DUMP}" "${BACKUP_FILE}"
  DUMP_SOURCE="${TMP_DUMP}"
fi

compose_cmd() {
  docker compose --project-name "${PROJECT_NAME}" --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" "$@"
}

echo "==> Stopping API and Celery worker before restore..."
compose_cmd stop vortexen-api vortexen-worker || true

echo "==> Restoring PostgreSQL database '${POSTGRES_DB}'..."
docker exec -i vortexen-db pg_restore \
  -U "${POSTGRES_USER}" \
  -d "${POSTGRES_DB}" \
  --clean --if-exists --no-owner --no-privileges < "${DUMP_SOURCE}"

echo "==> Restarting Vortexen Estimator stack..."
compose_cmd up -d

/usr/local/sbin/vortexen-health
echo "==> Database restore verified healthy."
