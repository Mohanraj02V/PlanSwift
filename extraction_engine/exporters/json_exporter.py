"""Versioned canonical JSON and streaming JSONL exporters preserving native data and provenance."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from extraction_engine.core.extraction_result import CanonicalObject, CanonicalProject, ExtractionReport


def build_object_export_dict(
    project: CanonicalProject,
    obj: CanonicalObject,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Build canonical provenance-aware JSON representation for a single PlanSwift object."""
    return {
        "source_system": project.source_system,
        "project": {
            "native_guid": project.native_guid,
            "name": project.name,
        },
        "object": {
            "native_guid": obj.native_guid,
            "native_class": obj.native_class,
            "native_type": obj.native_type,
            "name": obj.name,
            "parent_guid": obj.parent_guid,
            "root_path": obj.root_path,
            "depth": obj.depth,
            "order_index": obj.order_index,
            "page_guid": obj.page_guid,
            "is_known_class": obj.is_known_class,
        },
        "relationships": [
            r.model_dump(mode="json")
            for r in project.relationships
            if r.source_guid.upper() == obj.native_guid.upper() or r.target_guid.upper() == obj.native_guid.upper()
        ],
        "properties": [p.model_dump(mode="json") for p in obj.properties],
        "measurements": [m.model_dump(mode="json") for m in obj.measurements],
        "sections": [s.model_dump(mode="json") for s in obj.sections],
        "geometry": [g.model_dump(mode="json") for g in obj.geometries],
        "formulas": [f.model_dump(mode="json") for f in obj.formulas],
        "denotations": [d.model_dump(mode="json") for d in obj.denotations],
        "remarks": [r.model_dump(mode="json") for r in obj.remarks],
        "provenance": {
            "source": "native_project_package",
            "status": obj.provenance.value,
            "extraction_run_id": run_id,
        },
    }


def build_structured_project_export(
    project: CanonicalProject,
    report: ExtractionReport | None = None,
) -> dict[str, Any]:
    """Build Section-17 compliant versioned canonical JSON payload without leaking server filesystem paths."""
    manifest = project.source_manifest
    source_filename = getattr(manifest, "source_name", "") if manifest else ""
    source_hash = getattr(manifest, "source_sha256", "") if manifest else ""
    warnings = list(getattr(manifest, "warnings", []) or []) if manifest else []

    takeoffs = [
        {
            "native_guid": o.native_guid,
            "native_class": o.native_class,
            "native_type": o.native_type,
            "name": o.name,
            "parent_guid": o.parent_guid,
            "division": o.division,
            "measurements": [m.model_dump(mode="json") for m in o.measurements],
            "section_count": len(o.sections) or sum(1 for c in project.objects if c.parent_guid == o.native_guid and c.is_measurement_section),
            "provenance": o.provenance.value,
        }
        for o in project.objects
        if not o.is_page and not o.is_measurement_section and o.depth >= 2
    ]

    calculations = [
        {
            "object_guid": f.object_guid,
            "property_guid": f.property_guid,
            "property_name": f.property_name,
            "raw_expression": f.raw_expression,
            "status": f.evaluation_status.value,
            "calculated_value": f.calculated_value,
            "calculated_numeric": f.calculated_numeric,
            "unit": f.calculation_unit,
            "reason": f.calculation_reason,
            "inputs": f.calculation_inputs,
        }
        for o in project.objects
        for f in o.formulas
    ]

    return {
        "schema_version": project.schema_version,
        "engine": {
            "name": project.engine_name,
            "version": project.engine_version,
        },
        "project": {
            "id": project.native_guid,
            "name": project.name,
            "native_version": project.native_project_version,
            "measurement_system": project.measurement_system or None,
            "xml_encoding": project.xml_encoding,
            "deterministic_digest_sha256": project.deterministic_digest_sha256,
        },
        "extraction": {
            "status": (report.status.lower() if report else "completed"),
            "source_filename": source_filename,
            "source_hash": source_hash,
            "duration_seconds": report.duration_seconds if report else None,
            "peak_memory_mb": report.peak_memory_mb if report else None,
            "warnings": warnings,
            "unsupported_objects": project.unsupported_objects,
        },
        "pages": [p.model_dump(mode="json") for p in project.pages],
        "takeoffs": takeoffs,
        "objects": [
            {
                "native_guid": o.native_guid,
                "native_class": o.native_class,
                "native_type": o.native_type,
                "name": o.name,
                "parent_guid": o.parent_guid,
                "root_path": o.root_path,
                "depth": o.depth,
                "order_index": o.order_index,
                "page_guid": o.page_guid,
                "is_known_class": o.is_known_class,
                "provenance": o.provenance.value,
                "properties": [p.model_dump(mode="json") for p in o.properties],
            }
            for o in project.objects
        ],
        "measurements": [m.model_dump(mode="json") for o in project.objects for m in o.measurements],
        "geometry": [g.model_dump(mode="json") for o in project.objects for g in o.geometries],
        "formulas": [f.model_dump(mode="json") for o in project.objects for f in o.formulas],
        "calculations": calculations,
        "relationships": [r.model_dump(mode="json") for r in project.relationships],
        "assemblies": [a.model_dump(mode="json") for a in project.assemblies],
        "validation": report.validation.model_dump(mode="json") if report and report.validation else None,
    }


def export_project_json(
    project: CanonicalProject,
    output_path: Path,
    report: ExtractionReport | None = None,
) -> Path:
    """Write complete versioned canonical project + validation report to UTF-8 JSON."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = build_structured_project_export(project, report=report)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return output_path


def export_objects_jsonl(
    project: CanonicalProject,
    output_path: Path,
    run_id: str | None = None,
) -> Path:
    """Stream objects line-by-line as JSONL for large projects and downstream pipelines."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as fh:
        for obj in project.objects:
            line = json.dumps(build_object_export_dict(project, obj, run_id=run_id), ensure_ascii=False)
            fh.write(line + "\n")
    return output_path
