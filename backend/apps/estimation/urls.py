from __future__ import annotations

from django.urls import include, path
from rest_framework import permissions, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.routers import DefaultRouter

from apps.audit_logs.services import log_audit_event
from apps.estimation.models import EstimationResult, EstimationSession
from apps.estimation.services import approve_estimation_session, generate_estimation_session
from apps.organizations.models import OrganizationMember
from apps.permissions.rbac import IsOrgEditor, IsOrgMember, IsOrgReviewerOrEditor, get_user_org_ids
from apps.projects.models import Project


class EstimationResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = EstimationResult
        fields = [
            "id",
            "object_guid",
            "object_name",
            "native_class",
            "category",
            "quantity",
            "unit",
            "unit_cost",
            "total_cost",
            "source_status",
            "formula_raw",
            "section_count",
            "notes",
        ]


class EstimationSessionSerializer(serializers.ModelSerializer):
    results = EstimationResultSerializer(many=True, read_only=True)

    class Meta:
        model = EstimationSession
        fields = ["id", "project", "project_version", "name", "status", "summary_json", "approved_at", "created_at", "results"]
        read_only_fields = ["id", "project_version", "status", "summary_json", "approved_at", "created_at", "results"]


class EstimationSessionViewSet(viewsets.ModelViewSet):
    serializer_class = EstimationSessionSerializer
    filterset_fields = ["project", "status"]

    def get_queryset(self):
        org_ids = get_user_org_ids(self.request.user)
        return (
            EstimationSession.objects.filter(project__organization_id__in=org_ids)
            .select_related("project", "project__organization")
            .prefetch_related("results")
        )

    def get_permissions(self):
        if self.action == "create":
            return [permissions.IsAuthenticated(), IsOrgEditor()]
        if self.action == "approve":
            return [permissions.IsAuthenticated(), IsOrgReviewerOrEditor()]
        return [permissions.IsAuthenticated(), IsOrgMember()]

    def create(self, request, *args, **kwargs):
        project_id = request.data.get("project")
        project = Project.objects.filter(id=project_id).select_related("organization").first()
        if not project:
            return Response({"detail": "Project not found."}, status=status.HTTP_404_NOT_FOUND)
        if not OrganizationMember.objects.filter(
            organization=project.organization,
            user=request.user,
            is_active=True,
            role__in=IsOrgEditor.ALLOWED_ROLES,
        ).exists():
            return Response({"detail": "Forbidden."}, status=status.HTTP_403_FORBIDDEN)
        try:
            session = generate_estimation_session(project, request.user, session_name=request.data.get("name", ""))
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        log_audit_event(
            action="estimation.generated",
            actor=request.user,
            organization=project.organization,
            request=request,
            resource_type="EstimationSession",
            resource_id=str(session.id),
        )
        return Response(EstimationSessionSerializer(session).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        session = self.get_object()
        approve_estimation_session(session, request.user)
        log_audit_event(
            action="estimation.approved",
            actor=request.user,
            organization=session.project.organization,
            request=request,
            resource_type="EstimationSession",
            resource_id=str(session.id),
        )
        return Response(EstimationSessionSerializer(session).data)


router = DefaultRouter()
router.register("sessions", EstimationSessionViewSet, basename="estimation-session")

urlpatterns = [path("", include(router.urls))]
