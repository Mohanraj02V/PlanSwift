from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class EstimationSession(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        REVIEWED = "reviewed", "Reviewed"
        APPROVED = "approved", "Approved"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey("projects.Project", on_delete=models.CASCADE, related_name="estimation_sessions")
    project_version = models.ForeignKey("projects.ProjectVersion", on_delete=models.CASCADE, related_name="estimation_sessions")
    name = models.CharField(max_length=255)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.DRAFT)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="approved_estimations",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    summary_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "estimation_sessions"
        ordering = ["-created_at"]


class EstimationResult(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(EstimationSession, on_delete=models.CASCADE, related_name="results")
    project_object = models.ForeignKey(
        "object_model.ProjectObject",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    object_guid = models.CharField(max_length=64, db_index=True)
    object_name = models.CharField(max_length=512)
    native_class = models.CharField(max_length=128)
    category = models.CharField(max_length=128, blank=True)
    quantity = models.FloatField(default=0.0)
    unit = models.CharField(max_length=64, blank=True)
    unit_cost = models.FloatField(null=True, blank=True)
    total_cost = models.FloatField(null=True, blank=True)
    source_status = models.CharField(max_length=32, default="derived")
    formula_raw = models.TextField(blank=True)
    section_count = models.IntegerField(default=0)
    notes = models.TextField(blank=True)

    class Meta:
        db_table = "estimation_results"
        ordering = ["object_name"]
