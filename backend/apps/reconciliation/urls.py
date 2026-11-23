from django.urls import path
from rest_framework import generics, serializers

from apps.permissions.rbac import get_user_org_ids
from apps.reconciliation.models import ReconciliationReport


class ReconciliationReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReconciliationReport
        fields = [
            "id",
            "project_version",
            "extraction_run",
            "mode",
            "com_available",
            "matched_objects",
            "package_only_objects",
            "com_only_objects",
            "computed_values_applied",
            "duplicate_guid_count",
            "summary_json",
            "created_at",
        ]


class ReconciliationListView(generics.ListAPIView):
    serializer_class = ReconciliationReportSerializer
    filterset_fields = ["project_version", "project_version__project", "mode"]

    def get_queryset(self):
        org_ids = get_user_org_ids(self.request.user)
        return ReconciliationReport.objects.filter(project_version__project__organization_id__in=org_ids)


urlpatterns = [path("", ReconciliationListView.as_view(), name="reconciliation-list")]
