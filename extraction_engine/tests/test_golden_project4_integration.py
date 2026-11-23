"""Golden dataset integration test running on real project 4.SwiftJob.zip."""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from extraction_engine.core.extraction_context import ExtractionCancelledError, ExtractionConfig, ExtractionContext
from extraction_engine.core.extraction_result import ProvenanceStatus
from extraction_engine.exporters.geometry_exporter import export_geometry_geojson
from extraction_engine.exporters.json_exporter import export_objects_jsonl, export_project_json
from extraction_engine.exporters.tabular_exporter import export_project_excel, export_takeoff_csv
from extraction_engine.pipeline import ExtractionPipeline

PROJECT_4_PATH = Path(__file__).resolve().parents[2] / "project 4.SwiftJob.zip"


@pytest.mark.skipif(not PROJECT_4_PATH.exists(), reason="Real project 4.SwiftJob.zip not present in workspace root.")
def test_golden_project_4_extraction_accuracy_idempotency_and_exports(tmp_path: Path) -> None:
    pipeline = ExtractionPipeline(ExtractionConfig(checkpoint_dir=tmp_path / "checkpoints"))
    project, report = pipeline.run(PROJECT_4_PATH)

    # 1. Container & zero-raster manifest accuracy
    assert project.source_manifest.container_format == "pkzip_swiftjob"
    assert project.source_manifest.total_entries == 325
    assert project.source_manifest.raster_entry_count == 324
    assert project.source_manifest.xml_entry_path == "XMLData.XML"

    # 2. Root project metadata
    assert project.native_guid == "{27F9E929-A81C-4ED6-9A44-4B224F5C19ED}"
    assert project.name == "project 4"
    assert project.description == "Marina hotel"
    assert project.measurement_system == "Metric"
    assert project.excel_workbook_connected is True

    # 3. Exact object & property counts verified from native XMLData.XML
    assert len(project.objects) == 1461
    assert sum(len(o.properties) for o in project.objects) == 28355
    assert sum(1 for o in project.objects for p in o.properties if p.name == "") == 16
    assert project.discovered_classes == {
        "Item": 4,
        "Folder": 2,
        "Page": 324,
        "Count": 78,
        "Count Section": 1052,
        "Segment": 1,
    }

    # 4. Page & TIFF linkage + Section PageGUID resolution
    assert len(project.pages) == 324
    assert sum(1 for p in project.pages if p.tiff_archive_path) == 324
    all_sections = [s for o in project.objects for s in o.sections]
    assert len(all_sections) == 1052
    page_guids = {p.native_guid.upper() for p in project.pages}
    assert all(s.page_guid and s.page_guid.upper() in page_guids for s in all_sections)

    # 5. Digitizer geometry & total point fidelity
    all_geoms = [g for o in project.objects for g in o.geometries]
    assert len(all_geoms) == 1052
    assert sum(g.point_count for g in all_geoms) == 4868

    # 6. Spot-check real takeoff items
    by_name = {o.name: o for o in project.objects if o.native_class in ("Count", "Segment")}
    assert by_name["CHR ans CHS 100"].get_property("Qty").raw_value == "[Takeoff]"
    assert next(m for m in by_name["CHR ans CHS 100"].measurements if m.property_name == "Qty").derived_quantity == 21.0
    assert next(m for m in by_name["CHS and CHR20 mm dia"].measurements if m.property_name == "Qty").derived_quantity == 922.0
    assert next(m for m in by_name["Duct 350x200mm"].measurements if m.property_name == "Qty").derived_quantity == 286.0
    assert next(m for m in by_name["ELECTRICALPVC 25mm"].measurements if m.property_name == "Qty").derived_quantity == 354.0
    assert by_name["New Segment"].native_class == "Segment"

    # 7. PascalScript & formula preservation (no eval)
    pascal_formulas = [f for o in project.objects for f in o.formulas if f.is_pascal_script]
    assert len(pascal_formulas) == 78
    assert all(f.evaluation_status == ProvenanceStatus.UNRESOLVED for f in pascal_formulas)

    # 8. Performance & memory sanity (must stay well below 256 MB RAM while reading 556 MB archive)
    assert report.status == "COMPLETED"
    assert report.peak_memory_mb < 256.0
    assert report.validation.objects_extracted == 1461
    assert report.validation.points_extracted == 4868
    assert report.validation.overall_verified_accuracy_pct == 100.0

    # 9. Idempotency: second run produces identical deterministic SHA-256 digest
    project2, report2 = pipeline.run(PROJECT_4_PATH)
    assert project2.deterministic_digest_sha256 == project.deterministic_digest_sha256
    assert report2.validation.objects_extracted == 1461

    # 10. All exports succeed cleanly
    p_json = export_project_json(project, tmp_path / "out.json", report=report)
    p_jsonl = export_objects_jsonl(project, tmp_path / "out.jsonl", run_id=report.run_id)
    p_geo = export_geometry_geojson(project, tmp_path / "out.geojson")
    p_csv = export_takeoff_csv(project, tmp_path / "out.csv")
    p_xlsx = export_project_excel(project, tmp_path / "out.xlsx")
    assert p_json.exists() and p_jsonl.exists() and p_geo.exists() and p_csv.exists() and p_xlsx.exists()
    geo_data = json.loads(p_geo.read_text(encoding="utf-8"))
    non_empty_geom_count = sum(1 for g in all_geoms if g.point_count > 0)
    assert len(geo_data["features"]) == non_empty_geom_count
    assert non_empty_geom_count >= 1046


@pytest.mark.skipif(not PROJECT_4_PATH.exists(), reason="Real project 4.SwiftJob.zip not present.")
def test_extraction_cancellation_support() -> None:
    cancel_evt = threading.Event()
    cancel_evt.set()
    ctx = ExtractionContext(cancel_event=cancel_evt)
    pipeline = ExtractionPipeline()
    with pytest.raises(ExtractionCancelledError):
        pipeline.run(PROJECT_4_PATH, ctx=ctx)
