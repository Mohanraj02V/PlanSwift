from __future__ import annotations

from rest_framework import permissions, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.audit_logs.services import log_audit_event
from apps.background_jobs.tasks import dispatch_extraction_run
from apps.extraction.models import ExtractionError, ExtractionEvent, ExtractionRun
from apps.organizations.models import OrganizationMember
from apps.permissions.rbac import IsOrgEditor, IsOrgMember, get_user_org_ids
from apps.project_sources.models import ProjectSource
from apps.projects.models import Project


class ExtractionEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExtractionEvent
        fields = ["id", "stage", "progress_pct", "message", "created_at"]


class ExtractionErrorSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExtractionError
        fields = ["id", "stage", "code", "message", "recoverable", "created_at"]


class ExtractionRunSerializer(serializers.ModelSerializer):
    events = ExtractionEventSerializer(many=True, read_only=True)
    errors = ExtractionErrorSerializer(many=True, read_only=True)
    project_name = serializers.CharField(source="project.name", read_only=True)

    class Meta:
        model = ExtractionRun
        fields = [
            "id",
            "project",
            "project_name",
            "project_version",
            "project_source",
            "status",
            "progress_pct",
            "adapter_used",
            "parser_version",
            "source_sha256",
            "deterministic_digest_sha256",
            "duration_seconds",
            "peak_memory_mb",
            "cancel_requested",
            "summary",
            "started_at",
            "finished_at",
            "created_at",
            "events",
            "errors",
        ]
        read_only_fields = [
            "id",
            "project_name",
            "project_version",
            "status",
            "progress_pct",
            "adapter_used",
            "parser_version",
            "source_sha256",
            "deterministic_digest_sha256",
            "duration_seconds",
            "peak_memory_mb",
            "cancel_requested",
            "summary",
            "started_at",
            "finished_at",
            "created_at",
            "events",
            "errors",
        ]


class ExtractionRunViewSet(viewsets.ModelViewSet):
    serializer_class = ExtractionRunSerializer
    filterset_fields = ["project", "status"]

    def get_queryset(self):
        org_ids = get_user_org_ids(self.request.user)
        return (
            ExtractionRun.objects.filter(project__organization_id__in=org_ids)
            .select_related("project", "project__organization", "project_source", "project_version")
            .prefetch_related("events", "errors")
        )

    def get_permissions(self):
        if self.action in ("create", "cancel", "destroy"):
            return [permissions.IsAuthenticated(), IsOrgEditor()]
        return [permissions.IsAuthenticated(), IsOrgMember()]

    def create(self, request, *args, **kwargs):
        project_id = request.data.get("project")
        source_id = request.data.get("project_source")
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

        source = (
            ProjectSource.objects.filter(id=source_id, project=project).first()
            if source_id
            else ProjectSource.objects.filter(project=project).order_by("-created_at").first()
        )
        if not source:
            return Response({"detail": "No registered ProjectSource found for project."}, status=status.HTTP_400_BAD_REQUEST)

        run = ExtractionRun.objects.create(
            project=project,
            project_source=source,
            triggered_by=request.user,
            status=ExtractionRun.Status.PENDING,
        )
        log_audit_event(
            action="extraction.started",
            actor=request.user,
            organization=project.organization,
            request=request,
            resource_type="ExtractionRun",
            resource_id=str(run.id),
        )
        dispatch_extraction_run(run, request.user)
        run.refresh_from_db()
        return Response(ExtractionRunSerializer(run).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        run = self.get_object()
        run.cancel_requested = True
        if run.status in (ExtractionRun.Status.PENDING, ExtractionRun.Status.QUEUED):
            run.status = ExtractionRun.Status.CANCELLED
        run.save(update_fields=["cancel_requested", "status"])
        return Response(ExtractionRunSerializer(run).data)

    @action(detail=True, methods=["get"], url_path="logs")
    def logs(self, request, pk=None):
        """Return ordered extraction stage events and error logs for an ExtractionRun."""
        run = self.get_object()
        return Response(
            {
                "run_id": str(run.id),
                "status": run.status,
                "progress_pct": run.progress_pct,
                "duration_seconds": run.duration_seconds,
                "peak_memory_mb": run.peak_memory_mb,
                "events": ExtractionEventSerializer(run.events.all(), many=True).data,
                "errors": ExtractionErrorSerializer(run.errors.all(), many=True).data,
            }
        )
