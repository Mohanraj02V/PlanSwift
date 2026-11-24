"""SourceAdapter implementation for IFC STEP models via IfcOpenShell."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import ifcopenshell

from extraction_engine.adapters.ifc.ifc_document_reader import inspect_ifc_manifest, open_ifc_model
from extraction_engine.adapters.ifc.ifc_object_extractor import extract_all_ifc_elements
from extraction_engine.core.cad_models import CanonicalCADDocument
from extraction_engine.core.extraction_context import ExtractionContext, ExtractionStage
from extraction_engine.core.extraction_result import CanonicalProject
from extraction_engine.core.format_detector import detect_source_format
from extraction_engine.core.source_manifest import SourceManifest


class IFCAdapter:
    """Extracts IFC2X3 / IFC4 / IFC4X3 STEP BIM models cleanly using IfcOpenShell."""

    adapter_name = "ifc_ifcopenshell"
    adapter_version = "1.0.0"

    def can_handle(self, source_path: Path | None = None, payload: dict[str, Any] | None = None) -> bool:
        if source_path is None or not source_path.exists() or not source_path.is_file():
            return False
        try:
            return detect_source_format(source_path) == "ifc_step"
        except Exception:
            return False

    def inspect_source(self, source_path: Path, ctx: ExtractionContext) -> SourceManifest:
        return inspect_ifc_manifest(source_path, ctx.config)

    def extract(self, ctx: ExtractionContext, manifest: SourceManifest | None = None) -> CanonicalProject:
        if ctx.source_path is None:
            raise ValueError("ExtractionContext.source_path is required for IFCAdapter.")

        timings: dict[str, float] = {}
        t0 = time.perf_counter()
        active_manifest = manifest or self.inspect_source(ctx.source_path, ctx)
        timings["inspect_manifest_s"] = round(time.perf_counter() - t0, 4)

        doc_hash = active_manifest.source_sha256
        hash_prefix = doc_hash[:12]

        ctx.transition(
            ExtractionStage.PARSING_XML,
            30,
            f"Opening IFC STEP model via IfcOpenShell {ifcopenshell.version}.",
        )
        t_open = time.perf_counter()
        model, unit_meta, reader_warnings = open_ifc_model(ctx.source_path, ctx.config)
        timings["open_and_parse_s"] = round(time.perf_counter() - t_open, 4)
        active_manifest.detected_project_version = unit_meta["schema_name"]
        active_manifest.warnings.extend(reader_warnings)

        ctx.transition(
            ExtractionStage.INTERPRETING_OBJECTS,
            55,
            (
                "Extracting IFC objects, relationships, Psets & Qto_* "
                + ("+ bounded 3D geometry iterator." if ctx.config.ifc_extract_geometry else "(property/quantity mode).")
            ),
        )
        t_ext = time.perf_counter()
        res = extract_all_ifc_elements(
            model=model,
            doc_hash=doc_hash,
            source_name=active_manifest.source_name,
            unit_meta=unit_meta,
            config=ctx.config,
        )
        timings["elements_rels_and_geom_s"] = round(time.perf_counter() - t_ext, 4)
        if res["warnings"]:
            active_manifest.warnings.extend(res["warnings"])

        # Extract IfcProject name & GlobalId when present
        ifc_proj = next((e for e in res["ifc_elements"] if e.ifc_class == "IfcProject"), None)
        proj_guid = ifc_proj.global_id if ifc_proj else f"ifc:{hash_prefix}"
        proj_name = (ifc_proj.name if ifc_proj and ifc_proj.name else "") or ctx.source_path.stem

        cad_doc = CanonicalCADDocument(
            source_format="ifc_step",
            library_name="ifcopenshell",
            library_version=str(ifcopenshell.version),
            file_version=unit_meta["schema_name"],
            schema_name=unit_meta["schema_name"],
            source_units=unit_meta.get("length_unit") or "",
            unit_to_meter_factor=unit_meta.get("unit_to_meter_factor"),
            header_variables=unit_meta["header_variables"],
            extraction_options={
                "ifc_extract_geometry": ctx.config.ifc_extract_geometry,
                "ifc_geometry_threads": ctx.config.ifc_geometry_threads,
            },
            ifc_elements=res["ifc_elements"],
            stage_timings=timings,
        )

        return CanonicalProject(
            engine_name="Vortexen Standalone CAD/BIM Extraction Engine",
            engine_version=ctx.config.parser_version,
            source_system="IFC",
            native_guid=proj_guid,
            name=proj_name,
            native_project_version=unit_meta["schema_name"],
            project_type="IFC_BIM_MODEL",
            measurement_system=unit_meta.get("length_unit") or "",
            xml_encoding="utf-8",
            source_manifest=active_manifest,
            pages=res["pages"],
            objects=res["objects"],
            relationships=res["relationships"],
            discovered_classes=res["discovered_classes"],
            unsupported_classes=res["unsupported_classes"],
            unsupported_objects=res["unsupported_objects"],
            provenance_records=res["provenance_records"],
            cad_document=cad_doc,
        )
