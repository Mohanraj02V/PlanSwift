from __future__ import annotations

import uuid

from django.db import models


class Denotation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project_version = models.ForeignKey("projects.ProjectVersion", on_delete=models.CASCADE, related_name="denotations")
    project_object = models.ForeignKey("object_model.ProjectObject", on_delete=models.CASCADE, related_name="denotations")
    denotation_key = models.CharField(max_length=255)
    kind = models.CharField(max_length=64, db_index=True)
    label = models.CharField(max_length=255)
    value = models.TextField()
    metadata = models.JSONField(default=dict, blank=True)
    provenance = models.CharField(max_length=32, default="original")

    class Meta:
        db_table = "denotations"
        unique_together = [("project_version", "denotation_key")]
