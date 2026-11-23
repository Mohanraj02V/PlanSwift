# PLANSWIFT_FORMAT_RESEARCH.md — Native Archive, XML, Geometry & COM Investigation

> **Evidence Rule**: Every fact in Sections 1–6 was observed directly via read-only inspection of `C:\Users\mohan\OneDrive\Desktop\Vortexen Estimator\project 4.SwiftJob.zip`. Section 7 documents PlanSwift COM interfaces from official PlanSwift/ConstructConnect developer documentation, clearly distinguishing documented interfaces from locally executed capabilities (since PlanSwift Desktop is not installed on this workstation).

---

## 1. Container & Archive Structure (Confirmed Facts)

| Metric | Observed Value |
|---|---|
| Source Filename | `project 4.SwiftJob.zip` |
| Extension | `.zip` (`.SwiftJob.zip` compound naming) |
| File Size (Compressed) | `582,831,166` bytes (`555.83 MiB`) |
| Magic Bytes (Offset `0..15`) | `50 4B 03 04 14 00 00 00 08 00 00 00 00 00 B9 65` (`PK\x03\x04` — standard PKZIP archive) |
| Total ZIP Entries | `325` |
| Total Uncompressed Size | `1,493,984,282` bytes (`1,424.77 MiB`) |
| Overall Compression Ratio | `2.56x` |
| Path Traversal / Absolute Paths / Symlinks / Executables / Nested Archives | `0` detected |
| Primary Project Data File | `XMLData.XML` (`8,052,152` bytes uncompressed) |
| Embedded Raster Page Files | `324` `.tiff` files under `Pages/<PageName>/{<ImagePropertyGUID>}.tiff` (`1,485,932,130` bytes total) |
| Nested Binary Databases / SQLite / JSON Files | `0` found in archive |

### Key Finding on TIFFs
The `.tiff` files represent 99.46% of the archive bytes (`1.486 GB` of `1.494 GB`), while the entire structured PlanSwift project object tree, properties, formulas, SwiftExcel metadata, and digitizer vector geometry reside inside the single `8.05 MB` `XMLData.XML` file. By streaming only `XMLData.XML` and cataloging `.tiff` headers via ZIP central directory metadata, extraction achieves **100% native project extraction with zero raster decoding and low memory overhead**.

---

## 2. `XMLData.XML` Encoding & Tree Structure (Confirmed Facts)

- **XML Declaration**: `<?xml version="1.0" encoding="Windows-1252" standalone="no"?>`
  - **Crucial**: Must be parsed as raw bytes or `windows-1252` stream so `lxml` respects the declared single-byte encoding cleanly.
- **Maximum XML Element Depth**: `8` (Root `<Item>` at depth 0, properties/children nested via `<Properties><Property .../></Properties>` and `<Items><Item .../></Items>`).
- **Total Elements**:
  - `<Item>`: `1,461`
  - `<Properties>`: `1,461` (1 per `<Item>`)
  - `<Items>`: `1,461` (1 per `<Item>`)
  - `<Property>`: `28,355`

### Root & Depth-1 Containers
- **Depth 0 (Root Job)**:
  - `Class="Item"`, `Name="project 4"`, `GUID="{27F9E929-A81C-4ED6-9A44-4B224F5C19ED}"`
  - Properties include: `Type="Job"`, `Description="Marina hotel"`, `Measurement Type="Metric"`, `ExcelWorkbookConnected="True"`, `Time Stamp="4/1/2026 9:44:..."`, `OrderIndex="9"`.
- **Depth 1 (5 Containers)**:
  1. `Pages` (`Class="Folder"`, `Type="Folder"`, `GUID="{8F381F3A-FDF7-4FE1-A65B-04D2D59C2D13}"`) — `324` direct children.
  2. `Links` (`Class="Item"`, `Type=""`, `GUID="{C9107784-5172-45A9-ABF9-81F454FFDE6F}"`) — `0` children.
  3. `Takeoff` (`Class="Folder"`, `Type="Folder"`, `GUID="{BA630457-834C-481A-AA57-E33D401C9B04}"`) — `79` direct children.
  4. `RememberValues` (`Class="Item"`, `Type=""`, `GUID="{491FB703-A1D5-45AB-87BF-BBE7FAC2EB9D}"`) — `0` children.
  5. `AutoLists` (`Class="Item"`, `Type=""`, `GUID="{249822EE-E4A4-4581-BA05-7210059A6689}"`) — `0` children.

### Complete Object Class & Type Distribution (`1,461` Items)

| Tree Level | XML `Class` | `Type` Property | Count | Role |
|---|---|---|---|---|
| 0 | `Item` | `Job` | `1` | Root PlanSwift job |
| 1 | `Folder` | `Folder` | `2` | `Pages` and `Takeoff` folders |
| 1 | `Item` | *(empty)* | `3` | `Links`, `RememberValues`, `AutoLists` |
| 2 | `Page` | `.TIFF Page` | `324` | Drawing page definitions |
| 2 | `Count` | `Count` | `78` | MEP/drainage/electrical count takeoff items |
| 2 | `Segment` | `Segment` | `1` | Segment takeoff item (`New Segment`, 0 sections) |
| 3 | `Count Section` | `Count Section` | `1,052` | Per-page digitizer point instances under `Count` items |
| **Total** | | | **1,461** | |

