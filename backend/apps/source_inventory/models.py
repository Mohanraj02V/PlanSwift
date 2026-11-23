from __future__ import annotations

import uuid

from django.db import models


class SourceFile(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project_source = models.ForeignKey("project_sources.ProjectSource", on_delete=models.CASCADE, related_name="files")
    relative_path = models.CharField(max_length=1024)
    file_name = models.CharField(max_length=255)
    extension = models.CharField(max_length=32, blank=True, db_index=True)
    compressed_size = models.BigIntegerField(default=0)
    uncompressed_size = models.BigIntegerField(default=0)
    compression_ratio = models.FloatField(default=1.0)
    crc32 = models.BigIntegerField(null=True, blank=True)
    is_xml_data = models.BooleanField(default=False, db_index=True)
    is_raster_asset = models.BooleanField(default=False, db_index=True)
    asset_guid = models.CharField(max_length=64, blank=True, db_index=True)
    linked_page_guid = models.CharField(max_length=64, blank=True, db_index=True)
    security_status = models.CharField(max_length=32, default="safe")

    class Meta:
        db_table = "source_files"
        unique_together = [("project_source", "relative_path")]
        ordering = ["relative_path"]
