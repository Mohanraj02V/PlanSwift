from django.db.models import Q
from django.urls import path
from rest_framework import generics, permissions, serializers

from apps.audit_logs.models import AuditLog
from apps.organizations.models import OrganizationMember
from apps.permissions.rbac import IsOrgAdminOnly, get_user_org_ids, is_org_admin_user


class AuditLogSerializer(serializers.ModelSerializer):
    actor_email = serializers.EmailField(source="actor.email", read_only=True, default=None)
    actor_name = serializers.SerializerMethodField()
    organization_name = serializers.CharField(source="organization.name", read_only=True, default=None)
    date = serializers.SerializerMethodField()
    time = serializers.SerializerMethodField()

    def get_actor_name(self, obj: AuditLog) -> str:
        if obj.actor is not None:
            return obj.actor.full_name or obj.actor.email
        meta = obj.metadata or {}
        return str(meta.get("uploaded_by_name") or meta.get("email") or "system")

    def get_date(self, obj: AuditLog) -> str:
        return obj.created_at.strftime("%Y-%m-%d")

    def get_time(self, obj: AuditLog) -> str:
        return obj.created_at.strftime("%H:%M:%S UTC")

    class Meta:
        model = AuditLog
        fields = [
            "id",
            "organization",
            "organization_name",
            "actor",
            "actor_email",
            "actor_name",
            "action",
            "resource_type",
            "resource_id",
            "ip_address",
            "user_agent",
            "metadata",
            "date",
            "time",
            "created_at",
        ]


class AuditLogListView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated, IsOrgAdminOnly]
    serializer_class = AuditLogSerializer
    filterset_fields = ["action", "resource_type", "organization"]
    search_fields = ["action", "resource_type", "resource_id", "actor__email"]

    def get_queryset(self):
        org_ids = get_user_org_ids(self.request.user)
        qs = AuditLog.objects.select_related("actor", "organization")
        if is_org_admin_user(self.request.user):
            member_user_ids = list(
                OrganizationMember.objects.filter(organization_id__in=org_ids).values_list("user_id", flat=True)
            )
            qs = qs.filter(Q(organization_id__in=org_ids) | Q(organization__isnull=True, actor_id__in=member_user_ids))
        else:
            qs = qs.filter(organization_id__in=org_ids)

        category = (self.request.query_params.get("category") or "").strip().lower()
        if category == "uploads":
            qs = qs.filter(Q(action__startswith="file.") | Q(action="project_source.registered"))
        elif category == "auth":
            qs = qs.filter(action__startswith="auth.")
        elif category == "users":
            qs = qs.filter(action__startswith="admin.user_")
        elif category == "estimation":
            qs = qs.filter(action__startswith="estimation.")
        elif category == "extraction":
            qs = qs.filter(action__startswith="extraction.")

        actor_email = (self.request.query_params.get("actor_email") or "").strip()
        if actor_email:
            qs = qs.filter(Q(actor__email__icontains=actor_email) | Q(metadata__email__icontains=actor_email))

        date_from = (self.request.query_params.get("date_from") or "").strip()
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)
        date_to = (self.request.query_params.get("date_to") or "").strip()
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)
        return qs


urlpatterns = [
    path("", AuditLogListView.as_view(), name="audit-list"),
]
