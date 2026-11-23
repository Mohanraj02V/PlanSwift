from django.urls import path
from rest_framework import generics, serializers

from apps.components.models import AssemblyComponent
from apps.permissions.rbac import get_user_org_ids


class ComponentSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssemblyComponent
        fields = ["id", "assembly", "native_guid", "name", "native_class", "quantity_raw", "unit", "cost_each_raw", "provenance"]


class ComponentListView(generics.ListAPIView):
    serializer_class = ComponentSerializer

    def get_queryset(self):
        org_ids = get_user_org_ids(self.request.user)
        return AssemblyComponent.objects.filter(project_version__project__organization_id__in=org_ids)


urlpatterns = [path("", ComponentListView.as_view(), name="component-list")]
