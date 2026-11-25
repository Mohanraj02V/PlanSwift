#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# Vortexen Estimator — Non-Destructive Hostinger KVM 2 Co-Hosting Setup
# Designed to coexist cleanly alongside Market Intel DB on 189.72.180.37.
# Does NOT modify UFW, SSH daemon, or any /opt/marketintel / marketintel* asset.
# ==============================================================================

if [[ "$(id -u)" -ne 0 ]]; then
  echo "ERROR: Run setup_vortexen.sh as root (e.g. sudo bash setup_vortexen.sh)." >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOSTINGER_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
BASE_DIR="/opt/vortexen-estimator"
APP_UID=10002
APP_GID=10002

echo "==> Checking prerequisites (non-destructive)..."
for cmd in docker nginx certbot visudo flock openssl curl; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "ERROR: Missing required command '$cmd'. Install it before running setup_vortexen.sh." >&2
    exit 1
  fi
done

if ! docker compose version >/dev/null 2>&1; then
  echo "ERROR: Docker Compose v2 plugin ('docker compose') is required." >&2
  exit 1
fi

if ! id -u deploy >/dev/null 2>&1; then
  echo "==> Creating restricted 'deploy' user..."
  useradd --create-home --shell /bin/bash deploy
else
  echo "==> Reusing existing 'deploy' user cleanly (Market Intel sudoers left untouched)."
fi

echo "==> Creating isolated directory tree under ${BASE_DIR}..."
install -d -m 0755 -o root -g root \
  "${BASE_DIR}" \
  "${BASE_DIR}/releases" \
  "${BASE_DIR}/deploy" \
  "${BASE_DIR}/src"
install -d -m 0750 -o root -g root "${BASE_DIR}/backups"
install -d -m 0755 -o deploy -g deploy "${BASE_DIR}/incoming"
install -d -m 0755 -o "${APP_UID}" -g "${APP_GID}" "${BASE_DIR}/staticfiles"
install -d -m 0755 -o www-data -g www-data /var/www/certbot

echo "==> Installing compose manifest and environment template..."
install -m 0644 -o root -g root \
  "${HOSTINGER_DIR}/docker-compose.production.yml" \
  "${BASE_DIR}/deploy/docker-compose.production.yml"
sed -i 's/\r$//' "${BASE_DIR}/deploy/docker-compose.production.yml"

install -m 0644 -o root -g root \
  "${HOSTINGER_DIR}/env.production.example" \
  "${BASE_DIR}/deploy/env.production.example"
sed -i 's/\r$//' "${BASE_DIR}/deploy/env.production.example"

if [[ ! -f "${BASE_DIR}/.env" ]]; then
  cp "${BASE_DIR}/deploy/env.production.example" "${BASE_DIR}/.env"
  chown root:root "${BASE_DIR}/.env"
  chmod 0640 "${BASE_DIR}/.env"
  echo "    Created ${BASE_DIR}/.env from template (edit secrets/domain before deploying!)."
else
  chown root:root "${BASE_DIR}/.env"
  chmod 0640 "${BASE_DIR}/.env"
  echo "    Preserved existing ${BASE_DIR}/.env."
fi

echo "==> Installing root-owned operational scripts to /usr/local/sbin/..."
install_script() {
  local src="$1"
  local dst="$2"
  install -m 0755 -o root -g root "${src}" "${dst}"
  sed -i 's/\r$//' "${dst}"
}

install_script "${SCRIPT_DIR}/deploy.sh" /usr/local/sbin/vortexen-deploy
install_script "${SCRIPT_DIR}/rollback.sh" /usr/local/sbin/vortexen-rollback
install_script "${SCRIPT_DIR}/health_check.sh" /usr/local/sbin/vortexen-health
install_script "${SCRIPT_DIR}/backup.sh" /usr/local/sbin/vortexen-backup
install_script "${SCRIPT_DIR}/restore.sh" /usr/local/sbin/vortexen-restore

