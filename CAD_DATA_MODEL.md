# CAD & BIM Canonical Data Model & Schema Extensions

Vortexen Estimator preserves the original PlanSwift schema (`Project`, `ProjectVersion`, `CanonicalObject`, `CanonicalProperty`, `CanonicalMeasurement`, `CanonicalGeometry`, `CanonicalFormula`, `CanonicalRelationship`) untouched and extends it **additively** for DXF and IFC.

---

## 1. Standalone Canonical Pydantic Models (`extraction_engine/core/cad_models.py`)

| Model | Purpose | Key Fields & Identity |
|---|---|---|
| `CanonicalCADDocument` | Top-level CAD/BIM metadata container on `CanonicalProject.cad_document` | `source_format` (`dxf_ascii`, `dxf_binary`, `ifc_step`), `library_name`, `library_version`, `file_version`, `schema_name`, `source_units`, `unit_to_meter_factor`, `header_variables`, `external_references`, `extraction_options`, `stage_timings`, `peak_rss_mb`, `layers`, `blocks`, `cad_entities`, `ifc_elements` |
| `CanonicalCADLayer` | DXF `LAYER` table definition | `layer_id`, `name`, `color`, `true_color`, `linetype`, `lineweight`, `is_on`, `is_frozen`, `is_locked`, `is_plottable`, `entity_count`, `provenance="native"` |
| `CanonicalCADBlock` | DXF `BLOCK` definition separate from `INSERT` placements | `block_id`, `name`, `base_point`, `is_layout`, `is_anonymous`, `is_xref`, `xref_path`, `entity_count`, `nested_block_names`, `provenance="native"` |
| `CADClassificationInfo` | Separates native CAD entity type from rule-based layer hint | `native_type`, `rule_based_category`, `rule_based_discipline`, `user_mapping`, `classification_provenance` (`native` or `inferred`) |
| `CanonicalCADEntity` | DXF entity record with native/WCS separation | `entity_key` (`dxf:<sha12>:<handle>` or nested path), `handle`, `entity_type`, `owner_handle`, `layer`, `layout_name`, `block_name`, `extrusion`, `elevation`, `thickness`, `ocs_applied`, `is_supported`, `native_coordinates`, `world_coordinates`, `geometry_metrics`, `dimension_data`, `classification`, `warnings`, `provenance` |
| `CanonicalIFCPropertySet` | IFC `IfcPropertySet` | `name`, `global_id`, `step_id`, `is_type_inherited`, `properties`, `provenance="native"` |
| `CanonicalIFCQuantityItem` | Individual native quantity inside `Qto_*` | `name`, `quantity_type`, `raw_value`, `raw_unit`, `normalized_value`, `normalized_unit`, `formula`, `provenance="native"` |
| `CanonicalIFCQuantitySet` | IFC `IfcElementQuantity` container | `name`, `global_id`, `step_id`, `quantities`, `provenance="native"` |
| `CanonicalIFCGeometrySummary` | Opt-in 3D geometry metrics | `status` (`skipped_property_only`, `calculated`, `no_representation`, `unsupported`, `failed`), `bbox_min`, `bbox_max`, `dimensions_xyz`, `surface_area`, `volume`, `is_watertight`, `vertex_count`, `face_count`, `unit`, `normalized_surface_area_m2`, `normalized_volume_m3`, `provenance="calculated"` |
| `CanonicalIFCElement` | IFC spatial/product element | `global_id`, `step_id`, `ifc_class`, `name`, `description`, `object_type`, `predefined_type`, `tag`, `spatial_parent_guid`, `storey_name`, `placement_matrix`, `world_origin`, `property_sets`, `quantity_sets`, `materials`, `classifications`, `representations`, `geometry_summary`, `provenance="native"` |

Each CAD entity or IFC element is also projected cleanly into `CanonicalProject.objects`, `CanonicalProject.pages`, `CanonicalProject.relationships`, `CanonicalProject.discovered_classes`, `unsupported_classes`, and `unsupported_objects` so existing downstream project summaries, validation checks, exports, and audit trails work consistently across all three formats.

---

## 2. Additive Django Database Extensions

### New App: `backend/apps/cad_bim/` (`migrations/0001_initial.py`)
- `cad_documents` (`CADDocument`, `OneToOneField` to `projects.ProjectVersion`)
- `cad_layers` (`CADLayer`)
- `cad_blocks` (`CADBlock`)
- `cad_entities` (`CADEntity`, unique per `(cad_document, entity_key)` — respecting that DXF handles are document-scoped, never globally unique)
- `bim_elements` (`BIMElement`, unique per `(cad_document, step_id)`, indexed by `global_id`, `ifc_class`, `storey_name`)

### Additive Columns on Existing Models
- `projects.Project.source_format` (default `"planswift"`, migration `projects/0003`)
- `project_sources.ProjectSource.source_format` + new `SourceType` choices `UPLOADED_DXF`, `UPLOADED_IFC` (migration `project_sources/0002`)
- `extraction.ExtractionRun.peak_rss_mb`, `extraction_options` (migration `extraction/0003`)
- `assemblies.Assembly.Meta.ordering = ["name"]` (migration `assemblies/0002`, deterministic DRF pagination without altering schema columns)

All existing PlanSwift rows and migrations remain untouched.

---

## 3. REST Endpoints (`/api/v1/cad-bim/`)

- `GET /api/v1/cad-bim/documents/` (filterable by `project_version`, `project_version__project`, `source_format`, `schema_name`)
- `GET /api/v1/cad-bim/layers/` (filterable by `cad_document`, `name`)
- `GET /api/v1/cad-bim/blocks/` (filterable by `cad_document`, `name`, `is_xref`)
- `GET /api/v1/cad-bim/entities/` (filterable by `cad_document`, `entity_type`, `layer_name`, `layout_name`, `is_supported`, `provenance`)
- `GET /api/v1/cad-bim/elements/` (filterable by `cad_document`, `ifc_class`, `storey_name`, `global_id`)

All endpoints enforce JWT authentication + organization membership (`IsOrgMember` / `get_user_org_ids`) matching existing PlanSwift endpoints. `GET /api/v1/exports/<project_id>/?export_format=json|csv|xlsx` includes the full `cad_document` hierarchy when present and falls back cleanly for PlanSwift projects.
