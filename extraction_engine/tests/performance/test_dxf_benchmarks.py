"""Performance & output-completeness sanity benchmark test for DXF."""

from __future__ import annotations

from pathlib import Path

import ezdxf

from extraction_engine.pipeline import ExtractionPipeline


def test_dxf_medium_benchmark_complete_and_bounded(tmp_path: Path) -> None:
    p = tmp_path / "bench_1000.dxf"
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6
    msp = doc.modelspace()
    for i in range(1000):
        msp.add_line((float(i), 0.0), (float(i) + 1.0, 0.0))
    doc.saveas(p)

    proj, rep = ExtractionPipeline().run(p)
    assert len(proj.cad_document.cad_entities) == 1000
    assert rep.duration_seconds < 10.0
    assert rep.peak_rss_mb > 0.0
