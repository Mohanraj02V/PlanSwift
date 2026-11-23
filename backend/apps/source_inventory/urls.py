from django.urls import path
from rest_framework import generics, serializers

from apps.permissions.rbac import get_user_org_ids
from apps.source_inventory.models import SourceFile


class SourceFileSerializer(serializers.ModelSerializer):
    class Meta:
        model = SourceFile
        fields = [
            "id",
            "project_source",
            "relative_path",
            "file_name",
            "extension",
            "compressed_size",
            "uncompressed_size",
            "compression_ratio",
            "crc32",
            "is_xml_data",
            "is_raster_asset",
            "asset_guid",
            "linked_page_guid",
            "security_status",
        ]


class SourceFileListView(generics.ListAPIView):
    serializer_class = SourceFileSerializer
    filterset_fields = ["project_source", "extension", "is_xml_data", "is_raster_asset"]
    search_fields = ["relative_path", "file_name", "asset_guid"]

    def get_queryset(self):
        org_ids = get_user_org_ids(self.request.user)
        return SourceFile.objects.filter(project_source__project__organization_id__in=org_ids)


urlpatterns = [path("", SourceFileListView.as_view(), name="source-inventory-list")]
