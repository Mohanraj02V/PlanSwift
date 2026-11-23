from __future__ import annotations

import uuid

from django.db import models


class Remark(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project_version = models.ForeignKey("projects.ProjectVersion", on_delete=models.CASCADE, related_name="remarks")
    project_object = models.ForeignKey("object_model.ProjectObject", on_delete=models.CASCADE, related_name="remarks")
    remark_key = models.CharField(max_length=255)
    field_name = models.CharField(max_length=128)
    text = models.TextField()
    provenance = models.CharField(max_length=32, default="original")

    class Meta:
        db_table = "remarks"
        unique_together = [("project_version", "remark_key")]
