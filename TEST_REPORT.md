# Automated Test Verification Report (`TEST_REPORT.md`)

## 1. Execution Summary (All Verified Post-Final-Edit)

| Suite | Command | Outcome | Duration | Scope |
| :--- | :--- | :--- | :--- | :--- |
| **Extraction Engine & Backend Pytest** | `.\backend\.venv\Scripts\python.exe -m pytest extraction_engine\tests backend\tests -v` | **29 / 29 PASSED (0 failed)** | `119.92s` | Unit, security, geometry, formula AST, real project regression (`project 4` & `Sample Project`), COM oracle parity, DB persistence, RBAC, multipart ZIP upload, exports, AI isolation |
| **Django System Check** | `.\backend\.venv\Scripts\python.exe backend\manage.py check` | **0 issues** | `< 2s` | Full Django 5.1.15 app registry & URL/model integrity |
| **Frontend TypeScript Check** | `npm run typecheck` (`tsc --noEmit`) | **PASSED (0 errors)** | `< 3s` | All Next.js 14 TypeScript pages, hooks, API client, and components |
| **Frontend Vitest Unit Tests** | `npm test` (`vitest run`) | **4 / 4 PASSED (2 files)** | `4.78s` | Standalone provenance badges, calibrated `GeometryDataViewer` (0 `<canvas>`/`<img>`), `ObjectInspector`, `LoginPage` |
| **Frontend Production Build** | `npm run build` (`next build`) | **PASSED (21 / 21 routes)** | `< 20s` | Static prerender + SSR chunk verification |
| **Live HTTP Server E2E Probe** | Local Django WSGI server (`127.0.0.1:8012`) | **PASSED (exit 0)** | `< 14s` | Live JWT login, removed `/api/v1/planswift/environment/` → `404`, `source_path` redaction, multipart `.SwiftJob.zip` upload, auto-extraction (`12` events, `0` errors), `/objects/unsupported/`, `/exports/?export_format=json` (`20.0 SQ FT` calculated) |
| **Docker Compose Config Check** | Static inspection of `docker-compose.yml` & `docker-compose.prod.yml` | **PASSED** | Instant | Zero `CONNECTOR_`, `windows_connector`, or `planswift_connector` references |

---

## 2. Detailed Test Coverage Breakdown (`29` Pytest Tests)

### Standalone Formula Interpreter (`extraction_engine/tests/test_formula_evaluator.py`)
- Rejects malformed syntax (`[A] + * [B]`, `[A] + (`) with `FormulaSyntaxError`.
- Evaluates `RoundUp`, `Sqrt`, `If`, `Min`, `Max`, parent/ancestor refs (`[..]`, `[..\Name]`), root job refs (`[\Job\Sales Tax 1]`), cross-object page lookup (`[[PageGUID]\Name]`), `[!TakeoffFolder]`, arithmetic literals (`10 * 10`), label templates (`Slab Area (1 EA)`).
- Verifies honest error reasons (`division_by_zero`, `missing_external_settings`, `unsupported_pascal_script`, `system_variable_unavailable`).

### Calibrated Geometry & Quantities (`extraction_engine/tests/test_calibrated_geometry_and_quantities.py`)
- Calibrates `ScaleX=37.5 FT` polyline (`375 px → 10.0 FT = 3.048 m`) while preserving raw pixel geometry (`375.0`).
- Verifies uncalibrated pages keep `is_calibrated=False`, `calibrated_length=None`, and `status=UNRESOLVED` (zero scale fabrication).
- Skips `NaN` / non-numeric DigitizerData coordinates cleanly with `validation_warnings`.
- Validates SI length & area conversions (`convert_length_to_meters`, `convert_area_to_sq_meters`).

### Generic Classes, Circular Formulas & Reconciliation (`extraction_engine/tests/test_generic_classes_and_formulas.py`)
- Preserves unknown `FutureCustomClass` with `is_known_class=False`, empty-name properties, and `unsupported_objects` tracking.
- Detects mutual circular formulas (`[A] -> [B] -> [A]`) with `has_circular_dependency=True` and `circular_dependency` reason.
- Runs `reconcile_standalone_project` cleanly with `com_available=False`.

### Security & Resource Limit Guards (`extraction_engine/tests/test_security_guards.py` — 12 Tests)
- Blocks Zip-Slip traversal (`../../evil.xml`), absolute paths (`/etc/passwd`), disallowed executables (`.exe`), nested archives (`.zip` inside `.zip`), symlinks, ZIP bombs (`max_compression_ratio`), oversized archives (`max_upload_bytes`), corrupt ZIP signatures, outside `ALLOWED_SOURCE_ROOTS` paths.
- Detects duplicate/case-colliding archive entries.
- Blocks XXE `<!DOCTYPE` / `<!ENTITY` in both `XMLData.XML` and `DigitizerData` (`SecurityValidationError`), plus `max_xml_depth` and `max_xml_nodes` limits.

### Real Fixture Regression, Oracle Parity & Boundary Scans (`test_golden_project4_integration.py` + `test_standalone_regression_and_accuracy.py`)
- **`project 4.SwiftJob.zip`**: Verifies `1,461` objects, `28,355` properties, `16` empty-name properties, `324/324` TIFF links, `1,052` sections, `4,868` points, exact Count quantities (`21`, `922`, `286`, `354`), `78` decimal separator probes, `180` `PageWidth` unresolved formulas, cancellation support, and export outputs.
- **`com_snapshot.json` Oracle Parity**: **`5,418 / 5,418` (`100.00%`)** exact match against live PlanSwift 11 values without any PlanSwift runtime.
- **`Sample Project.SwiftJob`**: Verifies `224` objects, `42` pages, `14` assemblies, calibrated `Conference Room` (`500.38 SQ FT`), `Carpet` (`55.60 SQ YD`), `Exterior Walls` (`264.95 FT` linear / `2,384.53 SQ FT` wall area), and `5/8" Type X Drywall` (`67 EA`).
- **Edge Cases**: Missing `XMLData.XML`, malformed XML, and nested `MultiDataJob/Takeoff/Data.xml` directory extraction.
- **Architectural AST Scan (`test_standalone_security_no_com_no_ocr_no_eval_across_codebase`)**: Confirms **zero** COM/Windows/OCR/image imports and **zero** `eval()`/`exec()` calls across all Python modules.

### Backend API & End-to-End Persistence (`backend/tests/test_backend_api_and_e2e.py`)
- Auth JWT lifecycle, RBAC (`VIEWER` write denial), cross-tenant isolation, immutable `AuditLog`, AI-vs-extraction decoupling, multipart ZIP upload + security rejection + `/objects/unsupported/` + `/formulas/calculations/` + `/extraction/{id}/logs/` + `source_path` redaction + versioned JSON export.
