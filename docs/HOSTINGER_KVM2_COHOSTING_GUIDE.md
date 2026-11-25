# Hostinger KVM 2 Co-Hosting Guide (Alongside Market Intel DB)

This guide explains how to deploy **Vortexen Estimator** onto your existing **Hostinger KVM 2 VPS** (`189.72.180.37` / `srv2197184`, Ubuntu 24.04.5 LTS, 2 vCPU / 8 GB RAM / 100 GB NVMe) **without disturbing your live Market Intel DB deployment**.

---

## 1. Zero-Conflict Isolation Matrix

Every port, directory, Docker resource, Nginx zone, sudoers rule, and cron slot is completely separated from Market Intel DB:

| Resource | Market Intel DB (Existing) | Vortexen Estimator (New) |
|---|---|---|
| Base directory | `/opt/marketintel` | `/opt/vortexen-estimator` |
| System CLI wrappers | `/usr/local/sbin/marketintel-*` | `/usr/local/sbin/vortexen-{deploy,rollback,health,backup,restore}` |
| Sudoers file (`deploy` user) | `/etc/sudoers.d/marketintel-deploy` | `/etc/sudoers.d/vortexen-deploy` |
| Nginx virtual host | `/etc/nginx/sites-available/marketintel` | `/etc/nginx/sites-available/vortexen-estimator` |
| Nginx rate-limit zones | `mi_auth_limit`, `mi_webhook_limit` | `vx_auth_login_limit`, `vx_auth_refresh_limit` |
| Host loopback ports | `127.0.0.1:5432`, `127.0.0.1:8000` | `127.0.0.1:8100` (API), `127.0.0.1:3100` (Next.js) |
| Database / Redis host ports | `127.0.0.1:5432` | **None** (`vortexen_internal` Docker bridge only) |
| Docker Compose project | `marketintel` | `vortexen-estimator` |
| Docker containers | `marketintel-*` | `vortexen-db`, `vortexen-redis`, `vortexen-api`, `vortexen-worker`, `vortexen-web` |
| Docker volumes | `marketintel_pgdata` | `vortexen_pgdata`, `vortexen_uploads` |
| Daily DB backup cron | `02:30 UTC` (`/etc/cron.d/marketintel-ops`) | `03:15 UTC` (`/etc/cron.d/vortexen-ops`) |

### KVM 2 Memory & CPU Budget (8 GB RAM + Swap)

- `vortexen-db` (`postgres:16-alpine`): `512m` limit, `0.4` CPU
- `vortexen-redis` (`redis:7-alpine`, `maxmemory 128mb`): `192m` limit, `0.2` CPU
- `vortexen-api` (`gunicorn --workers 2 --threads 2`): `1024m` limit, `0.7` CPU
- `vortexen-worker` (`celery --concurrency=1 --max-tasks-per-child=20`, `IFC_GEOMETRY_THREADS=1`): `1280m` limit, `0.8` CPU
- `vortexen-web` (`node server.js`, `--max-old-space-size=384`): `448m` limit, `0.4` CPU

Idle actual footprint for all 5 Vortexen containers is ~450–650 MB RAM, leaving comfortable headroom alongside Market Intel DB. Host Nginx owns ports `80` and `443` directly — **do not run a containerized Nginx** on this VPS.

---

## 2. Single-Domain DNS Setup

Vortexen Estimator uses **HttpOnly `SameSite=Lax` JWT cookies (`vortexen_access`, `vortexen_refresh`) and CSRF cookies**. Hosting both the frontend (`/`) and backend (`/api/`, `/admin/`) under **one domain** avoids cross-origin cookie issues completely:

1. Create **one** DNS `A` record pointing your chosen subdomain (for example `estimator.vortexen.com` or `estimator.hikasimat.com`) to `189.72.180.37`.
2. **Important (Cloudflare users):** Keep the proxy toggle on **DNS Only (grey cloud)** while issuing the Let's Encrypt certificate **and** afterwards if you upload `.SwiftJob.zip` or `.ifc` packages larger than **100 MB** (Cloudflare Free caps single HTTP upload requests at 100 MB).

