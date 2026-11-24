"""Release-gate PlanSwift regression suite ensuring CAD/BIM additions never alter PlanSwift outputs."""

from __future__ import annotations

from pathlib import Path

import pytest

from extraction_engine.core.format_detector import UnsupportedFormatError, detect_source_format
from extraction_engine.pipeline import ExtractionPipeline

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
PROJECT_4_PATH = WORKSPACE_ROOT / "project 4.SwiftJob.zip"
SAMPLE_PROJECT_PATH = WORKSPACE_ROOT / "extracted_tmp" / "Sample Project.SwiftJob"


def test_planswift_format_isolation(tmp_path: Path) -> None:
    junk = tmp_path / "random.bin"
    junk.write_bytes(b"\x00\x01\x02\x03INVALID")
    with pytest.raises(UnsupportedFormatError):
        detect_source_format(junk)


@pytest.mark.skipif(not PROJECT_4_PATH.exists(), reason="Real project 4.SwiftJob.zip not available in environment.")
def test_planswift_project4_regression_release_gate() -> None:
    project, report = ExtractionPipeline().run(PROJECT_4_PATH)
    assert report.adapter_used == "planswift_native_package"
    assert len(project.objects) == 1461
    assert sum(len(o.properties) for o in project.objects) == 28355
    assert len(project.pages) == 324
    assert sum(len(o.sections) for o in project.objects) == 1052
    assert sum(g.point_count for o in project.objects for g in o.geometries) == 4868
    assert project.cad_document is None
    assert report.validation.overall_verified_accuracy_pct == 100.0


@pytest.mark.skipif(not SAMPLE_PROJECT_PATH.exists(), reason="Sample Project.SwiftJob not available in environment.")
def test_planswift_sample_project_regression_release_gate() -> None:
    project, report = ExtractionPipeline().run(SAMPLE_PROJECT_PATH)
    assert report.adapter_used == "planswift_native_package"
    assert len(project.objects) == 224
    assert len(project.pages) == 42
    assert len(project.assemblies) == 14
    assert project.cad_document is None
