# DXF Extraction Design & Behavior (`ezdxf`)

The DXF extraction adapter (`extraction_engine/adapters/dxf/`) uses **`ezdxf 1.4.5`** with Cython C-extensions enabled (`ezdxf.options.use_c_ext == True`) to extract both **ASCII DXF** and **Binary DXF** drawings without AutoCAD, screenshots, OCR, or vision models.

---

## Supported Formats, Versions & Units

- **Containers**:
  - ASCII DXF (`dxf_ascii`) verified structurally via DXF group-code/value header pairs (`999`, `0 / SECTION`).
  - Binary DXF (`dxf_binary`) verified via the `AutoCAD Binary DXF\r\n\x1a\x00` 22-byte magic signature.
- **Versions Verified in Automated Tests**: `AC1009` (`R12`), `AC1015` (`R2000`), `AC1024` (`R2010`), and `AC1032` (`R2018`). Syntax/encoding anomalies fall back automatically to `ezdxf.recover.readfile()` with auditor warnings preserved.
- **Units & Zero Fabrication**:
  - Reads `$INSUNITS` (codes `0..21`, e.g., `1=in`, `2=ft`, `4=mm`, `5=cm`, `6=m`, `21=us_ft`) and `$MEASUREMENT`.
  - When `$INSUNITS == 0` (unitless) or missing, `source_units="unitless"` and `unit_to_meter_factor=None` — raw DXF coordinates are preserved without inventing metric conversions.

---

## Module Breakdown (`extraction_engine/adapters/dxf/`)

| Module | Responsibility |
|---|---|
| `dxf_document_reader.py` | Signature/size bounds check (`dxf_max_file_bytes`), SHA-256 manifest, single `ezdxf.readfile()` / `recover.readfile()` open, header/unit parsing. |
| `dxf_layer_extractor.py` | Extracts full `LAYER` table (`color`, `true_color`, `linetype`, `lineweight`, `is_on`, `is_frozen`, `is_locked`, `is_plottable`, entity counts) cleanly sorted. |
| `dxf_block_extractor.py` | Extracts `BLOCK` definitions (`base_point`, `is_layout`, `is_anonymous`, nested block names, `is_xref`, `xref_path`) separately from `INSERT` references. External `XREF` paths are stored strictly as untrusted metadata (`loaded=False`). |
| `dxf_geometry_extractor.py` | Double-precision geometry metrics (`LINE`, `LWPOLYLINE`/`POLYLINE` with exact circular bulge arc-length and signed bulge area, `CIRCLE`, `ARC`, `ELLIPSE`, `SPLINE` via `ezdxf.math`, `HATCH`, `SOLID`/`3DFACE`/`TRACE`, `MESH`, `TEXT`/`MTEXT`, `RAY`/`XLINE`, `REGION`/`3DSOLID`/`BODY`), OCS-to-WCS transforms via `entity.ocs()`, and nested `INSERT` `Matrix44` composition. |
| `dxf_dimension_extractor.py` | Separates `DIMENSION` native `actual_measurement`, independent geometric `defpoint2`/`defpoint3` distance verification (`geometry_measured`, `discrepancy`), and explicit user text overrides (`text != ""` and `"<>" not in text`). |
| `dxf_entity_extractor.py` | Traverses Modelspace, Paperspace layouts, and nested `INSERT` block expansions (up to `dxf_max_block_depth=32` with cycle protection), assigning document-scoped keys (`dxf:<sha12>:<handle>`) and tagging optional rule-based layer classifications strictly as `provenance="inferred"`. |
| `dxf_validator.py` | Generates `ValidationSummary` covering header/units, layers/blocks, handle uniqueness, geometry accuracy, dimension override audits, XREF security isolation, and unsupported entity tracking. |
| `dxf_adapter.py` | Orchestrates inspection, parsing, extraction, and validation into `CanonicalProject` + `CanonicalCADDocument`. |

---

## Accuracy, Overrides & Unsupported Entities

1. **Nested `INSERT` & OCS/WCS Precision**: Block geometry inside `INSERT` entities composes parent `Matrix44` transforms (`insert.matrix44()`) recursively with depth and cycle guards, keeping both `native_coordinates` and transformed `world_coordinates`.
2. **Dimension Override Separation**: Manual override strings such as `"FORCE 999mm"` do not overwrite `actual_measurement` or `geometry_measured`; all three (`actual_measurement`, `geometry_measured`, `text_override`) remain independently inspectable.
3. **Unsupported Entities**: Unregistered or unsupported vendor/custom entities (`DXFTagStorage`, `ACIS` opaque solids without mesh breakdown, etc.) are **never discarded** — they are stored with `is_supported=False`, `provenance="unsupported"`, raw DXF handle/attributes, and an entry in `project.unsupported_objects`.

---

## `ezdxf.addons.iterdxf` Evaluation (Measured Evidence)

We benchmarked `ezdxf.addons.iterdxf.opendxf()` on the 15,000-entity ASCII DXF fixture (`2.26 MB`):
- **`iterdxf` modelspace stream only**: **`2.2475s`** wall-clock across 15,000 raw modelspace entities.
- **Full `ezdxf.readfile()` open & parse (`open_and_parse_s`)**: **`1.1819s`** wall-clock (with `use_c_ext=True`); complete canonical extraction + WCS geometry + validation + digest: **`8.3760s`** median.
- **Architectural conclusion**: `iterdxf` is a streaming reader that only iterates entity streams cleanly without constructing full `HEADER` (`$INSUNITS`, `$ACADVER`), `TABLES` (`LAYER`), `BLOCKS` definitions (required for resolving `INSERT` transforms), or cross-entity indexing. Therefore **`iterdxf` was NOT chosen as the default adapter**. Single-open `ezdxf.readfile()` preserves 100% of headers, layers, block definitions, and Paperspace layouts with faster parse speed (`1.18s` vs `2.25s`) under `use_c_ext=True`.
