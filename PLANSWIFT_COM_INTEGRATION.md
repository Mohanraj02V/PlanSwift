# PLANSWIFT_COM_INTEGRATION.md — Windows COM Automation & Connector Architecture

## 1. Verified Installed PlanSwift 11 COM TypeLib (`PlanSwift9.PlanSwift`)

Inspected directly via `LoadTypeLib` from `C:\Program Files (x86)\PlanSwift11\PlanSwift.exe`:

- **ProgID**: `PlanSwift9.PlanSwift` (CLSID `{B521BEFE-947B-4FDD-8EA5-6478E4CB7D1D}`, `LocalServer32`, TypeLib `{60A9C20E-DE24-420D-B22E-C43286CC9AA6}`)
- **PlanSwift 12+ (64-bit)**: ProgID `PlanSwift.PlanSwift12` (documented ConstructConnect 64-bit COM endpoint).
- **Session Constraint**: PlanSwift COM executes out-of-process over `LocalServer32` inside an active, signed-in Windows desktop session with the target project open in PlanSwift. It cannot execute inside a Linux Docker container.

### Verified Read-Only COM Interfaces

| Interface | Verified Methods / Properties Used by `ReadOnlyComExtractor.cs` |
|---|---|
| `IPlanSwift` | `CurrentVersion()`, `Edition()`, `IsJobOpen()`, `GetItem("\\Job")`, `Root()` |
| `IItem` | `HasChildren()`, `LoadChildren()`, `GUID()`, `Name`, `ItemType`, `GetClassName()`, `FullPath()`, `ChildCount()`, `ChildItem(Index)`, `PropertyCount()`, `PropertyItem(Index)`, `PointCount()`, `GetPoint(PointIndex)` |
| `IPropertyObject` | `GUID()`, `Name`, `Formula`, `ResultAsString()`, `Units`, `Group`, `PropertyType()`, `Expression` |
| `IPoint` | `X`, `Y`, `PointType` |

**Read-Only Guarantee**: `ReadOnlyComExtractor.cs` never invokes `SetPropertyFormula`, `Delete`, `DeleteItem`, `NewItem`, `NewPoint`, or screenshot methods.

---

## 2. Performance & Hang-Prevention Engineering (`v1.2.3`)

Live profiling against `PlanSwift 11.0.0.129` showed that:
- Calling `IPropertyObject.ResultAsString()` on binary/image properties (`Icon`, `Image`, etc.) stalls **~1,549 ms per item** (versus 1–3 ms for normal properties).
- Reading TIFF page dimensions across all 324 large TIFF drawings inside 32-bit PlanSwift 11 triggers `psGraphic.LoadPsGraphicFromFile(...): Out of memory` (~2 seconds/page, peaking at ~3.55 GB RAM).
- `GetItem("\\Job").GUID()` always returns PlanSwift's fixed virtual `\Job` mount GUID (`{44E8B3E7-3F5F-471C-8C43-DAB66A9AC511}`) rather than the job's `Data.xml` GUID (`{27F9E929-A81C-4ED6-9A44-4B224F5C19ED}`).

`VortexenPlanSwiftConnector.exe` (`v1.2.3`) handles this via:
- **Pre-flight process check & hard background watchdogs**: Fails fast if `PlanSwift.exe` is not running, logs an informational note if a minimized/Delphi VCL window reports `MainWindowHandle == 0`, enforces `--connect-timeout <int>` (default `20s`) around COM connection and `--max-seconds <int>` (`+15s` hard limit, default `300s`) around traversal, exiting cleanly (`Exit(4)`) if a single PlanSwift COM call hangs.
- **`[STAThread]` COM apartment** on `Main` for clean cross-process STA COM marshaling.
- **Hard binary property blacklist**: `Icon`, `Image`, `Thumb`, `Thumbnail`, `Bitmap`, `ImageData`, `DigitizerData`, `PageImage`, `Preview`, `Picture`, `Glyph`, `ImageFile`, `Photo`, and `Snapshot` are skipped before calling `Formula` or `ResultAsString()`.
- **Default `--mode fast` & optional `--skip-page-dimensions`**: Evaluates only formula/computed properties (`Qty`, `PageWidth`, `PageHeight`, `Scale`, `ScaleUnits`, `DPI`, `Area`, `Length`, etc.) and skips `PointCount()`/`GetPoint()` unless `--include-points` is passed. Passing `--skip-page-dimensions` skips `PageWidth`/`PageHeight` evaluation on giant 324-page TIFF jobs in 32-bit PlanSwift 11 so takeoff items (`Qty`, `Page`, `sep`, etc.) extract in seconds without risking PlanSwift OOM.
- **Root + Depth-1 Folder `--expected-guid` Matching**: Accepts a single GUID or comma-separated GUIDs and verifies against root properties (`GUID` property + mount GUID) AND depth-1 `Pages` (`{8F381F3A-FDF7-4FE1-A65B-04D2D59C2D13}`) / `Takeoff` (`{BA630457-834C-481A-AA57-E33D401C9B04}`) folder GUIDs before traversing.
- **Lazy load gating & pre-flight authentication**: Calls `LoadChildren()` only when `HasChildren()` is true, refuses silent fallback to `Root()` unless `--allow-root` is set, authenticates with `/api/v1/auth/login/` before touching COM, and streams live progress every 25 objects (`Ctrl+C` supported).

