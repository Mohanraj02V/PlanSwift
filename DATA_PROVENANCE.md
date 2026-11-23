# DATA_PROVENANCE.md — Mandatory Data Provenance & Audit Contract

Every extracted object, property, measurement, geometry point, formula, estimation result, and AI answer carries one of the 8 mandatory provenance statuses:

| Status | Meaning | Example in Vortexen Estimator |
|---|---|---|
| `original` | Read directly from native PlanSwift archive / `XMLData.XML` | Object GUIDs, class names, raw property values, `DigitizerData` `(X, Y)` coordinates, `[Takeoff]` formulas |
| `api_extracted` | Retrieved live via Windows PlanSwift COM interface | `VortexenPlanSwiftConnector.exe` snapshot objects & properties |
| `normalized` | Deterministically unit/type normalized without overwriting raw value | `units="M"` -> `normalized_unit="m"`, `CheckBox="True"` -> `true` |
| `computed_by_planswift` | Evaluated by PlanSwift's own calculation engine via COM | `GetPropertyResultAsString("Qty", "")` returned via `/api/v1/planswift/ingest/` |
| `derived` | Computed deterministically by Vortexen from native geometry/relational records | Sum of `DigitizerData` `<Point>` count (`286` on `Duct 350x200mm`), bounding boxes, Shoelace polygon area |
| `ai_inferred` | Suggested or interpreted by an AI model beyond direct source storage | Any future AI-suggested classification (`inference_used: true`) |
| `unresolved` | Cannot be deterministically evaluated offline without live PlanSwift runtime or calibration | `[!PageWidth]`, `[\Settings\...]`, `78` PascalScript `Expression="-1"` blocks, uncalibrated `normalized_x` |
| `unsupported` | Native PlanSwift object class not yet mapped in `KNOWN_CLASS_BEHAVIORS` | Generic fallback preserves unknown `<Item>` and all its properties cleanly |

## Invariants Enforced Across Code & Tests

- Raw source fields (`raw_value`, `raw_formula`, `raw_x`, `raw_y`, `raw_digitizer_xml`) are **never** overwritten by normalized, derived, or AI values.
- AI responses are validated against `StructuredAIResponseContract` and record `source_objects` citations alongside `data_status` and `inference_used`.
- `ProvenanceRecord` rows and append-only `AuditLog` records preserve full lineage per `ExtractionRun` and `ProjectVersion`.
