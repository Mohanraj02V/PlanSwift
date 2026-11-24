"""Canonical Digital Project Model schemas and standalone provenance definitions."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class ProvenanceStatus(str, Enum):
    """Mandatory provenance classification distinguishing native facts, deterministic calculations, and inferences."""

    NATIVE = "native"
    CALCULATED = "calculated"
    RECONSTRUCTED = "reconstructed"
    INFERRED = "inferred"
    AI_GENERATED = "ai_generated"
    UNRESOLVED = "unresolved"
    UNSUPPORTED = "unsupported"
    # Backward-compatible aliases (normalized at API/UI boundary if present in legacy rows)
    ORIGINAL = "original"
    NORMALIZED = "normalized"
    DERIVED = "derived"


class ProvenanceRecord(BaseModel):
    """Traceability record showing the exact origin of a stored object, property, or value."""

    source_system: str = "PlanSwift"
    source_adapter: str
    source_file: str
    source_location: str | None = None
    source_object_guid: str | None = None
    source_class: str | None = None
    property_name: str | None = None
    status: ProvenanceStatus
    parser_version: str = "2.0.0"
    extraction_run_id: str | None = None
    extracted_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    notes: str | None = None


class CanonicalProperty(BaseModel):
    """Preserves every PlanSwift <Property> including empty-name properties and all XML attrs."""

    native_property_guid: str
    name: str  # Preserved verbatim, including "" when Name=""
    property_class: str
    raw_value: str
    parsed_value: Any = None
    normalized_value: Any = None
    normalized_unit: str | None = None
    units: str | None = None
    input_units: str | None = None
    group: str | None = None
    order_index: int | None = None
    decimal_places: str | None = None
    parse_formula: str | None = None
    expression_flag: str | None = None
    is_formula: bool = False
    is_expression_script: bool = False
    is_dynamic_page_order: bool = False
    dynamic_page_guid: str | None = None
    has_image_data: bool = False
    image_data_length: int = 0
    image_data_sha256: str | None = None
    attributes: dict[str, str] = Field(default_factory=dict)
    source_location: str | None = None
    provenance: ProvenanceStatus = ProvenanceStatus.NATIVE
    normalization_provenance: ProvenanceStatus | None = None


class CanonicalPoint(BaseModel):
    """Raw native DigitizerData coordinate point plus optional calibrated coordinates."""

    point_order: int
    x: float
    y: float
    point_type: str = "Normal"
    raw_x: str
    raw_y: str
    normalized_x: float | None = None
    normalized_y: float | None = None
    provenance: ProvenanceStatus = ProvenanceStatus.NATIVE


class CanonicalGeometry(BaseModel):
    """Structured native geometry extracted from DigitizerData XML without image processing."""

    section_guid: str
    parent_object_guid: str
    page_guid: str | None = None
    geometry_type: str  # PointCollection, Polyline, Polygon, Segment, MultiPoint, Empty, Invalid
    coordinate_system: str = "planswift_page_digitizer_raw"
    point_count: int = 0
    points: list[CanonicalPoint] = Field(default_factory=list)
    bbox_min_x: float | None = None
    bbox_min_y: float | None = None
    bbox_max_x: float | None = None
    bbox_max_y: float | None = None
    derived_polyline_length: float | None = None
    derived_polygon_area: float | None = None
    scale_x: float | None = None
    scale_y: float | None = None
    scale_unit: str = ""
    is_calibrated: bool = False
    calibrated_length: float | None = None
    calibrated_area: float | None = None
    calibrated_unit: str = ""
    normalized_length_m: float | None = None
    normalized_area_m2: float | None = None
    validation_warnings: list[str] = Field(default_factory=list)
    raw_digitizer_xml: str = ""
    provenance: ProvenanceStatus = ProvenanceStatus.NATIVE
    derived_metrics_provenance: ProvenanceStatus = ProvenanceStatus.RECONSTRUCTED


class CanonicalMeasurementSection(BaseModel):
    """Represents a child section (e.g. Count Section, Linear Section, Area Section)."""

    native_guid: str
    parent_object_guid: str
    native_class: str
    name: str
    order_index: int | None = None
    z_order: int | None = None
    page_guid: str | None = None
    page_name_formula: str | None = None
    visible: bool | None = None
    box_mode: str | None = None
    point_count: int = 0
    derived_quantity: float | None = None
    derived_unit: str | None = None
    geometry: CanonicalGeometry | None = None
    provenance: ProvenanceStatus = ProvenanceStatus.NATIVE


class CanonicalMeasurement(BaseModel):
    """Measurement record strictly separating native stored text from calculated & reconstructed quantities."""

    measurement_key: str
    object_guid: str
    section_guid: str | None = None
    page_guid: str | None = None
    measurement_type: str
    property_name: str
    raw_formula: str | None = None
    native_stored_value: str | None = None
    calculated_quantity: float | None = None
    reconstructed_quantity: float | None = None
    derived_quantity: float | None = None
    unit: str | None = None
    normalized_quantity: float | None = None
    normalized_unit: str | None = None
    precision: str | None = None
    is_default_template_value: bool = False
    calculation_formula: str = ""
    calculation_inputs: dict[str, Any] = Field(default_factory=dict)
    provenance_classification: str = "native"
    status: ProvenanceStatus = ProvenanceStatus.NATIVE
    notes: str | None = None


class CanonicalFormulaDependency(BaseModel):
    """Single dependency reference extracted statically from a PlanSwift formula."""

    raw_token: str
    reference_kind: Literal[
        "takeoff_aggregation",
        "system_variable",
        "settings_path",
        "parent_inheritance",
        "cross_object_guid_path",
        "property_reference",
        "pascal_script",
    ]
    target_property: str | None = None
    target_object_guid: str | None = None
    resolved: bool = False


class CanonicalFormula(BaseModel):
    """Parsed & safely evaluated PlanSwift formula or expression (never executed with eval)."""

    formula_key: str
    object_guid: str
    property_guid: str
    property_name: str
    raw_expression: str
    is_pascal_script: bool = False
    parse_formula_attr: str | None = None
    expression_attr: str | None = None
    dependencies: list[CanonicalFormulaDependency] = Field(default_factory=list)
    has_circular_dependency: bool = False
    circular_path: list[str] = Field(default_factory=list)
    unresolved_references: list[str] = Field(default_factory=list)
    evaluation_status: ProvenanceStatus = ProvenanceStatus.UNRESOLVED
    calculated_value: str | None = None
    calculated_numeric: float | None = None
    calculation_unit: str = ""
    calculation_reason: str = ""
    calculation_inputs: dict[str, Any] = Field(default_factory=dict)


class CanonicalRelationship(BaseModel):
    """Explicit directed edge in the PlanSwift project object graph."""

    relationship_key: str
    relationship_type: Literal[
        "parent_child",
        "page_reference",
        "page_order",
        "group_member",
        "assembly_component",
        "swift_excel_link",
        "cross_reference",
    ]
    source_guid: str
    target_guid: str
    order_index: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    provenance: ProvenanceStatus = ProvenanceStatus.NATIVE


class CanonicalPage(BaseModel):
    """PlanSwift drawing page definition and its matched source TIFF asset."""

    native_guid: str
    name: str
    native_class: str = "Page"
    page_type: str = ".TIFF Page"
    order_index: int | None = None
    image_property_guid: str | None = None
    tiff_archive_path: str | None = None
    tiff_size_bytes: int | None = None
    scale_units: str | None = None
    scale_x: float | None = None
    scale_y: float | None = None
    page_width_raw: str | None = None
    page_height_raw: str | None = None
    numeric_scale_factor: float | None = None
    rotation_degrees: float | None = None
    created_by: str | None = None
    timestamp_raw: str | None = None
    pages_window_expanded: bool | None = None
    section_count: int = 0
    provenance: ProvenanceStatus = ProvenanceStatus.NATIVE


class CanonicalAssemblyComponent(BaseModel):
    """Component or part belonging to a native PlanSwift assembly."""

    native_guid: str
    assembly_guid: str
    name: str
    native_class: str
    quantity_raw: str | None = None
    calculated_quantity: float | None = None
    unit: str | None = None
    cost_each_raw: str | None = None
    provenance: ProvenanceStatus = ProvenanceStatus.NATIVE


class CanonicalAssembly(BaseModel):
    """Native assembly container discovered in PlanSwift project."""

    native_guid: str
    name: str
    native_class: str
    assembly_type: str | None = None
    components: list[CanonicalAssemblyComponent] = Field(default_factory=list)
    provenance: ProvenanceStatus = ProvenanceStatus.NATIVE


class CanonicalDenotation(BaseModel):
    """Native identifier, item code, or SwiftExcel link binding."""

    denotation_key: str
    object_guid: str
    kind: Literal["item_number", "group_id", "swift_excel_token", "cost_code", "custom_tag"]
    label: str
    value: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    provenance: ProvenanceStatus = ProvenanceStatus.NATIVE


class CanonicalRemark(BaseModel):
    """Descriptions, notes, remarks, or memo entries extracted from an object."""

    remark_key: str
    object_guid: str
    field_name: str
    text: str
    provenance: ProvenanceStatus = ProvenanceStatus.NATIVE


class CanonicalObject(BaseModel):
    """Generic lossless representation for every PlanSwift <Item> including unknown classes."""

    native_guid: str
    native_class: str
    native_type: str = ""
    name: str
    parent_guid: str | None = None
    root_path: str = ""
    depth: int = 0
    order_index: int | None = None
    child_guids: list[str] = Field(default_factory=list)
    is_known_class: bool = True
    is_measurement_section: bool = False
    is_page: bool = False
    page_guid: str | None = None
    group_id: str | None = None
    division: str | None = None
    subdivision: str | None = None
    phase: str | None = None
    cost_code: str | None = None
    location: str | None = None
    zone: str | None = None
    created_by: str | None = None
    timestamp_raw: str | None = None
    properties: list[CanonicalProperty] = Field(default_factory=list)
    measurements: list[CanonicalMeasurement] = Field(default_factory=list)
    sections: list[CanonicalMeasurementSection] = Field(default_factory=list)
    geometries: list[CanonicalGeometry] = Field(default_factory=list)
    formulas: list[CanonicalFormula] = Field(default_factory=list)
    denotations: list[CanonicalDenotation] = Field(default_factory=list)
    remarks: list[CanonicalRemark] = Field(default_factory=list)
    provenance: ProvenanceStatus = ProvenanceStatus.NATIVE
    raw_attributes: dict[str, str] = Field(default_factory=dict)

    def get_property(self, name: str) -> CanonicalProperty | None:
        target = name.lower()
        for prop in self.properties:
            if prop.name == name:
                return prop
        for prop in self.properties:
            if prop.name and prop.name.lower() == target:
                return prop
        return None

    def properties_dict(self) -> dict[str, Any]:
        """Convenience view keyed by property name (or GUID fallback for empty-name props)."""
        result: dict[str, Any] = {}
        for prop in self.properties:
            key = prop.name if prop.name else prop.native_property_guid
            result[key] = prop.raw_value
        return result


class ExtractionEventRecord(BaseModel):
    """Ordered execution trace event recorded during pipeline stages."""

    timestamp: str
    stage: str
    progress_pct: int = 0
    message: str


class ExtractionErrorRecord(BaseModel):
    """Structured error or warning recorded without aborting valid partial extraction."""

    timestamp: str
    stage: str
    code: str
    message: str
    recoverable: bool = False


class ValidationCheckResult(BaseModel):
    """Single validation assertion outcome distinguishing verified vs unverified vs unsupported."""

    check_name: str
    category: str
    status: Literal["verified_correct", "partially_verified", "unverified", "incorrect", "unsupported"]
    discovered_count: int = 0
    extracted_count: int = 0
    accuracy_pct: float | None = None
    completeness_pct: float | None = None
    details: str = ""


class ValidationSummary(BaseModel):
    """Aggregate validation scorecard produced for an extracted CanonicalProject."""

    overall_status: Literal["verified_correct", "partially_verified", "unverified", "incorrect"]
    objects_discovered: int = 0
    objects_extracted: int = 0
    unknown_class_objects: int = 0
    skipped_objects: int = 0
    properties_extracted: int = 0
    empty_name_properties: int = 0
    pages_discovered: int = 0
    pages_matched_to_tiff: int = 0
    sections_extracted: int = 0
    sections_with_resolved_page: int = 0
    geometry_features_extracted: int = 0
    points_extracted: int = 0
    formulas_extracted: int = 0
    formulas_calculated: int = 0
    unresolved_formulas: int = 0
    circular_formulas: int = 0
    unresolved_references: int = 0
    unparsed_files: int = 0
    unsupported_classes: list[str] = Field(default_factory=list)
    overall_verified_accuracy_pct: float = 0.0
    checks: list[ValidationCheckResult] = Field(default_factory=list)


class CanonicalProject(BaseModel):
    """Root Canonical Digital Project Model preserving full PlanSwift source fidelity."""

    schema_version: str = "1.0"
    engine_name: str = "Standalone PlanSwift ZIP Extraction Engine"
    engine_version: str = "2.0.0"
    source_system: str = "PlanSwift"
    native_guid: str
    name: str
    native_project_version: str | None = None
    description: str = ""
    notes: str = ""
    project_type: str = "Job"
    measurement_system: str = ""
    excel_workbook_connected: bool | None = None
    job_id_raw: str = ""
    created_by: str = ""
    timestamp_raw: str = ""
    xml_encoding: str = "Windows-1252"
    source_manifest: Any = None
    pages: list[CanonicalPage] = Field(default_factory=list)
    objects: list[CanonicalObject] = Field(default_factory=list)
    relationships: list[CanonicalRelationship] = Field(default_factory=list)
    assemblies: list[CanonicalAssembly] = Field(default_factory=list)
    discovered_classes: dict[str, int] = Field(default_factory=dict)
    unsupported_classes: dict[str, int] = Field(default_factory=dict)
    unsupported_objects: list[dict[str, Any]] = Field(default_factory=list)
    provenance_records: list[ProvenanceRecord] = Field(default_factory=list)
    deterministic_digest_sha256: str | None = None


class ExtractionReport(BaseModel):
    """Final extraction run metadata, stats, validation scorecard, and audit events."""

    run_id: str
    adapter_used: str
    parser_version: str
    status: str
    started_at: str
    finished_at: str
    duration_seconds: float
    peak_memory_mb: float = 0.0
    project_guid: str | None = None
    project_name: str | None = None
    validation: ValidationSummary | None = None
    reconciliation_summary: dict[str, Any] | None = None
    events: list[ExtractionEventRecord] = Field(default_factory=list)
    errors: list[ExtractionErrorRecord] = Field(default_factory=list)
