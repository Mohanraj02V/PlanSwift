from django.urls import path
from rest_framework import generics, serializers

from apps.denotations.models import Denotation
from apps.permissions.rbac import get_user_org_ids


class SwiftExcelLinkSerializer(serializers.ModelSerializer):
    object_name = serializers.CharField(source="project_object.name", read_only=True)
    object_guid = serializers.CharField(source="project_object.native_guid", read_only=True)

    class Meta:
        model = Denotation
        fields = ["id", "object_guid", "object_name", "kind", "label", "value", "metadata", "provenance"]


class SwiftExcelLinkListView(generics.ListAPIView):
    serializer_class = SwiftExcelLinkSerializer
    filterset_fields = ["project_version", "kind"]

    def get_queryset(self):
        org_ids = get_user_org_ids(self.request.user)
        return Denotation.objects.filter(project_version__project__organization_id__in=org_ids).select_related("project_object")


urlpatterns = [path("denotations/", SwiftExcelLinkListView.as_view(), name="integration-denotations")]