---

## 3. Opening a `.SwiftJob.zip` Archive Properly in PlanSwift 11

On Windows, PlanSwift associates `.SwiftJob` (`HKCR\.SwiftJob` → `"C:\Program Files (x86)\PlanSwift11\PlanSwift.exe" "%1"`) rather than `.SwiftJob.zip`. Importing a file ending in `.zip` directly via the UI may treat it as raw TIFF images rather than restoring `XMLData.xml`, takeoffs, and original GUIDs.

To open `project 4.SwiftJob.zip` in PlanSwift 11 **without modifying or renaming the original archive**:

```powershell
Copy-Item ".\project 4.SwiftJob.zip" "$env:TEMP\project 4.SwiftJob" -Force
Start-Process "C:\Program Files (x86)\PlanSwift11\PlanSwift.exe" -ArgumentList "`"$env:TEMP\project 4.SwiftJob`""
```

Confirm in PlanSwift 11 that pages **and** Takeoff items load before running COM extraction (root GUID `{27F9E929-A81C-4ED6-9A44-4B224F5C19ED}`).

---

## 4. Single-Line Live Extraction & Auto-Reconciliation Commands

All commands below use single lines so pasting into Windows PowerShell never stalls on continuation backticks:

```powershell
# Option A: Direct extract + upload + auto-reconcile (matches job or Pages/Takeoff folder GUIDs; add --skip-page-dimensions to avoid 32-bit PlanSwift TIFF OOM on 324-page jobs)
.\windows_connector\bin\VortexenPlanSwiftConnector.exe --extract-com --expected-guid "{27F9E929-A81C-4ED6-9A44-4B224F5C19ED},{8F381F3A-FDF7-4FE1-A65B-04D2D59C2D13}" --skip-page-dimensions --out com_snapshot.json --upload-url http://127.0.0.1:8000/api/v1/planswift/ingest/ --project-id <PROJECT-UUID> --email estimator@vortexen.local --password VortexenDev123! --allow-insecure-local

# Option B: Export JSON only and upload via UI (/extraction -> Upload COM Snapshot JSON)
.\windows_connector\bin\VortexenPlanSwiftConnector.exe --extract-com --expected-guid "{27F9E929-A81C-4ED6-9A44-4B224F5C19ED},{8F381F3A-FDF7-4FE1-A65B-04D2D59C2D13}" --skip-page-dimensions --out com_snapshot.json

# Option C (v1.2.4): Fast --pages-only pass for [!PageWidth] and [!PageHeight] (direct GetPropertyResultAsString, skips Icon/Image & Count Sections)
.\windows_connector\bin\VortexenPlanSwiftConnector.exe --extract-com --pages-only --expected-guid "{27F9E929-A81C-4ED6-9A44-4B224F5C19ED},{8F381F3A-FDF7-4FE1-A65B-04D2D59C2D13}" --max-seconds 180 --out com_pages_snapshot.json --upload-url http://127.0.0.1:8000/api/v1/planswift/ingest/ --project-id <PROJECT-UUID> --email estimator@vortexen.local --password VortexenDev123! --allow-insecure-local
```

When `/api/v1/planswift/ingest/` receives the payload (`auto_reconcile: true`), it immediately matches objects by canonical `GUID` and updates evaluated formulas (`PageWidth`, `PageHeight`, `Qty`, etc.) to `computed_by_planswift` without overwriting the original formula expressions.
