from __future__ import annotations

import uuid

from django.db import models
from django.utils import timezone


class ObjectClassification(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project_version = models.ForeignKey("projects.ProjectVersion", on_delete=models.CASCADE, related_name="classifications")
    project_object = models.ForeignKey("object_model.ProjectObject", on_delete=models.CASCADE, related_name="classifications")
    family = models.CharField(max_length=128, blank=True, db_index=True)
    category = models.CharField(max_length=128, blank=True, db_index=True)
    discipline = models.CharField(max_length=128, blank=True, db_index=True)
    division = models.CharField(max_length=128, blank=True)
    subdivision = models.CharField(max_length=128, blank=True)
    cost_code = models.CharField(max_length=128, blank=True)
    provenance = models.CharField(max_length=32, default="original", db_index=True)
    confidence = models.FloatField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "object_classifications"
        ordering = ["-created_at"]
