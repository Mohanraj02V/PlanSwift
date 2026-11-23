"""Core protocols and abstract interfaces for extraction adapters, parsers, and exporters."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from extraction_engine.core.extraction_context import ExtractionContext
from extraction_engine.core.extraction_result import CanonicalProject, ExtractionReport
from extraction_engine.core.source_manifest import SourceManifest


@runtime_checkable
class SourceAdapter(Protocol):
    """Protocol implemented by every PlanSwift source extraction adapter."""

    adapter_name: str
    adapter_version: str

    def can_handle(self, source_path: Path | None = None, payload: dict[str, Any] | None = None) -> bool:
        """Return True if this adapter can process the provided source or payload."""
        ...

    def inspect_source(self, source_path: Path, ctx: ExtractionContext) -> SourceManifest:
        """Safely inspect source container and produce a SourceManifest without modifying source."""
        ...

    def extract(self, ctx: ExtractionContext, manifest: SourceManifest | None = None) -> CanonicalProject:
        """Extract canonical native objects without rendering images or invoking LLMs."""
        ...


@runtime_checkable
class Exporter(Protocol):
    """Protocol implemented by all canonical project exporters."""

    format_name: str

    def export(self, project: CanonicalProject, output_path: Path, report: ExtractionReport | None = None) -> Path:
        """Export the canonical project model to the requested output path."""
        ...
