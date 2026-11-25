# DEPLOYMENT.md — Container & Production Deployment Guide

## 1. Settings Profiles

- `config.settings.development` — Local development (`DEBUG=True`, SQLite or PostgreSQL, eager/thread extraction).
- `config.settings.testing` — Automated test profile (in-memory SQLite, MD5 fast hasher, auth throttle scopes configured).
- `config.settings.staging` — `DEBUG=False`, HTTPS proxy headers, `JWT_COOKIE_SECURE=True`, secure session/CSRF cookies.
- `config.settings.production` — Enforces fail-fast checks on `SECRET_KEY` (>=50 chars, non-default), explicit `ALLOWED_HOSTS` (no `*`), `CORS_ALLOWED_ORIGINS`, `CSRF_TRUSTED_ORIGINS`; enables HSTS preload, SSL redirect, `X_FRAME_OPTIONS="DENY"`, `ENABLE_API_DOCS=False`, and `JWT_COOKIE_SECURE=True`.

## 2. Container Architecture (`docker-compose.yml` & `docker-compose.prod.yml`)

- **postgres** (`postgis/postgis:16-3.4`) — Isolated on `private_net` in production (no public port exposure).
- **redis** (`redis:7-alpine`) — Isolated on `private_net` in production for Celery broker/backend and rate limiting.
- **migrate** — Dedicated one-shot service (`python manage.py migrate --noinput`, `restart: "no"`) that completes before `backend` and `celery_worker` start. Migrations never run inside multi-worker Gunicorn startup commands.
- **backend** (`backend/Dockerfile`) — Runs as non-root user `vortexen` with Gunicorn (`--workers 4 --timeout 300 --graceful-timeout 30`), sharing private named volume `uploads_data` (`uploads_prod_data`) mounted at `/data/uploads`.
- **celery_worker** — Executes asynchronous PlanSwift/DXF/IFC extractions with the same `uploads_data` volume, `CELERY_TASK_TIME_LIMIT=600`, `CELERY_TASK_SOFT_TIME_LIMIT=540`, and `CELERY_WORKER_MAX_TASKS_PER_CHILD=50`.
- **frontend** (`frontend/Dockerfile`) — Standalone Next.js 14 server running as non-root `nextjs`.
- **nginx** (`nginx/nginx.conf`, prod compose) — TLS 1.2/1.3 reverse proxy with `client_max_body_size 1024M` (aligned with `MAX_UPLOAD_ZIP_BYTES` / `MAX_UPLOAD_IFC_BYTES`), `300s` upload/proxy timeouts, rate limiting on `/api/v1/auth/login/` and `/api/v1/auth/refresh/`, security headers, and public blocking of `/api/docs/` & `/api/schema/`.

## 3. Production Deployment Steps

```bash
# 1. Populate production .env from .env.example (set SECRET_KEY >= 50 chars, POSTGRES_PASSWORD,
#    ALLOWED_HOSTS, CORS_ALLOWED_ORIGINS, CSRF_TRUSTED_ORIGINS, NEXT_PUBLIC_API_BASE_URL)
cp .env.example .env

# 2. Place TLS certificates in ./certs/fullchain.pem and ./certs/privkey.pem
# 3. Validate production Compose config and deploy
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d
```

## 4. Database Verification & Backups

- **Deployment Safety Check**:
  ```bash
  DJANGO_SETTINGS_MODULE=config.settings.production python backend/manage.py check --deploy
  ```
- **Health Probe**: `GET /api/v1/health/` verifies live DB connectivity (`SELECT 1`).
- **PostgreSQL Backup**:
  ```bash
  docker compose -f docker-compose.prod.yml exec postgres pg_dump -U vortexen vortexen_estimator > backups/vortexen_$(date +%F).sql
  ```

## 5. Hostinger KVM 2 Co-Hosting Stack (`deploy/hostinger/`)

For co-hosting Vortexen Estimator on an existing Hostinger KVM 2 VPS alongside another production application (such as Market Intel DB), use the isolated Hostinger stack under `deploy/hostinger/` instead of the root `docker-compose.prod.yml` (which binds ports `80`/`443`):

- `deploy/hostinger/docker-compose.production.yml` — Binds only loopback `127.0.0.1:8100` (API) and `127.0.0.1:3100` (Web), keeps PostgreSQL (`postgres:16-alpine`) and Redis internal to `vortexen_internal`, and tunes Gunicorn (`--workers 2 --threads 2`) and Celery (`--concurrency=1`) for 2 vCPU / 8 GB RAM.
- `deploy/hostinger/nginx/vortexen-estimator.conf` — Host Nginx vhost with unique rate-limit zones (`vx_auth_login_limit`, `vx_auth_refresh_limit`), `client_max_body_size 1024M`, and single-domain same-origin proxying for HttpOnly JWT/CSRF cookies.
- `deploy/hostinger/scripts/` — Non-destructive `setup_vortexen.sh`, atomic `deploy.sh` (supports both GitHub Actions tarballs via `.github/workflows/deploy-hostinger.yml` and direct `--build`), `rollback.sh`, `health_check.sh`, `backup.sh`, and `restore.sh`.
- Full step-by-step instructions: [`docs/HOSTINGER_KVM2_COHOSTING_GUIDE.md`](docs/HOSTINGER_KVM2_COHOSTING_GUIDE.md).