---

## 3. Initial Server Preparation (Run Once as Root)

Connect from Windows PowerShell:

```powershell
ssh -i C:\Users\mohan\.ssh\hostinger_kvm2_admin root@189.72.180.37
```

Clone or update the repository into `/opt/vortexen-estimator/src` (replace branch/URL if private; for private GitHub repos, use a deploy key or GitHub Actions tarball deployment in Section 6):

```bash
mkdir -p /opt/vortexen-estimator/src
git clone --branch main https://github.com/Mohanraj02V/PlanSwift.git /opt/vortexen-estimator/src
```

Run the non-destructive Hostinger co-hosting setup script (this leaves `/opt/marketintel`, UFW, SSH, and Market Intel Nginx untouched):

```bash
bash /opt/vortexen-estimator/src/deploy/hostinger/scripts/setup_vortexen.sh
```

Verify Market Intel DB is still healthy and untouched:

```bash
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

---

## 4. Configure `/opt/vortexen-estimator/.env` & TLS

Generate strong production secrets on the VPS:

```bash
openssl rand -hex 48
openssl rand -base64 24 | tr -dc 'A-Za-z0-9' ; echo
```

Edit `/opt/vortexen-estimator/.env` and replace **every `CHANGE_ME`** value and update `VORTEXEN_DOMAIN`, `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`, and `CSRF_TRUSTED_ORIGINS` to your real domain (e.g. `estimator.vortexen.com`):

```bash
nano /opt/vortexen-estimator/.env
```

If you used a domain other than `estimator.vortexen.com`, update `server_name` and certificate paths in `/etc/nginx/sites-available/vortexen-estimator`:

```bash
DOMAIN="estimator.vortexen.com"   # <-- change if using another subdomain
sed -i "s/estimator\.vortexen\.com/${DOMAIN}/g" /etc/nginx/sites-available/vortexen-estimator
```

### Issue Let's Encrypt SSL Certificate & Enable Nginx

Wait until DNS propagation reaches `189.72.180.37` (`dig +short "$DOMAIN"`), then issue the certificate using Nginx webroot (`/var/www/certbot`) or standalone certbot cleanly **without disturbing Market Intel DB**:

```bash
# Temporarily allow port 80 ACME challenge cleanly via existing host nginx:
certbot certonly --nginx -d "${DOMAIN}" --non-interactive --agree-tos -m admin@"${DOMAIN#*.}"
```

*(If certbot asks because the vhost isn't enabled yet, create `/etc/nginx/sites-enabled/vortexen-estimator` only after issuing via `--webroot` or after commenting SSL lines, OR simply run `certbot certonly --webroot -w /var/www/certbot -d "${DOMAIN}"` with a temporary port-80 `server` block or `certbot --nginx` after temporary HTTP block.)*

Specifically, cleanest zero-downtime sequence with host Nginx already serving Market Intel DB:

```bash
# 1. Create a minimal HTTP-only ACME block first
cat >/etc/nginx/sites-available/vortexen-acme <<EOF
server {
    listen 80;
    listen [::]:80;
    server_name ${DOMAIN};
    location /.well-known/acme-challenge/ { root /var/www/certbot; allow all; }
    location / { return 404; }
}
EOF
ln -sfn /etc/nginx/sites-available/vortexen-acme /etc/nginx/sites-enabled/vortexen-estimator
nginx -t && systemctl reload nginx

# 2. Obtain certificate via webroot (Market Intel stays 100% online)
mkdir -p /var/www/certbot
certbot certonly --webroot -w /var/www/certbot -d "${DOMAIN}"

