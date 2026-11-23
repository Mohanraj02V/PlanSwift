from __future__ import annotations

import uuid

from django.db import models
from django.utils import timezone


class ReconciliationReport(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project_version = models.ForeignKey("projects.ProjectVersion", on_delete=models.CASCADE, related_name="reconciliation_reports")
    extraction_run = models.ForeignKey(
        "extraction.ExtractionRun",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    mode = models.CharField(max_length=64, default="package_only")
    com_available = models.BooleanField(default=False)
    matched_objects = models.IntegerField(default=0)
    package_only_objects = models.IntegerField(default=0)
    com_only_objects = models.IntegerField(default=0)
    computed_values_applied = models.IntegerField(default=0)
    duplicate_guid_count = models.IntegerField(default=0)
    summary_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "reconciliation_reports"
        ordering = ["-created_at"]
