# Standalone Engine Architecture (`ENGINE_ARCHITECTURE.md`)

## 1. Architectural Overview

The extraction platform consists of a framework-agnostic Python package (`extraction_engine/`), a multi-tenant Django REST persistence layer (`backend/`), and a structured Next.js Data Explorer (`frontend/`). Notice the strict boundary:

- `extraction_engine/` never imports Django, AI providers, OCR/image decoders, or PlanSwift binaries.
- AI apps (`backend/apps/ai_*`, `retrieval/`, `knowledge_base/`) never import `extraction_engine` — they consume only persisted canonical SQL/JSON facts from `backend/db`.

---

## 2. 10-Stage Standalone Pipeline (`extraction_engine/pipeline.py`)

```text
Uploaded ZIP / SwiftJob / Directory / XML
   │
   ▼ 1. VALIDATING_ARCHIVE     (archive_parser.py: magic signature, max_upload_bytes, Zip-Slip, symlinks, zip-bomb ratio, exec ext)
   ▼ 2. INSPECTING_ARCHIVE     (archive_parser.py: streaming SHA-256, duplicate path check, XML encoding & format version detection, TIFF catalog without reading pixels)
   ▼ 3. PARSING_XML            (xml_parser.py: streaming lxml.etree.iterparse with DOCTYPE block, max_xml_depth, max_xml_nodes, timeout)
   ▼ 4. INTERPRETING_OBJECTS   (metadata_parser.py & property_parser.py: Page-to-TIFF GUID matching, ScaleX/ScaleY, empty-name props, unsupported objects preserved raw)
   ▼ 5. RECONSTRUCTING_RELS    (relationship_parser.py: parent_child, page_reference, OrderIndex_{PageGUID}, group_member, Assembly/Component, SwiftExcel links)
   ▼ 6. PROCESSING_GEOMETRY    (geometry_parser.py & geometry_normalizer.py: DigitizerData <Point> sequences, ScaleX/ScaleY calibrated length & area, SI conversions)
   ▼ 7. EVALUATING_FORMULAS    (formulas/lexer.py, parser.py, evaluator.py: cycle detection + safe recursive-descent AST evaluation)
   ▼ 8. CALCULATING_QUANTITIES (calculators/quantity_engine.py: separates native, reconstructed, and calculated quantities + BOM rollups)
   ▼ 9. RECONCILING_SOURCES    (reconciliation/standalone_reconciliation.py: duplicate GUID detection & reconstructed-vs-calculated cross-checks)
   ▼ 10. VALIDATING & DIGEST   (validators/project_validator.py: 10 multi-level validation checks + deterministic SHA-256 project digest)
```

---

## 3. Security & Resource Guardrails

| Guardrail | Default Policy (`ExtractionConfig`) | Enforcement Point |
| :--- | :--- | :--- |
| Allowed upload extensions | `.zip`, `.SwiftJob`, `.swift`, `.xml` | `ProjectSourceViewSet.upload` (`project_sources/views.py`) |
| Max upload archive size | `1 GiB` (`max_upload_bytes`) | Streaming chunk counter in `upload` + `inspect_archive_manifest` |
| Max uncompressed size | `5 GiB` (`max_uncompressed_bytes`) | `ZipInfo.file_size` summation prior to reading entries |
| Max archive entries | `10,000` (`max_archive_entries`) | `len(zf.infolist())` check |
| Max compression ratio | `100.0x` on files `> 10 MiB` (`max_compression_ratio`) | `archive_parser._inspect_zip_manifest` |
| Path traversal / symlinks / executables | Rejected (`SecurityValidationError`) | `validate_archive_member_path`, `_is_zip_symlink`, `disallowed_extensions` |
| Nested archives | Rejected when `max_nested_archive_depth == 0` | `archive_parser._inspect_zip_manifest` |
| XXE / DOCTYPE / DTD | Disabled in `lxml` (`resolve_entities=False, no_network=True, load_dtd=False`) + header check | `xml_parser.py`, `geometry_parser.py`, `archive_parser.py` |
| XML nesting depth & node bounds | `max_xml_depth=64`, `max_xml_nodes=2,000,000`, `max_parse_seconds=300.0` | Incremental depth & counter during `etree.iterparse` |
| Formula execution safety | Zero `eval()`/`exec()`; whitelisted AST grammar & math functions only | `extraction_engine/formulas/` |
| Internal filesystem path secrecy | `source_path` is `write_only=True` on API; exports emit `source_filename` basename only | `ProjectSourceSerializer`, `json_exporter.py`, `exports/urls.py` |

---

## 4. Resilience & Failure Isolation

- **Per-object fault isolation**: Malformed `DigitizerData` coordinates emit per-feature `validation_warnings` and skip only invalid points while continuing extraction; unresolvable formulas emit `evaluation_status="unresolved"` with structured `calculation_reason` rather than crashing or fabricating quantities; unknown PlanSwift classes are captured verbatim into `unsupported_objects`.
- **Stage checkpointing & idempotency**: `ExtractionPipeline._write_checkpoint()` records stage progress when `checkpoint_dir` is enabled, and `ExtractionOrchestrationService` deduplicates repeated extractions using `(source_sha256, deterministic_digest_sha256, engine_version)`.
