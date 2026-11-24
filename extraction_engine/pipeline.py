"""End-to-end 100% standalone PlanSwift ZIP extraction, geometry, formula, and quantity pipeline."""

from __future__ import annotations

import hashlib
import json
import time
import tracemalloc
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from extraction_engine.adapters.planswift_package.package_adapter import PlanSwiftPackageAdapter
from extraction_engine.adapters.planswift_xml.xml_adapter import PlanSwiftXMLAdapter
from extraction_engine.calculators.quantity_engine import compute_project_quantities
from extraction_engine.core.extraction_context import (
    ExtractionCancelledError,
    ExtractionConfig,
    ExtractionContext,
    ExtractionStage,
)
from extraction_engine.core.extraction_result import (
    CanonicalProject,
    ExtractionErrorRecord,
    ExtractionEventRecord,
    ExtractionReport,
)
from extraction_engine.core.source_manifest import SourceManifest
from extraction_engine.normalizers.geometry_normalizer import normalize_project_geometry
from extraction_engine.normalizers.property_normalizer import normalize_project_properties
from extraction_engine.parsers.formula_parser import resolve_and_evaluate_formulas
from extraction_engine.reconciliation.standalone_reconciliation import reconcile_standalone_project
from extraction_engine.validators.project_validator import validate_canonical_project


def compute_project_deterministic_digest(project: CanonicalProject) -> str:
    """Compute a deterministic SHA-256 digest over canonical objects, properties, geometries, and relationships."""
    hasher = hashlib.sha256()
    header = {
        "native_guid": project.native_guid,
        "name": project.name,
        "pages": len(project.pages),
        "objects": len(project.objects),
        "relationships": len(project.relationships),
    }
    hasher.update(json.dumps(header, sort_keys=True).encode("utf-8"))
    for obj in project.objects:
        obj_sig = {
            "guid": obj.native_guid,
            "cls": obj.native_class,
            "name": obj.name,
            "parent": obj.parent_guid,
            "props": [(p.native_property_guid, p.name, p.raw_value) for p in obj.properties],
            "points": [[(pt.raw_x, pt.raw_y, pt.point_type) for pt in g.points] for g in obj.geometries],
        }
        hasher.update(json.dumps(obj_sig, sort_keys=True).encode("utf-8"))
    return hasher.hexdigest()


