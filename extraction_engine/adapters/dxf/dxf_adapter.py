"""SourceAdapter implementation for ASCII and Binary DXF via ezdxf."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import ezdxf

from extraction_engine.adapters.dxf.dxf_block_extractor import extract_dxf_blocks
from extraction_engine.adapters.dxf.dxf_document_reader import inspect_dxf_manifest, open_dxf_document
from extraction_engine.adapters.dxf.dxf_entity_extractor import extract_all_dxf_entities
from extraction_engine.adapters.dxf.dxf_layer_extractor import extract_dxf_layers
from extraction_engine.core.cad_models import CanonicalCADDocument
from extraction_engine.core.extraction_context import ExtractionContext, ExtractionStage
from extraction_engine.core.extraction_result import CanonicalProject
from extraction_engine.core.format_detector import detect_source_format
from extraction_engine.core.source_manifest import SourceManifest


class DXFAdapter:
    """Extracts ASCII and Binary DXF CAD drawings using ezdxf without OCR or raster rendering."""

    adapter_name = "dxf_ezdxf"
    adapter_version = "1.0.0"

    def can_handle(self, source_path: Path | None = None, payload: dict[str, Any] | None = None) -> bool:
        if source_path is None or not source_path.exists() or not source_path.is_file():
            return False
        try:
            return detect_source_format(source_path) in ("dxf_ascii", "dxf_binary")
        except Exception:
            return False

    def inspect_source(self, source_path: Path, ctx: ExtractionContext) -> SourceManifest:
        return inspect_dxf_manifest(source_path, ctx.config)

    def extract(self, ctx: ExtractionContext, manifest: SourceManifest | None = None) -> CanonicalProject:
        if ctx.source_path is None:
            raise ValueError("ExtractionContext.source_path is required for DXFAdapter.")

        timings: dict[str, float] = {}
        t_manifest0 = time.perf_counter()
        active_manifest = manifest or self.inspect_source(ctx.source_path, ctx)
        timings["inspect_manifest_s"] = round(time.perf_counter() - t_manifest0, 4)

        doc_hash = active_manifest.source_sha256
        hash_prefix = doc_hash[:12]

        ctx.transition(ExtractionStage.PARSING_XML, 30, f"Reading DXF via ezdxf {ezdxf.__version__}.")
        t_open0 = time.perf_counter()
        doc, reader_warnings, meta = open_dxf_document(ctx.source_path, ctx.config)
        timings["open_and_parse_s"] = round(time.perf_counter() - t_open0, 4)

        active_manifest.detected_project_version = meta["dxfversion"]
        active_manifest.detected_xml_encoding = str(meta["encoding"])
        active_manifest.warnings.extend(reader_warnings)

        ctx.transition(ExtractionStage.INTERPRETING_OBJECTS, 48, "Extracting DXF layers and block definitions.")
        t_tbl0 = time.perf_counter()
        layers, layers_by_name = extract_dxf_layers(doc, hash_prefix)
        blocks, blocks_by_name, ext_refs = extract_dxf_blocks(doc, hash_prefix)
        timings["layers_and_blocks_s"] = round(time.perf_counter() - t_tbl0, 4)

        ctx.transition(ExtractionStage.PROCESSING_GEOMETRY, 68, "Extracting DXF entities, OCS/WCS transforms, and double-precision geometry.")
        t_ent0 = time.perf_counter()
        res = extract_all_dxf_entities(
            doc=doc,
            doc_hash=doc_hash,
            source_name=active_manifest.source_name,
            source_units=meta["source_units"],
            unit_factor_m=meta["unit_to_meter_factor"],
            layers=layers,
            layers_by_name=layers_by_name,
            blocks=blocks,
            blocks_by_name=blocks_by_name,
            ext_refs=ext_refs,
            config=ctx.config,
        )
        timings["entities_and_geometry_s"] = round(time.perf_counter() - t_ent0, 4)
        if res["warnings"]:
            active_manifest.warnings.extend(res["warnings"])

        cad_doc = CanonicalCADDocument(
            source_format=active_manifest.container_format,  # type: ignore[arg-type]
            library_name="ezdxf",
            library_version=ezdxf.__version__,
            file_version=f"{meta['dxfversion']} ({meta['acad_release']})" if meta.get("acad_release") else meta["dxfversion"],
            schema_name=meta["dxfversion"],
            source_units=meta["source_units"],
            unit_to_meter_factor=meta["unit_to_meter_factor"],
            header_variables=meta["header_variables"],
            external_references=ext_refs,
            extraction_options={
                "dxf_resolve_inserts": ctx.config.dxf_resolve_inserts,
                "dxf_max_block_depth": ctx.config.dxf_max_block_depth,
                "dxf_enable_rule_classification": ctx.config.dxf_enable_rule_classification,
            },
            layers=layers,
            blocks=blocks,
            cad_entities=res["cad_entities"],
            stage_timings=timings,
        )

        return CanonicalProject(
            engine_name="Vortexen Standalone CAD/BIM Extraction Engine",
            engine_version=ctx.config.parser_version,
            source_system="DXF",
            native_guid=f"dxf:{hash_prefix}",
            name=ctx.source_path.stem,
            native_project_version=meta["dxfversion"],
            project_type="DXF_DRAWING",
            measurement_system=meta["source_units"],
            xml_encoding=str(meta["encoding"]),
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
