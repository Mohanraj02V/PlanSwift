"""Project, ProjectVersion, and ProjectPage models."""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class Project(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE, related_name="projects")
    name = models.CharField(max_length=255)
    native_guid = models.CharField(max_length=64, blank=True, db_index=True)
    description = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    project_type = models.CharField(max_length=64, default="Job")
    measurement_system = models.CharField(max_length=64, blank=True)
    excel_workbook_connected = models.BooleanField(null=True, blank=True)
    xml_encoding = models.CharField(max_length=64, default="Windows-1252")
    native_timestamp_raw = models.CharField(max_length=120, blank=True)
    settings_json = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_projects",
    )
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "projects"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["organization", "native_guid"]),
            models.Index(fields=["organization", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.native_guid or self.id})"


class ProjectVersion(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="versions")
    version_number = models.PositiveIntegerField(default=1)
    source_sha256 = models.CharField(max_length=64, blank=True, db_index=True)
    deterministic_digest_sha256 = models.CharField(max_length=64, blank=True)
    is_current = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "project_versions"
        unique_together = [("project", "version_number")]
        ordering = ["-version_number"]


class ProjectPage(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project_version = models.ForeignKey(ProjectVersion, on_delete=models.CASCADE, related_name="pages")
    native_guid = models.CharField(max_length=64, db_index=True)
    name = models.CharField(max_length=512)
    native_class = models.CharField(max_length=64, default="Page")
    page_type = models.CharField(max_length=64, default=".TIFF Page")
    order_index = models.IntegerField(null=True, blank=True)
    image_property_guid = models.CharField(max_length=64, blank=True, db_index=True)
    tiff_archive_path = models.CharField(max_length=1024, blank=True)
    tiff_size_bytes = models.BigIntegerField(null=True, blank=True)
    scale_units = models.CharField(max_length=64, blank=True)
    page_width_raw = models.CharField(max_length=255, blank=True)
    page_height_raw = models.CharField(max_length=255, blank=True)
    numeric_scale_factor = models.FloatField(null=True, blank=True)
    rotation_degrees = models.FloatField(null=True, blank=True)
    section_count = models.IntegerField(default=0)
    created_by_raw = models.CharField(max_length=255, blank=True)
    timestamp_raw = models.CharField(max_length=120, blank=True)
    provenance = models.CharField(max_length=32, default="original")

    class Meta:
        db_table = "project_pages"
        unique_together = [("project_version", "native_guid")]
        ordering = ["order_index", "name"]
        indexes = [
            models.Index(fields=["project_version", "native_guid"]),
        ]
