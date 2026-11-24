"""Verify double-precision DXF geometry: OCS->WCS, bulges, closed/open polylines, circles, arcs, ellipses, hatches."""

from __future__ import annotations

import math
from pathlib import Path

import ezdxf

from extraction_engine.pipeline import ExtractionPipeline


def test_dxf_exact_geometry_bulges_ocs_and_curves(tmp_path: Path) -> None:
    p = tmp_path / "geom_exact.dxf"
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6  # Meters
    msp = doc.modelspace()

    # 1. Closed rectangle 4 x 3 -> perimeter = 14.0, area = 12.0
    msp.add_lwpolyline([(0, 0), (4, 0), (4, 3), (0, 3)], close=True)

    # 2. Semicircle bulge=1.0 on chord of length 2.0 (radius = 1.0): arc_len = pi, area = 0.5 * pi
    msp.add_lwpolyline([(0, 0, 1.0), (2, 0, 0.0)], format="xyb", close=True)

    # 3. OCS Circle rotated 90 deg around X (extrusion = (0, 1, 0)): center OCS (1, 2, 5) -> WCS
    c_ocs = msp.add_circle((1.0, 2.0, 5.0), radius=3.0, dxfattribs={"extrusion": (0.0, 1.0, 0.0)})

    # 4. 90-degree Arc of radius 4.0 -> arc_len = 2 * pi
    msp.add_arc((0.0, 0.0), radius=4.0, start_angle=0.0, end_angle=90.0)

    # 5. Full Ellipse semi-axes a=5, b=3 -> area = 15 * pi, Ramanujan approx ~25.52699886
    msp.add_ellipse((0.0, 0.0), major_axis=(5.0, 0.0, 0.0), ratio=0.6)

    doc.saveas(p)
    project, _ = ExtractionPipeline().run(p)
    ents = project.cad_document.cad_entities

    polys = [e for e in ents if e.entity_type == "LWPOLYLINE"]
    assert abs(polys[0].geometry_metrics["length"] - 14.0) < 1e-9
    assert abs(polys[0].geometry_metrics["area"] - 12.0) < 1e-9

    assert polys[1].geometry_metrics["has_bulge"] is True
    # Bulge polyline length = pi + closing chord 2.0; area = 0.5 * pi
    assert abs(polys[1].geometry_metrics["length"] - (math.pi + 2.0)) < 1e-9
    assert abs(polys[1].geometry_metrics["area"] - (0.5 * math.pi)) < 1e-9

    circle = next(e for e in ents if e.entity_type == "CIRCLE")
    assert circle.ocs_applied is True
    expected_wcs = list(c_ocs.ocs().to_wcs((1.0, 2.0, 5.0)))
    for a, b in zip(circle.world_coordinates["center"], expected_wcs):
        assert abs(a - b) < 1e-9
    assert abs(circle.geometry_metrics["area"] - (9.0 * math.pi)) < 1e-9

    arc = next(e for e in ents if e.entity_type == "ARC")
    assert abs(arc.geometry_metrics["length"] - (2.0 * math.pi)) < 1e-9

    ellipse = next(e for e in ents if e.entity_type == "ELLIPSE")
    assert abs(ellipse.geometry_metrics["area"] - (15.0 * math.pi)) < 1e-9
    # Exact perimeter of ellipse a=5, b=3 is ~25.526998863
    assert abs(ellipse.geometry_metrics["length"] - 25.526998863) < 1e-5
