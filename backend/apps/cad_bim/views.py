from __future__ import annotations

from rest_framework import serializers, viewsets

from apps.cad_bim.models import BIMElement, CADBlock, CADDocument, CADEntity, CADLayer
from apps.permissions.rbac import IsOrgMember, get_user_org_ids


class CADDocumentSerializer(serializers.ModelSerializer):
    project_id = serializers.UUIDField(source="project_version.project_id", read_only=True)
    project_name = serializers.CharField(source="project_version.project.name", read_only=True)
    version_number = serializers.IntegerField(source="project_version.version_number", read_only=True)
    source_name = serializers.SerializerMethodField()

    def get_source_name(self, obj: CADDocument) -> str:
        meta = obj.header_metadata_json or {}
        return str(meta.get("_source_name") or obj.project_version.project.name)

    class Meta:
        model = CADDocument
        fields = [
            "id",
            "project_id",
            "project_name",
            "project_version",
            "version_number",
            "source_name",
            "source_format",
            "library_name",
            "library_version",
            "file_version",
            "schema_name",
            "source_units",
            "unit_to_meter_factor",
            "entity_count",
            "layer_count",
            "block_count",
            "ifc_element_count",
            "unsupported_count",
            "header_metadata_json",
            "external_references_json",
            "extraction_options_json",
            "stage_timings_json",
            "peak_rss_mb",
        ]


class CADLayerSerializer(serializers.ModelSerializer):
    class Meta:
        model = CADLayer
        fields = [
            "id",
            "cad_document",
            "layer_id",
            "name",
            "color",
            "true_color",
            "linetype",
            "lineweight",
            "is_on",
            "is_frozen",
            "is_locked",
            "is_plottable",
            "entity_count",
            "raw_attributes_json",
            "provenance",
        ]


class CADBlockSerializer(serializers.ModelSerializer):
    class Meta:
        model = CADBlock
        fields = [
            "id",
            "cad_document",
            "block_id",
            "name",
            "base_point_json",
            "is_layout",
            "is_anonymous",
            "is_xref",
            "xref_path",
            "entity_count",
            "nested_blocks_json",
            "raw_attributes_json",
            "provenance",
        ]


class CADEntitySerializer(serializers.ModelSerializer):
    class Meta:
        model = CADEntity
        fields = [
            "id",
            "cad_document",
            "entity_key",
            "handle",
            "entity_type",
            "owner_handle",
            "layer_name",
            "layout_name",
            "block_name",
            "linetype",
            "color",
            "true_color",
            "lineweight",
            "invisible",
            "ocs_applied",
            "is_supported",
            "native_coordinates_json",
            "world_coordinates_json",
            "geometry_metrics_json",
            "dimension_data_json",
            "classification_json",
            "attributes_json",
            "warnings_json",
            "provenance",
        ]


class BIMElementSerializer(serializers.ModelSerializer):
    class Meta:
        model = BIMElement
        fields = [
            "id",
            "cad_document",
            "global_id",
            "step_id",
            "ifc_class",
            "name",
            "description",
            "object_type",
            "predefined_type",
            "tag",
            "spatial_parent_guid",
            "storey_name",
            "placement_json",
            "property_sets_json",
            "quantity_sets_json",
            "materials_json",
            "classifications_json",
            "representations_json",
            "geometry_summary_json",
            "warnings_json",
            "provenance",
        ]


class CADDocumentViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsOrgMember]
    serializer_class = CADDocumentSerializer
    filterset_fields = ["project_version", "project_version__project", "source_format", "schema_name"]

    def get_queryset(self):
        org_ids = get_user_org_ids(self.request.user)
        return CADDocument.objects.filter(
            project_version__project__organization_id__in=org_ids
        ).select_related("project_version", "project_version__project")


class CADLayerViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsOrgMember]
    serializer_class = CADLayerSerializer
    filterset_fields = ["cad_document", "cad_document__project_version__project", "is_on", "is_frozen"]
    search_fields = ["name", "linetype"]

    def get_queryset(self):
        org_ids = get_user_org_ids(self.request.user)
        return CADLayer.objects.filter(cad_document__project_version__project__organization_id__in=org_ids)


class CADBlockViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsOrgMember]
    serializer_class = CADBlockSerializer
    filterset_fields = ["cad_document", "cad_document__project_version__project", "is_xref", "is_layout"]
    search_fields = ["name", "xref_path"]

    def get_queryset(self):
        org_ids = get_user_org_ids(self.request.user)
        return CADBlock.objects.filter(cad_document__project_version__project__organization_id__in=org_ids)


class CADEntityViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsOrgMember]
    serializer_class = CADEntitySerializer
    filterset_fields = [
        "cad_document",
        "cad_document__project_version__project",
        "entity_type",
        "layer_name",
        "layout_name",
        "is_supported",
    ]
    search_fields = ["handle", "entity_type", "layer_name", "block_name", "entity_key"]

    def get_queryset(self):
        org_ids = get_user_org_ids(self.request.user)
        return CADEntity.objects.filter(cad_document__project_version__project__organization_id__in=org_ids)


class BIMElementViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsOrgMember]
    serializer_class = BIMElementSerializer
    filterset_fields = [
        "cad_document",
        "cad_document__project_version__project",
        "ifc_class",
        "storey_name",
        "spatial_parent_guid",
    ]
    search_fields = ["global_id", "name", "ifc_class", "object_type", "tag", "storey_name"]

    def get_queryset(self):
        org_ids = get_user_org_ids(self.request.user)
        return BIMElement.objects.filter(cad_document__project_version__project__organization_id__in=org_ids)
