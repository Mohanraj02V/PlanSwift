# Vortexen Estimator — PlanSwift, DXF & IFC Engineering Platform

Vortexen Estimator transforms native PlanSwift project packages (`.SwiftJob.zip` / `.zip` / `XMLData.XML`), AutoCAD DXF drawings (`.dxf`), and IFC BIM models (`.ifc`) into a structured, provenance-tracked Canonical Digital Project Model backed by Django 5 + DRF, PostgreSQL/SQLite, Celery/Redis, and a Next.js TypeScript frontend branded with official Vortexen identity.

---

## Core Capabilities

1. **Three Independent Standalone Extraction Paths (`extraction_engine/`)**
   - **PlanSwift Native ZIP / XML (`planswift_package`, `planswift_xml`)**: Streams `XMLData.XML` directly from archives without rasterizing `.tiff` images; evaluates formulas and PascalScript expressions statically (zero `eval()`); preserves geometry points, calibration scales, properties (including empty-name attributes), and unknown classes.
   - **DXF CAD (`ezdxf`)**: Supports ASCII & Binary DXF (`R12`–`R2018`), layer tables, block definitions, nested `INSERT` transforms, OCS-to-WCS math, curves/bulges, dimension override separation, XREF metadata isolation, and multi-file DXF/IFC ZIP bundle extraction.
   - **IFC BIM (`IfcOpenShell`)**: Supports `IFC2X3`, `IFC4`, and `IFC4X3_ADD2`, spatial hierarchy, direct & type-inherited `IfcPropertySet`s, native `IfcElementQuantity` (`Qto_*`) separated strictly from bounded opt-in 3D tessellation metrics.
2. **Organization-Controlled Three-Role RBAC (`Admin`, `Estimator`, `User`)**
   - **Admin (`admin`)**: Full platform management (organizations, user provisioning/resets, projects, uploads, extractions, commercial estimation, Excel BOQ & branded Vortexen PDF quotation exports, AI assistant, immutable audit logs, settings).
   - **Estimator (`estimator`)**: Scoped exclusively to the dedicated **Estimator Workspace** (`/estimator`). Can view org projects, upload PlanSwift/DXF/IFC files, trigger/re-run extraction, and inspect extracted results/validation. Cannot edit/delete/export/approve or access Admin modules.
   - **User (`user`)**: Scoped exclusively read-only inside `/estimator` to inspect projects, files, extracted results, measurements, geometry, and validation warnings.
3. **Enterprise Security & HttpOnly Cookie Authentication**
   - Public self-registration is disabled (`403`).
   - Authentication uses **HttpOnly, SameSite, Secure (prod) JWT cookies + CSRF protection**, login/refresh rate throttling, immediate `token_version` session revocation on role/status/password changes, and immutable `AuditLog` tracking.

---

## Quick Start (Local Development)

### 1. Backend & Extraction Engine
```powershell
.\backend\.venv\Scripts\python.exe backend\manage.py migrate
# Development-only demo seed (requires DEBUG=True and explicit password >= 10 chars)
.\backend\.venv\Scripts\python.exe backend\manage.py seed_demo_and_extract --password "YourDevPassword123!" --source "project 4.SwiftJob.zip"
.\backend\.venv\Scripts\python.exe backend\manage.py runserver 127.0.0.1:8000
```

### 2. Frontend
```powershell
cd frontend
npm run dev
```

Open `http://localhost:3000/login` and sign in with your organization-provisioned account.

---

## Documentation Index

- [ARCHITECTURE.md](ARCHITECTURE.md) — System boundaries, three-role RBAC & extraction architecture
- [SECURITY.md](SECURITY.md) — HttpOnly cookie JWT, CSRF, RBAC, upload/XML hardening, and audit logs
- [DEPLOYMENT.md](DEPLOYMENT.md) — Docker Compose, separate migration lifecycle, Celery/Redis, Nginx TLS
- [DATABASE_SCHEMA.md](DATABASE_SCHEMA.md) — Relational schema, constraints, migrations & indexes
- [API_DOCUMENTATION.md](API_DOCUMENTATION.md) — `/api/v1/` endpoints and three-role access matrix
- [DEPENDENCY_CLEANUP.md](DEPENDENCY_CLEANUP.md) — Legacy PlanSwift live-sync removal and dependency audit
- [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md) — Production delivery summary and verification report
- [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) — Upstream dependency versions & licenses