# 3. Switch symlink to full HTTPS production vhost and reload Nginx
ln -sfn /etc/nginx/sites-available/vortexen-estimator /etc/nginx/sites-enabled/vortexen-estimator
rm -f /etc/nginx/sites-available/vortexen-acme
nginx -t && systemctl reload nginx
```

---

## 5. First Build & Deploy (Direct on VPS)

Build and atomically deploy from `/opt/vortexen-estimator/src`:

```bash
sudo /usr/local/sbin/vortexen-deploy --build /opt/vortexen-estimator/src
```

This single command automatically:
1. Validates `/opt/vortexen-estimator/.env` has no `CHANGE_ME` placeholders.
2. Builds `vortexen-backend:<sha>` and `vortexen-frontend:<sha>` (baking `NEXT_PUBLIC_API_BASE_URL=/api/v1` into the Next.js bundle).
3. Starts `vortexen-db` and `vortexen-redis` cleanly on `vortexen_internal`.
4. Runs `manage.py check --deploy`, `manage.py migrate --noinput`, and `manage.py collectstatic --noinput`.
5. Starts `vortexen-api` (`127.0.0.1:8100`), `vortexen-worker`, and `vortexen-web` (`127.0.0.1:3100`).
6. Verifies all healthchecks via `/usr/local/sbin/vortexen-health`.

### Create the Initial Organization & Admin User

Public self-registration is disabled in production. Create your first Organization Admin account with:

```bash
docker compose \
  --project-name vortexen-estimator \
  --env-file /opt/vortexen-estimator/.env \
  -f /opt/vortexen-estimator/current/deploy/hostinger/docker-compose.production.yml \
  exec vortexen-api \
  python manage.py bootstrap_admin \
    --email admin@vortexen.com \
    --full-name "Vortexen Administrator" \
    --org-name "Vortexen Engineering" \
    --org-slug vortexen
```

You will be prompted securely for the Admin password (minimum 10 characters). Once created, sign in at `https://<your-domain>/login`.

---

## 6. Optional: GitHub Actions CI/CD Auto-Deploy (Recommended for Zero-Build-Load Deploys)

Building images on GitHub Runners avoids CPU/RAM spikes on your 2-vCPU KVM 2. The workflow `.github/workflows/deploy-hostinger.yml` reuses your existing restricted `deploy` SSH user (`/etc/sudoers.d/vortexen-deploy`).

Configure these **GitHub Repository Secrets**:
- `VPS_HOST`: `189.72.180.37`
- `VPS_USER`: `deploy`
- `VPS_PORT`: `22`
- `VPS_SSH_KEY`: Private SSH key matching `/home/deploy/.ssh/authorized_keys` on the VPS
- `VPS_SSH_KNOWN_HOSTS`: Output of `ssh-keyscan -p 22 189.72.180.37`
- `VORTEXEN_DOMAIN`: Your subdomain (e.g. `estimator.vortexen.com`)

Optionally add Repository Variable `ENABLE_HOSTINGER_AUTO_DEPLOY=true` to auto-deploy on every push to `main`, or trigger manually via **Actions -> Deploy Vortexen Estimator to Hostinger KVM 2 -> Run workflow**.

---

## 7. Verification & Day-2 Operations

```bash
# Check Vortexen health
sudo /usr/local/sbin/vortexen-health

# Check live HTTPS health & web login page
curl -fsS https://estimator.vortexen.com/api/v1/health/
curl -I https://estimator.vortexen.com/login

# Confirm both Market Intel DB and Vortexen Estimator containers and memory usage
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
docker stats --no-stream

# Manual backup, restore, and rollback commands
sudo /usr/local/sbin/vortexen-backup
sudo /usr/local/sbin/vortexen-restore /opt/vortexen-estimator/backups/<dump_file>
sudo /usr/local/sbin/vortexen-rollback
```

> **Optional Swap Recommendation:** If you frequently extract large IFC models concurrently while Market Intel DB runs heavy RAG indexing, consider expanding `/swapfile` from `2G` to `4G` on the host.
