"""Verify DXF DIMENSION actual_measurement, text override separation, and calculated geometry."""

from __future__ import annotations

from pathlib import Path

import ezdxf

from extraction_engine.pipeline import ExtractionPipeline


def test_dxf_dimension_override_separated_from_geometry(tmp_path: Path) -> None:
    p = tmp_path / "dims.dxf"
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 4  # mm
    msp = doc.modelspace()

    # True geometric length is 5000 mm, while estimator forced text override "8000"
    dim = msp.add_aligned_dim(
        p1=(0.0, 0.0),
        p2=(5000.0, 0.0),
        distance=500.0,
        text="8000",
    )
    dim.render()
    doc.saveas(p)

    project, _ = ExtractionPipeline().run(p)
    cad = project.cad_document
    dim_ent = next(e for e in cad.cad_entities if e.entity_type == "DIMENSION")
    dd = dim_ent.dimension_data
    assert dd["has_text_override"] is True
    assert dd["text_override"] == "8000"
    assert abs(dd["geometry_measured"] - 5000.0) < 1e-6
    assert abs(dd["actual_measurement"] - 5000.0) < 1e-6
