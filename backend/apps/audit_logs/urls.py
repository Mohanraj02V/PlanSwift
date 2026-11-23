from django.urls import path
from rest_framework import generics, serializers

from apps.audit_logs.models import AuditLog
from apps.permissions.rbac import get_user_org_ids


class AuditLogSerializer(serializers.ModelSerializer):
    actor_email = serializers.EmailField(source="actor.email", read_only=True, default=None)

    class Meta:
        model = AuditLog
        fields = [
            "id",
            "organization",
            "actor",
            "actor_email",
            "action",
            "resource_type",
            "resource_id",
            "ip_address",
            "metadata",
            "created_at",
        ]


class AuditLogListView(generics.ListAPIView):
    serializer_class = AuditLogSerializer
    filterset_fields = ["action", "resource_type", "organization"]
    search_fields = ["action", "resource_type", "resource_id"]

    def get_queryset(self):
        org_ids = get_user_org_ids(self.request.user)
        return AuditLog.objects.filter(organization_id__in=org_ids).select_related("actor", "organization")


urlpatterns = [
    path("", AuditLogListView.as_view(), name="audit-list"),
]
