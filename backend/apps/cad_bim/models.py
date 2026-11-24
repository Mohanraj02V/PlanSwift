from __future__ import annotations

import uuid

from django.db import models


class CADDocument(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project_version = models.OneToOneField(
        "projects.ProjectVersion",
        on_delete=models.CASCADE,
        related_name="cad_document",
    )
    source_format = models.CharField(max_length=32, db_index=True)
    library_name = models.CharField(max_length=64)
    library_version = models.CharField(max_length=64)
    file_version = models.CharField(max_length=128, blank=True)
    schema_name = models.CharField(max_length=64, blank=True, db_index=True)
    source_units = models.CharField(max_length=64, blank=True)
    unit_to_meter_factor = models.FloatField(null=True, blank=True)
    entity_count = models.IntegerField(default=0)
    layer_count = models.IntegerField(default=0)
    block_count = models.IntegerField(default=0)
    ifc_element_count = models.IntegerField(default=0)
    unsupported_count = models.IntegerField(default=0)
    header_metadata_json = models.JSONField(default=dict, blank=True)
    external_references_json = models.JSONField(default=list, blank=True)
    extraction_options_json = models.JSONField(default=dict, blank=True)
    stage_timings_json = models.JSONField(default=dict, blank=True)
    peak_rss_mb = models.FloatField(default=0.0)

    class Meta:
        db_table = "cad_documents"
        ordering = ["-project_version__created_at"]


class CADLayer(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cad_document = models.ForeignKey(CADDocument, on_delete=models.CASCADE, related_name="layers")
    layer_id = models.CharField(max_length=128, db_index=True)
    name = models.CharField(max_length=255, db_index=True)
    color = models.IntegerField(null=True, blank=True)
    true_color = models.IntegerField(null=True, blank=True)
    linetype = models.CharField(max_length=128, blank=True)
    lineweight = models.IntegerField(null=True, blank=True)
    is_on = models.BooleanField(default=True)
    is_frozen = models.BooleanField(default=False)
    is_locked = models.BooleanField(default=False)
    is_plottable = models.BooleanField(default=True)
    entity_count = models.IntegerField(default=0)
    raw_attributes_json = models.JSONField(default=dict, blank=True)
    provenance = models.CharField(max_length=32, default="native")

    class Meta:
        db_table = "cad_layers"
        ordering = ["name"]
        indexes = [models.Index(fields=["cad_document", "name"])]


class CADBlock(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cad_document = models.ForeignKey(CADDocument, on_delete=models.CASCADE, related_name="blocks")
    block_id = models.CharField(max_length=128, db_index=True)
    name = models.CharField(max_length=255, db_index=True)
    base_point_json = models.JSONField(default=list, blank=True)
    is_layout = models.BooleanField(default=False)
    is_anonymous = models.BooleanField(default=False)
    is_xref = models.BooleanField(default=False, db_index=True)
    xref_path = models.CharField(max_length=512, blank=True)
    entity_count = models.IntegerField(default=0)
    nested_blocks_json = models.JSONField(default=list, blank=True)
    raw_attributes_json = models.JSONField(default=dict, blank=True)
    provenance = models.CharField(max_length=32, default="native")

    class Meta:
        db_table = "cad_blocks"
        ordering = ["name"]
        indexes = [models.Index(fields=["cad_document", "name"])]


class CADEntity(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cad_document = models.ForeignKey(CADDocument, on_delete=models.CASCADE, related_name="entities")
    entity_key = models.CharField(max_length=160, db_index=True)
    # DXF handles are document-scoped ONLY (never globally unique!)
    handle = models.CharField(max_length=64, db_index=True)
    entity_type = models.CharField(max_length=64, db_index=True)
    owner_handle = models.CharField(max_length=64, blank=True)
    layer_name = models.CharField(max_length=255, default="0", db_index=True)
    layout_name = models.CharField(max_length=255, blank=True, db_index=True)
    block_name = models.CharField(max_length=255, blank=True, db_index=True)
    linetype = models.CharField(max_length=128, blank=True)
    color = models.IntegerField(null=True, blank=True)
    true_color = models.IntegerField(null=True, blank=True)
    lineweight = models.IntegerField(null=True, blank=True)
    invisible = models.BooleanField(default=False)
    ocs_applied = models.BooleanField(default=False)
    is_supported = models.BooleanField(default=True, db_index=True)
    native_coordinates_json = models.JSONField(default=dict, blank=True)
    world_coordinates_json = models.JSONField(default=dict, blank=True)
    geometry_metrics_json = models.JSONField(default=dict, blank=True)
    dimension_data_json = models.JSONField(default=dict, blank=True)
    classification_json = models.JSONField(default=dict, blank=True)
    attributes_json = models.JSONField(default=dict, blank=True)
    warnings_json = models.JSONField(default=list, blank=True)
    raw_metadata_json = models.JSONField(default=dict, blank=True)
    provenance = models.CharField(max_length=32, default="native", db_index=True)

    class Meta:
        db_table = "cad_entities"
        ordering = ["layout_name", "block_name", "handle"]
        unique_together = [("cad_document", "entity_key")]
        indexes = [
            models.Index(fields=["cad_document", "entity_type"]),
            models.Index(fields=["cad_document", "layer_name"]),
            models.Index(fields=["cad_document", "handle"]),
        ]


class BIMElement(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cad_document = models.ForeignKey(CADDocument, on_delete=models.CASCADE, related_name="bim_elements")
    global_id = models.CharField(max_length=128, db_index=True)
    step_id = models.IntegerField(db_index=True)
    ifc_class = models.CharField(max_length=128, db_index=True)
    name = models.CharField(max_length=512, blank=True, db_index=True)
    description = models.TextField(blank=True)
    object_type = models.CharField(max_length=255, blank=True)
    predefined_type = models.CharField(max_length=128, blank=True)
    tag = models.CharField(max_length=128, blank=True)
    spatial_parent_guid = models.CharField(max_length=128, null=True, blank=True, db_index=True)
    storey_name = models.CharField(max_length=255, blank=True, db_index=True)
    placement_json = models.JSONField(default=dict, blank=True)
    property_sets_json = models.JSONField(default=list, blank=True)
    quantity_sets_json = models.JSONField(default=list, blank=True)
    materials_json = models.JSONField(default=list, blank=True)
    classifications_json = models.JSONField(default=list, blank=True)
    representations_json = models.JSONField(default=list, blank=True)
    geometry_summary_json = models.JSONField(default=dict, blank=True)
    warnings_json = models.JSONField(default=list, blank=True)
    provenance = models.CharField(max_length=32, default="native", db_index=True)

    class Meta:
        db_table = "bim_elements"
        ordering = ["step_id"]
        unique_together = [("cad_document", "step_id")]
        indexes = [
            models.Index(fields=["cad_document", "global_id"]),
            models.Index(fields=["cad_document", "ifc_class"]),
            models.Index(fields=["cad_document", "storey_name"]),
        ]
