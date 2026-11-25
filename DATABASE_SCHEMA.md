# DATABASE_SCHEMA.md — Relational Database Design, Constraints & Indexes

## 1. Engine Support & Non-Destructive Evolution

- **Production / Staging**: PostgreSQL 16+ (optional `ENABLE_POSTGIS=true`).
- **Development / Automated Testing**: SQLite (`backend/db.sqlite3` dev / `:memory:` pytest) sharing identical Django migrations.
- **Role & Auth Migrations Applied**:
  - `accounts.0002_user_must_change_password_user_token_version` — Adds `token_version` (immediate session revocation counter) and `must_change_password` to `users`.
  - `organizations.0003_migrate_roles_to_three_role_model` — Non-destructive `RunPython` migration consolidating legacy roles (`owner/admin -> admin`, `estimator -> estimator`, `reviewer/viewer/estimation_only -> user`, `connector_agent -> deactivated user`).
  - `organizations.0004_alter_organizationmember_role` — Constrains `OrganizationMember.role` choices strictly to `admin`, `estimator`, `user` (default `user`).
  - `project_sources.0003_alter_projectsource_source_kind` — Removes `com_snapshot` from choices while keeping legacy `local_path` label for historical row integrity.

## 2. Core Tables & Uniqueness Keys

| Domain App | Table(s) | Key Constraints & Indexes |
|---|---|---|
| `accounts` | `users` | `id` (UUID PK), `email` (unique indexed), `token_version`, `must_change_password` |
| `organizations` | `organizations`, `organization_members` | `role` (`admin` \| `estimator` \| `user`), `unique_together (organization, user)`, index `(organization, user, role)` |
| `projects` | `projects`, `project_versions`, `project_pages` | `unique_together (project, version_number)`, `(project_version, native_guid)`, index `(organization, native_guid)` |
| `project_sources` | `project_sources` | `source_kind` (`local_path` \| `uploaded_archive` \| `uploaded_dxf` \| `uploaded_ifc`), index `(project, source_sha256)` |
| `source_inventory` | `source_files` | `unique_together (project_source, relative_path)` |
| `extraction` | `extraction_runs`, `extraction_events`, `extraction_errors` | index `(project, status, created_at)` |
| `cad_bim` | `cad_documents`, `cad_layers`, `cad_blocks`, `cad_entities`, `bim_elements` | `CADLayer`, `CADBlock`, `CADEntity` (DXF) and `BIMElement` (IFC) linked to `project_version` |
| `object_model` | `object_types`, `property_definitions`, `project_objects`, `object_properties`, `provenance_records` | `unique_together (project_version, native_guid)` on `project_objects`; `unique_together (project_object, native_property_guid)` on `object_properties` |
| `object_hierarchy` | `object_relationships`, `object_groups` | `unique_together (project_version, relationship_key)`, indexes on `(relationship_type, source_guid)` and `target_guid` |
| `measurements` | `measurement_sections`, `measurements` | `unique_together (project_version, native_guid)` and `(project_version, measurement_key)` |
| `geometry` | `geometry_features`, `measurement_points` | `unique_together (project_version, section_guid)`, `(geometry_feature, point_order)` |
| `formulas` | `formulas`, `formula_dependencies`, `calculated_values` | `unique_together (project_version, formula_key)` |
| `validation` & `reconciliation` | `validation_results`, `reconciliation_reports` | Linked to `project_version` and `extraction_run` |
| `estimation` | `estimation_sessions`, `estimation_results` | Commercial pricing, quotation metadata (`summary_json`), approval audit fields |
| `ai_*` & `retrieval` | `ai_provider_configs`, `ai_usage_records`, `ai_prompt_templates`, `knowledge_documents`, `knowledge_chunks`, `retrieval_records`, `ai_conversations`, `ai_messages` | Admin-only AI query history and grounded retrieval logs |
| `audit_logs` | `audit_logs` | Append-only immutability (`save()` update & `delete()` raise `ImmutableAuditError`) |
