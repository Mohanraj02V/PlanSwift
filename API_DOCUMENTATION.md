# API_DOCUMENTATION.md — REST API Reference (`/api/v1/`)

All endpoints return JSON and enforce JWT Bearer authentication (except `/api/v1/health/`, `/api/v1/auth/login/`, `/api/v1/auth/register/`, `/api/v1/auth/refresh/`). Interactive OpenAPI documentation is served at `/api/schema/` and `/api/docs/`.

## Endpoint Catalog

| Prefix | Methods | Purpose |
|---|---|---|
| `/api/v1/health/` | `GET` | Liveness + DB readiness probe |
| `/api/v1/auth/` | `POST` / `GET` / `PATCH` | `login/`, `refresh/`, `logout/` (token blacklist), `register/`, `me/`, `change-password/` |
| `/api/v1/organizations/` | `GET`, `POST`, `PATCH`, `DELETE` | Multi-tenant org management & `<id>/members/` RBAC roster |
| `/api/v1/projects/` | `GET`, `POST`, `PATCH`, `DELETE` | Project lifecycle & `<id>/pages/` paginated page listing |
| `/api/v1/project-sources/` | `GET`, `POST` | Register & manifest-inspect local `PLANSWIFT_SOURCE_PATH` archives |
| `/api/v1/source-inventory/` | `GET` | Query inventoried archive files (`XMLData.XML` + `.tiff` entries) |
| `/api/v1/planswift/` | `GET`, `POST` | `environment/`, `ingest/` (Windows COM JSON snapshot receiver), `batches/` |
| `/api/v1/extraction/` | `GET`, `POST` | Trigger extraction runs, poll stage events/errors, `<id>/cancel/` |
| `/api/v1/objects/` | `GET` | Search/filter canonical `ProjectObject`s & retrieve full properties |
| `/api/v1/hierarchy/` | `GET` | `tree/<project_id>/` (depth/parent traversal) & `relationships/` |
| `/api/v1/measurements/` | `GET` | Measurements (`/`), measurement sections (`sections/`) |
| `/api/v1/geometry/` | `GET` | Geometry features (`/`) & detailed `<id>/` coordinate point arrays |
| `/api/v1/formulas/` | `GET` | Formula expressions, PascalScript filter, cycle flags & dependency edges |
| `/api/v1/classifications/` | `GET` | Native WBS & normalized/inferred classifications |
| `/api/v1/assemblies/` | `GET` | Native assemblies and nested components |
| `/api/v1/components/` | `GET` | Component items |
| `/api/v1/annotations/` | `GET` | Annotations & markups |
| `/api/v1/validation/` | `GET` | Validation scorecards & field-level check matrix |
| `/api/v1/reconciliation/` | `GET` | COM-vs-Package reconciliation reports |
| `/api/v1/estimation/sessions/` | `GET`, `POST` | Generate deterministic SQL estimation rollups & `<id>/approve/` |
| `/api/v1/exports/<project_id>/` | `GET` | Download `?export_format=json|jsonl|csv|xlsx|geojson` |
| `/api/v1/integrations/denotations/` | `GET` | SwiftExcel link tokens, Item #, Cost Code, GroupId |
| `/api/v1/ai/` | `POST`, `GET` | `query/` (provenance-cited estimation Q&A) & `conversations/` |
| `/api/v1/retrieval/` | `POST`, `GET` | `preview/`, `logs/`, `knowledge/` (engineering reference docs) |
| `/api/v1/audit/` | `GET` | Append-only tenant-scoped audit trail |
| `/api/v1/notifications/` | `GET` | User & org extraction notifications |
