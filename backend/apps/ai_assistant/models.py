from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class AIConversation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey("projects.Project", on_delete=models.CASCADE, related_name="ai_conversations")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="ai_conversations")
    title = models.CharField(max_length=255, default="Estimation Analysis")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "ai_conversations"
        ordering = ["-created_at"]


class AIMessage(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(AIConversation, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=24)  # user | assistant
    content = models.TextField()
    source_objects = models.JSONField(default=list, blank=True)
    data_status = models.CharField(max_length=32, default="original")
    inference_used = models.BooleanField(default=False)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "ai_messages"
        ordering = ["created_at"]
