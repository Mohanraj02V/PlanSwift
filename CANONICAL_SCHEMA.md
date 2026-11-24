# Canonical Data Schema & Provenance (`CANONICAL_SCHEMA.md`)

## 1. Schema Metadata

- **Current Version**: `"1.0"` (`CanonicalProject.schema_version`)
- **Engine Metadata**: `{"name": "Standalone PlanSwift ZIP Extraction Engine", "version": "2.0.0"}`
- **Source of Truth**: `extraction_engine/core/extraction_result.py` and mirrored PostgreSQL/SQLite tables in `backend/apps/*`.

---

## 2. Provenance Taxonomy (`ProvenanceStatus`)

Every object, property, measurement, geometry feature, and formula carries an explicit provenance classification that prevents mixing native source facts with derived values or inferences:

| Status | Meaning | Where Applied |
| :--- | :--- | :--- |
| **`native`** | Extracted verbatim from native PlanSwift XML attributes or literal `<Property>` text. | `ProjectObject`, `CanonicalProperty`, raw `(X, Y)` `CanonicalPoint`, `CanonicalPage`, `CanonicalRelationship`, literal `EvalResult`. |
| **`calculated`** | Computed deterministically by the standalone AST formula engine from native/reconstructed inputs. | Evaluated `CanonicalFormula` rows and `CanonicalMeasurement` (`Qty`, `Wall Area`, `Material` BOM items, `CalculatedValue`). |
| **`reconstructed`** | Computed mathematically from raw native `DigitizerData` coordinates + explicit page `ScaleX`/`ScaleY`. | `CanonicalGeometry.calibrated_length`/`calibrated_area`, `MeasurementSection.derived_quantity`, DigitizerData geometry measurements, `[!Point Count]`, `[!Area]`, `[!Linear Total]`. |
| **`inferred`** | Structurally inferred when not explicitly stated. | Reserved for explicit structural inference metadata (not fabricated metrics). |
| **`ai_generated`** | Produced by AI Estimation / RAG assistant downstream (strictly forbidden from overwriting native/calculated records). | Downstream `AIQueryResponse` / AI explanations. |
| **`unresolved`** | Could not be computed honestly from ZIP XML alone; paired with structured `calculation_reason`. | `[!PageWidth]`/`[!PageHeight]`, missing `[\Settings\...]`, missing parent/job variables, circular dependencies, division by zero, missing page scale. |
| **`unsupported`** | Unknown PlanSwift object class or custom imperative PascalScript (`Expression="-1"`). | Custom `Class` objects (`unsupported_objects`), non-template PascalScripts (`unsupported_pascal_script`). |

---

## 3. Canonical Entities

### Core Hierarchy
- **`Project`** (`CanonicalProject`): `native_guid`, `name`, `native_project_version`, `measurement_system`, `xml_encoding`, `excel_workbook_connected`, `deterministic_digest_sha256`, `discovered_classes`, `unsupported_classes`, `unsupported_objects`.
- **`Pages`** (`CanonicalPage`): `native_guid`, `name`, `page_type`, `order_index`, `image_property_guid`, `tiff_archive_path`, `tiff_size_bytes`, `scale_units`, `scale_x`, `scale_y`, `numeric_scale_factor`, `section_count`.
- **`Objects`** (`CanonicalObject`): `native_guid`, `native_class`, `native_type`, `name`, `parent_guid`, `root_path`, `depth`, `order_index`, `child_guids`, `is_known_class`, `is_measurement_section`, `is_page`, `page_guid`, `group_id`, `division`, `cost_code`, `raw_attributes`, `provenance`.
- **`Properties`** (`CanonicalProperty`): Keyed by `(project_object, native_property_guid)` so empty `Name=""` properties (`16` in `project 4`) never collide. Preserves `raw_value`, `parsed_value`, `normalized_value`, `units`, `input_units`, `group`, `parse_formula`, `expression_flag`, `image_data_sha256`.

### Measurements, Geometry, Formulas & Relationships
- **`Geometry`** (`CanonicalGeometry` + `CanonicalPoint`): Keeps raw pixels (`x`, `y`, `raw_x`, `raw_y`, `derived_polyline_length`, `derived_polygon_area`) separate from scaled calibration (`scale_x`, `scale_y`, `scale_unit`, `is_calibrated`, `calibrated_length`, `calibrated_area`, `calibrated_unit`, `normalized_length_m`, `normalized_area_m2`).
- **`Formulas & Calculations`** (`CanonicalFormula`): Stores `raw_expression`, `dependencies`, `has_circular_dependency`, `circular_path`, `evaluation_status`, `calculated_value`, `calculated_numeric`, `calculation_unit`, `calculation_reason`, `calculation_inputs`.
- **`Measurements`** (`CanonicalMeasurement`): Stores `raw_formula` & `native_stored_value` alongside separate `reconstructed_quantity`, `calculated_quantity`, `normalized_quantity`, `normalized_unit`, `calculation_inputs`, `status`.
- **`Relationships`** (`CanonicalRelationship`): Typed edges (`parent_child`, `page_reference`, `page_order`, `group_member`, `assembly_component`, `swift_excel_link`, `cross_reference`).

---

## 4. Versioned JSON Export Structure (`1.0`)

Generated identically by `extraction_engine/exporters/json_exporter.py` (`build_structured_project_export`) and `GET /api/v1/exports/<project_id>/?export_format=json`:

```json
{
  "schema_version": "1.0",
  "engine": { "name": "Standalone PlanSwift ZIP Extraction Engine", "version": "2.0.0" },
  "project": { "id": "...", "name": "...", "native_version": "...", "measurement_system": "..." },
  "extraction": { "status": "completed", "source_filename": "...", "source_hash": "...", "warnings": [], "unsupported_objects": [] },
  "pages": [],
  "takeoffs": [],
  "objects": [],
  "measurements": [],
  "geometry": [],
  "formulas": [],
  "calculations": [],
  "relationships": [],
  "validation": []
}
```
Internal server filesystem paths (`source_path`) are excluded from all API and JSON export payloads.
