from __future__ import annotations

import uuid

from django.db import models
from django.utils import timezone


class RetrievalRecord(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey("projects.Project", on_delete=models.CASCADE, related_name="retrieval_records")
    query_text = models.TextField()
    sql_object_count = models.IntegerField(default=0)
    graph_edge_count = models.IntegerField(default=0)
    geometry_count = models.IntegerField(default=0)
    vector_snippet_count = models.IntegerField(default=0)
    retrieved_guids = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "retrieval_records"
        ordering = ["-created_at"]
