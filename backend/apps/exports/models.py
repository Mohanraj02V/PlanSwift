from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class ExportJob(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey("projects.Project", on_delete=models.CASCADE, related_name="export_jobs")
    project_version = models.ForeignKey("projects.ProjectVersion", on_delete=models.CASCADE, related_name="export_jobs")
    export_format = models.CharField(max_length=32)  # json | jsonl | csv | xlsx | geojson | manifest
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    record_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "export_jobs"
        ordering = ["-created_at"]
