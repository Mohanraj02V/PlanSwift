# TESTING.md — Automated Verification, Golden Dataset & Observed Results

Every test suite below was executed directly after final code edits, with zero skipped or mocked assertions on the real source archive.

---

## 1. Native Extraction Engine (`extraction_engine/tests/`)

Command:
```powershell
.\backend\.venv\Scripts\pytest.exe extraction_engine/tests -v --tb=short
```

Observed result: **12 / 12 PASSED** (54.53s including double full-run idempotency + multi-format export generation on `project 4.SwiftJob.zip`):

- **`test_security_guards.py` (9 tests)**:
  - Rejects Zip Slip traversal (`../../evil.xml`)
  - Rejects absolute archive paths (`/etc/passwd`)
  - Rejects disallowed executables (`payload.exe`)
  - Rejects nested archives (`inner.zip`)
  - Rejects ZIP Unix symlinks (`0o120777`)
  - Rejects ZIP bomb compression ratios (`>50x` on `12 MB` payload)
  - Enforces `ALLOWED_SOURCE_ROOTS` confinement
  - Blocks XXE external entity expansion in `XMLData.XML` (`resolve_entities=False`, `no_network=True`, `load_dtd=False`)
  - Blocks DTD/XXE injection in `DigitizerData` (`defusedxml.ElementTree`)
- **`test_generic_classes_and_formulas.py` (1 test)**:
  - Verifies generic preservation of unknown custom class (`FutureCustomClass`, empty property name), `Assembly` + `Part` components, circular formula dependency detection (`[A]` <-> `[B]`), Shoelace derived polygon area (`50.0` while preserving `Qty="[Takeoff]"`), and COM reconciliation (`computed_by_planswift`).
- **`test_golden_project4_integration.py` (2 tests)**:
  - Verifies real `project 4.SwiftJob.zip` (`582,831,166` bytes) extraction: `325` archive entries, `324` `.tiff` assets cataloged without decoding, `1,461` objects (`Item=4, Folder=2, Page=324, Count=78, Count Section=1052, Segment=1`), `28,355` properties (`16` empty-name props), `324/324` Page-to-TIFF matches, `1,052/1,052` resolved `PageGUID` links, `4,868` raw coordinates, `78` PascalScript formulas (`unresolved`), spot checks (`CHR ans CHS 100`=21, `CHS and CHR20 mm dia`=922, `Duct 350x200mm`=286, `ELECTRICALPVC 25mm`=354), peak memory `< 256 MB` (measured `169.49 MB` in CLI validate at `16.32s`), identical SHA-256 digest (`43178b01eb2d9427ec66f81b36b93826ca1709e520f5828056570dae162376a8`) across consecutive runs, and JSON/JSONL/GeoJSON/CSV/XLSX export creation.
  - Verifies cooperative cancellation via `ExtractionCancelledError`.

---

## 2. Windows x64 COM Connector (`windows_connector/`)

Compiled with `C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe -platform:x64`:
- `--health`: exit 0 (`is_64_bit_process: true`, `is_user_interactive: true`, `com_ready: false`)
- `--detect`: exit 0 (`RegisteredProgIds: []`, confirms PlanSwift Desktop is not installed on host)
- `--self-test`: exit 0 (`self_test: "passed"`, SHA-256 payload digest computed)
- `--extract-com`: exit 2 (`PLANSWIFT_COM_UNAVAILABLE`, graceful handling without crash)

*Note: Live COM attachment tests against an active PlanSwift Desktop GUI session must be executed on a Windows workstation with PlanSwift 11 or 12 installed and signed in.*

---

## 3. Django Backend API, RBAC, E2E & Architectural Guardrails (`backend/tests/`)

Command:
```powershell
.\backend\.venv\Scripts\pytest.exe -c backend\pytest.ini backend\tests -v --tb=short
```

Observed result: **4 / 4 PASSED** (124.36s):
- `test_auth_lifecycle_rbac_tenant_isolation_and_audit_immutability`: JWT login, refresh rotation, logout token blacklisting, cross-tenant `404`/`403` isolation, `viewer` write denial (`403`), and `AuditLog` append-only immutability (`ImmutableAuditError`).
- `test_ai_layer_has_zero_extraction_engine_imports`: AST import scan across all `ai_*` and `retrieval` modules confirming zero imports of `extraction_engine`.
- `test_extraction_engine_has_zero_image_ocr_or_llm_imports`: AST import scan across `extraction_engine/` confirming zero imports of `PIL`, `cv2`, `pytesseract`, `ultralytics`, `torch`, `openai`, `anthropic`, `google.genai`, or `apps.ai_*`.
- `test_end_to_end_real_project4_extraction_idempotency_estimation_exports_and_ai`:
  - Registers `project 4.SwiftJob.zip`, runs extraction #1 (`1,461` `ProjectObject`, `28,355` `ObjectProperty`, `16` empty-name props, `324` `ProjectPage`, `1,052` `MeasurementSection`, `4,868` `MeasurementPoint`).
  - Runs extraction #2 and verifies **strict idempotency** (counts remain identical).
  - Verifies `/api/v1/hierarchy/tree/`, `/api/v1/objects/`, `/api/v1/geometry/`, `/api/v1/validation/` (`100.0%` verified accuracy on supported fields), estimation generation (`79` items, `Duct 350x200mm` = `286.0` `derived`, formula `[Takeoff]`) & approval, 5 export formats, Knowledge Base indexing + `/api/v1/ai/query/` (`data_status="derived"`, `inference_used=False`, cites `Duct 350x200mm` GUID), and `/api/v1/planswift/ingest/` COM payload + re-extraction reconciliation (`computed_by_planswift`).

---

## 4. Live HTTP Server End-to-End Verification

Seeded `project 4.SwiftJob.zip` into SQLite dev database via `manage.py seed_demo_and_extract`, booted `manage.py runserver 127.0.0.1:8019 --noreload`, and verified live HTTP responses (`httpx`):
- `LIVE_HTTP_E2E_OK`: `projects=1`, `objects=1461`, `tree_nodes_depth2=409`, `geometries=1052`, `validation_accuracy_pct=100.0`, `estimation_items=79`, `ai_data_status='derived'`, `ai_citations=15`, `export_json_bytes=6303643`, `audit_count=4`.

---

## 5. Next.js TypeScript Frontend (`frontend/`)

Commands:
```powershell
npm --prefix frontend run typecheck
npm --prefix frontend run test
npm --prefix frontend run build
```

Observed results:
- `tsc --noEmit`: exit 0 (0 TypeScript errors).
- `vitest run`: **2 / 2 test files, 4 / 4 tests PASSED** (`ProvenanceBadge`, `GeometryDataViewer` asserting zero `<canvas>`/`<img>` drawing elements, `ObjectInspector` empty-name property rendering, `LoginPage` Zod validation).
- `next build`: exit 0, built all 21 App Router routes (`/` through `/validation`).
