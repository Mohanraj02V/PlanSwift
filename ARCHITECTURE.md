# ARCHITECTURE.md — Vortexen Estimator System Architecture

## 1. High-Level Architectural Boundaries

```text
+-----------------------------------------------------------------------+
|                       Next.js TypeScript Frontend                     |
|  App Router UI: Dashboard | Explorer | Geometry Data | AI Assistant   |
+-----------------------------------+-----------------------------------+
                                    | HTTPS / JWT (/api/v1/)
                                    v
+-----------------------------------------------------------------------+
|                    Django 5 + DRF Modular Monolith                    |
|                                                                       |
|  Identity & Tenancy:  accounts, organizations, permissions, audit_logs|
|  Ingestion & Jobs:    projects, project_sources, source_inventory,    |
|                       planswift_connector, extraction, background_jobs|
|  Canonical Model:     object_model, object_hierarchy, measurements,   |
|                       geometry, formulas, classifications,            |
|                       dimensions, annotations, assemblies,            |
|                       components, denotations, remarks                |
|  Quality & Business:  validation, reconciliation, estimation, exports |
|  Independent AI:      ai_providers, ai_prompts, knowledge_base,       |
|                       retrieval, ai_agents, ai_assistant              |
+------------------+----------------------------------+-----------------+
                   |                                  |
                   v                                  v
+----------------------------------+  +---------------------------------+
|   Native Extraction Engine       |  |   PostgreSQL (+PostGIS opt.)    |
|   (Pure Python, Zero LLM/OCR)    |  |   & Redis / Celery Workers      |
|   extraction_engine/             |  +---------------------------------+
+------------------+---------------+
                   | Read-Only Stream (XMLData.XML only; TIFFs skipped)
                   v
      [Local .SwiftJob.zip / XMLData.XML]

+-----------------------------------------------------------------------+
|   Optional Windows Workstation Agent (windows_connector/, x64 C#)     |
|   Read-Only PlanSwift COM -> HTTPS JSON -> /api/v1/planswift/ingest/  |
+-----------------------------------------------------------------------+
```

---

## 2. Hard Architectural Invariants

1. **No Visual Guessing**: `extraction_engine/` does not import PIL, OpenCV, Tesseract, YOLO, PyTorch, or LLM SDKs (verified automatically via AST import tests).
2. **Independent AI Layer**: None of `apps/ai_*` or `apps/retrieval` import `extraction_engine/`. AI operates strictly over persisted PostgreSQL/SQLite canonical rows and optional `KnowledgeChunk` vectors.
3. **Structured Retrieval First**: `HybridRetrievalService` always resolves native `ProjectObject`, `Measurement`, `Formula`, `ObjectRelationship`, and `GeometryFeature` rows via SQL before scoring textual remarks/knowledge chunks.
4. **Windows COM Separation**: PlanSwift COM requires an interactive Windows user session and x64 desktop registration (`PlanSwift.PlanSwift12`). Therefore COM execution lives in `windows_connector/` rather than Linux backend containers.
5. **GUID-Keyed Identity**: Every PlanSwift object is keyed by `(project_version, native_guid)` and every property by `(project_object, native_property_guid)` — preserving duplicate object names and empty-name properties losslessly.
