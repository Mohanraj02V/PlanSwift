from __future__ import annotations

import uuid

from django.db import models
from django.utils import timezone


class KnowledgeDocument(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE, related_name="knowledge_documents")
    title = models.CharField(max_length=255)
    category = models.CharField(max_length=128, blank=True)
    content = models.TextField()
    source_reference = models.CharField(max_length=512, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "knowledge_documents"
        ordering = ["-created_at"]


class KnowledgeChunk(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(KnowledgeDocument, on_delete=models.CASCADE, related_name="chunks")
    chunk_index = models.IntegerField(default=0)
    text = models.TextField()
    term_weights_json = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "knowledge_chunks"
        ordering = ["chunk_index"]