---

## 3. Page & TIFF Asset Mapping (Confirmed Facts)

- **Total `Page` items**: `324`
- **TIFF linkage**: Every `Page` has `<Property Class="Large Image" Name="Image" GUID="{...}" Transparent="0" ImageType="TTiffGraphic"/>`.
- **Verification**: All `324 / 324` `Image` property GUIDs match the corresponding ZIP entry `Pages/<PageName>/{<ImagePropertyGUID>}.tiff` (`0` unmatched, `0` orphaned TIFFs).
- **Page Properties Observed**:
  - Present on all `324` pages: `Name`, `Type` (`.TIFF Page`), `OrderIndex`, `GUID`, `Image`, `Created By`, `Time Stamp`.
  - Present on `180` pages: `PageWidth` (`[!PageWidth]`), `PageHeight` (`[!PageHeight]`).
  - Present on `112` pages: `PagesWindow_Expanded` (`True`), `Scale Units` (`M`).
  - **Important Limitation**: No numeric pixel-to-meter `Scale` ratio property is stored inside `XMLData.XML` for these pages. `Scale Units` is `M`, and `PageWidth`/`PageHeight` are system formulas `[!PageWidth]` / `[!PageHeight]`. Therefore, raw `DigitizerData` coordinates are preserved in their native page pixel space and **never** fabricated into meters.

---

## 4. Property Schema, Attributes & Special Patterns (Confirmed Facts)

- **Total `<Property>` elements**: `28,355`
- **Distinct Property `Name` values**: `240`
- **9 Property `Class` types**: `Text` (13,893), `Number` (5,311), `CheckBox` (2,564), `Type` (1,461), `Image` (1,272), `Color` (1,212), `Memo` (1,187), `Slider` (1,131), `Large Image` (324).
- **11 Property `group` categories**: `Fill` (7,181), `Item` (5,186), `Audit Trail` (2,916), `Other` (614), `Work Breakdown Structure` (553), `Symbol Properties` (468), `Estimating` (316), `Size` (234), `Takeoff Data` (197), `Swift Excel` (109), `Videos` (79).
- **34 Distinct `<Property>` XML Attributes**: `Name`, `Class`, `GUID`, `OrderIndex`, `DecimalPlaces`, `ParseFormula`, `group`, `List`, `PluginToExecute`, `inheritaction`, `systemhidden`, `input`, `inputcondition`, `SimpleList`, `systemlocked`, `required`, `Transparent`, `ListType`, `ListPropertiesToSet`, `ListVisibleColumnsInDropdown`, `TreeList`, `Max`, `Min`, `ShowTicks`, `TickFrequency`, `units`, `inputunits`, `ImageType`, `hidden`, `locked`, `RememberValue`, `calculatebefore`, `Expression`, `ImageData`.

### Critical Edge Cases Discovered
1. **16 Empty-Name Properties (`Name=""`)**: Found across 16 `Count` items (e.g., `WP/SP PVC 150mm`, `250 x 50 mm cable tray`), each carrying a unique `GUID`. Storing properties keyed by `(object, name)` would collide or lose data; keying by `(object, native_property_guid)` preserves all 28,355 properties losslessly.
2. **Duplicate Object Names**: Multiple `Count` items are named `"New Count"`, and all 1,052 `Count Section` children are named `"Section"`. Identity must strictly use `GUID`.
3. **Dynamic Page Ordering (`OrderIndex_{PAGE-GUID}`)**: Takeoff items store per-page display sort keys named `OrderIndex_{PAGE-GUID}` (e.g., `OrderIndex_{A496DDA7-D1E4-4BF2-8A4F-A2B35507BE3E}="0"`).
4. **SwiftExcel Integration (`group="Swift Excel"`)**: `53` takeoff items carry `SwiftExcelLinkedItem="True"` plus a `Memo` property named after a `TokenGuid` containing key-value bindings (`Group=`, `TokenGuid=`, `Path=`, `DigitizerType=`, `Color=`, `PropertyName=Qty`, `SheetName=Sheet1`, `Coords=System.Int32[]`).
5. **Embedded `Form Layout` XML**: `1,131` properties store an XML UI form layout inside a `Memo` property (`<?xml version="1.0" encoding="iso-8859-1"?><Items>...</Items>`).
6. **Binary `ImageData` Attribute**: `63` `Image` properties carry an `ImageData` attribute on UI icon properties (`Icon`). We record its presence, length, and SHA-256 without loading raw image payloads into AI prompts.

---

## 5. Geometry (`DigitizerData`) & Formulas (Confirmed Facts)

### `DigitizerData` Nested XML
- Every `Count Section` (`1,052 / 1,052`) has a non-empty `DigitizerData` property containing nested UTF-8 XML:
  ```xml
  <?xml version="1.0" encoding="UTF-8"?>
  <Points><Point X="3234.37109375" Y="755.450866699219" PointType="Normal"/>...</Points>
  ```
