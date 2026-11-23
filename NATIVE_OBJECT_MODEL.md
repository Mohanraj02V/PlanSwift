# NATIVE_OBJECT_MODEL.md — Discovered PlanSwift Native Object Model

## 1. Item Class Taxonomy

`extraction_engine.core.extraction_registry.KNOWN_CLASS_BEHAVIORS` models standard PlanSwift classes while assigning any unrecognized class to `ClassBehavior(role="custom", known=False)` with `provenance="unsupported"` so unknown objects are never discarded.

### Classes Confirmed in `project 4.SwiftJob.zip`

| Native `Class` | `Type` Property | Count | Role | Geometry Representation |
|---|---|---:|---|---|
| `Item` | `Job` | 1 | Root job metadata (`project 4`) | None |
| `Item` | *(empty)* | 3 | `Links`, `RememberValues`, `AutoLists` containers | None |
| `Folder` | `Folder` | 2 | `Pages`, `Takeoff` hierarchy folders | None |
| `Page` | `.TIFF Page` | 324 | Drawing page reference + `Image` property GUID -> `.tiff` | None (no raster decoding) |
| `Count` | `Count` | 78 | Count takeoff items (ducts, pipes, cable trays, etc.) | Aggregates child `Count Section`s |
| `Segment` | `Segment` | 1 | Segment takeoff item (`New Segment`) | Aggregates child sections (`0` in sample) |
| `Count Section` | `Count Section` | 1,052 | Per-page digitized count instance | Embedded `DigitizerData` `<Points>` XML |

### Additional Classes Supported Generically by `extraction_engine`
- `Linear` / `Linear Section` (Polyline length)
- `Segment Section` (2-point segment length)
- `Area` / `Area Section`, `Perimeter` / `Perimeter Section`, `Volume` / `Volume Section` (Polygon Shoelace area + perimeter)
- `Assembly`, `Part`, `Component` (Parent assembly -> child components)
- `Annotation`, `Markup`, `Note`, `Dimension`

---

## 2. Property Model (`28,355` Properties Across `240` Distinct Names)

- **9 Property Classes**: `Text`, `Number`, `CheckBox`, `Type`, `Image`, `Color`, `Memo`, `Slider`, `Large Image`.
- **11 Property Groups**: `Fill`, `Item`, `Audit Trail`, `Other`, `Work Breakdown Structure`, `Symbol Properties`, `Estimating`, `Size`, `Takeoff Data`, `Swift Excel`, `Videos`.
- **34 XML Attributes Preserved**: Every `<Property>` retains all attributes inside `CanonicalProperty.attributes` (`ObjectProperty.attributes_json`), including `OrderIndex`, `DecimalPlaces`, `ParseFormula`, `units`, `inputunits`, `Expression`, `ListPropertiesToSet`, `TreeList`, `Min`, `Max`, etc.
- **16 Empty-Name Properties (`Name=""`)**: Preserved cleanly via `native_property_guid`.
- **Dynamic Per-Page Sort Keys**: Properties matching `OrderIndex_{PAGE-GUID}` are tagged `is_dynamic_page_order=True` and emitted as `page_order` graph relationships.
- **Binary Icon Metadata**: `ImageData` attributes (63 properties) store byte length + SHA-256 hash without stuffing binary blobs into text search or AI contexts.
- **SwiftExcel Tokens**: `53` `Count` items contain `SwiftExcelLinkedItem="True"` and a `Memo` token parsed into `CanonicalDenotation(kind="swift_excel_token")`.

---

## 3. Measurements vs. Template Defaults

On `Count` objects:
- `Qty = "[Takeoff]"` is preserved verbatim as `raw_formula`.
- The sum of `<Point>` elements across child `Count Section`s is stored separately as `derived_quantity` with `status="derived"` (or `status="computed_by_planswift"` once supplied via COM).
- Default template values `Length="1"` and `Width="1"` (`units="[ScaleUnits]"`) on `Count` objects are explicitly flagged `is_default_template_value=True` so estimators and AI agents never mistake them for measured pipe/duct lengths.
