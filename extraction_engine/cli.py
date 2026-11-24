"""Command-line interface for inspecting, extracting, validating, and exporting PlanSwift ZIP, DXF, and IFC files."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from extraction_engine.core.extraction_context import ExtractionConfig, ExtractionContext
from extraction_engine.exporters.geometry_exporter import export_geometry_geojson
from extraction_engine.exporters.json_exporter import export_objects_jsonl, export_project_json
from extraction_engine.exporters.tabular_exporter import export_project_excel, export_takeoff_csv
from extraction_engine.pipeline import ExtractionPipeline


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vortexen-extract", description="Standalone PlanSwift / DXF / IFC Extraction CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_inspect = sub.add_parser("inspect", help="Inspect source format and manifest without full extraction")
    p_inspect.add_argument("--source", required=True, type=Path)

    p_validate = sub.add_parser("validate", help="Extract and print full validation report")
    p_validate.add_argument("--source", required=True, type=Path)
    p_validate.add_argument("--extract-geometry", action="store_true", help="Enable 3D IFC geometry iterator")
    p_validate.add_argument("--ifc-threads", type=int, default=2, help="Bounded IfcOpenShell geometry threads (1-4)")

    p_export = sub.add_parser("export", help="Extract and export JSON/JSONL/GeoJSON/CSV/XLSX")
    p_export.add_argument("--source", required=True, type=Path)
    p_export.add_argument("--out-dir", required=True, type=Path)
    p_export.add_argument("--extract-geometry", action="store_true", help="Enable 3D IFC geometry iterator")
    p_export.add_argument("--ifc-threads", type=int, default=2, help="Bounded IfcOpenShell geometry threads (1-4)")

    args = parser.parse_args(argv)

    cfg = ExtractionConfig(
        ifc_extract_geometry=bool(getattr(args, "extract_geometry", False)),
        ifc_geometry_threads=max(1, min(int(getattr(args, "ifc_threads", 2)), 4)),
    )
    pipeline = ExtractionPipeline(config=cfg)

    if args.command == "inspect":
        adapter = pipeline._select_adapter(args.source)
        manifest = adapter.inspect_source(args.source, ExtractionContext(source_path=args.source, config=cfg))
        summary = manifest.model_dump(exclude={"entries"})
        print(json.dumps(summary, indent=2))
        return 0

    if args.command == "validate":
        project, report = pipeline.run(args.source)
        output = {
            "source_system": project.source_system,
            "project_guid": project.native_guid,
            "project_name": project.name,
            "digest_sha256": project.deterministic_digest_sha256,
            "discovered_classes": project.discovered_classes,
            "duration_seconds": report.duration_seconds,
            "peak_memory_mb": report.peak_memory_mb,
            "peak_rss_mb": report.peak_rss_mb,
            "stage_timings": report.stage_timings,
            "validation": report.validation.model_dump(mode="json") if report.validation else None,
        }
        print(json.dumps(output, indent=2))
        return 0

    if args.command == "export":
        project, report = pipeline.run(args.source)
        out_dir: Path = args.out_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        export_project_json(project, out_dir / "canonical_project.json", report=report)
        export_objects_jsonl(project, out_dir / "objects.jsonl", run_id=report.run_id)
        export_geometry_geojson(project, out_dir / "geometry.geojson")
        export_takeoff_csv(project, out_dir / "takeoff.csv")
        export_project_excel(project, out_dir / "project_report.xlsx")
        print(f"Exported all formats to {out_dir}")
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
