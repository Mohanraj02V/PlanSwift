"""Verify ASCII DXF extraction across multiple DXF versions (R12/AC1009, R2000/AC1015, R2010/AC1024, R2018/AC1032)."""

from __future__ import annotations

from pathlib import Path

import ezdxf
import pytest

from extraction_engine.pipeline import ExtractionPipeline


@pytest.mark.parametrize("dxf_ver", ["R12", "R2000", "R2010", "R2018"])
def test_ascii_dxf_multiple_versions(tmp_path: Path, dxf_ver: str) -> None:
    p = tmp_path / f"sample_{dxf_ver}.dxf"
    doc = ezdxf.new(dxf_ver)
    doc.header["$INSUNITS"] = 6  # Meters
    msp = doc.modelspace()
    msp.add_line((0.0, 0.0, 0.0), (5.0, 0.0, 0.0))
    msp.add_circle((2.0, 3.0, 0.0), radius=4.0)
    doc.saveas(p)

    project, report = ExtractionPipeline().run(p)
    assert report.adapter_used == "dxf_ezdxf"
    assert project.source_system == "DXF"
    assert project.source_manifest.container_format == "dxf_ascii"
    assert project.cad_document is not None
    assert project.cad_document.file_version.startswith(doc.dxfversion)
    assert len(project.cad_document.cad_entities) >= 2
    lines = [e for e in project.cad_document.cad_entities if e.entity_type == "LINE"]
    assert len(lines) == 1
    assert abs(lines[0].geometry_metrics["length"] - 5.0) < 1e-9
