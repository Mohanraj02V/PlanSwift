# Performance & Optimization Report (`PERFORMANCE_REPORT.md`)

## 1. Benchmark Methodology

All measurements were executed directly against the refactored standalone pipeline (`ExtractionPipeline.run`) inside `c:\Users\mohan\OneDrive\Desktop\Vortexen Estimator` using Python `time.perf_counter()` wall-clock timing and `tracemalloc.get_traced_memory()` peak RSS-traced Python heap allocation (`extract_raster_tiffs=False`, streaming ZIP + `lxml.etree.iterparse` element clearing).

---

## 2. Measured Pipeline Benchmarks (Small / Medium / Large)

| Metric | Small (Synthetic ZIP) | Medium (`Sample Project.SwiftJob`) | Large (`project 4.SwiftJob.zip`) |
| :--- | :--- | :--- | :--- |
| **Archive File Size** | `< 0.01 MiB` | `67.22 MiB` | `555.83 MiB` |
| **Total Archive Entries** | `1` (`0` rasters) | `43` (`42` TIFFs skipped) | `325` (`324` TIFFs skipped) |
| **Native XML Size** | `1.0 KB` (`UTF-8`) | `1,800.6 KB` (`utf-8`) | `7,863.4 KB` (`Windows-1252`) |
| **Objects Extracted** | `4` | `224` | `1,461` |
| **Pages Discovered** | `1` | `42` (`40` calibrated) | `324` (`0` calibrated) |
| **Relationships Built** | `4` | `425` | `3,163` |
| **Geometry Features** | `1` (`1` calibrated) | `41` (`41` calibrated) | `1,052` (`0` calibrated, `4,868` pts) |
| **Formulas Evaluated** | `1 / 1` calculated | `949 / 1,517` calculated (`568` explicit unresolved) | `6,470 / 9,013` calculated (`2,543` explicit unresolved) |
| **Wall-Clock Extraction Time** | **`0.0423 s`** | **`2.2008 s`** | **`10.2940 s`** |
| **Peak Traced Memory (`tracemalloc`)** | **`4.01 MiB`** | **`39.65 MiB`** | **`177.22 MiB`** |
| **Errors / Warnings** | `0` / `0` | `0` / `0` | `0` / `0` |

---

## 3. Optimization Techniques Implemented

1. **Zero-Extraction Raster Skipping**: PlanSwift archives are dominated by multi-hundred-megabyte TIFFs (`~548 MiB` in `project 4.SwiftJob.zip`). `inspect_archive_manifest()` reads only ZIP central directory headers + 512-byte XML encoding prologue, streaming ONLY `XMLData.XML` cleanly into memory-bounded `iterparse`. Peak RAM remains **`177.22 MiB`** on a **`555.83 MiB`** ZIP file (`~0.32x` file size).
2. **Incremental `lxml.etree.iterparse` Element Clearing**: Every `<Property>` and `<Item>` clears its element and preceding siblings immediately after frame finalization, avoiding building a redundant multi-hundred-MB DOM tree for 28,355+ properties.
3. **AST Caching & Property Memoization (`FormulaEvaluator`)**:
   - Compiled AST nodes (`_ast_cache`) are cached by raw formula expression string across repeating templates (e.g., `(RoundUp([Qty Formula] * ...))` repeated 83x in `Sample Project` and `[[PageGUID]\Name]` repeated 1,052x in `project 4` parse only once!).
   - Evaluated property outcomes (`_memo`) are cached by `(object_guid, property_name_lower)` so shared parent/job properties evaluate in $O(1)$ on repeated child references.
4. **Streaming Chunked Multipart Upload (`backend/apps/project_sources/views.py` & `settings/base.py`)**:
   - Configured `TemporaryFileUploadHandler` with `FILE_UPLOAD_MAX_MEMORY_SIZE = 2 MiB` and streams uploaded archives in `1 MiB` chunks while computing SHA-256 on the fly.
5. **Relational Bulk Writes & Query Optimization (`backend/apps/extraction/services.py` & `object_model/views.py`)**:
   - Batch persistence via Django `bulk_create(..., batch_size=500/1000)` keeps database round-trips constant regardless of 28,355+ properties.
   - Replaced per-row `properties.count()` N+1 query in `ProjectObjectListSerializer` with SQL `Count("properties")` annotation in `ProjectObjectViewSet.get_queryset()`.
   - Versioned idempotency check `(source_sha256, deterministic_digest_sha256, engine_version)` skips redundant DB writes when re-extracting unchanged archives.
