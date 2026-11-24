from __future__ import annotations

from django.urls import path
from rest_framework import generics, serializers

from apps.measurements.models import Measurement, MeasurementSection
from apps.permissions.rbac import get_user_org_ids


class MeasurementSerializer(serializers.ModelSerializer):
    object_name = serializers.CharField(source="project_object.name", read_only=True)
    object_guid = serializers.CharField(source="project_object.native_guid", read_only=True)

    class Meta:
        model = Measurement
        fields = [
            "id",
            "project_version",
            "object_guid",
            "object_name",
            "measurement_key",
            "page_guid",
            "measurement_type",
            "property_name",
            "raw_formula",
            "native_stored_value",
            "calculated_quantity",
            "reconstructed_quantity",
            "derived_quantity",
            "unit",
            "normalized_quantity",
            "normalized_unit",
            "precision",
            "is_default_template_value",
            "calculation_inputs_json",
            "status",
            "notes",
        ]


class MeasurementSectionSerializer(serializers.ModelSerializer):
    parent_name = serializers.CharField(source="parent_object.name", read_only=True, default="")
    page_name = serializers.CharField(source="page.name", read_only=True, default="")

    class Meta:
        model = MeasurementSection
        fields = [
            "id",
            "project_version",
            "native_guid",
            "native_class",
            "name",
            "parent_name",
            "order_index",
            "page_guid",
            "page_name",
            "visible",
            "point_count",
            "derived_quantity",
            "derived_unit",
            "provenance",
        ]


class MeasurementListView(generics.ListAPIView):
    serializer_class = MeasurementSerializer
    filterset_fields = ["project_version", "project_version__project", "measurement_type", "property_name", "status", "page_guid"]
    search_fields = ["project_object__name", "project_object__native_guid", "raw_formula"]

    def get_queryset(self):
        org_ids = get_user_org_ids(self.request.user)
        return (
            Measurement.objects.filter(project_version__project__organization_id__in=org_ids)
            .select_related("project_object")
            .order_by("project_object__name", "property_name", "id")
        )


class MeasurementSectionListView(generics.ListAPIView):
    serializer_class = MeasurementSectionSerializer
    filterset_fields = ["project_version", "project_version__project", "page_guid", "native_class"]
    search_fields = ["name", "native_guid", "parent_object__name"]

    def get_queryset(self):
        org_ids = get_user_org_ids(self.request.user)
        return (
            MeasurementSection.objects.filter(project_version__project__organization_id__in=org_ids)
            .select_related("parent_object", "page")
            .order_by("parent_object__name", "order_index", "id")
        )


urlpatterns = [
    path("", MeasurementListView.as_view(), name="measurement-list"),
    path("sections/", MeasurementSectionListView.as_view(), name="measurement-section-list"),
]
