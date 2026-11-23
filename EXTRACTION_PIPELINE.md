# EXTRACTION_PIPELINE.md — 10-Stage Native Extraction Pipeline & State Machine

## 1. Pipeline State Machine

Implemented in `extraction_engine/pipeline.py` and mirrored in `apps.extraction.models.ExtractionRun`:

```text
PENDING -> INSPECTING_SOURCE -> BUILDING_MANIFEST -> PARSING_PACKAGE
        -> CONNECTING_TO_PLANSWIFT -> EXTRACTING_OBJECTS -> BUILDING_RELATIONSHIPS
        -> NORMALIZING_DATA -> RECONCILING_SOURCES -> VALIDATING -> COMPLETED
```

Terminal / resumable exception states also supported:
`FAILED`, `CANCELLED`, `PAUSED`, `REQUIRES_USER_ACTION`, `PARTIALLY_COMPLETED`.

## 2. Stage Responsibilities

1. **`INSPECTING_SOURCE`**: Validates `source_path` against `ALLOWED_SOURCE_ROOTS`, reads 16-byte magic signature (`50 4B 03 04`), computes streaming 4 MiB chunk SHA-256, checks Zip Slip, absolute paths, symlinks, disallowed executables, nested archives, and ZIP bomb ratios.
2. **`BUILDING_MANIFEST`**: Indexes all entries (`325` in `project 4.SwiftJob.zip`), flags `324` `.tiff` entries as `skipped_raster`, extracts `{GUID}` asset keys, and detects CRC+size duplicate entries.
3. **`PARSING_PACKAGE`**: Streams `XMLData.XML` directly out of the ZIP entry with `lxml.etree.iterparse(..., resolve_entities=False, no_network=True, load_dtd=False)` — clearing processed XML nodes iteratively to bound RAM (`169.49 MB` peak on `project 4`).
4. **`CONNECTING_TO_PLANSWIFT`**: Checks host Windows COM availability (`version_detector.py`) and attaches any previously uploaded `ConnectorSyncBatch` payload; gracefully skips live COM on non-PlanSwift hosts without losing native package data.
5. **`EXTRACTING_OBJECTS`**: Emits `CanonicalObject`, `CanonicalProperty`, `CanonicalMeasurementSection`, `CanonicalMeasurement`, `CanonicalGeometry`, `CanonicalPoint`, `CanonicalFormula`, `CanonicalDenotation`, and `CanonicalRemark` instances.
6. **`BUILDING_RELATIONSHIPS`**: Constructs `parent_child`, `page_reference`, `page_order`, `group_member`, `swift_excel_link`, and `assembly_component` edges, plus runs static formula dependency resolution and DFS circular-reference detection.
7. **`NORMALIZING_DATA`**: Computes normalized units/scalars and deterministic SHA-256 project digest (`compute_project_deterministic_digest`) without overwriting raw values or uncalibrated coordinates.
8. **`RECONCILING_SOURCES`**: Merges optional COM-computed values via `reconcile_package_and_com()` while preserving raw formulas and flagging field-level diffs.
9. **`VALIDATING`**: Produces `ValidationSummary` distinguishing `verified_correct`, `partially_verified`, `unverified`, `incorrect`, and `unsupported`.
10. **`COMPLETED`**: Writes final checkpoint and persists into PostgreSQL/SQLite atomically.

## 3. Idempotency & Cancellation

- **Idempotent Re-runs**: `ExtractionOrchestrationService._persist_canonical_project` matches `(project, source_sha256, deterministic_digest_sha256)`. Re-running extraction on an unchanged archive reuses the existing `ProjectVersion` cleanly (`1,461` objects remain `1,461`, `28,355` properties remain `28,355`, `4,868` points remain `4,868`).
- **Checkpoints & Cancellation**: JSON checkpoints write after key stages to `checkpoint_dir`. Every 250 `<Item>` nodes and at stage boundaries, `ctx.check_cancelled()` checks `ExtractionRun.cancel_requested` and halts cleanly.
