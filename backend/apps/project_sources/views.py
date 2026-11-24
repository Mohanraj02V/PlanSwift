"""Secure ProjectSource registration & streaming multipart PlanSwift ZIP upload endpoints."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import uuid
import zipfile
from datetime import datetime, timezone
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
from extraction_engine.adapters.dxf.dxf_document_reader import inspect_dxf_manifest
from extraction_engine.adapters.ifc.ifc_document_reader import inspect_ifc_manifest
from extraction_engine.core.extraction_context import ExtractionConfig, SecurityValidationError
from extraction_engine.core.format_detector import UnsupportedFormatError, detect_source_format
from extraction_engine.parsers.archive_parser import inspect_archive_manifest, validate_archive_member_path

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
            "source_format",
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
            "source_format",
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
        source_format=manifest.container_format,
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

    now_utc = datetime.now(timezone.utc)
    actor_name = getattr(user, "full_name", "") or getattr(user, "email", "")
    actor_email = getattr(user, "email", "")
    upload_meta = {
        "file_name": clean_name,
        "file_size_bytes": manifest.file_size_bytes,
        "source_format": manifest.container_format,
        "source_kind": source_kind,
        "sha256": manifest.source_sha256,
        "total_entries": manifest.total_entries,
        "project_id": str(project.id),
        "project_name": project.name,
        "uploaded_by_email": actor_email,
        "uploaded_by_name": actor_name,
        "uploaded_date": now_utc.strftime("%Y-%m-%d"),
        "uploaded_time": now_utc.strftime("%H:%M:%S UTC"),
        "uploaded_at_iso": now_utc.isoformat(),
    }

    log_audit_event(
        action="project_source.registered",
        actor=user,
        organization=project.organization,
        request=request,
        resource_type="ProjectSource",
        resource_id=str(source_obj.id),
        metadata=upload_meta,
    )
    log_audit_event(
        action="file.uploaded",
        actor=user,
        organization=project.organization,
        request=request,
        resource_type="ProjectSource",
        resource_id=str(source_obj.id),
        metadata=upload_meta,
    )
    return source_obj


_CAD_BIM_BUNDLE_EXTS = (".dxf", ".ifc")


def _is_cad_bim_bundle_member(rel_path: str) -> bool:
    """Return True for valid .dxf/.ifc members inside a ZIP, ignoring macOS metadata entries."""
    norm = rel_path.replace("\\", "/")
    parts = [p for p in norm.split("/") if p]
    if not parts:
        return False
    if any(p == "__MACOSX" for p in parts) or parts[-1].startswith("._"):
        return False
    return Path(parts[-1]).suffix.lower() in _CAD_BIM_BUNDLE_EXTS


def _extract_cad_bim_zip_bundle(
    zip_path: Path,
    upload_dir: Path,
    cfg: ExtractionConfig,
) -> tuple[Path, list[tuple[str, Path, str]]]:
    """Safely stream .dxf and .ifc files out of a validated ZIP bundle into an isolated workspace directory."""
    bundle_dir = (upload_dir / f"bundle_{uuid.uuid4().hex}").resolve()
    bundle_dir.mkdir(parents=True, exist_ok=True)
    extracted: list[tuple[str, Path, str]] = []
    cumulative_bytes = 0

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            members = sorted(
                (info for info in zf.infolist() if not info.is_dir() and _is_cad_bim_bundle_member(info.filename)),
                key=lambda info: info.filename.lower(),
            )
            for idx, info in enumerate(members, start=1):
                clean_rel = validate_archive_member_path(info.filename)
                member_base = Path(clean_rel).name
                safe_member = _SAFE_FILENAME_RE.sub("_", member_base).strip("._ ") or f"item_{idx}"
                ext = Path(safe_member).suffix.lower()
                if ext not in _CAD_BIM_BUNDLE_EXTS:
                    continue
                per_file_limit = cfg.dxf_max_file_bytes if ext == ".dxf" else cfg.ifc_max_file_bytes
                target = (bundle_dir / f"{idx:04d}_{safe_member}").resolve()
                if not target.is_relative_to(bundle_dir):
                    raise SecurityValidationError(f"Bundle member escapes target folder: {info.filename}")

                file_written = 0
                with zf.open(info, "r") as src_fh, target.open("wb") as out_fh:
                    while True:
                        chunk = src_fh.read(1024 * 1024)
                        if not chunk:
                            break
                        file_written += len(chunk)
                        cumulative_bytes += len(chunk)
                        if file_written > per_file_limit:
                            raise SecurityValidationError(
                                f"Bundle file '{member_base}' exceeds size limit ({per_file_limit} bytes)."
                            )
                        if cumulative_bytes > cfg.max_uncompressed_bytes:
                            raise SecurityValidationError(
                                f"Bundle uncompressed bytes exceed limit ({cfg.max_uncompressed_bytes} bytes)."
                            )
                        out_fh.write(chunk)
                extracted.append((member_base, target, ext))
    except Exception:
        shutil.rmtree(bundle_dir, ignore_errors=True)
        raise

    return bundle_dir, extracted


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
            dxf_max_file_bytes=int(getattr(settings, "MAX_UPLOAD_DXF_BYTES", 512 * 1024 * 1024)),
            ifc_max_file_bytes=int(getattr(settings, "MAX_UPLOAD_IFC_BYTES", 1024 * 1024 * 1024)),
        )
        try:
            src_p = Path(raw_path)
            fmt = detect_source_format(src_p)
            if fmt in ("dxf_ascii", "dxf_binary"):
                manifest = inspect_dxf_manifest(src_p, config=cfg)
            elif fmt == "ifc_step":
                manifest = inspect_ifc_manifest(src_p, config=cfg)
            else:
                manifest = inspect_archive_manifest(src_p, config=cfg)
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
        """Stream an uploaded PlanSwift (.zip/.SwiftJob/.xml), DXF (.dxf), or IFC (.ifc) file safely and extract."""
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
        if ext not in (".zip", ".swiftjob", ".swift", ".xml", ".dxf", ".ifc"):
            return Response(
                {"detail": f"Unsupported file extension '{ext}'. Allowed: .zip, .SwiftJob, .xml, .dxf, .ifc."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if ext == ".dxf":
            max_bytes = int(getattr(settings, "MAX_UPLOAD_DXF_BYTES", 512 * 1024 * 1024))
        elif ext == ".ifc":
            max_bytes = int(getattr(settings, "MAX_UPLOAD_IFC_BYTES", 1024 * 1024 * 1024))
        else:
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
                        raise SecurityValidationError(f"Uploaded file exceeds size limit ({max_bytes} bytes).")
                    sha.update(chunk)
                    out_fh.write(chunk)

            cfg = ExtractionConfig(
                allowed_source_roots=(upload_dir,),
                max_upload_bytes=max_bytes,
                dxf_max_file_bytes=int(getattr(settings, "MAX_UPLOAD_DXF_BYTES", 512 * 1024 * 1024)),
                ifc_max_file_bytes=int(getattr(settings, "MAX_UPLOAD_IFC_BYTES", 1024 * 1024 * 1024)),
                max_archive_entries=int(getattr(settings, "EXTRACTION_MAX_ARCHIVE_ENTRIES", 10_000)),
                max_uncompressed_bytes=int(getattr(settings, "EXTRACTION_MAX_UNCOMPRESSED_BYTES", 5 * 1024 * 1024 * 1024)),
                max_compression_ratio=float(getattr(settings, "EXTRACTION_MAX_COMPRESSION_RATIO", 100.0)),
            )
            detected_fmt = detect_source_format(dest_path)
            if detected_fmt in ("dxf_ascii", "dxf_binary"):
                manifest = inspect_dxf_manifest(dest_path, config=cfg)
                src_kind = ProjectSource.SourceKind.UPLOADED_DXF
            elif detected_fmt == "ifc_step":
                manifest = inspect_ifc_manifest(dest_path, config=cfg)
                src_kind = ProjectSource.SourceKind.UPLOADED_IFC
            else:
                manifest = inspect_archive_manifest(dest_path, config=cfg)
                src_kind = ProjectSource.SourceKind.UPLOADED_ARCHIVE
        except (UnsupportedFormatError, SecurityValidationError, OSError, ValueError) as exc:
            if dest_path.exists():
                os.unlink(dest_path)
            now_utc = datetime.now(timezone.utc)
            log_audit_event(
                action="file.upload_rejected",
                actor=request.user,
                organization=project.organization,
                request=request,
                resource_type="Project",
                resource_id=str(project.id),
                metadata={
                    "file_name": safe_name,
                    "reason": str(exc),
                    "uploaded_by_email": request.user.email,
                    "uploaded_date": now_utc.strftime("%Y-%m-%d"),
                    "uploaded_time": now_utc.strftime("%H:%M:%S UTC"),
                },
            )
            return Response({"detail": f"File upload rejected: {exc}"}, status=status.HTTP_400_BAD_REQUEST)

        auto_extract_raw = str(request.data.get("auto_extract", "true")).strip().lower()
        auto_extract = auto_extract_raw in ("true", "1", "yes", "")
        extract_geom_raw = str(request.data.get("extract_geometry", "")).strip().lower()
        extract_geom = extract_geom_raw in ("true", "1", "yes")

        # Handle multi-file DXF / IFC ZIP bundles (archives containing .dxf/.ifc and NO PlanSwift XMLData.XML)
        if (
            detected_fmt == "planswift_package"
            and manifest.xml_entry_path is None
            and any(_is_cad_bim_bundle_member(e.relative_path) for e in manifest.entries)
        ):
            try:
                bundle_dir, extracted_items = _extract_cad_bim_zip_bundle(dest_path, upload_dir, cfg)
            except (SecurityValidationError, zipfile.BadZipFile, OSError, ValueError) as exc:
                if dest_path.exists():
                    os.unlink(dest_path)
                return Response({"detail": f"ZIP bundle extraction failed: {exc}"}, status=status.HTTP_400_BAD_REQUEST)
            finally:
                if dest_path.exists():
                    os.unlink(dest_path)

            created_sources: list[ProjectSource] = []
            created_runs: list[dict] = []
            skipped_files: list[dict[str, str]] = []

            for member_name, child_path, _ext in extracted_items:
                try:
                    child_fmt = detect_source_format(child_path)
                    if child_fmt in ("dxf_ascii", "dxf_binary"):
                        child_manifest = inspect_dxf_manifest(child_path, config=cfg)
                        child_kind = ProjectSource.SourceKind.UPLOADED_DXF
                        child_opts: dict = {}
                    elif child_fmt == "ifc_step":
                        child_manifest = inspect_ifc_manifest(child_path, config=cfg)
                        child_kind = ProjectSource.SourceKind.UPLOADED_IFC
                        child_opts = {"ifc_extract_geometry": extract_geom}
                    else:
                        raise UnsupportedFormatError(f"Unsupported bundle member format '{child_fmt}'.")
                except (UnsupportedFormatError, SecurityValidationError, OSError, ValueError) as exc:
                    if child_path.exists():
                        os.unlink(child_path)
                    skipped_files.append({"name": member_name, "reason": str(exc)})
                    continue

                child_source = _persist_source_and_inventory(
                    project=project,
                    source_kind=child_kind,
                    manifest=child_manifest,
                    user=request.user,
                    request=request,
                    display_name=member_name,
                )
                created_sources.append(child_source)
                if auto_extract:
                    run = ExtractionRun.objects.create(
                        project=project,
                        project_source=child_source,
                        triggered_by=request.user,
                        status=ExtractionRun.Status.QUEUED,
                        extraction_options=child_opts,
                    )
                    log_audit_event(
                        action="extraction.started",
                        actor=request.user,
                        organization=project.organization,
                        request=request,
                        resource_type="ExtractionRun",
                        resource_id=str(run.id),
                        metadata={"upload_source_id": str(child_source.id), "bundle_name": safe_name},
                    )
                    dispatch_extraction_run(run, request.user)
                    run.refresh_from_db()
                    created_runs.append(ExtractionRunSerializer(run).data)

            if not created_sources:
                shutil.rmtree(bundle_dir, ignore_errors=True)
                return Response(
                    {"detail": "ZIP bundle contained no valid DXF or IFC files.", "skipped_files": skipped_files},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            now_utc = datetime.now(timezone.utc)
            log_audit_event(
                action="file.bundle_uploaded",
                actor=request.user,
                organization=project.organization,
                request=request,
                resource_type="Project",
                resource_id=str(project.id),
                metadata={
                    "bundle_name": safe_name,
                    "processed_count": len(created_sources),
                    "files": [s.source_name for s in created_sources],
                    "skipped_count": len(skipped_files),
                    "uploaded_by_email": request.user.email,
                    "uploaded_by_name": request.user.full_name or request.user.email,
                    "uploaded_date": now_utc.strftime("%Y-%m-%d"),
                    "uploaded_time": now_utc.strftime("%H:%M:%S UTC"),
                },
            )

            return Response(
                {
                    "bundle": True,
                    "bundle_name": safe_name,
                    "processed_count": len(created_sources),
                    "skipped_files": skipped_files,
                    "source": ProjectSourceSerializer(created_sources[0]).data,
                    "extraction_run": created_runs[-1] if created_runs else None,
                    "sources": [ProjectSourceSerializer(s).data for s in created_sources],
                    "extraction_runs": created_runs,
                },
                status=status.HTTP_201_CREATED,
            )

        source_obj = _persist_source_and_inventory(
            project=project,
            source_kind=src_kind,
            manifest=manifest,
            user=request.user,
            request=request,
            display_name=safe_name,
        )

        ext_opts = {"ifc_extract_geometry": extract_geom} if detected_fmt == "ifc_step" else {}

        run_data = None
        if auto_extract:
            run = ExtractionRun.objects.create(
                project=project,
                project_source=source_obj,
                triggered_by=request.user,
                status=ExtractionRun.Status.QUEUED,
                extraction_options=ext_opts,
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
