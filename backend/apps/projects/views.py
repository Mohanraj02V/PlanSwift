from __future__ import annotations

from django.db import transaction
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.audit_logs.services import log_audit_event
from apps.permissions.rbac import IsAdminOnly, IsOrgMember, get_user_org_ids, is_admin
from apps.projects.models import Project, ProjectPage, ProjectVersion
from apps.projects.serializers import ProjectPageSerializer, ProjectSerializer


class ProjectViewSet(viewsets.ModelViewSet):
    serializer_class = ProjectSerializer
    filterset_fields = ["organization", "measurement_system", "native_guid"]
    search_fields = ["name", "description", "native_guid"]
    ordering_fields = ["created_at", "name", "updated_at"]

    def get_queryset(self):
        org_ids = get_user_org_ids(self.request.user)
        return (
            Project.objects.filter(organization_id__in=org_ids)
            .select_related("organization")
            .prefetch_related("versions")
        )

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "destroy"):
            return [permissions.IsAuthenticated(), IsAdminOnly()]
        return [permissions.IsAuthenticated(), IsOrgMember()]

    def create(self, request, *args, **kwargs):
        org_id = request.data.get("organization")
        if not org_id or not is_admin(request.user, org_id):
            return Response({"detail": "Organization Admin privileges required to create projects."}, status=status.HTTP_403_FORBIDDEN)
        return super().create(request, *args, **kwargs)

    @transaction.atomic
    def perform_create(self, serializer):
        project = serializer.save(created_by=self.request.user)
        ProjectVersion.objects.create(project=project, version_number=1, is_current=True)
        log_audit_event(
            action="project.created",
            actor=self.request.user,
            organization=project.organization,
            request=self.request,
            resource_type="Project",
            resource_id=str(project.id),
            metadata={"name": project.name},
        )

    @action(detail=True, methods=["get"], url_path="pages")
    def pages(self, request, pk=None):
        project = self.get_object()
        ver = project.versions.filter(is_current=True).first()
        qs = ProjectPage.objects.filter(project_version=ver) if ver else ProjectPage.objects.none()
        page = self.paginate_queryset(qs)
        if page is not None:
            return self.get_paginated_response(ProjectPageSerializer(page, many=True).data)
        return Response(ProjectPageSerializer(qs, many=True).data)
