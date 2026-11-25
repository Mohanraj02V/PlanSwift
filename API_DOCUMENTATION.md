# API_DOCUMENTATION.md — REST API Reference & Role Matrix (`/api/v1/`)

All endpoints return JSON (except binary downloads) and authenticate via HttpOnly JWT cookies (`vortexen_access` / `vortexen_refresh`) + `X-CSRFToken` on unsafe methods (or `Authorization: Bearer` for programmatic clients). OpenAPI schema endpoints (`/api/schema/`, `/api/docs/`) are disabled in production (`ENABLE_API_DOCS=false`) and restricted exclusively to active Organization Admins when enabled.

## Three-Role Access Matrix

| Endpoint Prefix | Methods | Admin | Estimator | User |
|---|---|---|---|---|
| `/api/v1/health/` | `GET` | AllowAny | AllowAny | AllowAny |
| `/api/v1/auth/csrf/`, `/auth/login/`, `/auth/refresh/` | `GET` / `POST` | AllowAny (throttled) | AllowAny (throttled) | AllowAny (throttled) |
| `/api/v1/auth/register/` | `POST` | **403 Disabled** | **403 Disabled** | **403 Disabled** |
| `/api/v1/auth/logout/`, `/auth/me/`, `/auth/change-password/` | `GET`/`PATCH`/`POST` | Allowed | Allowed | Allowed |
| `/api/v1/auth/users/` & `/auth/users/<id>/` | `GET`/`POST`/`PATCH`/`DELETE` | Allowed | 403 | 403 |
| `/api/v1/organizations/` (list/retrieve) | `GET` | Allowed | Allowed (own orgs) | Allowed (own orgs) |
| `/api/v1/organizations/` (write) & `/members/` | `GET`/`POST`/`PATCH`/`DELETE` | Allowed | 403 | 403 |
| `/api/v1/projects/` & `/projects/<id>/pages/` | `GET` | Allowed | Allowed (own org) | Allowed (own org) |
| `/api/v1/projects/` (create/edit/delete) | `POST`/`PATCH`/`DELETE` | Allowed | 403 | 403 |
| `/api/v1/project-sources/` | `GET` | Allowed | Allowed (own org) | Allowed (own org) |
| `/api/v1/project-sources/` (direct path POST) | `POST` | **405 Disabled** | **405 Disabled** | 403 |
| `/api/v1/project-sources/upload/` | `POST` (multipart) | Allowed | Allowed (own org) | 403 |
| `/api/v1/project-sources/<id>/` | `PATCH`/`DELETE` | Allowed | 403 | 403 |
| `/api/v1/extraction/` & `/<id>/logs/` | `GET` | Allowed | Allowed (own org) | Allowed (own org) |
| `/api/v1/extraction/` (trigger/re-run) | `POST` | Allowed | Allowed (own org) | 403 |
| `/api/v1/extraction/<id>/cancel/`, `<id>/` | `POST`/`DELETE` | Allowed | 403 | 403 |
| `/api/v1/source-inventory/`, `/cad-bim/`, `/objects/`, `/hierarchy/`, `/measurements/`, `/geometry/`, `/formulas/`, `/assemblies/`, `/classifications/`, `/components/`, `/annotations/`, `/validation/`, `/reconciliation/`, `/integrations/` | `GET` | Allowed | Allowed (own org) | Allowed (own org) |
| `/api/v1/estimation/sessions/` (`list`, `create`, `update-quotation`, `approve`, `export-excel`, `export-pdf`) | All | Allowed | 403 | 403 |
| `/api/v1/exports/<project_id>/` (`json`, `jsonl`, `csv`, `xlsx`, `geojson`) | `GET` | Allowed | 403 | 403 |
| `/api/v1/ai/`, `/retrieval/`, `/audit/`, `/notifications/` | All | Allowed | 403 | 403 |
