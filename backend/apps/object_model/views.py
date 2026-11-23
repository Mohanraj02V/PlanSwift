from __future__ import annotations

from rest_framework import serializers, viewsets

from apps.object_model.models import ObjectProperty, ProjectObject
from apps.permissions.rbac import IsOrgMember, get_user_org_ids


class ObjectPropertySerializer(serializers.ModelSerializer):
    class Meta:
        model = ObjectProperty
        fields = [
            "id",
            "native_property_guid",
            "name",
            "property_class",
            "raw_value",
            "parsed_value_json",
            "normalized_value_json",
            "normalized_unit",
            "units",
            "input_units",
            "group",
            "order_index",
            "decimal_places",
            "parse_formula",
            "expression_flag",
            "is_formula",
            "is_expression_script",
            "is_dynamic_page_order",
            "dynamic_page_guid",
            "has_image_data",
            "image_data_length",
            "image_data_sha256",
            "attributes_json",
            "source_location",
            "provenance",
            "normalization_provenance",
        ]


class ProjectObjectListSerializer(serializers.ModelSerializer):
    property_count = serializers.IntegerField(source="properties.count", read_only=True)

    class Meta:
        model = ProjectObject
        fields = [
            "id",
            "project_version",
            "native_guid",
            "native_class",
            "native_type",
            "name",
            "parent_guid",
            "root_path",
            "depth",
            "order_index",
            "is_known_class",
            "is_measurement_section",
            "is_page",
            "page_guid",
            "group_id",
            "division",
            "cost_code",
            "provenance",
            "property_count",
        ]


class ProjectObjectDetailSerializer(ProjectObjectListSerializer):
    properties = ObjectPropertySerializer(many=True, read_only=True)

    class Meta(ProjectObjectListSerializer.Meta):
        fields = [*ProjectObjectListSerializer.Meta.fields, "subdivision", "phase", "location", "zone", "created_by_raw", "timestamp_raw", "raw_attributes", "properties"]


class ProjectObjectViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsOrgMember]
    filterset_fields = ["project_version", "project_version__project", "native_class", "is_known_class", "is_measurement_section", "is_page", "parent_guid", "page_guid"]
    search_fields = ["name", "native_guid", "native_class", "root_path"]
    ordering_fields = ["depth", "order_index", "name", "native_class"]

    def get_serializer_class(self):
        if self.action == "retrieve":
            return ProjectObjectDetailSerializer
        return ProjectObjectListSerializer

    def get_queryset(self):
        org_ids = get_user_org_ids(self.request.user)
        qs = ProjectObject.objects.filter(project_version__project__organization_id__in=org_ids).select_related(
            "project_version", "project_version__project", "project_version__project__organization"
        )
        if self.action == "retrieve":
            qs = qs.prefetch_related("properties")
        return qs
