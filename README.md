# Vortexen Estimator — PlanSwift Native Project Extraction & AI Estimation Platform

Vortexen Estimator transforms native PlanSwift project packages (`.SwiftJob.zip` / `XMLData.XML` and optional Windows COM snapshots) into a structured, provenance-tracked Canonical Digital Project Model backed by Django REST Framework, PostgreSQL/SQLite, Celery/Redis, and a Next.js TypeScript explorer — **without drawing rasterization, PDF-to-image conversion, OCR, or vision models**.

---

## Key Capabilities

1. **Zero-Raster Native Extraction Engine (`extraction_engine/`)**
   - Streams `XMLData.XML` directly from large PlanSwift ZIP archives (`582.8 MB` `project 4.SwiftJob.zip` verified in ~16.3s at ~169.5 MB peak memory) without extracting or decoding the `324` embedded `.tiff` files (`1.486 GB` uncompressed).
   - Protects against Zip Slip (`../`), absolute paths, symlinks, zip bombs, nested archives, unexpected executables, and XML XXE/DTD attacks (`defusedxml` + `lxml` entity prohibition).
   - Preserves all `1,461` `<Item>` objects, `28,355` `<Property>` elements (including `16` empty-name `Name=""` properties and `34` XML attributes), `324/324` Page-to-TIFF manifest matches, `1,052` `Count Section` `DigitizerData` coordinate collections (`4,868` raw points), and `9,013` formulas/PascalScript expressions without calling `eval()`.
2. **Version-Aware Windows 64-Bit PlanSwift COM Connector (`windows_connector/`)**
   - Compiled x64 C# console agent (`VortexenPlanSwiftConnector.exe`) supporting PlanSwift 12 (`PlanSwift.PlanSwift12`) and PlanSwift 9–11 (`PlanSwift9.PlanSwift`) read-only traversal, authenticating and pushing snapshots to `/api/v1/planswift/ingest/`.
3. **Modular Django 5 + DRF Backend (`backend/`)**
   - Domain-separated Django apps covering multi-tenant organizations, JWT auth with refresh rotation & token revocation, RBAC permissions, source inventory, extraction state machine, canonical object/measurement/geometry/formula storage, validation scorecards, COM-vs-package reconciliation, deterministic SQL estimation, multi-format exports (`JSON`, `JSONL`, `CSV`, `XLSX`, `GeoJSON`), immutable audit logs, and an **independent AI estimation layer** (`SQL + Graph + Geometry` first, `Vector RAG` strictly for supporting text).
4. **Next.js TypeScript Explorer (`frontend/`)**
   - Responsive dashboard, native hierarchy explorer, object/property inspector, measurement & formula viewers, structured coordinate geometry data explorer (no drawing canvas), validation/reconciliation reports, estimation approvals, provenance-tagged AI assistant, and audit trail.

---

## Quick Start (Local Development)

### 1. Extraction Engine & Backend Setup

```powershell
# Activate Python 3.12 virtualenv created at backend\.venv
.\backend\.venv\Scripts\python.exe backend\manage.py migrate
.\backend\.venv\Scripts\python.exe backend\manage.py seed_demo_and_extract --source "project 4.SwiftJob.zip"
.\backend\.venv\Scripts\python.exe backend\manage.py runserver 127.0.0.1:8000
```

### 2. Frontend Setup

```powershell
cd frontend
npm run dev
```

Open `http://localhost:3000` and sign in with the seeded dev account (`estimator@vortexen.local` / `VortexenDev123!`, or set `DEV_ADMIN_PASSWORD`).

---

## Documentation Index

- [PROJECT_ANALYSIS.md](PROJECT_ANALYSIS.md) — Initial repository & environment assessment
- [ARCHITECTURE.md](ARCHITECTURE.md) — System & domain architecture
- [PLANSWIFT_FORMAT_RESEARCH.md](PLANSWIFT_FORMAT_RESEARCH.md) — Native `.SwiftJob.zip` & `XMLData.XML` schema findings
- [PLANSWIFT_COM_INTEGRATION.md](PLANSWIFT_COM_INTEGRATION.md) — Windows 64-bit COM connector & desktop constraints
- [NATIVE_OBJECT_MODEL.md](NATIVE_OBJECT_MODEL.md) — PlanSwift native classes, properties, geometry & formulas
- [EXTRACTION_PIPELINE.md](EXTRACTION_PIPELINE.md) — 10-stage state machine, idempotency & checkpoints
- [CANONICAL_DATA_MODEL.md](CANONICAL_DATA_MODEL.md) — Canonical schemas & JSON structure
- [DATABASE_SCHEMA.md](DATABASE_SCHEMA.md) — Relational schema, constraints & indexes
- [DATA_PROVENANCE.md](DATA_PROVENANCE.md) — Mandatory 8-status provenance contract
- [API_DOCUMENTATION.md](API_DOCUMENTATION.md) — REST endpoints (`/api/v1/`)
- [SECURITY.md](SECURITY.md) — Auth, RBAC, tenant isolation, ZIP/XML hardening
- [TESTING.md](TESTING.md) — Automated unit, integration, golden dataset & E2E verification
- [DEPLOYMENT.md](DEPLOYMENT.md) — Docker Compose, PostgreSQL/PostGIS, Celery/Redis, Nginx TLS
- [EXTRACTION_LIMITATIONS.md](EXTRACTION_LIMITATIONS.md) — Explicit unverified/unresolved boundaries
