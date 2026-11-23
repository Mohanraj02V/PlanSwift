# PROJECT_ANALYSIS.md — Existing Repository & Environment Assessment

## 1. Initial Repository State

Inspection of `c:\Users\mohan\OneDrive\Desktop\Vortexen Estimator` at project inception confirmed a **greenfield workspace**:

- **Files present**: Only `project 4.SwiftJob.zip` (`582,831,166` bytes).
- **Git repository**: Not initialized yet (`.git` absent).
- **Existing Django backend**: None.
- **Existing Next.js frontend**: None.
- **Existing database schema / migrations**: None.
- **Existing tests / deployment config**: None.

Because no legacy application code exists, there is no legacy functionality to deprecate or migrate. Instead, the primary preservation obligation applies to the **original local PlanSwift archive (`project 4.SwiftJob.zip`)**, which must remain strictly untouched, read-only, and excluded from version control.

---

## 2. Development Machine Environment Assessment

Verified directly on Windows:

| Component | Status | Observed Version / Path | Architectural Note |
|---|---|---|---|
| Python | Installed | `Python 3.12.0` at `C:\Users\mohan\AppData\Local\Programs\Python\Python312\python.exe` | Default `python` / `py` on PATH points to Windows Store stub; use dedicated `backend\.venv`. |
| `uv` | Installed | `uv 0.10.2` | Available alongside `pip 23.2.1`. |
| Node.js / npm | Installed | `node v24.21.0`, `npm 11.19.0` | Suitable for Next.js + TypeScript + Vitest frontend. |
| .NET Framework x64 C# Compiler | Installed | `C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe` | Supports compiling a native 64-bit Windows COM connector (`-platform:x64`). |
| PostgreSQL | Installed locally | PostgreSQL 18 (`C:\Program Files\PostgreSQL\18\bin\psql.exe`) | PostGIS and pgvector extensions are not pre-installed in the local PostgreSQL 18 share directory; Docker Desktop is installed (`29.7.2`) with daemon stopped. |
| PlanSwift Desktop | **Not Installed** | Checked `Program Files`, `Program Files (x86)`, `ProgramData`, `AppData`, and COM Registry (`HKLM`, `HKCU`, `WOW6432Node`) | No PlanSwift binary or COM ProgID (`PlanSwift.PlanSwift12`, `PlanSwift9.PlanSwift`) is registered on this machine. Live COM execution tests cannot run locally here and must be documented clearly as environment-bound. |

---

## 3. Architectural Strategy

### 3.1 Core Separation of Concerns

1. **Native Extraction Engine (`extraction_engine/`)** — Pure Python library with **zero dependency on Django, LLMs, OCR, or image rasterization**.
   - Streams `project 4.SwiftJob.zip` safely (Zip Slip / ZIP bomb / symlink / XXE protection) without decompressing the 324 `.tiff` files (1.48 GB uncompressed).
   - Parses `XMLData.XML` (`Windows-1252`, `8.05 MB`) and nested `DigitizerData` XML natively.
   - Emits canonical Pydantic models with strict provenance statuses (`original`, `api_extracted`, `normalized`, `computed_by_planswift`, `derived`, `ai_inferred`, `unresolved`, `unsupported`).

2. **Version-Aware Windows PlanSwift COM Connector (`windows_connector/`)** — Compiled 64-bit C# console agent.
   - Detects running/registered PlanSwift 12 (`PlanSwift.PlanSwift12`, 64-bit) or PlanSwift 9–11 (`PlanSwift9.PlanSwift`, 32-bit compatibility boundary) inside an interactive Windows user session.
   - Uses strictly read-only late-bound COM traversal (`GetItem`, `ChildCount`, `ChildItem`, `PropertyCount`, `PropertyName`, `GetPropertyFormula`, `GetPropertyResult`, `GetPropertyResultAsString`) and uploads JSON payloads over an authenticated token endpoint to Django.

3. **Modular Django 5 + DRF Backend (`backend/`)** — Domain-separated Django apps:
   - Identity & Tenancy: `accounts`, `organizations`, `permissions`, `audit_logs`, `notifications`.
   - Source & Extraction: `projects`, `project_sources`, `source_inventory`, `planswift_connector`, `extraction`, `background_jobs`.
   - Canonical Project Model: `object_model`, `object_hierarchy`, `measurements`, `geometry`, `formulas`, `classifications`, `dimensions`, `annotations`, `assemblies`, `components`, `denotations`, `remarks`.
   - Quality & Business Logic: `validation`, `reconciliation`, `estimation`, `exports`, `integrations`.
   - Independent AI Layer: `ai_providers`, `ai_prompts`, `knowledge_base`, `retrieval`, `ai_agents`, `ai_assistant`. Zero imports from `extraction_engine`; always retrieves structured SQL/graph/measurement/geometry records first before optional semantic RAG on text/knowledge docs.

4. **Next.js TypeScript Frontend (`frontend/`)** — App Router UI communicating solely via `/api/v1/` REST APIs:
   - Provides Dashboard, Project Management, Safe Source Import, Native Project Hierarchy Explorer, Object Inspector, Measurement & Formula Explorers, Geometry Data Explorer (structured coordinates & GeoJSON — **never** rasterized drawing views), Validation Dashboard, Estimation Rollups, AI Estimation Assistant with source citations, and Audit Logs.

5. **Database Strategy**:
   - **Development & CI Testing**: SQLite by default for zero-friction reproducible tests when PostgreSQL service/PostGIS are unavailable, plus full PostgreSQL + PostGIS + pgvector configuration in `docker-compose.yml` and `config/settings/production.py`.
   - **Critical Schema Keys**: Uniqueness is keyed by `(project_version, native_guid)` for objects and `(project_object, native_property_guid)` for properties — **never** by display name, because the real project contains duplicate object names (`New Count`, `Section`) and 16 empty-name properties (`Name=""`).

---

## 4. Security & Operational Guardrails Established from Day One

- `.gitignore` excludes `*.SwiftJob.zip`, `*.Swift`, `*.tiff`, `.env`, SQLite files, virtual environments, and build outputs.
- `ALLOWED_SOURCE_ROOTS` restricts local filesystem ingestion paths so arbitrary paths cannot be probed via public APIs.
- All XML parsing prohibits DTDs and external entity resolution (`resolve_entities=False`, `no_network=True`).
- Formulas and embedded PascalScript (`Expression="-1"`) are lexed statically and **never** passed to `eval()` / `exec()`.
- Multi-tenant isolation is enforced at both queryset and object permission levels in Django DRF views.
