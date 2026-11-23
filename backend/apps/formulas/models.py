from __future__ import annotations

import uuid

from django.db import models


class Formula(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project_version = models.ForeignKey("projects.ProjectVersion", on_delete=models.CASCADE, related_name="formulas")
    project_object = models.ForeignKey("object_model.ProjectObject", on_delete=models.CASCADE, related_name="formulas")
    formula_key = models.CharField(max_length=255)
    property_guid = models.CharField(max_length=64)
    property_name = models.CharField(max_length=255, db_index=True)
    raw_expression = models.TextField()
    is_pascal_script = models.BooleanField(default=False, db_index=True)
    parse_formula_attr = models.CharField(max_length=32, blank=True)
    expression_attr = models.CharField(max_length=32, blank=True)
    has_circular_dependency = models.BooleanField(default=False, db_index=True)
    circular_path = models.JSONField(default=list, blank=True)
    unresolved_references = models.JSONField(default=list, blank=True)
    evaluation_status = models.CharField(max_length=32, default="unresolved", db_index=True)
    planswift_evaluated_value = models.TextField(blank=True)

    class Meta:
        db_table = "formulas"
        unique_together = [("project_version", "formula_key")]


class FormulaDependency(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    formula = models.ForeignKey(Formula, on_delete=models.CASCADE, related_name="dependencies")
    raw_token = models.CharField(max_length=255)
    reference_kind = models.CharField(max_length=64)
    target_property = models.CharField(max_length=255, blank=True)
    target_object_guid = models.CharField(max_length=64, blank=True)
    resolved = models.BooleanField(default=False)

    class Meta:
        db_table = "formula_dependencies"


class CalculatedValue(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    formula = models.ForeignKey(Formula, on_delete=models.CASCADE, related_name="calculated_values")
    value_text = models.TextField()
    numeric_value = models.FloatField(null=True, blank=True)
    source_status = models.CharField(max_length=32, default="computed_by_planswift")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "calculated_values"
