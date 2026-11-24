"""Secure ProjectSource registration & streaming multipart PlanSwift ZIP upload endpoints."""

from __future__ import annotations

import hashlib
import os
import re
import uuid
from pathlib import Path

from django.conf import settings
from rest_framework import permissions, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from apps.audit_logs.services import log_audit_event
from apps.background_jobs.tasks import dispatch_extraction_run
from apps.extraction.models import ExtractionRun
from apps.extraction.views import ExtractionRunSerializer
from apps.organizations.models import OrganizationMember
from apps.permissions.rbac import IsOrgEditor, IsOrgMember, get_user_org_ids
from apps.project_sources.models import ProjectSource
from apps.projects.models import Project
from apps.source_inventory.models import SourceFile
from extraction_engine.core.extraction_context import ExtractionConfig, SecurityValidationError
from extraction_engine.parsers.archive_parser import inspect_archive_manifest

_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._ -]+")


class ProjectSourceSerializer(serializers.ModelSerializer):
    # Accept source_path only on write (for pre-mounted server batch registration); NEVER expose internal filesystem paths
    source_path = serializers.CharField(write_only=True, required=False, allow_blank=True)

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

    def to_representation(self, instance):
        data = super().to_representation(instance)
        summary = dict(data.get("manifest_summary") or {})
        summary.pop("source_path", None)
        data["manifest_summary"] = summary
        return data


def _persist_source_and_inventory(project: Project, source_kind: str, manifest, user, request, display_name: str | None = None) -> ProjectSource:
    clean_name = display_name or manifest.source_name
    manifest_summary = manifest.model_dump(exclude={"entries"})
    manifest_summary.pop("source_path", None)
    manifest_summary["source_name"] = clean_name

    source_obj = ProjectSource.objects.create(
        project=project,
        source_kind=source_kind,
        source_path=manifest.source_path,
        source_name=clean_name,
        actual_extension=manifest.actual_extension,
        magic_bytes_hex=manifest.magic_bytes_hex,
        container_format=manifest.container_format,
        file_size_bytes=manifest.file_size_bytes,
        source_sha256=manifest.source_sha256,
        is_read_only=True,
        manifest_summary=manifest_summary,
        registered_by=user,
    )

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
        ],
        batch_size=500,
    )

    log_audit_event(
        action="project_source.registered",
        actor=user,
        organization=project.organization,
        request=request,
        resource_type="ProjectSource",
        resource_id=str(source_obj.id),
        metadata={"sha256": manifest.source_sha256, "total_entries": manifest.total_entries, "source_kind": source_kind},
    )
    return source_obj


