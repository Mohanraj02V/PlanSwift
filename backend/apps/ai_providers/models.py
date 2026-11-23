from __future__ import annotations

import uuid

from django.db import models
from django.utils import timezone


class AIProviderConfig(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE, related_name="ai_providers")
    provider_name = models.CharField(max_length=64)  # deterministic | openai | anthropic | gemini
    model_name = models.CharField(max_length=128)
    api_base_url = models.URLField(blank=True)
    api_key_env_var = models.CharField(max_length=128, blank=True)
    timeout_seconds = models.IntegerField(default=30)
    max_retries = models.IntegerField(default=2)
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "ai_provider_configs"


class AIUsageRecord(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE, related_name="ai_usage_records")
    project = models.ForeignKey("projects.Project", null=True, blank=True, on_delete=models.SET_NULL)
    provider_name = models.CharField(max_length=64)
    model_name = models.CharField(max_length=128)
    prompt_tokens = models.IntegerField(default=0)
    completion_tokens = models.IntegerField(default=0)
    estimated_cost_usd = models.FloatField(default=0.0)
    latency_ms = models.IntegerField(default=0)
    succeeded = models.BooleanField(default=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "ai_usage_records"
        ordering = ["-created_at"]
