from __future__ import annotations

import uuid

from django.db import models


class GeometryFeature(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project_version = models.ForeignKey("projects.ProjectVersion", on_delete=models.CASCADE, related_name="geometry_features")
    project_object = models.ForeignKey("object_model.ProjectObject", on_delete=models.CASCADE, related_name="geometries")
    section = models.ForeignKey(
        "measurements.MeasurementSection",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="geometry_features",
    )
    section_guid = models.CharField(max_length=64, db_index=True)
    parent_object_guid = models.CharField(max_length=64, db_index=True)
    page_guid = models.CharField(max_length=64, null=True, blank=True, db_index=True)
    geometry_type = models.CharField(max_length=64, db_index=True)
    coordinate_system = models.CharField(max_length=128, default="planswift_page_digitizer_raw")
    point_count = models.IntegerField(default=0)
    bbox_min_x = models.FloatField(null=True, blank=True)
    bbox_min_y = models.FloatField(null=True, blank=True)
    bbox_max_x = models.FloatField(null=True, blank=True)
    bbox_max_y = models.FloatField(null=True, blank=True)
    derived_polyline_length = models.FloatField(null=True, blank=True)
    derived_polygon_area = models.FloatField(null=True, blank=True)
    raw_digitizer_xml = models.TextField(blank=True)
    provenance = models.CharField(max_length=32, default="original")
    derived_metrics_provenance = models.CharField(max_length=32, default="derived")

    class Meta:
        db_table = "geometry_features"
        unique_together = [("project_version", "section_guid")]
        indexes = [models.Index(fields=["project_version", "page_guid", "geometry_type"])]


class MeasurementPoint(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    geometry_feature = models.ForeignKey(GeometryFeature, on_delete=models.CASCADE, related_name="points")
    point_order = models.IntegerField()
    x = models.FloatField()
    y = models.FloatField()
    point_type = models.CharField(max_length=64, default="Normal")
    raw_x = models.CharField(max_length=64)
    raw_y = models.CharField(max_length=64)
    normalized_x = models.FloatField(null=True, blank=True)
    normalized_y = models.FloatField(null=True, blank=True)
    provenance = models.CharField(max_length=32, default="original")

    class Meta:
        db_table = "measurement_points"
        unique_together = [("geometry_feature", "point_order")]
        ordering = ["point_order"]
