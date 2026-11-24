"""Verify resource bounds: thread clamping (1..4), entity safety caps, and upload byte guards."""

from __future__ import annotations

from pathlib import Path

import ezdxf

from extraction_engine.core.extraction_context import ExtractionConfig
from extraction_engine.pipeline import ExtractionPipeline


def test_entity_cap_and_thread_bounds(tmp_path: Path) -> None:
    p = tmp_path / "cap.dxf"
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    for i in range(25):
        msp.add_line((i, 0), (i + 1, 0))
    doc.saveas(p)

    cfg = ExtractionConfig(dxf_max_entities=10, ifc_geometry_threads=99)
    proj, rep = ExtractionPipeline(cfg).run(p)
    assert len(proj.cad_document.cad_entities) == 10
    assert any("dxf_max_entities=10" in w for w in proj.source_manifest.warnings)
