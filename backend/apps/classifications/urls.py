from django.urls import path
from rest_framework import generics, serializers

from apps.classifications.models import ObjectClassification
from apps.permissions.rbac import get_user_org_ids


class ObjectClassificationSerializer(serializers.ModelSerializer):
    object_name = serializers.CharField(source="project_object.name", read_only=True)
    object_guid = serializers.CharField(source="project_object.native_guid", read_only=True)

    class Meta:
        model = ObjectClassification
        fields = ["id", "object_guid", "object_name", "family", "category", "discipline", "division", "subdivision", "cost_code", "provenance", "confidence", "notes", "created_at"]


class ObjectClassificationListView(generics.ListAPIView):
    serializer_class = ObjectClassificationSerializer
    filterset_fields = ["project_version", "project_version__project", "family", "provenance"]

    def get_queryset(self):
        org_ids = get_user_org_ids(self.request.user)
        return ObjectClassification.objects.filter(project_version__project__organization_id__in=org_ids).select_related("project_object")


urlpatterns = [path("", ObjectClassificationListView.as_view(), name="classification-list")]
