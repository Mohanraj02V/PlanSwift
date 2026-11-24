"""Verify Binary DXF format signature detection and lossless extraction."""

from __future__ import annotations

from pathlib import Path

import ezdxf

from extraction_engine.core.format_detector import detect_source_format
from extraction_engine.pipeline import ExtractionPipeline


def test_binary_dxf_detection_and_extraction(tmp_path: Path) -> None:
    p = tmp_path / "binary_sample.dxf"
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 4  # Millimeters
    msp = doc.modelspace()
    msp.add_line((0.0, 0.0, 0.0), (3000.0, 4000.0, 0.0))
    msp.add_lwpolyline([(0, 0), (1000, 0), (1000, 2000), (0, 2000)], close=True)
    doc.saveas(p, fmt="bin")

    assert detect_source_format(p) == "dxf_binary"
    project, report = ExtractionPipeline().run(p)
    assert report.adapter_used == "dxf_ezdxf"
    assert project.source_manifest.container_format == "dxf_binary"
    cad = project.cad_document
    assert cad.source_units == "mm"
    line = next(e for e in cad.cad_entities if e.entity_type == "LINE")
    assert abs(line.geometry_metrics["length"] - 5000.0) < 1e-9
    assert abs(line.geometry_metrics["normalized_length_m"] - 5.0) < 1e-9
    poly = next(e for e in cad.cad_entities if e.entity_type == "LWPOLYLINE")
    assert abs(poly.geometry_metrics["area"] - 2_000_000.0) < 1e-6
    assert abs(poly.geometry_metrics["normalized_area_m2"] - 2.0) < 1e-9
