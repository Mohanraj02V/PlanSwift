from __future__ import annotations

import uuid

from django.db import models


class Annotation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project_version = models.ForeignKey("projects.ProjectVersion", on_delete=models.CASCADE, related_name="annotations")
    project_object = models.ForeignKey("object_model.ProjectObject", on_delete=models.CASCADE, related_name="annotations")
    native_guid = models.CharField(max_length=64, db_index=True)
    annotation_class = models.CharField(max_length=64, default="Annotation")
    text = models.TextField(blank=True)
    page_guid = models.CharField(max_length=64, blank=True)
    provenance = models.CharField(max_length=32, default="original")

    class Meta:
        db_table = "annotations"
