from __future__ import annotations

import uuid

from django.db import models


class MeasurementSection(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project_version = models.ForeignKey("projects.ProjectVersion", on_delete=models.CASCADE, related_name="measurement_sections")
    project_object = models.OneToOneField("object_model.ProjectObject", on_delete=models.CASCADE, related_name="section_detail")
    parent_object = models.ForeignKey(
        "object_model.ProjectObject",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="child_sections",
    )
    native_guid = models.CharField(max_length=64, db_index=True)
    native_class = models.CharField(max_length=128)
    name = models.CharField(max_length=255)
    order_index = models.IntegerField(null=True, blank=True)
    z_order = models.IntegerField(null=True, blank=True)
    page_guid = models.CharField(max_length=64, null=True, blank=True, db_index=True)
    page = models.ForeignKey("projects.ProjectPage", null=True, blank=True, on_delete=models.SET_NULL, related_name="sections")
    page_name_formula = models.CharField(max_length=255, blank=True)
    visible = models.BooleanField(null=True, blank=True)
    box_mode = models.CharField(max_length=64, blank=True)
    point_count = models.IntegerField(default=0)
    derived_quantity = models.FloatField(null=True, blank=True)
    derived_unit = models.CharField(max_length=64, blank=True)
    provenance = models.CharField(max_length=32, default="original")

    class Meta:
        db_table = "measurement_sections"
        unique_together = [("project_version", "native_guid")]
        ordering = ["order_index", "name"]


class Measurement(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project_version = models.ForeignKey("projects.ProjectVersion", on_delete=models.CASCADE, related_name="measurements")
    project_object = models.ForeignKey("object_model.ProjectObject", on_delete=models.CASCADE, related_name="measurements")
    section = models.ForeignKey(MeasurementSection, null=True, blank=True, on_delete=models.SET_NULL, related_name="measurements")
    measurement_key = models.CharField(max_length=255)
    page_guid = models.CharField(max_length=64, null=True, blank=True, db_index=True)
    measurement_type = models.CharField(max_length=128, db_index=True)
    property_name = models.CharField(max_length=128, db_index=True)
    raw_formula = models.TextField(blank=True)
    native_stored_value = models.TextField(blank=True)
    planswift_computed_quantity = models.FloatField(null=True, blank=True)
    calculated_quantity = models.FloatField(null=True, blank=True)
    reconstructed_quantity = models.FloatField(null=True, blank=True)
    derived_quantity = models.FloatField(null=True, blank=True)
    unit = models.CharField(max_length=64, blank=True)
    normalized_quantity = models.FloatField(null=True, blank=True)
    normalized_unit = models.CharField(max_length=64, blank=True)
    precision = models.CharField(max_length=32, blank=True)
    is_default_template_value = models.BooleanField(default=False)
    calculation_inputs_json = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=32, default="native", db_index=True)
    notes = models.TextField(blank=True)

    class Meta:
        db_table = "measurements"
        unique_together = [("project_version", "measurement_key")]
        indexes = [models.Index(fields=["project_version", "property_name", "status"])]
