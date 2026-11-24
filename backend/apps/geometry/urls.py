from __future__ import annotations

from django.urls import path
from rest_framework import generics, serializers

from apps.geometry.models import GeometryFeature, MeasurementPoint
from apps.permissions.rbac import get_user_org_ids


class MeasurementPointSerializer(serializers.ModelSerializer):
    class Meta:
        model = MeasurementPoint
        fields = ["point_order", "x", "y", "point_type", "raw_x", "raw_y", "normalized_x", "normalized_y", "provenance"]


class GeometryFeatureListSerializer(serializers.ModelSerializer):
    parent_name = serializers.CharField(source="project_object.parent_guid", read_only=True)

    class Meta:
        model = GeometryFeature
        fields = [
            "id",
            "project_version",
            "section_guid",
            "parent_object_guid",
            "parent_name",
            "page_guid",
            "geometry_type",
            "coordinate_system",
            "point_count",
            "bbox_min_x",
            "bbox_min_y",
            "bbox_max_x",
            "bbox_max_y",
            "derived_polyline_length",
            "derived_polygon_area",
            "scale_x",
            "scale_y",
            "scale_unit",
            "is_calibrated",
            "calibrated_length",
            "calibrated_area",
            "calibrated_unit",
            "normalized_length_m",
            "normalized_area_m2",
            "provenance",
            "derived_metrics_provenance",
        ]


class GeometryFeatureDetailSerializer(GeometryFeatureListSerializer):
    points = MeasurementPointSerializer(many=True, read_only=True)

    class Meta(GeometryFeatureListSerializer.Meta):
        fields = [*GeometryFeatureListSerializer.Meta.fields, "raw_digitizer_xml", "points"]


class GeometryListView(generics.ListAPIView):
    serializer_class = GeometryFeatureListSerializer
    filterset_fields = ["project_version", "project_version__project", "page_guid", "geometry_type", "parent_object_guid", "section_guid", "is_calibrated"]
    search_fields = ["section_guid", "parent_object_guid", "page_guid"]

    def get_queryset(self):
        org_ids = get_user_org_ids(self.request.user)
        return (
            GeometryFeature.objects.filter(project_version__project__organization_id__in=org_ids)
            .select_related("project_object")
            .order_by("section_guid")
        )


class GeometryDetailView(generics.RetrieveAPIView):
    serializer_class = GeometryFeatureDetailSerializer

    def get_queryset(self):
        org_ids = get_user_org_ids(self.request.user)
        return GeometryFeature.objects.filter(project_version__project__organization_id__in=org_ids).prefetch_related("points")


urlpatterns = [
    path("", GeometryListView.as_view(), name="geometry-list"),
    path("<uuid:pk>/", GeometryDetailView.as_view(), name="geometry-detail"),
]
