from __future__ import annotations

import uuid

from django.db import models
from django.utils import timezone


class BackgroundJob(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE, related_name="background_jobs")
    task_name = models.CharField(max_length=255)
    celery_task_id = models.CharField(max_length=128, blank=True, db_index=True)
    resource_type = models.CharField(max_length=128, blank=True)
    resource_id = models.CharField(max_length=128, blank=True)
    status = models.CharField(max_length=32, default="PENDING", db_index=True)
    retries = models.IntegerField(default=0)
    error_message = models.TextField(blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "background_jobs"
        ordering = ["-created_at"]
