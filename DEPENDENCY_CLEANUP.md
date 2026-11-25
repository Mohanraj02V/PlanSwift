# Dependency & Code Cleanup Report (`DEPENDENCY_CLEANUP.md`)

## 1. Objective

Ensure **Vortexen Estimator** runs cleanly across Linux/Windows Docker containers and production environments without obsolete PlanSwift Desktop live-sync/COM code, direct server-path ingestion loopholes, dev-only test dependencies in runtime images, or browser-exposed JWT tokens.

---

## 2. Removed Obsolete Features, Configs & Dependencies

| Artifact / Config / Dependency | Previous Usage | Action Taken | Replacement |
| :--- | :--- | :--- | :--- |
| `CONNECTOR_REQUIRE_TLS` | `production.py`, `staging.py` | Removed obsolete COM connector flag | Standard TLS 1.2/1.3 HTTPS (`SECURE_SSL_REDIRECT`, HSTS) |
| `COM_SNAPSHOT` (`ProjectSource.SourceKind`) & `PLANSWIFT_COM` (`ExternalIntegration.kind` comment) | Legacy COM snapshot source markers | Removed via `project_sources.0003` migration & model cleanup (`com_snapshot.json` kept strictly as an offline regression oracle fixture) | Uploaded `.SwiftJob.zip` / `.zip` / `.xml` / `.dxf` / `.ifc` sources |
| Server-path API ingestion (`POST /api/v1/project-sources/`, `PLANSWIFT_DEFAULT_SOURCE_PATH`, `./sources` host mount) | Allowed probing configured host paths via API & mounted host `./sources` in Compose | Disabled `ProjectSourceViewSet.create` (`405`), removed "Import Pre-Staged Server Archive" UI card, removed `PLANSWIFT_DEFAULT_SOURCE_PATH` & `./sources` Compose mounts | Browser multipart streaming `POST /api/v1/project-sources/upload/` into private `uploads_data` volume |
| Public self-signup (`RegisterView`, `registerSchema`, `/login` Register tab) | Open account creation & default unprivileged viewer role | Disabled `POST /api/v1/auth/register/` (`403` + audit event), removed frontend signup tab & `registerSchema` | Admin-only user creation in `/users` (`/api/v1/auth/users/`) |
| Legacy 7-role choices (`owner`, `reviewer`, `viewer`, `estimation_only`, `connector_agent`) | Complex overlapping RBAC & permission leakage (`is_staff` bypass) | Consolidated via non-destructive migration (`organizations.0003` + `0004`) to `admin`, `estimator`, `user` | Centralized `backend/apps/permissions/rbac.py` & `frontend/src/lib/rbac.ts` |
| `frontend/tsconfig.tsbuildinfo` & hardcoded dev seed password | Untracked TS build cache; hardcoded default admin secret in `seed_demo_and_extract.py` | Deleted `.tsbuildinfo`, ignored in `.gitignore`, gated `seed_demo_and_extract.py` strictly behind `DEBUG=True` + explicit password arg | Clean source tree & explicit env/CLI secrets |

---

## 3. Retained Production Dependencies Audit

- **Extraction Engine (`extraction_engine/pyproject.toml`)**: `pydantic`, `lxml`, `openpyxl`, `ezdxf`, `ifcopenshell`, `psutil`.
- **Django Backend (`backend/requirements.txt`)**: `Django`, `djangorestframework`, `djangorestframework-simplejwt`, `django-cors-headers`, `django-filter`, `drf-spectacular`, `pydantic`, `lxml`, `celery`, `redis`, `psycopg[binary]`, `openpyxl`, `reportlab`, `httpx`, `whitenoise`, `gunicorn`, `ezdxf`, `ifcopenshell`, `psutil`.
- **Dev/Test Only (`backend/requirements-dev.txt`)**: `pytest`, `pytest-django` (excluded from production Docker images).
- **Frontend (`frontend/package.json`)**: `next`, `react`, `react-dom`, `lucide-react`, `zod` (prod); `vitest`, `@testing-library/react`, `typescript`, `tailwindcss` (dev).

---

## 4. Prohibited Dependency & Security Verification

AST static analysis across every `.py` file under `extraction_engine/` and `backend/` (enforced by `test_standalone_security_no_com_no_ocr_no_eval_across_codebase` in `extraction_engine/tests/test_standalone_regression_and_accuracy.py`) confirms zero direct imports of COM/Windows libs (`winreg`, `win32com`, `pythoncom`, `comtypes`), zero OCR/CV libs (`pytesseract`, `easyocr`, `cv2`, `PIL`, `pdf2image`, `pypdf`, `fitz`), and zero `eval()`/`exec()` calls.
