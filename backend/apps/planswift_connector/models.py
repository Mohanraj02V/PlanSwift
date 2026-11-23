from __future__ import annotations

import uuid

from django.db import models
from django.utils import timezone


class ConnectorAgent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE, related_name="connector_agents")
    name = models.CharField(max_length=128)
    machine_name = models.CharField(max_length=255, blank=True)
    prog_id = models.CharField(max_length=128, blank=True)
    planswift_version = models.CharField(max_length=64, blank=True)
    is_64_bit = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "connector_agents"


class ConnectorSyncBatch(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey("projects.Project", on_delete=models.CASCADE, related_name="com_sync_batches")
    agent = models.ForeignKey(ConnectorAgent, null=True, blank=True, on_delete=models.SET_NULL)
    prog_id = models.CharField(max_length=128)
    planswift_version = models.CharField(max_length=64, blank=True)
    payload_sha256 = models.CharField(max_length=64, db_index=True)
    object_count = models.IntegerField(default=0)
    raw_payload = models.JSONField(default=dict)
    warnings = models.JSONField(default=list, blank=True)
    received_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "connector_sync_batches"
        ordering = ["-received_at"]
