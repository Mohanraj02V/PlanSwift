from django.urls import path
from rest_framework import generics, serializers

from apps.assemblies.models import Assembly
from apps.components.models import AssemblyComponent
from apps.permissions.rbac import get_user_org_ids


class AssemblyComponentSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssemblyComponent
        fields = ["id", "native_guid", "name", "native_class", "quantity_raw", "unit", "cost_each_raw", "provenance"]


class AssemblySerializer(serializers.ModelSerializer):
    components = AssemblyComponentSerializer(many=True, read_only=True)

    class Meta:
        model = Assembly
        fields = ["id", "project_version", "native_guid", "name", "native_class", "assembly_type", "provenance", "components"]


class AssemblyListView(generics.ListAPIView):
    serializer_class = AssemblySerializer
    filterset_fields = ["project_version", "project_version__project"]

    def get_queryset(self):
        org_ids = get_user_org_ids(self.request.user)
        return Assembly.objects.filter(project_version__project__organization_id__in=org_ids).prefetch_related("components")


urlpatterns = [path("", AssemblyListView.as_view(), name="assembly-list")]
