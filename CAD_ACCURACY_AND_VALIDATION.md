# CAD & BIM Extraction Accuracy, Provenance & Validation

Vortexen Estimator enforces strict separation between native file data, deterministic unit normalization, geometric calculation, rule-based inference, and unsupported/unresolvable records across PlanSwift, DXF, and IFC.

---

## 1. Provenance & Anti-Fabrication Rules

1. **Zero Fabricated Dimensions or Units**:
   - DXF files with `$INSUNITS == 0` preserve `source_units = "unitless"` and `unit_to_meter_factor = None`. Raw entity coordinates are preserved verbatim without guessing millimeters/meters/feet.
   - IFC files lacking unit definitions preserve raw quantities cleanly and set `unit_to_meter_factor = None`.
   - Spatial or unrepresented IFC entities record `geometry_summary.status = "no_representation"` rather than zero-filled bounding boxes.
2. **Native Values Never Overwritten**:
   - **DXF `DIMENSION`**: Preserves native `actual_measurement`, raw text string, `has_text_override` / `text_override`, and independent `geometry_measured` (`defpoint2`–`defpoint3` calculation) side by side.
   - **IFC `IfcElementQuantity` (`Qto_*`)**: Preserved inside `quantity_sets` with `provenance = "native"` and never mutated when `geometry_summary` (`provenance = "calculated"`) runs.
3. **Rule-Based Inference Tagged Explicitly**:
   - Optional DXF layer-name classification (`Wall`, `Door`, `HVAC Duct`, etc.) is stored in `CADClassificationInfo` with `classification_provenance = "inferred"`, while `native_type` remains untouched (`provenance = "native"`).
4. **Unsupported Entity & Schema Integrity**:
   - Unrecognized or unsupported DXF entities (`DXFTagStorage`, opaque custom vendor types) are retained in `cad_entities` with `is_supported = False` and in `project.unsupported_objects` with original handle/raw attributes.
   - IFC files declaring schemas outside `ifcopenshell.ifcopenshell_wrapper.schema_names()` (`['HEADER_SECTION_SCHEMA', 'IFC2X3', 'IFC4', 'IFC4X3_ADD2']`) are rejected explicitly with `SecurityValidationError` rather than silently coerced.
   - Non-watertight 3D meshes (`is_watertight = False`) return `surface_area` and bounding box without fabricating an invalid tetrahedral `volume` (`volume = None`).

---

## 2. Deterministic Digests & Validator Scorecards

- **DXF Validator (`validate_dxf_project`)**: Audits DXF header/units completeness, layer/block extraction counts, document-scoped `dxf:<sha12>:<handle>` uniqueness, double-precision geometry metrics, `DIMENSION` text override detection, XREF isolation (`loaded=False`), and unsupported class tracking.
- **IFC Validator (`validate_ifc_project`)**: Audits schema compilation support (`IFC2X3`, `IFC4`, `IFC4X3_ADD2`), STEP ID & `GlobalId` uniqueness, spatial containment hierarchy completeness, `IfcPropertySet` / native `Qto_*` totals, and optional `geom.iterator` calculation pass rates (`skipped_property_only` vs `calculated`).
- **Deterministic SHA-256 Digest (`compute_cad_deterministic_digest`)**: Covers source SHA-256 hash, library version, extraction options (`ifc_extract_geometry`, `dxf_resolve_inserts`, etc.), and canonical extracted metrics. Option toggles produce distinct digests so idempotent re-extraction never serves a stale property-only cache when 3D geometry is requested.

---

## 3. Automated Test Coverage Summary

| Test Suite | Scope Verified | Result |
|---|---|---|
| `extraction_engine/tests/` + `backend/tests/` (66 tests) | Full PlanSwift golden `project 4` (`1,461` objects, `28,355` properties, `324` pages, `1,052` sections, `4,868` geometry points, `100%` accuracy), `Sample Project`, formula evaluator, ZIP/XXE/AST security (`0` vision/OCR/eval imports), 12 DXF suites (ASCII R12–R2018, Binary DXF, layers, blocks, nested `INSERT`, OCS/WCS, bulges/curves, dimensions, units, XREF security, unsupported, determinism), 12 IFC suites (`IFC2X3`, `IFC4`, `IFC4X3_ADD2`, unsupported schema rejection, objects, spatial hierarchy, Psets/materials/classifications, `Qto_*` separation, relationships/voids/fills, nested placements & cycle guard, non-watertight/empty reps, determinism), 3 performance suites, and Django REST/RBAC/E2E tests | **66 / 66 passed** |
| Post-final-edit regression, performance, API & PlanSwift verification | `manage.py check` (`0` issues), `manage.py migrate --check` (up to date), `test_planswift_regression.py`, `test_standalone_regression_and_accuracy.py`, `performance/`, `test_cad_bim_api_and_e2e.py`, plus DXF & IFC CLI `inspect` / `validate` / `export` smoke checks | **Passed** (`11 / 11` targeted pytest cases + CLI checks) |
| Frontend (`frontend/`) | `npm run typecheck`, `npm test` (Vitest component tests), `npm run build` (`next build`, 22 routes including `/cad-bim` and `/extraction`) | **5 / 5 tests, 22 / 22 routes built** |
