from __future__ import annotations

import uuid

from django.db import models


class ExternalIntegration(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE, related_name="integrations")
    kind = models.CharField(max_length=64)  # swift_excel | planswift_com | webhook
    name = models.CharField(max_length=128)
    config_json = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "external_integrations"
