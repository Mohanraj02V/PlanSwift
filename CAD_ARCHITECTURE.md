# CAD & BIM Extraction Architecture

**Vortexen Estimator** follows a **one application, three independent source extraction paths** architecture:

1. **PlanSwift Path (Preserved Unchanged)**: Native `.SwiftJob` / `.SwiftJob.zip` / `XMLData.XML` streaming adapters (`planswift_package`, `planswift_xml`) and optional Windows COM ingestion (`planswift_com`). Zero changes were made to PlanSwift parsing, formula evaluation, geometry parsing, or canonical outputs.
2. **DXF Path (New Standalone CAD Adapter)**: ASCII and Binary `.dxf` drawings parsed deterministically with **`ezdxf 1.4.5`** (`use_c_ext=True`, Cython-accelerated).
3. **IFC Path (New Standalone BIM Adapter)**: ISO-10303-21 STEP `.ifc` models parsed deterministically with **`IfcOpenShell 0.9.0.post1`**.

No desktop CAD/BIM application (AutoCAD, Revit, PlanSwift Desktop), rasterization, OCR, screenshot rendering, computer vision, or LLM is used in any extraction path.

---

## High-Level Flow

```
Upload / CLI Path
       │
       ▼
extraction_engine/core/format_detector.py  (magic-byte + header signature verification)
       ├── "planswift_package" / "planswift_xml" ──► PlanSwift Package/XML Adapter (unchanged)
       ├── "dxf_ascii" / "dxf_binary"            ──► DXFAdapter (ezdxf)
       └── "ifc_step"                            ──► IFCAdapter (IfcOpenShell)
                                                         │
                                                         ▼
                                            CanonicalProject + optional .cad_document
                                                         │
                                                         ▼
                         Django extraction/services.py -> PostgreSQL/SQLite (additive cad_bim tables)
                                                         │
                                                         ▼
                          DRF API (/api/v1/cad-bim/...) + Exports + Next.js (/cad-bim & /extraction)
```

---

## Core Design Principles

### 1. Signature-Based Format Detection (`format_detector.py`)
`detect_source_format()` inspects up to 8 KiB of binary magic bytes and structural headers before choosing an adapter—never relying on filename extensions alone:
- `AutoCAD Binary DXF\r\n\x1a\x00` → `dxf_binary`
- `PK\x03\x04` (ZIP signature) → `planswift_package`
- `ISO-10303-21;` with `FILE_SCHEMA` / `HEADER;` → `ifc_step`
- `<?xml` / `<Item` → `planswift_xml`
- Clean DXF group-code/value header (`999` comments, `0 / SECTION / 2 / HEADER|...`) → `dxf_ascii`
- Extension/signature mismatches (for example, a `.zip` renamed to `.dxf`, a `.png` renamed to `.ifc`, or empty/binary garbage) raise `UnsupportedFormatError` / `SecurityValidationError`.

### 2. Zero Contamination of PlanSwift
- `extraction_engine/pipeline.py` uses explicit adapter routing (`PlanSwiftPackageAdapter`, `PlanSwiftXMLAdapter`, `DXFAdapter`, `IFCAdapter`).
- PlanSwift parsing (`parsers/`, `calculators/`, `reconciliation/`) was left completely untouched.
- `CanonicalProject` keeps all existing PlanSwift fields identical and adds an optional `cad_document: CanonicalCADDocument | None = None` field, excluded from JSON when `None` (`exclude_none` compatibility) so PlanSwift output JSON and deterministic SHA-256 digests remain byte-identical.

### 3. Additive Backend Persistence & Multi-Tenancy
- New Django app `backend/apps/cad_bim/` provides `CADDocument`, `CADLayer`, `CADBlock`, `CADEntity`, and `BIMElement` with bulk `bulk_create` insertion and option-aware extraction idempotency (`extraction_options` hash check so re-running IFC with `extract_geometry=True` after `False` executes cleanly instead of returning a stale property-only cache hit).
- Existing tenant isolation (`IsOrgMember`, `get_user_org_ids`, and `cad_document` added to `backend/apps/permissions/rbac.py`) enforces organization scoping on `/api/v1/cad-bim/documents/`, `/layers/`, `/blocks/`, `/entities/`, `/elements/`, and `/api/v1/exports/<project_id>/`.

### 4. Bounded Concurrency & Production Runtime Safety
- **IFC Geometry Opt-In**: Defaults to `ifc_extract_geometry=False` (property, spatial hierarchy, relationship, and native `Qto_*` quantity mode). Heavy 3D tessellation via `ifcopenshell.geom.iterator` only runs when explicitly requested (`extract_geometry=True` in API/UI or `--extract-geometry` in `python -m extraction_engine.cli`).
- **Thread Bounds**: `IFC_GEOMETRY_THREADS` is hard-bounded to `1..4` (configured as `2` in `docker-compose.yml` and `docker-compose.prod.yml` alongside Celery `--concurrency=2`) to prevent CPU/RAM oversubscription under parallel worker processes.
- **No Uncontrolled External I/O**: DXF External References (`XREF`s) and `IMAGE` / `UNDERLAY` links are recorded as metadata only (`external_references_json`), never fetched over network/SMB or traversed on the host filesystem.

---

## Frontend Integration (`frontend/`)

- **Extraction & Upload (`frontend/src/app/extraction/page.tsx`)**: Supports `.SwiftJob`, `.SwiftJob.zip`, `.xml`, `.dxf`, and `.ifc` uploads with an explicit checkbox toggle for **IFC 3D Geometry Extraction** and an immediate **Open CAD / BIM Explorer** link on CAD/BIM runs.
- **CAD / BIM Explorer (`frontend/src/app/cad-bim/page.tsx`)**: Dedicated `/cad-bim` workspace (linked in `AppShell.tsx`) showing summary cards, DXF tabs (*Entities*, *Layers*, *Blocks*, *Dimensions*, *Unsupported*), IFC tabs (*Elements*, *Property Sets*, *Quantity Sets*, *Geometry*, *Unsupported*), provenance/override badges, and `JSON`, `CSV`, and `XLSX` export triggers.
