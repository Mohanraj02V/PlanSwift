from __future__ import annotations

import uuid

from django.db import models


class Assembly(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project_version = models.ForeignKey("projects.ProjectVersion", on_delete=models.CASCADE, related_name="assemblies")
    project_object = models.OneToOneField("object_model.ProjectObject", on_delete=models.CASCADE, related_name="assembly_detail")
    native_guid = models.CharField(max_length=64, db_index=True)
    name = models.CharField(max_length=255)
    native_class = models.CharField(max_length=128)
    assembly_type = models.CharField(max_length=128, blank=True)
    provenance = models.CharField(max_length=32, default="original")

    class Meta:
        db_table = "assemblies"
        unique_together = [("project_version", "native_guid")]
