from __future__ import annotations

import uuid

from django.db import models
from django.utils import timezone


class ProvenanceChoices(models.TextChoices):
    NATIVE = "native", "Native"
    CALCULATED = "calculated", "Calculated"
    RECONSTRUCTED = "reconstructed", "Reconstructed"
    INFERRED = "inferred", "Inferred"
    AI_GENERATED = "ai_generated", "AI Generated"
    ORIGINAL = "original", "Original"
    API_EXTRACTED = "api_extracted", "API Extracted"
    NORMALIZED = "normalized", "Normalized"
    COMPUTED_BY_PLANSWIFT = "computed_by_planswift", "Computed by PlanSwift"
    DERIVED = "derived", "Derived"
    AI_INFERRED = "ai_inferred", "AI Inferred"
    UNRESOLVED = "unresolved", "Unresolved"
    UNSUPPORTED = "unsupported", "Unsupported"


class ObjectType(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project_version = models.ForeignKey("projects.ProjectVersion", on_delete=models.CASCADE, related_name="object_types")
    native_class = models.CharField(max_length=128)
    object_count = models.IntegerField(default=0)
    is_known_class = models.BooleanField(default=True)

    class Meta:
        db_table = "object_types"
        unique_together = [("project_version", "native_class")]


class PropertyDefinition(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project_version = models.ForeignKey("projects.ProjectVersion", on_delete=models.CASCADE, related_name="property_definitions")
    name = models.CharField(max_length=255, blank=True)
    property_class = models.CharField(max_length=64)
    group = models.CharField(max_length=128, blank=True)
    occurrence_count = models.IntegerField(default=0)

    class Meta:
        db_table = "property_definitions"
        unique_together = [("project_version", "name", "property_class")]


class ProjectObject(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project_version = models.ForeignKey("projects.ProjectVersion", on_delete=models.CASCADE, related_name="project_objects")
    native_guid = models.CharField(max_length=64, db_index=True)
    native_class = models.CharField(max_length=128, db_index=True)
    native_type = models.CharField(max_length=128, blank=True)
    name = models.CharField(max_length=512, blank=True, db_index=True)
    parent_guid = models.CharField(max_length=64, null=True, blank=True, db_index=True)
    root_path = models.TextField(blank=True)
    depth = models.IntegerField(default=0, db_index=True)
    order_index = models.IntegerField(null=True, blank=True)
    is_known_class = models.BooleanField(default=True, db_index=True)
    is_measurement_section = models.BooleanField(default=False, db_index=True)
    is_page = models.BooleanField(default=False, db_index=True)
    page_guid = models.CharField(max_length=64, null=True, blank=True, db_index=True)
    group_id = models.CharField(max_length=64, null=True, blank=True, db_index=True)
    division = models.CharField(max_length=255, blank=True)
    subdivision = models.CharField(max_length=255, blank=True)
    phase = models.CharField(max_length=255, blank=True)
    cost_code = models.CharField(max_length=255, blank=True)
    location = models.CharField(max_length=255, blank=True)
    zone = models.CharField(max_length=255, blank=True)
    created_by_raw = models.CharField(max_length=255, blank=True)
    timestamp_raw = models.CharField(max_length=120, blank=True)
    provenance = models.CharField(max_length=32, choices=ProvenanceChoices.choices, default=ProvenanceChoices.ORIGINAL)
    raw_attributes = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "project_objects"
        unique_together = [("project_version", "native_guid")]
        ordering = ["depth", "order_index", "name"]
        indexes = [
            models.Index(fields=["project_version", "native_class"]),
            models.Index(fields=["project_version", "parent_guid"]),
            models.Index(fields=["project_version", "page_guid"]),
        ]

    def __str__(self) -> str:
        return f"[{self.native_class}] {self.name} ({self.native_guid})"


class ObjectProperty(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project_object = models.ForeignKey(ProjectObject, on_delete=models.CASCADE, related_name="properties")
    native_property_guid = models.CharField(max_length=64, db_index=True)
    name = models.CharField(max_length=255, blank=True, db_index=True)
    property_class = models.CharField(max_length=64, db_index=True)
    raw_value = models.TextField(blank=True)
    parsed_value_json = models.JSONField(null=True, blank=True)
    normalized_value_json = models.JSONField(null=True, blank=True)
    normalized_unit = models.CharField(max_length=64, blank=True)
    units = models.CharField(max_length=64, blank=True)
    input_units = models.CharField(max_length=64, blank=True)
    group = models.CharField(max_length=128, blank=True, db_index=True)
    order_index = models.IntegerField(null=True, blank=True)
    decimal_places = models.CharField(max_length=32, blank=True)
    parse_formula = models.CharField(max_length=32, blank=True)
    expression_flag = models.CharField(max_length=32, blank=True)
    is_formula = models.BooleanField(default=False, db_index=True)
    is_expression_script = models.BooleanField(default=False)
    is_dynamic_page_order = models.BooleanField(default=False)
    dynamic_page_guid = models.CharField(max_length=64, blank=True)
    has_image_data = models.BooleanField(default=False)
    image_data_length = models.IntegerField(default=0)
    image_data_sha256 = models.CharField(max_length=64, blank=True)
    attributes_json = models.JSONField(default=dict, blank=True)
    source_location = models.TextField(blank=True)
    provenance = models.CharField(max_length=32, choices=ProvenanceChoices.choices, default=ProvenanceChoices.ORIGINAL)
    normalization_provenance = models.CharField(max_length=32, blank=True)

    class Meta:
        db_table = "object_properties"
        # Keyed by native_property_guid (not name) so empty-name properties never collide
        unique_together = [("project_object", "native_property_guid")]
        ordering = ["order_index", "name"]


class ProvenanceRecord(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project_version = models.ForeignKey("projects.ProjectVersion", on_delete=models.CASCADE, related_name="provenance_records")
    extraction_run = models.ForeignKey(
        "extraction.ExtractionRun",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="provenance_records",
    )
    source_system = models.CharField(max_length=64, default="PlanSwift")
    source_adapter = models.CharField(max_length=128)
    source_file = models.CharField(max_length=512)
    source_location = models.TextField(blank=True)
    source_object_guid = models.CharField(max_length=64, blank=True, db_index=True)
    source_class = models.CharField(max_length=128, blank=True)
    property_name = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=32, choices=ProvenanceChoices.choices, db_index=True)
    parser_version = models.CharField(max_length=32, default="1.0.0")
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "provenance_records"
        indexes = [models.Index(fields=["project_version", "source_object_guid", "status"])]
