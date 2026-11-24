"""Verify complete extraction coverage across all required DXF entity types and metadata."""

from __future__ import annotations

from pathlib import Path

import ezdxf

from extraction_engine.pipeline import ExtractionPipeline


def test_dxf_required_entity_types_and_metadata(tmp_path: Path) -> None:
    p = tmp_path / "entities_all.dxf"
    doc = ezdxf.new("R2013")
    doc.header["$INSUNITS"] = 6
    msp = doc.modelspace()

    msp.add_point((1.0, 2.0, 3.0))
    msp.add_line((0.0, 0.0, 0.0), (10.0, 0.0, 0.0), dxfattribs={"color": 3, "lineweight": 25})
    msp.add_ray((0.0, 0.0, 0.0), (1.0, 0.0, 0.0))
    msp.add_xline((0.0, 0.0, 0.0), (0.0, 1.0, 0.0))
    msp.add_circle((0.0, 0.0, 0.0), 5.0)
    msp.add_arc((0.0, 0.0, 0.0), 10.0, 0.0, 90.0)
    msp.add_ellipse((0.0, 0.0, 0.0), major_axis=(4.0, 0.0, 0.0), ratio=0.5)
    msp.add_spline([(0.0, 0.0, 0.0), (1.0, 2.0, 0.0), (3.0, 1.0, 0.0), (4.0, 0.0, 0.0)])
    msp.add_lwpolyline([(0.0, 0.0), (2.0, 0.0), (2.0, 3.0)], close=False)
    msp.add_polyline3d([(0.0, 0.0, 0.0), (0.0, 0.0, 4.0), (3.0, 0.0, 4.0)])
    msp.add_3dface([(0.0, 0.0, 0.0), (2.0, 0.0, 0.0), (2.0, 2.0, 0.0), (0.0, 2.0, 0.0)])
    msp.add_solid([(0.0, 0.0), (2.0, 0.0), (0.0, 2.0), (2.0, 2.0)])
    msp.add_trace([(0.0, 0.0), (3.0, 0.0), (0.0, 1.0), (3.0, 1.0)])
    hatch = msp.add_hatch(color=2)
    hatch.paths.add_polyline_path([(0.0, 0.0), (5.0, 0.0), (5.0, 4.0), (0.0, 4.0)], is_closed=True)
    mesh = msp.add_mesh()
    with mesh.edit_data() as mdata:
        mdata.vertices = [(0, 0, 0), (2, 0, 0), (2, 2, 0), (0, 2, 0)]
        mdata.faces = [[0, 1, 2, 3]]
    msp.add_text("NOTE A", dxfattribs={"insert": (1.0, 1.0), "height": 0.25})
    msp.add_mtext("MULTI\\PLINE", dxfattribs={"insert": (2.0, 2.0), "char_height": 0.3})
    msp.add_leader([(0.0, 0.0, 0.0), (3.0, 4.0, 0.0)])

    # Paperspace viewport + Image definition reference metadata
    ps = doc.paperspace()
    ps.add_viewport(center=(100.0, 100.0), size=(200.0, 150.0), view_center_point=(0.0, 0.0), view_height=50.0)
    img_def = doc.add_image_def("C:/restricted/blueprint.tif", size_in_pixel=(4000, 3000))
    msp.add_image(insert=(0, 0), size_in_units=(10, 8), image_def=img_def)

    doc.saveas(p)
    project, _ = ExtractionPipeline().run(p)
    cad = project.cad_document
    found_types = {e.entity_type for e in cad.cad_entities}
    expected = {
        "POINT",
        "LINE",
        "RAY",
        "XLINE",
        "CIRCLE",
        "ARC",
        "ELLIPSE",
        "SPLINE",
        "LWPOLYLINE",
        "POLYLINE",
        "3DFACE",
        "SOLID",
        "TRACE",
        "HATCH",
        "MESH",
        "TEXT",
        "MTEXT",
        "LEADER",
        "VIEWPORT",
        "IMAGE",
    }
    assert expected.issubset(found_types)

    # Infinite RAY/XLINE never fabricate length
    ray = next(e for e in cad.cad_entities if e.entity_type == "RAY")
    assert ray.geometry_metrics["length"] is None

    # IMAGE records external path in metadata WITHOUT attempting filesystem read
    img = next(e for e in cad.cad_entities if e.entity_type == "IMAGE")
    assert "blueprint.tif" in img.attributes["image_path"]
    assert any(ref["kind"] == "dxf_image_def" and ref["loaded"] is False for ref in cad.external_references)
