# Repository & Codebase Audit (`PROJECT_AUDIT.md`)

## 1. Executive Summary

Prior to refactoring, **Vortexen Estimator** combined a strong core XML streaming parser (`extraction_engine/parsers/xml_parser.py`) and relational Django schema (`backend/apps/`) with runtime dependencies on an external Windows C#/.NET PlanSwift COM connector (`windows_connector/`, `backend/apps/planswift_connector/`, `extraction_engine/adapters/planswift_com/`, `extraction_engine/adapters/planswift_version_adapters/`). As a result:

1. Over 9,013 formulas in `project 4.SwiftJob.zip` and 1,517 formulas in `Sample Project.SwiftJob` remained `evaluation_status="unresolved"` unless PlanSwift Desktop was installed and running on Windows.
2. Geometry lengths and areas were computed in uncalibrated raw pixels (`raw_page_units` / `raw_page_units_sq`) even when pages explicitly carried `ScaleX`, `ScaleY`, and `Scale Units`.
3. `ProjectSourceViewSet` accepted only pre-mounted local filesystem paths (`source_path`) and leaked `source_path` in API responses; browsers had no chunked multipart `.zip`/`.SwiftJob` upload flow.
4. `backend/requirements.txt` mixed production dependencies with `pytest`/`pytest-django` and shipped `defusedxml` alongside `lxml`.

---

## 2. Module & Component Classification Matrix

| Component | Classification | Action Taken | Rationale |
| :--- | :--- | :--- | :--- |
| `windows_connector/` | **Obsolete / Unnecessary** | **Removed completely** | C#/.NET PlanSwift COM UIAutomation binary violates PlanSwift-free server execution. |
| `backend/apps/planswift_connector/` | **Obsolete / Dead Endpoint** | **Migrated to `zero` & Removed** | `/api/v1/planswift/` COM ingestion removed from `config/urls.py` and `INSTALLED_APPS`. |
| `extraction_engine/adapters/planswift_com/` | **Obsolete** | **Removed completely** | Dead COM adapter directory. |
| `extraction_engine/adapters/planswift_version_adapters/` | **Obsolete / Windows-only** | **Removed completely** | Used Python stdlib `winreg` to query Windows registry ProgIDs. |
| `extraction_engine/reconciliation/com_package_reconciliation.py` | **Replaceable** | **Replaced** | Replaced with `extraction_engine/reconciliation/standalone_reconciliation.py`. |
| `PLANSWIFT_COM_INTEGRATION.md` | **Obsolete** | **Removed completely** | Superseded by standalone extraction & calculation documentation. |
| `extraction_engine/parsers/archive_parser.py` | **Required — Upgraded** | **Preserved & Hardened** | Added upload limit enforcement, corrupt ZIP handling, case-insensitive duplicate path detection, XML encoding & version detection. |
| `extraction_engine/parsers/xml_parser.py` | **Required — Upgraded** | **Preserved & Hardened** | Added XML depth, node-count, timeout limits, strict DOCTYPE/ENTITY rejection, and `unsupported_objects` tracking. |
| `extraction_engine/parsers/geometry_parser.py` | **Required — Upgraded** | **Switched `defusedxml` → `lxml`** | Uses hardened `lxml.etree.XMLParser` + explicit DOCTYPE/ENTITY rejection + `NaN`/`Inf` coordinate validation. |
| `extraction_engine/normalizers/geometry_normalizer.py` | **Upgraded** | **Implemented Calibration** | Computes real-world lengths and polygon areas via `ScaleX`/`ScaleY` while preserving raw pixel values intact. |
| `extraction_engine/parsers/formula_parser.py` + `extraction_engine/formulas/` | **Core Gap — Built** | **Implemented AST Interpreter** | Replaced static-only stub with safe recursive-descent lexer, AST parser, dependency graph, and PlanSwift evaluator (zero `eval()`). |
| `extraction_engine/calculators/quantity_engine.py` | **New Required Module** | **Implemented** | Separates `native_stored_value`, `reconstructed_quantity`, `calculated_quantity`, and SI normalized quantities. |
| `backend/apps/project_sources/views.py` | **Required — Upgraded** | **Added Streaming ZIP Upload** | Added `POST /api/v1/project-sources/upload/` with `TemporaryFileUploadHandler` chunking and removed `source_path` from read responses. |
| `backend/apps/object_model/views.py` | **Required — Optimized** | **Fixed N+1 + Added `/unsupported/`** | Added `Count("properties")` query annotation and `/api/v1/objects/unsupported/`. |
| `backend/apps/formulas/urls.py` | **Required — Upgraded** | **Added `/calculations/`** | Added calculated results endpoint & filter fields (`calculation_reason`). |
| `backend/apps/extraction/views.py` | **Required — Upgraded** | **Added `/logs/`** | Exposes structured stage telemetry & error records per run. |
| `backend/apps/exports/urls.py` | **Required — Upgraded** | **Versioned JSON Export (`1.0`)** | Outputs canonical schema including `calculations`, `unsupported_objects`, calibrated geometry, and zero internal paths. |
| `frontend/src/app/extraction/page.tsx` | **Upgraded** | **Removed COM UI; Added Dropzone** | Replaced COM snapshot upload/status with drag-and-drop ZIP upload, progress bar, and stage log viewer. |
| `frontend/src/components/object-inspector/ObjectInspector.tsx` | **Upgraded** | **10-Section Data Inspector** | Added tabs for Overview, Properties, Geometry, Measurements, Formulas, Calculations, Relationships, Raw Data, Provenance, Validation. |
| `backend/apps/ai_providers/`, `retrieval/`, `knowledge_base/` | **Required — Preserved Boundary** | **Updated Provenance Reading** | Preserved strict decoupling from `extraction_engine`; updated to surface standalone `calculated`/`reconstructed` quantities. |

---

## 3. Specific Bugs & Security/Performance Issues Identified & Resolved

1. **Missing Direct Multipart ZIP Upload (`backend/apps/project_sources/views.py`)**: Browsers could only pass server local file paths. Implemented streaming chunked upload to `EXTRACTION_WORK_DIR/uploads/` with extension, magic-byte, size, Zip-Slip, zip-bomb, and symlink enforcement.
2. **Internal Server Path Leakage (`ProjectSourceSerializer`)**: `source_path` was previously serialized in `ProjectSource` read responses and `manifest_summary`. Made `source_path` `write_only=True` and stripped it from `manifest_summary` and JSON exports.
3. **N+1 Query on Object Listings (`ProjectObjectListSerializer`)**: Previously executed `obj.properties.count()` per row (`N+1` SQL queries). Fixed via `.annotate(property_count=Count("properties"))`.
4. **Property Masking on Child BOM Items (`extraction_engine/formulas/evaluator.py`)**: During development verification against `Sample Project.SwiftJob`, child `<Item Class="Item">` objects (e.g. `5/8" Type X Drywall`) initially resolved `[Linear Total]` to `0.0` before checking their parent `<Item Class="Linear">` (`Exterior Walls`). Restricting virtual geometry defaults strictly to takeoff/section classes restored parent inheritance (`264.95 FT -> 2,384.53 SQ FT Wall Area -> 67 EA`).
5. **Non-bracket Arithmetic Property Literals**: `15 mil Vapor Barrier` stored `Material Coverage = '20 * 100'` without `[...]` brackets. Added safe AST arithmetic evaluation for `Number`/`Slider` properties containing arithmetic operators.
6. **Uncalibrated Pixel-Only Quantities**: `geometry_normalizer.py` previously divided point coordinates by `ScaleX` only without computing calibrated polyline/segment/polygon quantities or units.
