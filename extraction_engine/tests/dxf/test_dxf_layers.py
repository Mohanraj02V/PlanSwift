"""Verify DXF layer metadata extraction, entity membership counts, and non-guaranteed semantic rule provenance."""

from __future__ import annotations

from pathlib import Path

import ezdxf

from extraction_engine.core.extraction_result import ProvenanceStatus
from extraction_engine.pipeline import ExtractionPipeline


def test_dxf_layers_and_inferred_classification_separation(tmp_path: Path) -> None:
    p = tmp_path / "layers.dxf"
    doc = ezdxf.new("R2010")
    doc.layers.add("A-WALL", color=1, linetype="CONTINUOUS")
    lyr_off = doc.layers.add("TEMP-OFF", color=7)
    lyr_off.off()
    lyr_off.freeze()
    lyr_off.lock()

    msp = doc.modelspace()
    msp.add_line((0, 0), (10, 0), dxfattribs={"layer": "A-WALL"})
    msp.add_line((0, 1), (10, 1), dxfattribs={"layer": "A-WALL"})
    msp.add_circle((0, 0), 2.0, dxfattribs={"layer": "TEMP-OFF"})
    doc.saveas(p)

    project, _ = ExtractionPipeline().run(p)
    cad = project.cad_document
    by_name = {l.name: l for l in cad.layers}

    assert by_name["A-WALL"].color == 1
    assert by_name["A-WALL"].is_on is True
    assert by_name["A-WALL"].entity_count == 2
    assert by_name["TEMP-OFF"].is_on is False
    assert by_name["TEMP-OFF"].is_frozen is True
    assert by_name["TEMP-OFF"].is_locked is True
    assert by_name["TEMP-OFF"].entity_count == 1

    wall_ent = next(e for e in cad.cad_entities if e.layer == "A-WALL")
    assert wall_ent.classification.native_type == "LINE"
    assert wall_ent.classification.rule_based_category == "Wall"
    assert wall_ent.classification.classification_provenance == ProvenanceStatus.INFERRED