class ExtractionPipeline:
    """Orchestrates standalone PlanSwift ZIP validation, parsing, geometry, formula evaluation, quantities, and validation."""

    def __init__(self, config: ExtractionConfig | None = None) -> None:
        self.config = config or ExtractionConfig()
        self.package_adapter = PlanSwiftPackageAdapter()
        self.xml_adapter = PlanSwiftXMLAdapter()

    def _select_adapter(self, source_path: Path):
        if self.xml_adapter.can_handle(source_path):
            return self.xml_adapter
        if self.package_adapter.can_handle(source_path):
            return self.package_adapter
        return self.package_adapter

    def _write_checkpoint(self, ctx: ExtractionContext, stage: ExtractionStage, extra: dict[str, Any] | None = None) -> None:
        if not ctx.config.checkpoint_dir:
            return
        ctx.config.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        cp_file = ctx.config.checkpoint_dir / f"{ctx.run_id}.checkpoint.json"
        payload = {
            "run_id": ctx.run_id,
            "stage": stage.value,
            "completed_stages": ctx.completed_stages,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "extra": extra or {},
        }
        cp_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def run(
        self,
        source_path: Path,
        ctx: ExtractionContext | None = None,
        track_memory: bool = True,
    ) -> tuple[CanonicalProject, ExtractionReport]:
        """Run the full standalone ZIP extraction pipeline and return (CanonicalProject, ExtractionReport)."""
        active_ctx = ctx or ExtractionContext(source_path=source_path, config=self.config)
        active_ctx.source_path = source_path
        t0 = time.perf_counter()
        tracing_here = False
        if track_memory and not tracemalloc.is_tracing():
            tracemalloc.start()
            tracing_here = True

        adapter = self._select_adapter(source_path)
        manifest: SourceManifest | None = None
        project: CanonicalProject | None = None
        reconciliation: dict[str, Any] | None = None
        validation = None

        try:
            active_ctx.transition(ExtractionStage.VALIDATING_ARCHIVE, 10, f"Validating archive '{source_path.name}'.")
            manifest = adapter.inspect_source(source_path, active_ctx)
            self._write_checkpoint(active_ctx, ExtractionStage.VALIDATING_ARCHIVE, {"sha256": manifest.source_sha256})

            active_ctx.transition(
                ExtractionStage.INSPECTING_ARCHIVE,
                20,
                f"Inventory complete: {manifest.total_entries} entries, format={manifest.detected_project_version}, encoding={manifest.detected_xml_encoding}.",
            )
            self._write_checkpoint(active_ctx, ExtractionStage.INSPECTING_ARCHIVE)

            active_ctx.transition(ExtractionStage.PARSING_XML, 35, f"Streaming native XML via {adapter.adapter_name}.")
            project = adapter.extract(active_ctx, manifest=manifest)
            self._write_checkpoint(active_ctx, ExtractionStage.PARSING_XML, {"objects": len(project.objects)})

            active_ctx.transition(
                ExtractionStage.INTERPRETING_OBJECTS,
                48,
                f"Interpreted {len(project.objects)} objects across {len(project.pages)} pages ({len(project.unsupported_objects)} unsupported preserved raw).",
            )

            active_ctx.transition(
                ExtractionStage.RECONSTRUCTING_RELATIONSHIPS,
                58,
                f"Built {len(project.relationships)} relationships and {len(project.assemblies)} assemblies.",
            )

            active_ctx.transition(
                ExtractionStage.PROCESSING_GEOMETRY,
                68,
                "Normalizing properties and calibrating native DigitizerData geometry from ScaleX/ScaleY.",
            )
            normalize_project_properties(project)
            normalize_project_geometry(project)

            active_ctx.transition(
                ExtractionStage.EVALUATING_FORMULAS,
                78,
                "Building dependency graph and safely evaluating native PlanSwift formulas.",
            )
            resolve_and_evaluate_formulas(project)

            active_ctx.transition(
                ExtractionStage.CALCULATING_QUANTITIES,
                86,
                "Computing standalone calibrated and calculated quantities with full provenance.",
            )
            compute_project_quantities(project)
            project.deterministic_digest_sha256 = compute_project_deterministic_digest(project)

            active_ctx.transition(ExtractionStage.RECONCILING_SOURCES, 92, "Running standalone internal consistency checks.")
            reconciliation = reconcile_standalone_project(project)

            active_ctx.transition(ExtractionStage.VALIDATING, 96, "Validating ZIP, metadata, hierarchy, geometry, formulas, and quantities.")
            validation = validate_canonical_project(project)

            final_stage = ExtractionStage.COMPLETED
            msg = "Standalone PlanSwift ZIP extraction completed."
            if project.unsupported_classes or (manifest and manifest.warnings):
                final_stage = ExtractionStage.COMPLETED_WITH_WARNINGS
                msg = "Standalone extraction completed with warnings/unsupported objects preserved."
            active_ctx.transition(final_stage, 100, msg)
            # Keep COMPLETED string status for API clients while exposing warnings in validation & report
            final_status = ExtractionStage.COMPLETED.value
        except ExtractionCancelledError as exc:
            active_ctx.record_error(active_ctx.current_stage, "CANCELLED", str(exc), recoverable=True)
            final_status = ExtractionStage.CANCELLED.value
            raise
        except Exception as exc:
            active_ctx.current_stage = ExtractionStage.FAILED
            active_ctx.record_error(active_ctx.current_stage, type(exc).__name__, str(exc), recoverable=False)
            raise
        finally:
            peak_mb = 0.0
            if tracing_here:
                _, peak_bytes = tracemalloc.get_traced_memory()
                peak_mb = round(peak_bytes / (1024 * 1024), 2)
                tracemalloc.stop()

        duration = round(time.perf_counter() - t0, 3)
        report = ExtractionReport(
            run_id=active_ctx.run_id,
            adapter_used=adapter.adapter_name,
            parser_version=active_ctx.config.parser_version,
            status=final_status,
            started_at=active_ctx.started_at.isoformat(),
            finished_at=datetime.now(timezone.utc).isoformat(),
            duration_seconds=duration,
            peak_memory_mb=peak_mb,
            project_guid=project.native_guid if project else None,
            project_name=project.name if project else None,
            validation=validation,
            reconciliation_summary=reconciliation,
            events=[ExtractionEventRecord(**e) for e in active_ctx.events],
            errors=[ExtractionErrorRecord(**e) for e in active_ctx.errors],
        )
        assert project is not None
        return project, report
