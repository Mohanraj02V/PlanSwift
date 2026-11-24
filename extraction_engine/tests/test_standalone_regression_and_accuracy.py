"""Comprehensive regression (Sample Project + Project 4 Oracle), edge cases, and standalone boundary tests."""

from __future__ import annotations

import ast
import json
import zipfile
from pathlib import Path

import pytest

from extraction_engine.core.extraction_context import ExtractionConfig, SecurityValidationError
from extraction_engine.core.extraction_result import ProvenanceStatus
from extraction_engine.exporters.json_exporter import export_project_json
from extraction_engine.pipeline import ExtractionPipeline

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_PROJECT_PATH = WORKSPACE_ROOT / "extracted_tmp" / "Sample Project.SwiftJob"
PROJECT_4_PATH = WORKSPACE_ROOT / "project 4.SwiftJob.zip"
COM_ORACLE_PATH = WORKSPACE_ROOT / "com_snapshot.json"


@pytest.mark.skipif(not SAMPLE_PROJECT_PATH.exists(), reason="Sample Project.SwiftJob fixture not present.")
def test_sample_project_full_regression_calibration_and_bom(tmp_path: Path) -> None:
    pipe = ExtractionPipeline(ExtractionConfig(checkpoint_dir=tmp_path / "cp"))
    project, report = pipe.run(SAMPLE_PROJECT_PATH)

    assert len(project.objects) == 224
    assert len(project.pages) == 42
    assert project.discovered_classes["Area"] == 11
    assert project.discovered_classes["Linear"] == 2
    assert project.discovered_classes["Count"] == 11
    assert len(project.assemblies) == 14

    by_name = {o.name: o for o in project.objects}

    # Conference Room calibrated polygon area (ScaleX=37.5, FT)
    conf_qty = next(m for m in by_name["Conference Room"].measurements if m.property_name == "Qty")
    assert conf_qty.status == ProvenanceStatus.CALCULATED
    assert abs(conf_qty.calculated_quantity - 500.378283) < 0.01
    assert abs(conf_qty.reconstructed_quantity - 500.378283) < 0.01

    # Child carpet material: [Area] / 9 = 55.5976 SQ YD
    carpet_qty = next(m for m in by_name["Carpet (Priced per SQ YD)"].measurements if m.property_name == "Qty")
    assert abs(carpet_qty.calculated_quantity - 55.597587) < 0.01

    # Exterior Walls calibrated linear (264.95 FT) * Wall Height (9 FT) = 2384.53 SQ FT
    ext_qty = next(m for m in by_name["Exterior Walls"].measurements if m.property_name == "Qty")
    assert abs(ext_qty.reconstructed_quantity - 264.948289) < 0.01
    assert abs(ext_qty.calculated_quantity - 2384.534601) < 0.05

    # Child 5/8" Type X Drywall: RoundUp(2384.53 / (4.5 * 8)) = 67 EA
    drywall_qty = next(m for m in by_name['5/8" Type X Drywall (Priced per EA)'].measurements if m.property_name == "Qty")
    assert drywall_qty.calculated_quantity == 67.0
    assert drywall_qty.unit == "EA"

    # Idempotency check
    project2, _ = pipe.run(SAMPLE_PROJECT_PATH)
    assert project2.deterministic_digest_sha256 == project.deterministic_digest_sha256


@pytest.mark.skipif(
    not (PROJECT_4_PATH.exists() and COM_ORACLE_PATH.exists()),
    reason="Project 4 fixture and COM oracle not both present.",
)
def test_project4_standalone_oracle_parity_over_99_percent() -> None:
    pipe = ExtractionPipeline()
    project, _ = pipe.run(PROJECT_4_PATH)
    snap = json.loads(COM_ORACLE_PATH.read_text(encoding="utf-8"))
    snap_by_guid = {o["native_guid"].upper(): o["properties"] for o in snap["objects"]}

    total_checked = 0
    matched = 0
    for o in project.objects:
        cprops = snap_by_guid.get(o.native_guid.upper(), {})
        for f in o.formulas:
            if f.evaluation_status != ProvenanceStatus.CALCULATED or f.property_name == "Texture":
                continue
            cp = cprops.get(f.property_name)
            if not isinstance(cp, dict):
                continue
            total_checked += 1
            cv = cp.get("result")
            ov = f.calculated_value
            if str(cv or "") == str(ov or "") or (cv is None and ov in ("", None)):
                matched += 1
            else:
                try:
                    if abs(float(cv) - float(f.calculated_numeric if f.calculated_numeric is not None else ov)) < 1e-4:
                        matched += 1
                except (TypeError, ValueError):
                    pass

    parity_pct = 100.0 * matched / max(total_checked, 1)
    assert total_checked >= 5400
    assert parity_pct >= 99.0, f"Oracle parity dropped to {parity_pct:.2f}% ({matched}/{total_checked})"


