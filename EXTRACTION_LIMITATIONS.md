# EXTRACTION_LIMITATIONS.md — Verified Boundaries & Unresolved Source Aspects

This document explicitly distinguishes confirmed capabilities from current source-format or host-environment limitations so no missing field is ever masked or fabricated.

1. **PlanSwift Desktop COM Not Installed on Development Machine**
   - `VortexenPlanSwiftConnector.exe` is compiled for x64 and verified for `--health`, `--detect`, `--self-test`, and graceful unavailability detection (`PLANSWIFT_COM_UNAVAILABLE`), and Django `/api/v1/planswift/ingest/` + COM reconciliation are verified via automated tests.
   - Live out-of-process COM attachment to a running PlanSwift 12/11 GUI session could not be executed locally because PlanSwift Desktop is not installed on this machine.

2. **Formula Evaluation Without Live PlanSwift COM (`9,013` Formulas in `project 4`)**
   - All `9,013` formula strings (including `[Takeoff]`, `[!PageWidth]`, `[!PageHeight]`, `[\Settings\DefaultCountTransparency]`, `[[PageGUID]\Name]`, and `78` PascalScript `Expression="-1"` blocks) are preserved verbatim with `evaluation_status="unresolved"` rather than running unsafe `eval()`.
   - When PlanSwift COM snapshots are ingested via `/api/v1/planswift/ingest/`, evaluated values are recorded with `computed_by_planswift`.
   - For `Count` items, point sums across child `Count Section` `DigitizerData` XML are computed separately as `derived_quantity` (`status="derived"`).

3. **Unstored Numeric Page Scale Factor (`project 4.SwiftJob.zip`)**
   - `112` pages in `project 4` store `Scale Units = "M"` and `180` pages store `[!PageWidth]` / `[!PageHeight]`, with no numeric pixel-to-meter calibration multiplier serialized inside `XMLData.XML`.
   - Accordingly, `CanonicalPoint` keeps `raw_x` / `raw_y` verbatim in `planswift_page_digitizer_raw` coordinates and leaves `normalized_x` / `normalized_y` as `null` rather than guessing scale from TIFF image dimensions.

4. **Count Template Defaults (`Length="1"`, `Width="1"`)**
   - `Count` objects carry default property values `Length="1"` and `Width="1"` (`units="[ScaleUnits]"`). These are flagged `is_default_template_value=True` and excluded from real quantity aggregation.

5. **Empty Native Entity Classes in `project 4`**
   - `project 4.SwiftJob.zip` contains `Count`, `Count Section`, `Segment` (0 sections), `Page`, `Folder`, and `Item`, and contains **zero** `Assembly`, `Part`, `Linear`, `Area`, `Dimension`, or `Annotation` items. Support for those classes is verified through synthetic unit tests in `extraction_engine/tests/test_generic_classes_and_formulas.py`, while `project 4` preserves its actual empty collections truthfully.
