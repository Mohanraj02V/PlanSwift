# Native Geometry & Measurement Engine (`GEOMETRY_ENGINE.md`)

## 1. Zero-Image Native Geometry Principle

All geometry and spatial metrics are extracted exclusively from XML `DigitizerData` properties inside `XMLData.XML` / `Data.xml`. The engine never decodes TIFFs/PDFs, runs OCR, or uses computer vision.

---

## 2. Coordinate Parsing & Security (`extraction_engine/parsers/geometry_parser.py`)

1. Rejects any `<!DOCTYPE` or `<!ENTITY` payload with `SecurityValidationError` prior to parsing.
2. Parses `<Points><Point X="..." Y="..." PointType="..."/></Points>` with `lxml.etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False, huge_tree=False)`.
3. Validates every point coordinate (`float` parse + `math.isfinite`) — skipping invalid/`NaN`/`Inf` pairs with explicit `validation_warnings` rather than aborting extraction.
4. Preserves raw string (`raw_x`, `raw_y`) and raw float (`x`, `y`) pixel coordinates in `planswift_page_digitizer_raw` units alongside bounding boxes (`bbox_min_x..bbox_max_y`), raw polyline length (`derived_polyline_length`), and raw shoelace polygon area (`derived_polygon_area`).

### Geometry Type Classification
- `Area Section`, `Volume Section`, `Perimeter Section` → `Polygon` (closed perimeter + shoelace area)
- `Segment Section`, `Dimension` → `Segment` (segment-pair Euclidean sum `(0,1), (2,3)...`)
- `Linear Section`, `Markup` → `Segment` (2 points) or `Polyline` (3+ points)
- `Count Section`, `Annotation`, `Note`, `PageLegend` → `PointCollection`

---

## 3. Page Scale Calibration (`extraction_engine/normalizers/geometry_normalizer.py`)

Inspected native PlanSwift `Page` items (`Sample Project.SwiftJob`) verify that `ScaleX` and `ScaleY` represent **pixels per 1 `Scale Units`**:

$$\text{calibrated\_x}_i = \frac{x_i}{\text{ScaleX}}, \qquad \text{calibrated\_y}_i = \frac{y_i}{\text{ScaleY}}$$

$$\text{Calibrated Length} = \sum_{i} \sqrt{\left(\frac{x_{i+1} - x_i}{\text{ScaleX}}\right)^2 + \left(\frac{y_{i+1} - y_i}{\text{ScaleY}}\right)^2}$$

$$\text{Calibrated Area} = \frac{\left|\sum_{i=0}^{n-1} (x_i y_{i+1} - x_{i+1} y_i)\right|}{2 \cdot \text{ScaleX} \cdot \text{ScaleY}}$$

### Real-Project Verification (`Sample Project.SwiftJob`)
- **Page `Level 01 Floor Plan - A101`**: `AutoScaled = 1/8" = 1' 0"`, `ScaleX = 18.75`, `ScaleY = 18.75`, `Scale Units = FT`.
- **`Conference Room` (Area, Page calibrated `ScaleX=37.5 px/FT`)**:
  - Raw XML polygon area: `703,656.96 px²` (`derived_polygon_area`, preserved)
  - Calibrated area: `703,656.96 / 37.5² = 500.378283 SQ FT` (`calibrated_area`, provenance=`reconstructed`)
  - SI metric normalized: `46.486668 m²` (`normalized_area_m2`)
- **`Exterior Walls` (Linear, Page calibrated `ScaleX=37.5 px/FT`)**:
  - Raw XML polyline length: `9,935.560826 px` (`derived_polyline_length`, preserved)
  - Calibrated length: `9,935.560826 / 37.5 = 264.948289 FT` (`calibrated_length`, provenance=`reconstructed`)
- **`project 4.SwiftJob.zip` (Uncalibrated Pages)**:
  - All 324 pages lack positive `ScaleX`/`ScaleY` in XML → engine preserves raw coordinates (`4,868` points across `1,052` sections), sets `is_calibrated = False`, and refuses to fabricate scale or calibrated linear/area values.

---

## 4. Unit Normalization (`extraction_engine/normalizers/unit_normalizer.py`)

Converts calibrated measurements across `FT`, `IN`, `YD`, `M`, `CM`, `MM` into canonical SI meters (`m`) and square meters (`m^2`) while keeping native `unit` and `input_units` strings unchanged.
