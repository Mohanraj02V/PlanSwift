from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class ProjectSource(models.Model):
    class SourceKind(models.TextChoices):
        LOCAL_PATH = "local_path", "Local Configured Path"
        UPLOADED_ARCHIVE = "uploaded_archive", "Protected Uploaded Archive"
        UPLOADED_DXF = "uploaded_dxf", "Uploaded DXF Drawing"
        UPLOADED_IFC = "uploaded_ifc", "Uploaded IFC BIM Model"
        COM_SNAPSHOT = "com_snapshot", "PlanSwift COM Snapshot"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey("projects.Project", on_delete=models.CASCADE, related_name="sources")
    source_kind = models.CharField(max_length=32, choices=SourceKind.choices, default=SourceKind.LOCAL_PATH)
    source_format = models.CharField(max_length=32, default="planswift", db_index=True)
    source_path = models.CharField(max_length=1024)
    source_name = models.CharField(max_length=255)
    actual_extension = models.CharField(max_length=32, blank=True)
    magic_bytes_hex = models.CharField(max_length=128, blank=True)
    container_format = models.CharField(max_length=64, blank=True)
    file_size_bytes = models.BigIntegerField(default=0)
    source_sha256 = models.CharField(max_length=64, blank=True, db_index=True)
    is_read_only = models.BooleanField(default=True)
    manifest_summary = models.JSONField(default=dict, blank=True)
    registered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "project_sources"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["project", "source_sha256"])]
