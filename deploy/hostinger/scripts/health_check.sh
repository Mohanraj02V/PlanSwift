#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# Vortexen Estimator — Health Check Script
# Installed at: /usr/local/sbin/vortexen-health
# ==============================================================================

BASE_DIR="/opt/vortexen-estimator"
ENV_FILE="${BASE_DIR}/.env"
QUIET=0
MAX_ATTEMPTS=12
SLEEP_SECONDS=5

for arg in "$@"; do
  case "${arg}" in
    --quiet) QUIET=1 ;;
    --no-wait) MAX_ATTEMPTS=1 ;;
    *)
      echo "Unknown option: ${arg}" >&2
      exit 1
      ;;
  esac
done

log() {
  if [[ "${QUIET}" -eq 0 ]]; then
    echo "$@"
  fi
}

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "ERROR: Missing ${ENV_FILE}" >&2
  exit 1
fi

set -a
# shellcheck source=/dev/null
source "${ENV_FILE}"
set +a

check_once() {
  docker exec vortexen-db pg_isready -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" >/dev/null 2>&1 || return 1
  [[ "$(docker exec vortexen-redis redis-cli ping 2>/dev/null || true)" == "PONG" ]] || return 1

  local api_json
  api_json="$(curl -fsS --max-time 5 http://127.0.0.1:8100/api/v1/health/ 2>/dev/null || true)"
  if [[ "${api_json}" != *'"status"'* || "${api_json}" != *'"ok"'* ]]; then
    return 1
  fi

  local web_code
  web_code="$(curl -sS -o /dev/null -w "%{http_code}" --max-time 5 http://127.0.0.1:3100/login 2>/dev/null || echo 000)"
  if [[ "${web_code}" != "200" ]]; then
    return 1
  fi

  local worker_running
  worker_running="$(docker inspect -f '{{.State.Running}}' vortexen-worker 2>/dev/null || echo false)"
  if [[ "${worker_running}" != "true" ]]; then
    return 1
  fi

  local disk_pct
  disk_pct="$(df --output=pcent / | tail -n 1 | tr -dc '0-9')"
  if [[ -n "${disk_pct}" && "${disk_pct}" -ge 90 ]]; then
    echo "WARNING: Root filesystem usage is ${disk_pct}% (>= 90%)." >&2
  fi

  return 0
}

attempt=1
while [[ "${attempt}" -le "${MAX_ATTEMPTS}" ]]; do
  if check_once; then
    log "OK: Vortexen Estimator healthy (db, redis, api :8100, worker, web :3100)."
    exit 0
  fi
  if [[ "${attempt}" -lt "${MAX_ATTEMPTS}" ]]; then
    log "Waiting for Vortexen services (${attempt}/${MAX_ATTEMPTS})..."
    sleep "${SLEEP_SECONDS}"
  fi
  attempt=$((attempt + 1))
done

echo "ERROR: Vortexen Estimator health check failed after ${MAX_ATTEMPTS} attempt(s)." >&2
docker ps --filter "name=vortexen-" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" >&2 || true
exit 1