- **Total `<Point>` elements across project**: `4,868` (all `PointType="Normal"`).
- **Page Reference Integrity**: `1,052 / 1,052` `PageGUID` values match one of the `324` `Page` objects (`0` unresolved).
- **Spot-checked Takeoff Items**:
  - `CHR ans CHS 100`: `11` sections, `21` points
  - `CHS and CHR20 mm dia`: `93` sections, `922` points
  - `Duct 350x200mm`: `49` sections, `286` points
  - `ELECTRICALPVC 25mm`: `9` sections, `354` points
  - `New Segment`: `0` sections, `0` points

### Formula Patterns Observed
1. **Takeoff aggregation**: `Qty = "[Takeoff]"` (79 items). On a `Count` item, PlanSwift evaluates `[Takeoff]` from the count of points across its child `Count Section` `DigitizerData` elements, while preserving `Qty="[Takeoff]"` as the raw formula expression. Note that `Count` items also have default template properties `Length="1"` and `Width="1"` (`units="[ScaleUnits]"`), which **must not** be confused with measured length/width!
2. **Parent inheritance**: `Fill Type = "[..]"`, `Transparency = "[..]"`, etc. (1,052 sections inherit from parent `Count`).
3. **Cross-object path lookup**: `Page = "[[PageGUID]\Name]"`, `Line Width = "[Width]"`.
4. **System / Settings tokens**: `PageWidth = "[!PageWidth]"`, `PageHeight = "[!PageHeight]"`, `Transparency = "[\Settings\DefaultCountTransparency]"`, `units = "[!CU]"`.
5. **Embedded PascalScript (`Expression="-1"`)**: `sep` property (`78` items) stores multi-line PascalScript checking `[septest]` (`0,5`). Stored verbatim as `unresolved` and **never executed** (`eval` prohibited).

---

## 6. Supported vs Unsupported / Unresolved Aspects

- **Fully Supported from Native Package**: Project metadata, container/folder hierarchy, pages & TIFF inventory linkage, all `Count`/`Segment`/`Count Section` objects (plus generic support for `Linear`, `Area`, `Perimeter`, `Volume`, `Assembly`, `Part`, `Dimension`, `Annotation`, `Note`, `Markup` when present), all 28,355 properties (including empty-name, SwiftExcel memos, dynamic `OrderIndex_{GUID}`), all 1,052 `DigitizerData` point sequences, all formula texts & dependency edges.
- **Unresolved without Live PlanSwift Runtime**:
  - Runtime evaluation of `[!PageWidth]`, `[!PageHeight]`, `[\Settings\...]`, `[!CU]` currency symbol, and PascalScript `Expression="-1"` expressions.
  - Numeric pixel-to-real-world scale factor per page (only `Scale Units="M"` is present in `XMLData.XML`; calibration scale is either uncalibrated or stored outside the exported archive).

---

## 7. PlanSwift COM Automation Findings (Documented vs Observed)

- **Local Machine Verification**: PlanSwift Desktop is **not** installed on this machine (confirmed via filesystem and Windows Registry queries).
- **Documented PlanSwift COM Architecture (ConstructConnect / PlanSwift Official Developer Docs)**:
  - **PlanSwift 9–11 (32-bit)**: ProgID `PlanSwift9.PlanSwift`. Requires 32-bit COM client process (`x86`).
  - **PlanSwift 12+ (64-bit)**: ProgID `PlanSwift.PlanSwift12` (native 64-bit process; client must compile for `x64` to avoid `REGDB_E_CLASSNOTREG` / `TYPE_E_CANTLOADLIBRARY`).
  - **Session Constraint**: PlanSwift COM requires an interactive signed-in Windows desktop session with PlanSwift initialized and the user authenticated. It cannot execute as a headless Linux Docker service.
  - **Documented `IPlanSwift` Read-Only Traversal APIs**: `GetItem(path)`, `SelectedItem()`, `ChildCount`, `ChildItem(index)`, `PropertyCount`, `PropertyName(index)`, `GetPropertyFormula(name)`, `GetPropertyResult(name)`, `GetPropertyResultAsString(name, default)`.
- **COM vs Native Package Comparison**:
  - **Available via COM only (at runtime)**: PlanSwift-evaluated property values (`computed_by_planswift`), live `[!PageWidth]`/`[!PageHeight]`, user `[\Settings\...]`, and evaluated `[Takeoff]` results when calculated by PlanSwift's internal engine.
  - **Available via Native Package only (reliably & fast)**: Complete archive manifest (`324` `.tiff` hashes/sizes), full XML property attribute metadata (all 34 attributes including `ParseFormula`, `Expression`, `inputcondition`, `ListPropertiesToSet`), raw `DigitizerData` XML without interactive UI overhead, and deterministic offline batch processing.
  - **Unresolved Verification Question**: Exact runtime return formatting of `GetPropertyResultAsString` for `DigitizerData`, `PageWidth`, and `sep` in PlanSwift 12.x cannot be measured until executed on a licensed Windows workstation running PlanSwift.
