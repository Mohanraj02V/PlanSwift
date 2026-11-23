from __future__ import annotations

import uuid

from django.db import models
from pydantic import BaseModel, Field


class PromptTemplate(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(max_length=120, unique=True)
    version = models.CharField(max_length=32, default="1.0.0")
    system_prompt = models.TextField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ai_prompt_templates"


class SourceCitationContract(BaseModel):
    project_guid: str
    object_guid: str
    native_class: str
    source_property: str
    provenance: str = "original"


class StructuredAIResponseContract(BaseModel):
    answer: str
    source_objects: list[SourceCitationContract] = Field(default_factory=list)
    data_status: str
    inference_used: bool = False
