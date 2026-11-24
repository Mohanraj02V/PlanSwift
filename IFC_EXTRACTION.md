# IFC Extraction Design & Behavior (`IfcOpenShell`)

The IFC extraction adapter (`extraction_engine/adapters/ifc/`) uses **`IfcOpenShell 0.9.0.post1`** to extract ISO-10303-21 STEP BIM models without desktop BIM software, screenshots, OCR, or vision models.

---

## Verified Schema Support

Queried directly from `ifcopenshell.ifcopenshell_wrapper.schema_names()` in the installed `0.9.0.post1` build:

- **Supported**: `IFC2X3`, `IFC4`, `IFC4X3_ADD2` (reported by `IfcOpenShell` as `IFC4X3` on `model.schema` and `IFC4X3_ADD2` on `model.schema_identifier`)
- **Not Compiled in Installed Wheel**: `IFC4X1` (`IFC4.1`), `IFC4X2` (`IFC4.2`), or custom schemas outside `schema_names()`. When encountered in `FILE_SCHEMA(...)`, `open_ifc_model()` explicitly raises `SecurityValidationError` listing the genuinely supported schemas rather than guessing or silently coercing schemas.

---

## Module Breakdown (`extraction_engine/adapters/ifc/`)

| Module | Responsibility |
|---|---|
| `ifc_document_reader.py` | Header schema probe, signature & file-size guard (`ifc_max_file_bytes`), SHA-256 manifest, single `ifcopenshell.open()`, unit extraction (`ifcopenshell.util.unit`). |
| `ifc_relationship_extractor.py` | Extracts `IfcRelAggregates`, `IfcRelContainedInSpatialStructure`, `IfcRelDefinesByProperties`, `IfcRelDefinesByType`, `IfcRelAssociatesMaterial`, `IfcRelAssociatesClassification`, `IfcRelVoidsElement`, and `IfcRelFillsElement` using STEP ID indexing. |
| `ifc_property_extractor.py` | Extracts direct `IfcPropertySet` attributes and inherited type-level Psets from `IfcTypeObject` (`is_type_inherited=True`), keeping types unambiguous. |
| `ifc_quantity_extractor.py` | Extracts native `IfcElementQuantity` (`Qto_*`) items (`IfcQuantityLength`, `IfcQuantityArea`, `IfcQuantityVolume`, `IfcQuantityWeight`, `IfcQuantityCount`, `IfcQuantityTime`) preserving raw value, raw unit, formula string, and SI-normalized meters / m² / m³ when unit factor is known (`provenance="native"`). |
| `ifc_geometry_extractor.py` | Opt-in (`ifc_extract_geometry=True`) single-pass `ifcopenshell.geom.iterator` across only elements carrying `Representation`, computing double-precision `bbox_min`, `bbox_max`, `dimensions_xyz`, `surface_area`, directed-edge watertight check, and signed tetrahedral `volume` (`provenance="calculated"`). |
| `ifc_object_extractor.py` | Collects `IfcProject`, `IfcContext` (guarded for `IFC2X3` where `IfcContext` does not exist in schema), and `IfcObject` deterministically sorted by STEP ID; handles missing/duplicate `GlobalId` safely; computes world placements via `ifcopenshell.util.placement.get_local_placement`. |
| `ifc_validator.py` | Produces `ValidationSummary` across schema & units, STEP/GlobalId uniqueness, spatial hierarchy coverage, Pset/Qto completeness, and optional geometry pass rate. |
| `ifc_adapter.py` | Orchestrates inspection, model open, extraction, and validation into `CanonicalProject` + `CanonicalCADDocument`. |

---

## Strict Separation of Native vs. Calculated vs. Missing Data

1. **Native Quantities (`Qto_*`) vs. Calculated Geometry**:
   - `Qto_WallBaseQuantities` or custom `IfcElementQuantity` values live inside `element.quantity_sets` with `provenance="native"`.
   - When 3D tessellation is enabled (`ifc_extract_geometry=True`), computed bounding box, surface area, and watertight volume live inside `element.geometry_summary` with `status="calculated"` and `provenance="calculated"`.
   - Native `Qto_*` values are **never overwritten** by calculated mesh numbers, and calculated numbers are **never promoted** to look like native `Qto_*` values.
   - Because `ifcopenshell.geom` coordinates are returned in SI meters by default (`convert_back_units=False`), `surface_area` is m² and `volume` is m³ regardless of whether the STEP file used `MILLIMETRES`, `METRES`, or `FOOT`.

2. **Schema & Object Quirks Handled Safely**:
   - **IFC4 vs. IFC2X3**: In IFC4, `IfcProject` inherits from `IfcContext` rather than `IfcObject`; in IFC2X3, `IfcContext` does not exist at all. `ifc_object_extractor.py` queries `IfcProject`, guards `IfcContext` against `RuntimeError`, and merges `IfcObject` deduplicated by STEP ID.
   - **Duplicate or Missing `GlobalId`**: Preserved without crashing; flagged with explicit warnings and disambiguated via `STEP#<id>` keys while keeping the raw `GlobalId` searchable.
   - **Elements Without Geometry**: Spatial nodes (`IfcProject`, `IfcSite`, `IfcBuilding`, `IfcBuildingStorey`, `IfcSpace`) or unrepresented elements record `geometry_summary.status = "no_representation"` rather than fabricating zero dimensions.
   - **Property-Only Default**: When `ifc_extract_geometry=False`, `geometry_summary.status = "skipped_property_only"` so large IFC models finish quickly when only BIM hierarchy, properties, and `Qto_*` takeoffs are needed.