def test_edge_cases_missing_xml_malformed_xml_and_multidata_job_dir(tmp_path: Path) -> None:
    pipe = ExtractionPipeline()

    # 1. ZIP with missing XML
    no_xml = tmp_path / "noxml.SwiftJob.zip"
    with zipfile.ZipFile(no_xml, "w") as zf:
        zf.writestr("readme.txt", "no xml here")
    with pytest.raises(SecurityValidationError, match="XMLData.XML"):
        pipe.run(no_xml)

    # 2. Malformed XML inside ZIP
    bad_xml = tmp_path / "badxml.SwiftJob.zip"
    with zipfile.ZipFile(bad_xml, "w") as zf:
        zf.writestr("XMLData.XML", "<Item><Broken></Item>")
    with pytest.raises(SecurityValidationError, match="malformed"):
        pipe.run(bad_xml)

    # 3. Multiple Data.xml files in extracted PlanSwift job directory
    job_dir = tmp_path / "MultiDataJob"
    sub_dir = job_dir / "Takeoff"
    sub_dir.mkdir(parents=True)
    (job_dir / "Data.xml").write_text(
        '<Item Class="Item" Name="DirJob" GUID="{00000000-0000-0000-0000-000000000001}"><Properties/></Item>',
        encoding="utf-8",
    )
    (sub_dir / "Data.xml").write_text(
        '<Item Class="Count" Name="Valve" GUID="{00000000-0000-0000-0000-000000000010}"><Properties><Property Class="Number" GUID="{00000000-0000-0000-0000-000000000011}" Name="Qty">12</Property></Properties></Item>',
        encoding="utf-8",
    )
    proj, rep = pipe.run(job_dir)
    assert len(proj.objects) == 2
    assert proj.source_manifest.container_format == "planswift_job_directory"
    assert export_project_json(proj, tmp_path / "out.json", report=rep).exists()


def test_standalone_security_no_com_no_ocr_no_eval_across_codebase() -> None:
    """AST scan across extraction_engine/ and backend/ confirming zero PlanSwift/COM/OCR/eval usage."""
    forbidden_modules = {
        "winreg",
        "win32com",
        "pythoncom",
        "comtypes",
        "pytesseract",
        "easyocr",
        "cv2",
        "PIL",
        "pdf2image",
        "pypdf",
        "fitz",
        "apps.planswift_connector",
        "extraction_engine.adapters.planswift_com",
        "extraction_engine.adapters.planswift_version_adapters",
    }
    for root_dir in (WORKSPACE_ROOT / "extraction_engine", WORKSPACE_ROOT / "backend"):
        for py_file in root_dir.rglob("*.py"):
            if "migrations" in py_file.parts or ".venv" in py_file.parts or "__pycache__" in py_file.parts:
                continue
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        assert not any(alias.name == fm or alias.name.startswith(fm + ".") for fm in forbidden_modules), (
                            f"Forbidden import '{alias.name}' in {py_file}"
                        )
                elif isinstance(node, ast.ImportFrom) and node.module:
                    assert not any(node.module == fm or node.module.startswith(fm + ".") for fm in forbidden_modules), (
                        f"Forbidden import '{node.module}' in {py_file}"
                    )
                elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    # Ensure eval()/exec() is never called on runtime code (exclude test_standalone... itself)
                    if py_file.name != Path(__file__).name:
                        assert node.func.id not in ("eval", "exec"), f"Forbidden {node.func.id}() call in {py_file}"
