# DATABASE_SCHEMA.md — Relational Database Design, Constraints & Indexes

## 1. Engine Support

- **Production / Staging**: PostgreSQL 16+ (with optional `ENABLE_POSTGIS=true` and `pgvector` compatibility).
- **Development / Automated Testing**: SQLite (zero external daemon dependency) using identical Django migrations (`38` initial/app migrations applied cleanly).

## 2. Core Tables & Uniqueness Keys

| Domain App | Table(s) | Key Constraints & Indexes |
|---|---|---|
| `accounts` | `users` | `id` (UUID PK), `email` (unique indexed) |
| `organizations` | `organizations`, `organization_members` | `unique_together (organization, user)`, index `(organization, user, role)` |
| `projects` | `projects`, `project_versions`, `project_pages` | `unique_together (project, version_number)`, `(project_version, native_guid)`, index `(organization, native_guid)` |
| `project_sources` | `project_sources` | index `(project, source_sha256)` |
| `source_inventory` | `source_files` | `unique_together (project_source, relative_path)` |
| `extraction` | `extraction_runs`, `extraction_events`, `extraction_errors` | index `(project, status, created_at)` |
| `object_model` | `object_types`, `property_definitions`, `project_objects`, `object_properties`, `provenance_records` | `unique_together (project_version, native_guid)` on `project_objects`; **`unique_together (project_object, native_property_guid)`** on `object_properties` to preserve 16 empty-name props; indexes on `native_class`, `parent_guid`, `page_guid`, `source_object_guid` |
| `object_hierarchy` | `object_relationships`, `object_groups` | `unique_together (project_version, relationship_key)`, indexes on `(relationship_type, source_guid)` and `target_guid` |
| `measurements` | `measurement_sections`, `measurements` | `unique_together (project_version, native_guid)` and `(project_version, measurement_key)` |
| `geometry` | `geometry_features`, `measurement_points` | `unique_together (project_version, section_guid)`, `(geometry_feature, point_order)` |
| `formulas` | `formulas`, `formula_dependencies`, `calculated_values` | `unique_together (project_version, formula_key)` |
| `validation` & `reconciliation` | `validation_results`, `reconciliation_reports` | Linked to `project_version` and `extraction_run` |
| `estimation` | `estimation_sessions`, `estimation_results` | Approval audit fields (`approved_by`, `approved_at`) |
| `ai_*` & `retrieval` | `ai_provider_configs`, `ai_usage_records`, `ai_prompt_templates`, `knowledge_documents`, `knowledge_chunks`, `retrieval_records`, `ai_conversations`, `ai_messages` | Tracks token usage, latency, retrieved GUIDs, and source citations |
| `audit_logs` | `audit_logs` | Enforces append-only immutability (`save()` update & `delete()` raise `ImmutableAuditError`) |
