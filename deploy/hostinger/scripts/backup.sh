#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# Vortexen Estimator — PostgreSQL Backup Script
# Installed at: /usr/local/sbin/vortexen-backup
# Runs daily via /etc/cron.d/vortexen-ops at 03:15 UTC (staggered vs Market Intel).
# ==============================================================================

if [[ "$(id -u)" -ne 0 ]]; then
  echo "ERROR: Run vortexen-backup as root." >&2
  exit 1
fi

BASE_DIR="/opt/vortexen-estimator"
ENV_FILE="${BASE_DIR}/.env"
BACKUP_DIR="${BASE_DIR}/backups"
RETENTION_DAYS=14

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "ERROR: Missing ${ENV_FILE}" >&2
  exit 1
fi

set -a
# shellcheck source=/dev/null
source "${ENV_FILE}"
set +a

if ! docker ps --format '{{.Names}}' | grep -qx "vortexen-db"; then
  echo "ERROR: Container vortexen-db is not running." >&2
  exit 1
fi

install -d -m 0750 -o root -g root "${BACKUP_DIR}"
STAMP="$(date -u +%Y%m%d_%H%M%SZ)"
OUT_FILE="${BACKUP_DIR}/vortexen_db_${STAMP}.dump"

echo "==> Dumping PostgreSQL database '${POSTGRES_DB}'..."
docker exec vortexen-db pg_dump -U "${POSTGRES_USER}" -Fc "${POSTGRES_DB}" > "${OUT_FILE}"
chmod 0640 "${OUT_FILE}"

FINAL_FILE="${OUT_FILE}"
if [[ -n "${BACKUP_ENCRYPTION_PASSPHRASE:-}" ]]; then
  if command -v gpg >/dev/null 2>&1; then
    ENC_FILE="${OUT_FILE}.gpg"
    printf '%s' "${BACKUP_ENCRYPTION_PASSPHRASE}" \
      | gpg --batch --yes --passphrase-fd 0 --symmetric --cipher-algo AES256 -o "${ENC_FILE}" "${OUT_FILE}"
    rm -f "${OUT_FILE}"
    chmod 0640 "${ENC_FILE}"
    FINAL_FILE="${ENC_FILE}"
  else
    echo "WARNING: BACKUP_ENCRYPTION_PASSPHRASE set but 'gpg' not installed; keeping unencrypted dump." >&2
  fi
fi

(cd "${BACKUP_DIR}" && sha256sum "$(basename "${FINAL_FILE}")" > "$(basename "${FINAL_FILE}").sha256")
chmod 0640 "${FINAL_FILE}.sha256"

# Retain only last 14 days inside Vortexen backup directory
find "${BACKUP_DIR}" -maxdepth 1 -type f \( -name 'vortexen_db_*' \) -mtime +"${RETENTION_DAYS}" -delete

echo "==> Backup completed: ${FINAL_FILE}"
