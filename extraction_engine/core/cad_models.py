"""Source-aware canonical data models for DXF CAD and IFC BIM extractions (additive)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from extraction_engine.core.extraction_result import ProvenanceStatus


class CanonicalCADLayer(BaseModel):
    """Native DXF layer definition preserved with flags, linetype, color, and membership count."""

    layer_id: str
    name: str
    color: int | None = None
    true_color: int | None = None
    linetype: str = ""
    lineweight: int | None = None
    is_on: bool = True
    is_frozen: bool = False
    is_locked: bool = False
    is_plottable: bool = True
    entity_count: int = 0
    raw_attributes: dict[str, Any] = Field(default_factory=dict)
    provenance: ProvenanceStatus = ProvenanceStatus.NATIVE


class CanonicalCADBlock(BaseModel):
    """Native DXF block definition preserved separately from INSERT placements."""

    block_id: str
    name: str
    base_point: list[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    is_layout: bool = False
    is_anonymous: bool = False
    is_xref: bool = False
    xref_path: str = ""
    entity_count: int = 0
    nested_block_names: list[str] = Field(default_factory=list)
    raw_attributes: dict[str, Any] = Field(default_factory=dict)
    provenance: ProvenanceStatus = ProvenanceStatus.NATIVE


class CADClassificationInfo(BaseModel):
    """Separates native DXF/IFC type from rule-based / user semantic classifications."""

    native_type: str
    rule_based_category: str = ""
    rule_based_discipline: str = ""
    user_mapping: str = ""
    classification_provenance: ProvenanceStatus = ProvenanceStatus.NATIVE


class CanonicalCADEntity(BaseModel):
    """Canonical DXF entity preserving native coordinates, OCS/WCS transforms, metrics, and overrides."""

    entity_key: str  # Document-scoped stable key, e.g. dxf:<sha12>:<handle>
    handle: str
    entity_type: str
    owner_handle: str = ""
    layer: str = "0"
    layout_name: str = ""
    block_name: str = ""
    linetype: str = ""
    color: int | None = None
    true_color: int | None = None
    lineweight: int | None = None
    invisible: bool = False
    flags: int | None = None
    extrusion: list[float] = Field(default_factory=lambda: [0.0, 0.0, 1.0])
    elevation: float | None = None
    thickness: float | None = None
    ocs_applied: bool = False
    is_supported: bool = True
    native_coordinates: dict[str, Any] = Field(default_factory=dict)
    world_coordinates: dict[str, Any] = Field(default_factory=dict)
    geometry_metrics: dict[str, Any] = Field(default_factory=dict)
    dimension_data: dict[str, Any] = Field(default_factory=dict)
    attributes: dict[str, Any] = Field(default_factory=dict)
    classification: CADClassificationInfo
    warnings: list[str] = Field(default_factory=list)
    raw_metadata: dict[str, Any] = Field(default_factory=dict)
    provenance: ProvenanceStatus = ProvenanceStatus.NATIVE


class CanonicalIFCPropertySet(BaseModel):
    """Preserved IfcPropertySet attached to an element or inherited from its IfcTypeObject."""

    name: str
    global_id: str = ""
    step_id: int | None = None
    is_type_inherited: bool = False
    properties: dict[str, Any] = Field(default_factory=dict)
    provenance: ProvenanceStatus = ProvenanceStatus.NATIVE


class CanonicalIFCQuantityItem(BaseModel):
    """Single native quantity inside an IfcElementQuantity (Qto_*) keeping raw and SI separate."""

    name: str
    quantity_type: str
    raw_value: float | int | None = None
    raw_unit: str = ""
    normalized_value: float | None = None
    normalized_unit: str = ""
    formula: str = ""
    provenance: ProvenanceStatus = ProvenanceStatus.NATIVE


class CanonicalIFCQuantitySet(BaseModel):
    """Native IfcElementQuantity container preserved verbatim."""

    name: str
    global_id: str = ""
    step_id: int | None = None
    quantities: list[CanonicalIFCQuantityItem] = Field(default_factory=list)
    provenance: ProvenanceStatus = ProvenanceStatus.NATIVE


class CanonicalIFCGeometrySummary(BaseModel):
    """Optional geometry-engine summary strictly tagged separate from native Qto_* quantities."""

    status: Literal[
        "skipped_property_only",
        "calculated",
        "no_representation",
        "unsupported",
        "failed",
    ] = "skipped_property_only"
    bbox_min: list[float] | None = None
    bbox_max: list[float] | None = None
    dimensions_xyz: list[float] | None = None
    surface_area: float | None = None
    volume: float | None = None
    is_watertight: bool | None = None
    vertex_count: int = 0
    face_count: int = 0
    unit: str = ""
    normalized_surface_area_m2: float | None = None
    normalized_volume_m3: float | None = None
    error: str = ""
    provenance: ProvenanceStatus = ProvenanceStatus.CALCULATED


class CanonicalIFCElement(BaseModel):
    """Source-aware canonical BIM element preserving GlobalId, STEP ID, Psets, Qto, placement, and optional 3D summary."""

    global_id: str
    step_id: int
    ifc_class: str
    name: str = ""
    description: str = ""
    object_type: str = ""
    predefined_type: str = ""
    tag: str = ""
    spatial_parent_guid: str | None = None
    storey_name: str = ""
    placement_matrix: list[list[float]] | None = None
    world_origin: list[float] | None = None
    property_sets: list[CanonicalIFCPropertySet] = Field(default_factory=list)
    quantity_sets: list[CanonicalIFCQuantitySet] = Field(default_factory=list)
    materials: list[dict[str, Any]] = Field(default_factory=list)
    classifications: list[dict[str, Any]] = Field(default_factory=list)
    representations: list[dict[str, Any]] = Field(default_factory=list)
    geometry_summary: CanonicalIFCGeometrySummary = Field(default_factory=CanonicalIFCGeometrySummary)
    warnings: list[str] = Field(default_factory=list)
    raw_attributes: dict[str, Any] = Field(default_factory=dict)
    provenance: ProvenanceStatus = ProvenanceStatus.NATIVE


class CanonicalCADDocument(BaseModel):
    """Top-level source-aware container attached to CanonicalProject for DXF and IFC files."""

    schema_version: str = "1.0"
    source_format: Literal["dxf_ascii", "dxf_binary", "ifc_step"]
    library_name: str
    library_version: str
    file_version: str = ""
    schema_name: str = ""
    source_units: str = ""
    unit_to_meter_factor: float | None = None
    header_variables: dict[str, Any] = Field(default_factory=dict)
    external_references: list[dict[str, Any]] = Field(default_factory=list)
    extraction_options: dict[str, Any] = Field(default_factory=dict)
    layers: list[CanonicalCADLayer] = Field(default_factory=list)
    blocks: list[CanonicalCADBlock] = Field(default_factory=list)
    cad_entities: list[CanonicalCADEntity] = Field(default_factory=list)
    ifc_elements: list[CanonicalIFCElement] = Field(default_factory=list)
    stage_timings: dict[str, float] = Field(default_factory=dict)
    peak_rss_mb: float = 0.0
