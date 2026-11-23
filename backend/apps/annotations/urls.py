from django.urls import path
from rest_framework import generics, serializers

from apps.annotations.models import Annotation
from apps.permissions.rbac import get_user_org_ids


class AnnotationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Annotation
        fields = ["id", "project_version", "native_guid", "annotation_class", "text", "page_guid", "provenance"]


class AnnotationListView(generics.ListAPIView):
    serializer_class = AnnotationSerializer

    def get_queryset(self):
        org_ids = get_user_org_ids(self.request.user)
        return Annotation.objects.filter(project_version__project__organization_id__in=org_ids)


urlpatterns = [path("", AnnotationListView.as_view(), name="annotation-list")]
