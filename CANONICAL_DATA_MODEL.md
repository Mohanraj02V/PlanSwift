# CANONICAL_DATA_MODEL.md — Digital Project Model Specification

All extracted data flows through Pydantic v2 schemas defined in `extraction_engine/core/extraction_result.py` before persistence into Django models.

## 1. Entity Overview

- `CanonicalProject`: Root container (`native_guid`, `name`, `description`, `measurement_system`, `excel_workbook_connected`, `xml_encoding`, `deterministic_digest_sha256`).
- `CanonicalPage`: Drawing sheet record (`native_guid`, `image_property_guid`, `tiff_archive_path`, `tiff_size_bytes`, `scale_units`, `page_width_raw`, `page_height_raw`, `section_count`).
- `CanonicalObject`: Lossless generic node supporting all native PlanSwift classes (`native_guid`, `native_class`, `native_type`, `name`, `parent_guid`, `root_path`, `depth`, `order_index`, `is_known_class`, `provenance`, `raw_attributes`).
- `CanonicalProperty`: Lossless `<Property>` record (`native_property_guid`, `name` including `""`, `property_class`, `raw_value`, `parsed_value`, `normalized_value`, `units`, `normalized_unit`, `attributes`, `provenance`).
- `CanonicalMeasurementSection` & `CanonicalMeasurement`: Strictly separates `raw_formula`, `native_stored_value`, `planswift_computed_quantity`, and `derived_quantity`.
- `CanonicalGeometry` & `CanonicalPoint`: Raw coordinate list `(point_order, raw_x, raw_y, x, y, point_type)` + optional separate normalized coordinates + derived bounding box.
- `CanonicalFormula` & `CanonicalFormulaDependency`: Static expression tokens, PascalScript flag, circular-cycle path, unresolved references, and evaluation status.
- `CanonicalRelationship`: Directed edges (`parent_child`, `page_reference`, `page_order`, `group_member`, `assembly_component`, `swift_excel_link`).
- `CanonicalAssembly` & `CanonicalAssemblyComponent`: Hierarchical assemblies and parts.
- `CanonicalDenotation` & `CanonicalRemark`: Native item numbers, cost codes, SwiftExcel tokens, descriptions, and notes.
- `ProvenanceRecord`, `ValidationSummary`, `ExtractionReport`: Traceability & accuracy evidence.

## 2. Real Example Canonical Object (from `project 4.SwiftJob.zip`)

```json
{
  "source_system": "PlanSwift",
  "project": {
    "native_guid": "{27F9E929-A81C-4ED6-9A44-4B224F5C19ED}",
    "name": "project 4"
  },
  "object": {
    "native_guid": "{1CB26172-81E8-4EA8-A144-805C05A379B7}",
    "native_class": "Count",
    "native_type": "Count",
    "name": "CHR ans CHS 100",
    "parent_guid": "{BA630457-834C-481A-AA57-E33D401C9B04}"
  },
  "measurements": [
    {
      "property_name": "Qty",
      "raw_formula": "[Takeoff]",
      "derived_quantity": 21.0,
      "planswift_computed_quantity": null,
      "unit": "EA",
      "status": "original"
    }
  ],
  "provenance": {
    "source": "native_project_package",
    "status": "original"
  }
}
```
