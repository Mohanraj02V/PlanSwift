# Dependency Cleanup Report (`DEPENDENCY_CLEANUP.md`)

## 1. Objective

Ensure **Vortexen Estimator** runs on Linux or Windows containers without PlanSwift Desktop, PlanSwift DLLs, COM/ActiveX, Windows registry access, OCR engines, computer vision libraries, raster image decoders for extraction, or development tooling in production images.

---

## 2. Removed Dependencies & Packages

| Artifact / Dependency | Previous Usage | Removal Rationale | Replacement |
| :--- | :--- | :--- | :--- |
| `windows_connector/` (.NET / C# COM binary) | Queried PlanSwift 11 COM objects on Windows | Violates PlanSwift-free standalone requirement | Standalone ZIP/XML + AST Formula & Geometry Engines |
| `defusedxml>=0.7.1` | Used only in `extraction_engine/parsers/geometry_parser.py` (`fromstring`) while `xml_parser.py` & `archive_parser.py` already used hardened `lxml.etree` | Redundant XML parser dependency across engine and backend | `lxml.etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False, huge_tree=False)` + explicit `<!DOCTYPE`/`<!ENTITY` guard |
| `pytest`, `pytest-django` in `backend/requirements.txt` | Shipped inside production Docker container (`backend/Dockerfile`) | Unnecessary dev test runner in production images | Split into `backend/requirements-dev.txt` (`-r requirements.txt`) |
| `winreg` (`version_detector.py`) | Queried `HKEY_CLASSES_ROOT\PlanSwift*` | Windows-only PlanSwift COM discovery | Removed (`extraction_engine/adapters/planswift_version_adapters/` deleted) |
| `CONNECTOR_SHARED_TOKEN`, `CONNECTOR_REQUIRE_TLS` | `.env.example`, `backend/config/settings/base.py`, `docker-compose.prod.yml` | Unused COM connector auth secrets | Removed cleanly |

---

## 3. Retained Production Dependencies Audit

### Extraction Engine (`extraction_engine/pyproject.toml`)
| Package | Dependent Modules | Purpose | Production Needed? |
| :--- | :--- | :--- | :--- |
| `pydantic>=2.9.0` | `core/extraction_result.py`, `core/source_manifest.py` | Strict Canonical Data Model validation & serialization | **Yes** |
| `lxml>=5.3.0` | `parsers/xml_parser.py`, `parsers/archive_parser.py`, `parsers/geometry_parser.py` | Streaming `iterparse` for multi-MB `XMLData.XML` under low memory + XXE hardening | **Yes** (stdlib `xml.etree` lacks `huge_tree`/`no_network` & fast C `iterparse` cleanup) |
| `openpyxl>=3.1.5` | `exporters/tabular_exporter.py` | Multi-sheet native Excel (`.xlsx`) workbook generation | **Yes** |

### Django Backend (`backend/requirements.txt`)
| Package | Dependent Modules | Purpose |
| :--- | :--- | :--- |
| `Django`, `djangorestframework`, `djangorestframework-simplejwt`, `django-cors-headers`, `django-filter`, `drf-spectacular` | Core REST API, JWT auth, OpenAPI schema, filtering | **Yes** |
| `celery`, `redis` | `backend/config/celery.py`, `apps/background_jobs/tasks.py`, `docker-compose*.yml` | Async extraction task execution in production | **Yes** |
| `psycopg[binary]`, `whitenoise`, `gunicorn` | Production PostgreSQL driver, static serving, WSGI server | **Yes** |
| `httpx` | `apps/ai_providers/services.py` | Optional OpenAI-compatible AI assistant HTTP client | **Yes** (strictly isolated in AI layer) |

### Frontend (`frontend/package.json`)
| Package | Verified Imports | Purpose |
| :--- | :--- | :--- |
| `next`, `react`, `react-dom` | All pages & components | App Router React SSR/CSR UI |
| `lucide-react` | `components/layout/AppShell.tsx` | Minimal vector UI icons |
| `zod` | `package.json` validation utility | Runtime schema safety (dev/runtime minimal footprint; total prod deps = 5) |

---

## 4. Prohibited Dependency Verification

AST static analysis across **every `.py` file** under `extraction_engine/` and `backend/` (enforced by `test_standalone_security_no_com_no_ocr_no_eval_across_codebase` in `extraction_engine/tests/test_standalone_regression_and_accuracy.py`) confirms **zero imports** of:
- COM / Windows: `winreg`, `win32com`, `pythoncom`, `comtypes`, `apps.planswift_connector`, `planswift_com`, `planswift_version_adapters`
- OCR / Vision / Image / PDF libs: `pytesseract`, `easyocr`, `cv2`, `PIL`, `pdf2image`, `pypdf`, `fitz`, `ultralytics`, `torch`, `tensorflow`
- Unsafe code execution: **zero calls** to `eval()` or `exec()`.
