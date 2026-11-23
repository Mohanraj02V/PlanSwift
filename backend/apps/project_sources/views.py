from __future__ import annotations

from pathlib import Path

from django.conf import settings
from rest_framework import permissions, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.audit_logs.services import log_audit_event
from apps.organizations.models import OrganizationMember
from apps.permissions.rbac import IsOrgEditor, IsOrgMember, get_user_org_ids
from apps.project_sources.models import ProjectSource
from apps.projects.models import Project
from apps.source_inventory.models import SourceFile
from extraction_engine.core.extraction_context import ExtractionConfig, SecurityValidationError
from extraction_engine.parsers.archive_parser import inspect_archive_manifest


class ProjectSourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectSource
        fields = [
            "id",
            "project",
            "source_kind",
            "source_path",
            "source_name",
            "actual_extension",
            "magic_bytes_hex",
            "container_format",
            "file_size_bytes",
            "source_sha256",
            "is_read_only",
            "manifest_summary",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "source_name",
            "actual_extension",
            "magic_bytes_hex",
            "container_format",
            "file_size_bytes",
            "source_sha256",
            "is_read_only",
            "manifest_summary",
            "created_at",
        ]


class ProjectSourceViewSet(viewsets.ModelViewSet):
    serializer_class = ProjectSourceSerializer
    filterset_fields = ["project", "container_format", "source_kind"]

    def get_queryset(self):
        org_ids = get_user_org_ids(self.request.user)
        return ProjectSource.objects.filter(project__organization_id__in=org_ids).select_related("project", "project__organization")

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "destroy", "inspect_source"):
            return [permissions.IsAuthenticated(), IsOrgEditor()]
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

        raw_path = (request.data.get("source_path") or "").strip()
        if not raw_path:
            raw_path = settings.PLANSWIFT_DEFAULT_SOURCE_PATH

        allowed_roots = tuple(Path(r) for r in settings.ALLOWED_SOURCE_ROOTS)
        cfg = ExtractionConfig(allowed_source_roots=allowed_roots)
        try:
            manifest = inspect_archive_manifest(Path(raw_path), config=cfg)
        except (FileNotFoundError, SecurityValidationError, OSError) as exc:
            return Response({"detail": f"Source inspection failed: {exc}"}, status=status.HTTP_400_BAD_REQUEST)

        source_obj = ProjectSource.objects.create(
            project=project,
            source_kind=request.data.get("source_kind", ProjectSource.SourceKind.LOCAL_PATH),
            source_path=manifest.source_path,
            source_name=manifest.source_name,
            actual_extension=manifest.actual_extension,
            magic_bytes_hex=manifest.magic_bytes_hex,
            container_format=manifest.container_format,
            file_size_bytes=manifest.file_size_bytes,
            source_sha256=manifest.source_sha256,
            is_read_only=True,
            manifest_summary=manifest.model_dump(exclude={"entries"}),
            registered_by=request.user,
        )

        # Persist source inventory entries idempotently
        SourceFile.objects.bulk_create(
            [
                SourceFile(
                    project_source=source_obj,
                    relative_path=e.relative_path,
                    file_name=e.file_name,
                    extension=e.extension,
                    compressed_size=e.compressed_size,
                    uncompressed_size=e.uncompressed_size,
                    compression_ratio=e.compression_ratio,
                    crc32=e.crc32,
                    is_xml_data=e.is_xml_data,
                    is_raster_asset=e.is_raster_asset,
                    asset_guid=e.asset_guid or "",
                    security_status=e.security_status,
                )
                for e in manifest.entries
            ]
        )

        log_audit_event(
            action="project_source.registered",
            actor=request.user,
            organization=project.organization,
            request=request,
            resource_type="ProjectSource",
            resource_id=str(source_obj.id),
            metadata={"sha256": manifest.source_sha256, "total_entries": manifest.total_entries},
        )
        return Response(ProjectSourceSerializer(source_obj).data, status=status.HTTP_201_CREATED)
