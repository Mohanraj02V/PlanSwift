"""Management command to bootstrap a local dev organization, register project 4.SwiftJob.zip, and run extraction."""

from __future__ import annotations

import os
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.estimation.services import generate_estimation_session
from apps.extraction.models import ExtractionRun
from apps.extraction.services import ExtractionOrchestrationService
from apps.organizations.models import Organization, OrganizationMember
from apps.project_sources.models import ProjectSource
from apps.projects.models import Project
from apps.source_inventory.models import SourceFile
from extraction_engine.core.extraction_context import ExtractionConfig
from extraction_engine.parsers.archive_parser import inspect_archive_manifest


class Command(BaseCommand):
    help = "Development-only command to seed a local dev Admin/Org and extract a sample PlanSwift package."

    def add_arguments(self, parser):
        parser.add_argument("--email", default="estimator@vortexen.local")
        parser.add_argument("--password", default=os.environ.get("DEV_ADMIN_PASSWORD", ""))
        parser.add_argument("--source", default=getattr(settings, "PLANSWIFT_DEFAULT_SOURCE_PATH", ""))

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("seed_demo_and_extract is strictly limited to local development (DEBUG=True).")
        password = (options.get("password") or "").strip()
        if len(password) < 10:
            raise CommandError(
                "Pass --password (min 10 chars) or set DEV_ADMIN_PASSWORD in your environment before running."
            )

        User = get_user_model()
        user, created = User.objects.get_or_create(
            email=options["email"],
            defaults={"full_name": "Organization Admin", "job_title": "Principal Estimator"},
        )
        if created:
            user.set_password(password)
            user.save()

        org, _ = Organization.objects.get_or_create(slug="vortexen-demo", defaults={"name": "Vortexen Engineering", "created_by": user})
        OrganizationMember.objects.get_or_create(organization=org, user=user, defaults={"role": OrganizationMember.Role.ADMIN})

        project, _ = Project.objects.get_or_create(
            organization=org,
            name="project 4",
            defaults={"created_by": user},
        )

        source_path = Path(options["source"])
        if not source_path.exists():
            self.stdout.write(self.style.WARNING(f"Source file not found: {source_path}"))
            return

        cfg = ExtractionConfig(allowed_source_roots=tuple(Path(r) for r in settings.ALLOWED_SOURCE_ROOTS))
        manifest = inspect_archive_manifest(source_path, cfg)

        source_obj, src_created = ProjectSource.objects.get_or_create(
            project=project,
            source_sha256=manifest.source_sha256,
            defaults={
                "source_kind": ProjectSource.SourceKind.LOCAL_PATH,
                "source_path": manifest.source_path,
                "source_name": manifest.source_name,
                "actual_extension": manifest.actual_extension,
                "magic_bytes_hex": manifest.magic_bytes_hex,
                "container_format": manifest.container_format,
                "file_size_bytes": manifest.file_size_bytes,
                "is_read_only": True,
                "manifest_summary": manifest.model_dump(exclude={"entries"}),
                "registered_by": user,
            },
        )
        if src_created:
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

        run = ExtractionRun.objects.create(project=project, project_source=source_obj, triggered_by=user)
        run = ExtractionOrchestrationService.execute_run(str(run.id))
        if not project.estimation_sessions.exists():
            generate_estimation_session(project, user)

        self.stdout.write(self.style.SUCCESS(f"Seed & Extraction {run.status}: {run.summary}"))
