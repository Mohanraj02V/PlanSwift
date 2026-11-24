"""Verify nested DXF INSERT scale, rotation, and translation matrix composition and cycle guard."""

from __future__ import annotations

from pathlib import Path

import ezdxf

from extraction_engine.pipeline import ExtractionPipeline


def test_dxf_nested_block_scale_rotation_translation(tmp_path: Path) -> None:
    p = tmp_path / "nested_blocks.dxf"
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6

    inner = doc.blocks.new(name="INNER_UNIT")
    inner.add_line((0.0, 0.0, 0.0), (2.0, 0.0, 0.0))  # base length = 2.0

    outer = doc.blocks.new(name="OUTER_GROUP")
    # Two scaled (1.5x) instances inside outer -> each has length 3.0 -> total 6.0 in outer local coords
    outer.add_blockref("INNER_UNIT", insert=(1.0, 0.0), dxfattribs={"xscale": 1.5, "yscale": 1.5, "rotation": 45.0})
    outer.add_blockref("INNER_UNIT", insert=(5.0, 2.0), dxfattribs={"xscale": 1.5, "yscale": 1.5, "rotation": 90.0})

    msp = doc.modelspace()
    # Outer scaled 2.0x in WCS -> expected resolved total length = 2.0 * 6.0 = 12.0 m
    msp.add_blockref("OUTER_GROUP", insert=(10.0, 20.0), dxfattribs={"xscale": 2.0, "yscale": 2.0, "rotation": 30.0})
    doc.saveas(p)

    project, _ = ExtractionPipeline().run(p)
    cad = project.cad_document
    outer_blk = next(b for b in cad.blocks if b.name == "OUTER_GROUP")
    assert "INNER_UNIT" in outer_blk.nested_block_names

    msp_insert = next(e for e in cad.cad_entities if e.layout_name == "Model" and e.entity_type == "INSERT")
    summary = msp_insert.attributes["resolved_insert_summary"]
    assert summary["expanded_child_count"] == 2
    assert abs(summary["resolved_total_length"] - 12.0) < 1e-6
