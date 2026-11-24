export type ProvenanceStatus =
  | "native"
  | "calculated"
  | "reconstructed"
  | "inferred"
  | "ai_generated"
  | "unresolved"
  | "unsupported"
  | "original"
  | "api_extracted"
  | "normalized"
  | "computed_by_planswift"
  | "derived"
  | "ai_inferred";

export interface UserMembership {
  organization_id: string;
  organization_name: string;
  role: string;
}

export interface UserProfile {
  id: string;
  email: string;
  full_name: string;
  job_title: string;
  is_staff?: boolean;
  is_superuser?: boolean;
  is_admin?: boolean;
  primary_role?: string;
  allowed_pages?: string[];
  memberships?: UserMembership[];
  mfa_enabled: boolean;
  is_active: boolean;
  last_login?: string | null;
  created_at: string;
}

export interface Organization {
  id: string;
  name: string;
  slug: string;
  is_active: boolean;
  my_role: string | null;
  created_at: string;
}

export interface ProjectVersion {
  id: string;
  version_number: number;
  source_sha256: string;
  deterministic_digest_sha256: string;
  is_current: boolean;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface Project {
  id: string;
  organization: string;
  organization_name: string;
  name: string;
  native_guid: string;
  description: string;
  notes: string;
  project_type: string;
  source_format?: string;
  native_project_version?: string;
  measurement_system: string;
  excel_workbook_connected: boolean | null;
  xml_encoding: string;
  native_timestamp_raw: string;
  current_version: ProjectVersion | null;
  object_count: number;
  page_count: number;
  created_at: string;
  updated_at: string;
}

export interface ProjectSource {
  id: string;
  project: string;
  source_kind: string;
  source_format?: string;
  source_name: string;
  actual_extension: string;
  magic_bytes_hex: string;
  container_format: string;
  file_size_bytes: number;
  source_sha256: string;
  is_read_only: boolean;
  manifest_summary: Record<string, unknown>;
  created_at: string;
}

export interface ExtractionEvent {
  id: string;
  stage: string;
  progress_pct: number;
  message: string;
  created_at: string;
}

export interface ExtractionRun {
  id: string;
  project: string;
  project_name: string;
  project_version: string | null;
  project_source: string | null;
  status: string;
  progress_pct: number;
  adapter_used: string;
  parser_version: string;
  source_sha256: string;
  deterministic_digest_sha256: string;
  duration_seconds: number;
  peak_memory_mb: number;
  peak_rss_mb?: number;
  cancel_requested: boolean;
  extraction_options?: Record<string, unknown>;
  summary: Record<string, unknown>;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  events: ExtractionEvent[];
  errors: Array<{ id: string; stage: string; code: string; message: string; recoverable: boolean }>;
}

export interface HierarchyNode {
  id: string;
  native_guid: string;
  native_class: string;
  native_type: string;
  name: string;
  parent_guid: string | null;
  depth: number;
  order_index: number | null;
  is_page: boolean;
  is_measurement_section: boolean;
  is_known_class: boolean;
  page_guid: string | null;
  provenance: ProvenanceStatus;
}

export interface ObjectProperty {
  id: string;
  native_property_guid: string;
  name: string;
  property_class: string;
  raw_value: string;
  parsed_value_json: unknown;
  normalized_value_json: unknown;
  normalized_unit: string;
  units: string;
  input_units: string;
  group: string;
  order_index: number | null;
  decimal_places: string;
  parse_formula: string;
  expression_flag: string;
  is_formula: boolean;
  is_expression_script: boolean;
  is_dynamic_page_order: boolean;
  dynamic_page_guid: string;
  has_image_data: boolean;
  image_data_length: number;
  image_data_sha256: string;
  attributes_json: Record<string, string>;
  source_location: string;
  provenance: ProvenanceStatus;
  normalization_provenance: string;
}

export interface ProjectObject {
  id: string;
  project_version: string;
  native_guid: string;
  native_class: string;
  native_type: string;
  name: string;
  parent_guid: string | null;
  root_path: string;
  depth: number;
  order_index: number | null;
  is_known_class: boolean;
  is_measurement_section: boolean;
  is_page: boolean;
  page_guid: string | null;
  group_id: string | null;
  division: string;
  cost_code: string;
  provenance: ProvenanceStatus;
  property_count: number;
  subdivision?: string;
  phase?: string;
  location?: string;
  zone?: string;
  created_by_raw?: string;
  timestamp_raw?: string;
  raw_attributes?: Record<string, string>;
  properties?: ObjectProperty[];
}

export interface MeasurementRecord {
  id: string;
  object_guid: string;
  object_name: string;
  measurement_key: string;
  page_guid: string | null;
  measurement_type: string;
  property_name: string;
  raw_formula: string;
  native_stored_value: string;
  calculated_quantity?: number | null;
  reconstructed_quantity?: number | null;
  planswift_computed_quantity?: number | null;
  derived_quantity: number | null;
  unit: string;
  normalized_quantity: number | null;
  normalized_unit: string;
  precision: string;
  is_default_template_value: boolean;
  calculation_inputs_json?: Record<string, unknown>;
  status: ProvenanceStatus;
  notes: string;
}

export interface GeometryPoint {
  point_order: number;
  x: number;
  y: number;
  point_type: string;
  raw_x: string;
  raw_y: string;
  normalized_x: number | null;
  normalized_y: number | null;
  provenance: ProvenanceStatus;
}

export interface GeometryFeature {
  id: string;
  section_guid: string;
  parent_object_guid: string;
  page_guid: string | null;
  geometry_type: string;
  coordinate_system: string;
  point_count: number;
  bbox_min_x: number | null;
  bbox_min_y: number | null;
  bbox_max_x: number | null;
  bbox_max_y: number | null;
  derived_polyline_length: number | null;
  derived_polygon_area: number | null;
  scale_x?: number | null;
  scale_y?: number | null;
  scale_unit?: string;
  is_calibrated?: boolean;
  calibrated_length?: number | null;
  calibrated_area?: number | null;
  calibrated_unit?: string;
  normalized_length_m?: number | null;
  normalized_area_m2?: number | null;
  raw_digitizer_xml?: string;
  points?: GeometryPoint[];
  provenance: ProvenanceStatus;
  derived_metrics_provenance: ProvenanceStatus;
}

export interface FormulaRecord {
  id: string;
  object_guid: string;
  object_name: string;
  formula_key: string;
  property_guid: string;
  property_name: string;
  raw_expression: string;
  is_pascal_script: boolean;
  has_circular_dependency: boolean;
  circular_path: string[];
  unresolved_references: string[];
  evaluation_status: ProvenanceStatus;
  calculated_value?: string;
  calculated_numeric?: number | null;
  calculation_unit?: string;
  calculation_reason?: string;
  calculation_inputs_json?: Record<string, unknown>;
  planswift_evaluated_value?: string;
  dependencies: Array<{
    raw_token: string;
    reference_kind: string;
    target_property: string;
    target_object_guid: string;
    resolved: boolean;
  }>;
}

export interface ValidationResult {
  id: string;
  project_version: string;
  project_name: string;
  overall_status: string;
  objects_discovered: number;
  objects_extracted: number;
  unknown_class_objects: number;
  skipped_objects: number;
  properties_extracted: number;
  empty_name_properties: number;
  pages_discovered: number;
  pages_matched_to_tiff: number;
  sections_extracted: number;
  sections_with_resolved_page: number;
  geometry_features_extracted: number;
  points_extracted: number;
  formulas_extracted: number;
  unresolved_formulas: number;
  circular_formulas: number;
  unresolved_references: number;
  unparsed_files: number;
  unsupported_classes: string[];
  overall_verified_accuracy_pct: number;
  checks_json: Array<{
    check_name: string;
    category: string;
    status: string;
    discovered_count: number;
    extracted_count: number;
    accuracy_pct: number | null;
    completeness_pct: number | null;
    details: string;
  }>;
  created_at: string;
}

export interface QuotationMetadata {
  date?: string;
  reference?: string;
  to_client?: string;
  contact_person?: string;
  contact_number?: string;
  project_location?: string;
  subject?: string;
  intro_text?: string;
  contract_period?: string;
  currency?: string;
  rate_column_label?: string;
  vat_percent?: number;
  general_notes?: string[];
  payment_terms?: string[];
  validity?: string;
  scope_includes?: string[];
  exclusions?: string[];
  terms_conditions?: string[];
  closing_note?: string;
  signatory_name?: string;
  signatory_title?: string;
  signatory_phone?: string;
}

export interface EstimationResultRow {
  id: string;
  object_guid: string;
  object_name: string;
  native_class: string;
  category: string;
  quantity: number;
  unit: string;
  unit_cost?: number | null;
  total_cost?: number | null;
  source_status: ProvenanceStatus;
  formula_raw: string;
  section_count: number;
  notes: string;
}

export interface EstimationSession {
  id: string;
  project: string;
  name: string;
  status: string;
  summary_json: Record<string, unknown>;
  quotation_defaults?: QuotationMetadata;
  approved_at: string | null;
  created_at: string;
  results: EstimationResultRow[];
}

export interface AuditLogEntry {
  id: string;
  organization: string | null;
  organization_name: string | null;
  actor: string | null;
  actor_email: string | null;
  actor_name: string;
  action: string;
  resource_type: string;
  resource_id: string;
  ip_address: string | null;
  user_agent: string;
  metadata: Record<string, unknown>;
  date: string;
  time: string;
  created_at: string;
}

export interface AISourceObject {
  project_guid: string;
  object_guid: string;
  native_class: string;
  source_property: string;
  provenance: ProvenanceStatus;
}

export interface AIQueryResponse {
  conversation_id: string;
  answer: string;
  source_objects: AISourceObject[];
  data_status: ProvenanceStatus;
  inference_used: boolean;
  provider_used: string;
  retrieval_stats: {
    matched_objects: number;
    relationships: number;
    knowledge_snippets: number;
  };
}

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface CADDocumentRecord {
  id: string;
  project_id: string;
  project_name: string;
  project_version: string;
  version_number: number;
  source_name?: string;
  source_format: string;
  library_name: string;
  library_version: string;
  file_version: string;
  schema_name: string;
  source_units: string;
  unit_to_meter_factor: number | null;
  entity_count: number;
  layer_count: number;
  block_count: number;
  ifc_element_count: number;
  unsupported_count: number;
  header_metadata_json: Record<string, unknown>;
  external_references_json: Array<Record<string, unknown>>;
  extraction_options_json: Record<string, unknown>;
  stage_timings_json: Record<string, number>;
  peak_rss_mb: number;
}

export interface CADLayerRecord {
  id: string;
  layer_id: string;
  name: string;
  color: number | null;
  true_color: number | null;
  linetype: string;
  lineweight: number | null;
  is_on: boolean;
  is_frozen: boolean;
  is_locked: boolean;
  is_plottable: boolean;
  entity_count: number;
  provenance: ProvenanceStatus;
}

export interface CADBlockRecord {
  id: string;
  block_id: string;
  name: string;
  base_point_json: number[];
  is_layout: boolean;
  is_anonymous: boolean;
  is_xref: boolean;
  xref_path: string;
  entity_count: number;
  nested_blocks_json: string[];
  provenance: ProvenanceStatus;
}

export interface CADEntityRecord {
  id: string;
  entity_key: string;
  handle: string;
  entity_type: string;
  owner_handle: string;
  layer_name: string;
  layout_name: string;
  block_name: string;
  linetype: string;
  color: number | null;
  ocs_applied: boolean;
  is_supported: boolean;
  native_coordinates_json: Record<string, unknown>;
  world_coordinates_json: Record<string, unknown>;
  geometry_metrics_json: Record<string, unknown>;
  dimension_data_json: Record<string, unknown>;
  classification_json: Record<string, unknown>;
  attributes_json: Record<string, unknown>;
  warnings_json: string[];
  provenance: ProvenanceStatus;
}

export interface BIMElementRecord {
  id: string;
  global_id: string;
  step_id: number;
  ifc_class: string;
  name: string;
  description: string;
  object_type: string;
  predefined_type: string;
  tag: string;
  spatial_parent_guid: string | null;
  storey_name: string;
  placement_json: Record<string, unknown>;
  property_sets_json: Array<{ name: string; step_id?: number; is_type_inherited?: boolean; properties: Record<string, unknown> }>;
  quantity_sets_json: Array<{ name: string; quantities: Array<{ name: string; quantity_type: string; raw_value: number | null; raw_unit: string; normalized_value: number | null; normalized_unit: string; provenance: ProvenanceStatus }> }>;
  materials_json: Array<Record<string, unknown>>;
  classifications_json: Array<Record<string, unknown>>;
  representations_json: Array<Record<string, unknown>>;
  geometry_summary_json: {
    status: string;
    bbox_min?: number[] | null;
    bbox_max?: number[] | null;
    dimensions_xyz?: number[] | null;
    surface_area?: number | null;
    volume?: number | null;
    is_watertight?: boolean | null;
    vertex_count?: number;
    face_count?: number;
    unit?: string;
    normalized_surface_area_m2?: number | null;
    normalized_volume_m3?: number | null;
    error?: string;
    provenance?: ProvenanceStatus;
  };
  warnings_json: string[];
  provenance: ProvenanceStatus;
}
