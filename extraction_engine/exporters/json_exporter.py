"""JSON and streaming JSONL exporters preserving PlanSwift object provenance."""

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


def export_project_json(
    project: CanonicalProject,
    output_path: Path,
    report: ExtractionReport | None = None,
) -> Path:
    """Write complete canonical project + optional extraction report to JSON."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "project": project.model_dump(mode="json"),
        "report": report.model_dump(mode="json") if report else None,
    }
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
