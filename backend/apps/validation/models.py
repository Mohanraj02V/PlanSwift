from __future__ import annotations

import uuid

from django.db import models
from django.utils import timezone


class ValidationResult(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project_version = models.ForeignKey("projects.ProjectVersion", on_delete=models.CASCADE, related_name="validation_results")
    extraction_run = models.ForeignKey(
        "extraction.ExtractionRun",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="validation_results",
    )
    overall_status = models.CharField(max_length=32, db_index=True)
    objects_discovered = models.IntegerField(default=0)
    objects_extracted = models.IntegerField(default=0)
    unknown_class_objects = models.IntegerField(default=0)
    skipped_objects = models.IntegerField(default=0)
    properties_extracted = models.IntegerField(default=0)
    empty_name_properties = models.IntegerField(default=0)
    pages_discovered = models.IntegerField(default=0)
    pages_matched_to_tiff = models.IntegerField(default=0)
    sections_extracted = models.IntegerField(default=0)
    sections_with_resolved_page = models.IntegerField(default=0)
    geometry_features_extracted = models.IntegerField(default=0)
    points_extracted = models.IntegerField(default=0)
    formulas_extracted = models.IntegerField(default=0)
    unresolved_formulas = models.IntegerField(default=0)
    circular_formulas = models.IntegerField(default=0)
    unresolved_references = models.IntegerField(default=0)
    unparsed_files = models.IntegerField(default=0)
    unsupported_classes = models.JSONField(default=list, blank=True)
    overall_verified_accuracy_pct = models.FloatField(default=0.0)
    checks_json = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "validation_results"
        ordering = ["-created_at"]