echo "==> Installing scoped sudoers rule /etc/sudoers.d/vortexen-deploy..."
cat >/etc/sudoers.d/vortexen-deploy <<'EOF'
Defaults:deploy !requiretty
deploy ALL=(root) NOPASSWD: /usr/local/sbin/vortexen-deploy, /usr/local/sbin/vortexen-deploy *, /usr/local/sbin/vortexen-rollback, /usr/local/sbin/vortexen-rollback *, /usr/local/sbin/vortexen-health, /usr/local/sbin/vortexen-health *
EOF
chmod 0440 /etc/sudoers.d/vortexen-deploy
visudo -cf /etc/sudoers.d/vortexen-deploy

echo "==> Installing Nginx vhost template (not enabled until SSL cert is issued)..."
if [[ ! -f /etc/nginx/sites-available/vortexen-estimator ]]; then
  install -m 0644 -o root -g root \
    "${HOSTINGER_DIR}/nginx/vortexen-estimator.conf" \
    /etc/nginx/sites-available/vortexen-estimator
  sed -i 's/\r$//' /etc/nginx/sites-available/vortexen-estimator
  echo "    Installed /etc/nginx/sites-available/vortexen-estimator."
else
  echo "    Preserved existing /etc/nginx/sites-available/vortexen-estimator."
fi

echo "==> Installing staggered cron schedule (/etc/cron.d/vortexen-ops)..."
cat >/etc/cron.d/vortexen-ops <<'EOF'
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

# Daily PostgreSQL backup at 03:15 UTC (staggered 45 min after Market Intel DB at 02:30 UTC)
15 3 * * * root /usr/local/sbin/vortexen-backup >> /var/log/vortexen-backup.log 2>&1

# Health probe every 5 minutes
*/5 * * * * root /usr/local/sbin/vortexen-health --quiet --no-wait >> /var/log/vortexen-health.log 2>&1

# Weekly cleanup of old unused vortexen-* images (keeps latest 10 tags; never touches Market Intel images)
30 4 * * 0 root /bin/bash -c "docker image ls --format '{{.Repository}}:{{.Tag}} {{.ID}}' | grep -E '^vortexen-(backend|frontend):' | tail -n +11 | awk '{print \$2}' | xargs -r docker image rm >/dev/null 2>&1"
EOF
chmod 0644 /etc/cron.d/vortexen-ops
sed -i 's/\r$//' /etc/cron.d/vortexen-ops

echo "==> Installing logrotate config (/etc/logrotate.d/vortexen)..."
cat >/etc/logrotate.d/vortexen <<'EOF'
/var/log/vortexen-*.log /var/log/nginx/vortexen-estimator.*.log {
    daily
    rotate 14
    compress
    delaycompress
    missingok
    notifempty
    sharedscripts
    postrotate
        [ -f /var/run/nginx.pid ] && kill -USR1 "$(cat /var/run/nginx.pid)" || true
    endscript
}
EOF
chmod 0644 /etc/logrotate.d/vortexen
sed -i 's/\r$//' /etc/logrotate.d/vortexen

echo ""
echo "==> Host Resource Snapshot (verifying headroom alongside Market Intel DB):"
free -h
swapon --show || true
df -h /
echo "==> Running Docker Containers:"
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
echo ""
echo "Setup complete! Next steps:"
echo "  1. Edit ${BASE_DIR}/.env and replace CHANGE_ME secrets + VORTEXEN_DOMAIN."
echo "  2. Update server_name / cert paths in /etc/nginx/sites-available/vortexen-estimator if using a custom domain."
echo "  3. Issue Certbot TLS cert (DNS A record must point to 189.72.180.37) and enable the Nginx site."
echo "  4. Deploy via GitHub Actions or: sudo /usr/local/sbin/vortexen-deploy --build /opt/vortexen-estimator/src"
