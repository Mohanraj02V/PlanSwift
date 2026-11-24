"""Command-line interface for inspecting, extracting, validating, and exporting PlanSwift ZIP projects."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from extraction_engine.exporters.geometry_exporter import export_geometry_geojson
from extraction_engine.exporters.json_exporter import export_objects_jsonl, export_project_json
from extraction_engine.exporters.tabular_exporter import export_project_excel, export_takeoff_csv
from extraction_engine.parsers.archive_parser import inspect_archive_manifest
from extraction_engine.pipeline import ExtractionPipeline


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vortexen-extract", description="Standalone PlanSwift ZIP Extraction CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_inspect = sub.add_parser("inspect", help="Inspect container manifest without full extraction")
    p_inspect.add_argument("--source", required=True, type=Path)

    p_validate = sub.add_parser("validate", help="Extract and print full validation report")
    p_validate.add_argument("--source", required=True, type=Path)

    p_export = sub.add_parser("export", help="Extract and export JSON/JSONL/GeoJSON/CSV/XLSX")
    p_export.add_argument("--source", required=True, type=Path)
    p_export.add_argument("--out-dir", required=True, type=Path)

    args = parser.parse_args(argv)

    if args.command == "inspect":
        manifest = inspect_archive_manifest(args.source)
        summary = manifest.model_dump(exclude={"entries"})
        print(json.dumps(summary, indent=2))
        return 0

    pipeline = ExtractionPipeline()
    if args.command == "validate":
        project, report = pipeline.run(args.source)
        output = {
            "project_guid": project.native_guid,
            "project_name": project.name,
            "digest_sha256": project.deterministic_digest_sha256,
            "discovered_classes": project.discovered_classes,
            "duration_seconds": report.duration_seconds,
            "peak_memory_mb": report.peak_memory_mb,
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
