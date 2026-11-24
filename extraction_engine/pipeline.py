"""End-to-end 100% standalone PlanSwift ZIP, DXF (ezdxf), and IFC (IfcOpenShell) extraction pipeline."""

from __future__ import annotations

import hashlib
import json
import os
import time
import tracemalloc
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psutil

from extraction_engine.adapters.dxf.dxf_adapter import DXFAdapter
from extraction_engine.adapters.dxf.dxf_validator import validate_dxf_project
from extraction_engine.adapters.ifc.ifc_adapter import IFCAdapter
from extraction_engine.adapters.ifc.ifc_validator import validate_ifc_project
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
from extraction_engine.core.format_detector import UnsupportedFormatError, detect_source_format
from extraction_engine.core.source_manifest import SourceManifest
from extraction_engine.normalizers.geometry_normalizer import normalize_project_geometry
from extraction_engine.normalizers.property_normalizer import normalize_project_properties
from extraction_engine.parsers.formula_parser import resolve_and_evaluate_formulas
from extraction_engine.reconciliation.standalone_reconciliation import reconcile_standalone_project
from extraction_engine.validators.project_validator import validate_canonical_project


def _current_process_rss_mb() -> float:
    try:
        rss_bytes = psutil.Process(os.getpid()).memory_info().rss
        return round(rss_bytes / (1024 * 1024), 2)
    except Exception:
        return 0.0


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


def compute_cad_deterministic_digest(project: CanonicalProject) -> str:
    """Compute deterministic SHA-256 digest over DXF/IFC source hash, options, library version, and entities."""
    cad_doc = project.cad_document
    hasher = hashlib.sha256()
    header = {
        "schema_version": project.schema_version,
        "source_system": project.source_system,
        "source_sha256": project.source_manifest.source_sha256 if project.source_manifest else "",
        "source_format": cad_doc.source_format if cad_doc else "",
        "library_name": cad_doc.library_name if cad_doc else "",
        "library_version": cad_doc.library_version if cad_doc else "",
        "extraction_options": cad_doc.extraction_options if cad_doc else {},
        "pages": len(project.pages),
        "objects": len(project.objects),
        "relationships": len(project.relationships),
    }
    hasher.update(json.dumps(header, sort_keys=True, default=str).encode("utf-8"))
    if cad_doc is not None:
        for ent in cad_doc.cad_entities:
            hasher.update(
                json.dumps(
                    {"k": ent.entity_key, "t": ent.entity_type, "l": ent.layer, "m": ent.geometry_metrics},
                    sort_keys=True,
                ).encode("utf-8")
            )
        for el in cad_doc.ifc_elements:
            hasher.update(
                json.dumps(
                    {
                        "gid": el.global_id,
                        "sid": el.step_id,
                        "cls": el.ifc_class,
                        "gs": el.geometry_summary.status,
                        "sa": el.geometry_summary.surface_area,
                        "vol": el.geometry_summary.volume,
                    },
                    sort_keys=True,
                ).encode("utf-8")
            )
    return hasher.hexdigest()


