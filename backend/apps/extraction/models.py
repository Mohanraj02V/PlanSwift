from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class ExtractionRun(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        INSPECTING_SOURCE = "INSPECTING_SOURCE", "Inspecting Source"
        BUILDING_MANIFEST = "BUILDING_MANIFEST", "Building Manifest"
        PARSING_PACKAGE = "PARSING_PACKAGE", "Parsing Package"
        CONNECTING_TO_PLANSWIFT = "CONNECTING_TO_PLANSWIFT", "Connecting to PlanSwift"
        EXTRACTING_OBJECTS = "EXTRACTING_OBJECTS", "Extracting Objects"
        BUILDING_RELATIONSHIPS = "BUILDING_RELATIONSHIPS", "Building Relationships"
        NORMALIZING_DATA = "NORMALIZING_DATA", "Normalizing Data"
        RECONCILING_SOURCES = "RECONCILING_SOURCES", "Reconciling Sources"
        VALIDATING = "VALIDATING", "Validating"
        COMPLETED = "COMPLETED", "Completed"
        FAILED = "FAILED", "Failed"
        CANCELLED = "CANCELLED", "Cancelled"
        PAUSED = "PAUSED", "Paused"
        REQUIRES_USER_ACTION = "REQUIRES_USER_ACTION", "Requires User Action"
        PARTIALLY_COMPLETED = "PARTIALLY_COMPLETED", "Partially Completed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey("projects.Project", on_delete=models.CASCADE, related_name="extraction_runs")
    project_version = models.ForeignKey(
        "projects.ProjectVersion",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="extraction_runs",
    )
    project_source = models.ForeignKey(
        "project_sources.ProjectSource",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="extraction_runs",
    )
    triggered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.PENDING, db_index=True)
    progress_pct = models.IntegerField(default=0)
    adapter_used = models.CharField(max_length=128, blank=True)
    parser_version = models.CharField(max_length=32, default="1.0.0")
    source_sha256 = models.CharField(max_length=64, blank=True, db_index=True)
    deterministic_digest_sha256 = models.CharField(max_length=64, blank=True)
    duration_seconds = models.FloatField(default=0.0)
    peak_memory_mb = models.FloatField(default=0.0)
    cancel_requested = models.BooleanField(default=False)
    checkpoint_data = models.JSONField(default=dict, blank=True)
    summary = models.JSONField(default=dict, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "extraction_runs"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["project", "status", "created_at"])]


class ExtractionEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    extraction_run = models.ForeignKey(ExtractionRun, on_delete=models.CASCADE, related_name="events")
    stage = models.CharField(max_length=32)
    progress_pct = models.IntegerField(default=0)
    message = models.TextField()
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "extraction_events"
        ordering = ["created_at"]


class ExtractionError(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    extraction_run = models.ForeignKey(ExtractionRun, on_delete=models.CASCADE, related_name="errors")
    stage = models.CharField(max_length=32)
    code = models.CharField(max_length=64)
    message = models.TextField()
    recoverable = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "extraction_errors"
        ordering = ["created_at"]
