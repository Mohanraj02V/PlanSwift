from __future__ import annotations

import uuid

from django.db import models


class ObjectRelationship(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project_version = models.ForeignKey("projects.ProjectVersion", on_delete=models.CASCADE, related_name="relationships")
    relationship_key = models.CharField(max_length=255)
    relationship_type = models.CharField(max_length=64, db_index=True)
    source_guid = models.CharField(max_length=64, db_index=True)
    target_guid = models.CharField(max_length=64, db_index=True)
    order_index = models.IntegerField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    provenance = models.CharField(max_length=32, default="original")

    class Meta:
        db_table = "object_relationships"
        unique_together = [("project_version", "relationship_key")]
        indexes = [
            models.Index(fields=["project_version", "relationship_type", "source_guid"]),
            models.Index(fields=["project_version", "target_guid"]),
        ]


class ObjectGroup(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project_version = models.ForeignKey("projects.ProjectVersion", on_delete=models.CASCADE, related_name="object_groups")
    group_id = models.CharField(max_length=64, db_index=True)
    name = models.CharField(max_length=255, blank=True)
    member_count = models.IntegerField(default=0)
    provenance = models.CharField(max_length=32, default="original")

    class Meta:
        db_table = "object_groups"
        unique_together = [("project_version", "group_id")]