class ExtractionPipeline:
    """Orchestrates PlanSwift, DXF (ezdxf), and IFC (IfcOpenShell) extraction without cross-format leakage."""

    def __init__(self, config: ExtractionConfig | None = None) -> None:
        self.config = config or ExtractionConfig()
        self.package_adapter = PlanSwiftPackageAdapter()
        self.xml_adapter = PlanSwiftXMLAdapter()
        self.dxf_adapter = DXFAdapter()
        self.ifc_adapter = IFCAdapter()

    def _select_adapter(self, source_path: Path):
        fmt = detect_source_format(source_path)
        if fmt == "planswift_xml":
            return self.xml_adapter
        if fmt == "planswift_package":
            return self.package_adapter
        if fmt in ("dxf_ascii", "dxf_binary"):
            return self.dxf_adapter
        if fmt == "ifc_step":
            return self.ifc_adapter
        raise UnsupportedFormatError(f"Unsupported format '{fmt}' for '{source_path.name}'.")

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
        """Run standalone PlanSwift, DXF, or IFC extraction pipeline and return (CanonicalProject, ExtractionReport)."""
        active_ctx = ctx or ExtractionContext(source_path=source_path, config=self.config)
        active_ctx.source_path = source_path
        t0 = time.perf_counter()
        tracing_here = False
        if track_memory and not tracemalloc.is_tracing():
            tracemalloc.start()
            tracing_here = True

        peak_rss = _current_process_rss_mb()
        stage_timings: dict[str, float] = {}

        adapter = self._select_adapter(source_path)
        manifest: SourceManifest | None = None
        project: CanonicalProject | None = None
        reconciliation: dict[str, Any] | None = None
        validation = None

        try:
            if adapter in (self.dxf_adapter, self.ifc_adapter):
                project, manifest, validation, reconciliation, stage_timings = self._run_cad_bim(adapter, source_path, active_ctx)
                peak_rss = max(peak_rss, _current_process_rss_mb())
            else:
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
                peak_rss = max(peak_rss, _current_process_rss_mb())

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
            peak_rss_mb=max(peak_rss, _current_process_rss_mb()),
            stage_timings=stage_timings,
            project_guid=project.native_guid if project else None,
            project_name=project.name if project else None,
            validation=validation,
            reconciliation_summary=reconciliation,
            events=[ExtractionEventRecord(**e) for e in active_ctx.events],
            errors=[ExtractionErrorRecord(**e) for e in active_ctx.errors],
        )
        assert project is not None
        return project, report

    def _run_cad_bim(
        self,
        adapter: DXFAdapter | IFCAdapter,
        source_path: Path,
        active_ctx: ExtractionContext,
    ) -> tuple[CanonicalProject, SourceManifest, Any, dict[str, Any], dict[str, float]]:
        timings: dict[str, float] = {}
        t_val0 = time.perf_counter()
        active_ctx.transition(ExtractionStage.VALIDATING_ARCHIVE, 10, f"Validating signature and size bounds for '{source_path.name}'.")
        manifest = adapter.inspect_source(source_path, active_ctx)
        self._write_checkpoint(active_ctx, ExtractionStage.VALIDATING_ARCHIVE, {"sha256": manifest.source_sha256})
        timings["validate_and_inspect_s"] = round(time.perf_counter() - t_val0, 4)

        active_ctx.transition(
            ExtractionStage.INSPECTING_SOURCE,
            20,
            f"Format={manifest.container_format}, version={manifest.detected_project_version}, size={manifest.file_size_bytes} bytes.",
        )

        t_ext0 = time.perf_counter()
        project = adapter.extract(active_ctx, manifest=manifest)
        timings.update(project.cad_document.stage_timings if project.cad_document else {})
        timings["extract_total_s"] = round(time.perf_counter() - t_ext0, 4)

        t_dig0 = time.perf_counter()
        project.deterministic_digest_sha256 = compute_cad_deterministic_digest(project)
        timings["digest_s"] = round(time.perf_counter() - t_dig0, 4)

        active_ctx.transition(
            ExtractionStage.VALIDATING,
            94,
            f"Validating extracted {project.source_system} model integrity & provenance.",
        )
        t_v0 = time.perf_counter()
        if adapter is self.dxf_adapter:
            validation = validate_dxf_project(project)
            cad_doc = project.cad_document
            reconciliation = {
                "mode": "dxf_ezdxf_verified",
                "com_available": False,
                "matched_objects": len(project.objects),
                "layers_extracted": len(cad_doc.layers) if cad_doc else 0,
                "blocks_extracted": len(cad_doc.blocks) if cad_doc else 0,
                "entities_extracted": len(cad_doc.cad_entities) if cad_doc else 0,
                "unsupported_entities": len(project.unsupported_objects),
            }
        else:
            validation = validate_ifc_project(project)
            cad_doc = project.cad_document
            reconciliation = {
                "mode": "ifc_ifcopenshell_verified",
                "com_available": False,
                "matched_objects": len(project.objects),
                "ifc_elements_extracted": len(cad_doc.ifc_elements) if cad_doc else 0,
                "relationships_extracted": len(project.relationships),
                "geometry_enabled": bool(cad_doc and cad_doc.extraction_options.get("ifc_extract_geometry")),
                "unsupported_or_failed_geometry": len(project.unsupported_objects),
            }
        timings["validation_s"] = round(time.perf_counter() - t_v0, 4)

        if project.cad_document is not None:
            project.cad_document.stage_timings = timings
            project.cad_document.peak_rss_mb = _current_process_rss_mb()

        final_stage = ExtractionStage.COMPLETED
        msg = f"Standalone {project.source_system} extraction completed."
        if project.unsupported_classes or manifest.warnings:
            final_stage = ExtractionStage.COMPLETED_WITH_WARNINGS
            msg = f"Standalone {project.source_system} extraction completed with warnings/unsupported items preserved."
        active_ctx.transition(final_stage, 100, msg)
        return project, manifest, validation, reconciliation, timings
