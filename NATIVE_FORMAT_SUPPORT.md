# Native PlanSwift Format Support (`NATIVE_FORMAT_SUPPORT.md`)

## 1. Supported Container Formats Discovered & Handled

Real PlanSwift projects distribute structured data exclusively in XML without requiring proprietary binary database engines:

| Container Format (`container_format`) | Trigger Signature / Layout | Project Version Identifier | Observed Real Fixtures |
| :--- | :--- | :--- | :--- |
| **`pkzip_swiftjob`** | PKZIP archive (`.SwiftJob`, `.SwiftJob.zip`, `.zip`) containing `XMLData.XML` / `XMLData.xml` and raster TIFFs under `Pages/` | `PlanSwift-XML-SingleData` | `project 4.SwiftJob.zip` (`555.83 MiB`, `325` entries); `Sample Project.SwiftJob` (`67.22 MiB`, `43` entries) |
| **`pkzip_swiftjob` (MultiData fallback)** | PKZIP archive carrying root `Data.xml` without top-level `XMLData.XML` | `PlanSwift-XML-MultiData-Zip` | Tested via synthetic fallback test |
| **`planswift_job_directory`** | Unzipped PlanSwift job folder tree where each `<Item>` has a `Data.xml` inside nested folders ordered by `OrderIndex` | `PlanSwift-XML-MultiData-Folder` | Tested via multi-folder `Data.xml` integration test |
| **`directory_project`** | Unzipped directory containing top-level `XMLData.XML` | `PlanSwift-XML-SingleData` | Supported via `_inspect_directory_source` |
| **`xml_only`** | Direct exported `XMLData.XML` / `<Item ...>` UTF-8 or Windows-1252 file | `PlanSwift-XML-Direct` | Supported via direct stream reader |

---

## 2. Encoding Handling

- `archive_parser._detect_xml_encoding_header()` inspects only the first 512 bytes of `XMLData.XML` / `Data.xml` to extract the XML declaration encoding without reading multi-megabyte XML trees into memory:
  - `project 4.SwiftJob.zip` (`XMLData.XML`, `7,863.4 KB`): `Windows-1252` (`encoding="Windows-1252"`).
  - `Sample Project.SwiftJob` (`XMLData.xml`, `1,800.6 KB`): `utf-8` (`encoding="utf-8"`).

---

## 3. Native XML Structures & Class Semantics

Inside `XMLData.XML`, every PlanSwift entity is an `<Item Class="..." Name="..." GUID="{...}">` containing `<Properties><Property ...>` and nested `<Items>`:

| Category | Observed `Class` / `Type` Values | Structural Role & Handling |
| :--- | :--- | :--- |
| Root Project | `Item` (`Type="Job"`) | Captures `Name`, `GUID`, `Description`, `Notes`, `Measurement Type`, `ExcelWorkbookConnected`, `JobId`, `PlanSwift Version`. |
| Navigation Containers | `Folder`, `Item` | Preserves folder hierarchy (`Pages`, `Takeoff`, etc.), `OrderIndex`, `Division`, `Cost Code`. |
| Drawing Pages | `Page` (`Type=".TIFF Page"`, `.PDF Page`) | Links `Image` property GUID `{...}` to TIFF path in manifest without decoding pixels; extracts `ScaleX`, `ScaleY`, `Scale Units`, `AutoScaled`. |
| Primary Takeoffs | `Count`, `Linear`, `Segment`, `Area`, `Volume`, `Perimeter` | Links child measurement sections; evaluates `Qty`, `Takeoff`, `Wall Area`, `Cost Total`, `Price Total`. |
| Measurement Sections | `Count Section`, `Linear Section`, `Segment Section`, `Area Section`, `Volume Section`, `Perimeter Section` | Parses CDATA `DigitizerData` (`<Points><Point X="..." Y="..." PointType="Normal"/></Points>`) & `PageGUID` calibration. |
| Assemblies & BOM Items | `Assembly`, `Part`, `Component`, child `Item` (`Type` = `Material` / `Labor` / `Equipment` / `Subcontract`) | Reconstructs `CanonicalAssembly` + `CanonicalAssemblyComponent`, inherits parent takeoff quantities (`[Area]`, `[Linear Total]`, `[Wall Area]`) when referenced. |
| Annotations & Dimensions | `Note`, `Bookmark`, `PageLegend`, `Dimension`, `Annotation`, `Markup` | Preserved intact including `DigitizerData` & `OrderIndex_{PageGUID}` relations. |
| Unknown / Future Classes | Any unrecognized `Class` | Marked `is_known_class=False`, `provenance="unsupported"`, preserved completely with all raw properties/attributes inside `project.unsupported_objects` & `/api/v1/objects/unsupported/`. |

---

## 4. Raster Assets (TIFF/PNG/JPEG) Policy

- Archive entries matching image extensions (`.tiff`, `.tif`, `.png`, `.jpg`, `.jpeg`, `.bmp`, `.gif`) are cataloged by relative path, byte size, CRC-32, and `{GUID}` filename matching to `Page.Image` GUIDs (`324/324` matched in `project 4`).
- Raster bytes are **never decompressed, decoded, or passed to OCR/CV**.
