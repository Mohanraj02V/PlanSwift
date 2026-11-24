"""Verify DXF block definitions stay separate from INSERT placements and ATTRIBs are preserved."""

from __future__ import annotations

from pathlib import Path

import ezdxf

from extraction_engine.pipeline import ExtractionPipeline


def test_dxf_blocks_separate_from_inserts_and_attribs(tmp_path: Path) -> None:
    p = tmp_path / "blocks.dxf"
    doc = ezdxf.new("R2010")
    blk = doc.blocks.new(name="DOOR_SINGLE", base_point=(0.0, 0.0, 0.0))
    blk.add_line((0.0, 0.0), (0.9, 0.0))
    blk.add_attdef("DOOR_ID", insert=(0.2, 0.2), dxfattribs={"height": 0.15})

    msp = doc.modelspace()
    ins = msp.add_blockref("DOOR_SINGLE", insert=(10.0, 20.0), dxfattribs={"xscale": 1.0, "yscale": 1.0, "rotation": 90.0})
    ins.add_attrib("DOOR_ID", "D-101", insert=(10.2, 20.2), dxfattribs={"height": 0.15})
    doc.saveas(p)

    project, _ = ExtractionPipeline().run(p)
    cad = project.cad_document
    blk_map = {b.name: b for b in cad.blocks}
    assert "DOOR_SINGLE" in blk_map
    assert blk_map["DOOR_SINGLE"].entity_count == 2

    blk_lines = [e for e in cad.cad_entities if e.block_name == "DOOR_SINGLE" and e.entity_type == "LINE"]
    msp_inserts = [e for e in cad.cad_entities if e.layout_name == "Model" and e.entity_type == "INSERT"]
    assert len(blk_lines) == 1
    assert len(msp_inserts) == 1
    assert msp_inserts[0].attributes["block_name"] == "DOOR_SINGLE"
    assert msp_inserts[0].attributes["block_attribs"]["DOOR_ID"] == "D-101"
