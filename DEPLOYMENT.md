# DEPLOYMENT.md — Environment, Container & Production Deployment Guide

## 1. Supported Environments

- `config.settings.development` — Local dev (`DEBUG=True`, SQLite or PostgreSQL, eager/thread extraction).
- `config.settings.testing` — In-memory SQLite + fast password hasher for automated pytest suite.
- `config.settings.staging` — `DEBUG=False`, secure cookies, `CONNECTOR_REQUIRE_TLS=true`.
- `config.settings.production` — Enforces non-default `SECRET_KEY`, HSTS, SSL redirect, `X-Frame-Options: DENY`, Gunicorn + Nginx TLS termination.

## 2. Container Architecture (`docker-compose.yml` & `docker-compose.prod.yml`)

- **postgres** (`postgis/postgis:16-3.4`) — Primary relational & spatial database with persistent volume and `./backups` mount.
- **redis** (`redis:7-alpine`) — Celery broker & result store.
- **backend** (`backend/Dockerfile`) — Django REST API (`gunicorn`, 4 workers) mounting source directory read-only (`:ro`).
- **celery_worker** — Asynchronous resumable extraction workers (`EXTRACTION_EXECUTION_MODE=celery`).
- **frontend** (`frontend/Dockerfile`) — Standalone Next.js Node server.
- **nginx** (`nginx/nginx.conf`, prod compose) — TLS 1.2/1.3 reverse proxy routing `/api/` -> Django and `/` -> Next.js.

## 3. Windows COM Connector Separation

PlanSwift Desktop COM automation **must NOT** run inside Linux Docker containers. Deploy `windows_connector\bin\VortexenPlanSwiftConnector.exe` on an authorized estimator Windows x64 workstation where PlanSwift is installed and signed in, pointing `--upload-url https://<your-domain>/api/v1/planswift/ingest/` at the cloud backend.

## 4. Database Backups & Healthchecks

- **Health Probe**: `GET /api/v1/health/` executes `SELECT 1` against the active database.
- **Backup Command (PostgreSQL)**:
  ```bash
  docker compose -f docker-compose.prod.yml exec postgres pg_dump -U vortexen vortexen_estimator > backups/vortexen_$(date +%F).sql
  ```
