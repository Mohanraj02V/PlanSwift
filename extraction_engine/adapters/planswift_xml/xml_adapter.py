"""Standalone PlanSwift XMLData.XML adapter."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from extraction_engine.core.extraction_context import ExtractionContext
from extraction_engine.core.extraction_registry import ExtractionRegistry
from extraction_engine.core.extraction_result import CanonicalProject
from extraction_engine.core.source_manifest import SourceManifest
from extraction_engine.parsers.archive_parser import inspect_archive_manifest, open_xml_stream
from extraction_engine.parsers.metadata_parser import enrich_project_and_pages
from extraction_engine.parsers.relationship_parser import build_relationships_and_assemblies
from extraction_engine.parsers.xml_parser import parse_xmldata_stream


class PlanSwiftXMLAdapter:
    """Reads standalone XMLData.XML project files strictly read-only."""

    adapter_name = "planswift_xml_stream"
    adapter_version = "1.0.0"

    def __init__(self, registry: ExtractionRegistry | None = None) -> None:
        self.registry = registry or ExtractionRegistry()

    def can_handle(self, source_path: Path | None = None, payload: dict[str, Any] | None = None) -> bool:
        return source_path is not None and source_path.is_file() and source_path.suffix.lower() == ".xml"

    def inspect_source(self, source_path: Path, ctx: ExtractionContext) -> SourceManifest:
        return inspect_archive_manifest(source_path, ctx.config)

    def extract(self, ctx: ExtractionContext, manifest: SourceManifest | None = None) -> CanonicalProject:
        if ctx.source_path is None:
            raise ValueError("ExtractionContext.source_path is required for PlanSwiftXMLAdapter.")
        active_manifest = manifest or self.inspect_source(ctx.source_path, ctx)
        with open_xml_stream(ctx.source_path, active_manifest) as stream:
            project = parse_xmldata_stream(stream, ctx.source_path.name, ctx, registry=self.registry)
        project.source_manifest = active_manifest
        enrich_project_and_pages(project, active_manifest)
        build_relationships_and_assemblies(project)
        return project
