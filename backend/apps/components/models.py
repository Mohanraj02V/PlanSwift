from __future__ import annotations

import uuid

from django.db import models


class AssemblyComponent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project_version = models.ForeignKey("projects.ProjectVersion", on_delete=models.CASCADE, related_name="assembly_components")
    assembly = models.ForeignKey("assemblies.Assembly", on_delete=models.CASCADE, related_name="components")
    project_object = models.ForeignKey(
        "object_model.ProjectObject",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="component_records",
    )
    native_guid = models.CharField(max_length=64, db_index=True)
    name = models.CharField(max_length=255)
    native_class = models.CharField(max_length=128)
    quantity_raw = models.CharField(max_length=255, blank=True)
    unit = models.CharField(max_length=64, blank=True)
    cost_each_raw = models.CharField(max_length=255, blank=True)
    provenance = models.CharField(max_length=32, default="original")

    class Meta:
        db_table = "assembly_components"
        unique_together = [("project_version", "native_guid")]


class Part(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project_version = models.ForeignKey("projects.ProjectVersion", on_delete=models.CASCADE, related_name="parts")
    native_guid = models.CharField(max_length=64, db_index=True)
    name = models.CharField(max_length=255)
    part_number = models.CharField(max_length=128, blank=True)
    unit = models.CharField(max_length=64, blank=True)
    provenance = models.CharField(max_length=32, default="original")

    class Meta:
        db_table = "parts"
        unique_together = [("project_version", "native_guid")]