class ProjectSourceViewSet(viewsets.ModelViewSet):
    serializer_class = ProjectSourceSerializer
    filterset_fields = ["project", "container_format", "source_kind"]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_queryset(self):
        org_ids = get_user_org_ids(self.request.user)
        return ProjectSource.objects.filter(project__organization_id__in=org_ids).select_related("project", "project__organization")

    def get_permissions(self):
        if self.action in ("create", "upload", "update", "partial_update", "destroy", "inspect_source"):
            return [permissions.IsAuthenticated(), IsOrgEditor()]
        return [permissions.IsAuthenticated(), IsOrgMember()]

    def _check_project_editor(self, request, project_id):
        project = Project.objects.filter(id=project_id).select_related("organization").first()
        if not project:
            return None, Response({"detail": "Project not found."}, status=status.HTTP_404_NOT_FOUND)
        if not OrganizationMember.objects.filter(
            organization=project.organization,
            user=request.user,
            is_active=True,
            role__in=IsOrgEditor.ALLOWED_ROLES,
        ).exists():
            return None, Response({"detail": "Forbidden."}, status=status.HTTP_403_FORBIDDEN)
        return project, None

    def create(self, request, *args, **kwargs):
        project, err_resp = self._check_project_editor(request, request.data.get("project"))
        if err_resp is not None:
            return err_resp

        raw_path = (request.data.get("source_path") or "").strip()
        if not raw_path:
            raw_path = settings.PLANSWIFT_DEFAULT_SOURCE_PATH

        allowed_roots = tuple(Path(r) for r in settings.ALLOWED_SOURCE_ROOTS) + (
            Path(settings.EXTRACTION_WORK_DIR).resolve(),
        )
        cfg = ExtractionConfig(
            allowed_source_roots=allowed_roots,
            max_upload_bytes=int(getattr(settings, "MAX_UPLOAD_ZIP_BYTES", 1024 * 1024 * 1024)),
        )
        try:
            manifest = inspect_archive_manifest(Path(raw_path), config=cfg)
        except (FileNotFoundError, SecurityValidationError, OSError) as exc:
            return Response({"detail": f"Source inspection failed: {exc}"}, status=status.HTTP_400_BAD_REQUEST)

        source_obj = _persist_source_and_inventory(
            project=project,
            source_kind=request.data.get("source_kind", ProjectSource.SourceKind.LOCAL_PATH),
            manifest=manifest,
            user=request.user,
            request=request,
        )
        return Response(ProjectSourceSerializer(source_obj).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"], url_path="upload", parser_classes=[MultiPartParser, FormParser])
    def upload(self, request):
        """Stream an uploaded PlanSwift .zip/.SwiftJob file safely to isolated upload storage and optionally extract."""
        uploaded = request.FILES.get("file")
        if uploaded is None:
            return Response({"detail": "Missing multipart 'file' field."}, status=status.HTTP_400_BAD_REQUEST)

        project_id = request.data.get("project")
        project, err_resp = self._check_project_editor(request, project_id)
        if err_resp is not None:
            return err_resp

        orig_name = Path(uploaded.name or "upload.SwiftJob.zip").name
        safe_name = _SAFE_FILENAME_RE.sub("_", orig_name).strip("._ ") or "project.SwiftJob.zip"
        ext = Path(safe_name).suffix.lower()
        if ext not in (".zip", ".swiftjob", ".swift", ".xml"):
            return Response(
                {"detail": f"Unsupported file extension '{ext}'. Allowed: .zip, .SwiftJob, .xml."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        max_bytes = int(getattr(settings, "MAX_UPLOAD_ZIP_BYTES", 1024 * 1024 * 1024))
        upload_dir = (Path(settings.EXTRACTION_WORK_DIR) / "uploads").resolve()
        upload_dir.mkdir(parents=True, exist_ok=True)
        dest_path = (upload_dir / f"{uuid.uuid4().hex}_{safe_name}").resolve()
        if not dest_path.is_relative_to(upload_dir):
            return Response({"detail": "Invalid upload filename."}, status=status.HTTP_400_BAD_REQUEST)

        written = 0
        sha = hashlib.sha256()
        try:
            with dest_path.open("wb") as out_fh:
                for chunk in uploaded.chunks(chunk_size=1024 * 1024):
                    written += len(chunk)
                    if written > max_bytes:
                        raise SecurityValidationError(f"Uploaded file exceeds MAX_UPLOAD_ZIP_BYTES ({max_bytes} bytes).")
                    sha.update(chunk)
                    out_fh.write(chunk)

            cfg = ExtractionConfig(
                allowed_source_roots=(upload_dir,),
                max_upload_bytes=max_bytes,
                max_archive_entries=int(getattr(settings, "EXTRACTION_MAX_ARCHIVE_ENTRIES", 10_000)),
                max_uncompressed_bytes=int(getattr(settings, "EXTRACTION_MAX_UNCOMPRESSED_BYTES", 5 * 1024 * 1024 * 1024)),
                max_compression_ratio=float(getattr(settings, "EXTRACTION_MAX_COMPRESSION_RATIO", 100.0)),
            )
            manifest = inspect_archive_manifest(dest_path, config=cfg)
        except (SecurityValidationError, OSError, ValueError) as exc:
            if dest_path.exists():
                os.unlink(dest_path)
            return Response({"detail": f"ZIP upload rejected: {exc}"}, status=status.HTTP_400_BAD_REQUEST)

        source_obj = _persist_source_and_inventory(
            project=project,
            source_kind=ProjectSource.SourceKind.UPLOADED_ARCHIVE,
            manifest=manifest,
            user=request.user,
            request=request,
            display_name=safe_name,
        )

        auto_extract_raw = str(request.data.get("auto_extract", "true")).strip().lower()
        auto_extract = auto_extract_raw in ("true", "1", "yes", "")

        run_data = None
        if auto_extract:
            run = ExtractionRun.objects.create(
                project=project,
                project_source=source_obj,
                triggered_by=request.user,
                status=ExtractionRun.Status.QUEUED,
            )
            log_audit_event(
                action="extraction.started",
                actor=request.user,
                organization=project.organization,
                request=request,
                resource_type="ExtractionRun",
                resource_id=str(run.id),
                metadata={"upload_source_id": str(source_obj.id)},
            )
            dispatch_extraction_run(run, request.user)
            run.refresh_from_db()
            run_data = ExtractionRunSerializer(run).data

        return Response(
            {
                "source": ProjectSourceSerializer(source_obj).data,
                "extraction_run": run_data,
            },
            status=status.HTTP_201_CREATED,
        )
