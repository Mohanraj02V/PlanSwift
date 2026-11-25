# ARCHITECTURE.md — Vortexen Estimator System Architecture

## 1. High-Level Architectural Boundaries

```text
+-----------------------------------------------------------------------+
|                       Next.js 14 TypeScript Frontend                  |
|  Login (Org-Only) | /estimator (Admin/Estimator/User)                 |
|  Admin Modules: Dashboard | Users | Estimation & PDF/XLSX | Audit ... |
+-----------------------------------+-----------------------------------+
                                    | HTTPS + HttpOnly JWT Cookies + CSRF
                                    v
+-----------------------------------------------------------------------+
|                    Django 5 + DRF Modular Monolith                    |
|                                                                       |
|  Auth & RBAC:         CookieAwareJWTAuthentication, RolePolicyPermission|
|                       3 Roles ONLY: admin | estimator | user          |
|  Ingestion & Jobs:    projects, project_sources (upload-only),        |
|                       extraction, background_jobs                     |
|  Canonical Model:     object_model, object_hierarchy, measurements,   |
|                       geometry, formulas, cad_bim, classifications,   |
|                       dimensions, annotations, assemblies, components |
|  Quality & Business:  validation, reconciliation, estimation, exports |
|  Independent AI:      ai_providers, ai_prompts, knowledge_base,       |
|                       retrieval, ai_agents, ai_assistant (Admin-only) |
+------------------+----------------------------------+-----------------+
                   |                                  |
                   v                                  v
+----------------------------------+  +---------------------------------+
|   Standalone Extraction Engine   |  |   PostgreSQL (+PostGIS opt.)    |
|   extraction_engine/             |  |   & Redis / Celery Workers      |
|   1. PlanSwift ZIP / XML         |  +---------------------------------+
|   2. DXF CAD (ezdxf)             |
|   3. IFC BIM (IfcOpenShell)      |
+----------------------------------+
```

---

## 2. Hard Architectural Invariants

1. **Zero PlanSwift Live Sync / Zero COM**: All runtime extraction runs cleanly inside Linux or Windows containers over browser-uploaded `.SwiftJob.zip`, `.zip`, `.xml`, `.dxf`, and `.ifc` files. Direct server-path API ingestion is disabled (`405`), and obsolete live-sync/COM connector logic has been removed.
2. **Three-Path Engine Isolation**: PlanSwift XML, `ezdxf` CAD, and `IfcOpenShell` BIM run through isolated adapter pipelines converging cleanly into `CanonicalProject` while preserving exact `native`, `calculated`, `reconstructed`, `inferred`, `unresolved`, and `unsupported` provenance.
3. **No Visual Guessing**: `extraction_engine/` contains zero OCR, PDF rasterization, or computer vision imports (enforced via AST test scanning across `extraction_engine/` and `backend/`).
4. **Strict Role Enforcement (`backend/apps/permissions/rbac.py`)**: Organization Admin privileges derive strictly from active `OrganizationMember(role="admin")` (never from `is_staff=True` alone). `estimator` and `user` are isolated inside `/estimator` and blocked at the API layer (`403`) from Admin/Estimation/Export/AI/Users/Audit endpoints.
5. **Independent AI Layer**: AI modules never import `extraction_engine/` and operate strictly over persisted canonical SQL records for Admin users.
