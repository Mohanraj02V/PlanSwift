"""Verify DXF extraction determinism across repeated runs and option-sensitive digest invalidation."""

from __future__ import annotations

from pathlib import Path

import ezdxf

from extraction_engine.core.extraction_context import ExtractionConfig
from extraction_engine.exporters.json_exporter import build_structured_project_export
from extraction_engine.pipeline import ExtractionPipeline


def test_dxf_deterministic_output_and_digest(tmp_path: Path) -> None:
    p = tmp_path / "det.dxf"
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6
    msp = doc.modelspace()
    msp.add_line((0, 0), (5, 0))
    msp.add_circle((2, 2), 1.5)
    doc.saveas(p)

    proj1, rep1 = ExtractionPipeline().run(p)
    proj2, rep2 = ExtractionPipeline().run(p)

    assert proj1.deterministic_digest_sha256 == proj2.deterministic_digest_sha256
    e1 = [e.entity_key for e in proj1.cad_document.cad_entities]
    e2 = [e.entity_key for e in proj2.cad_document.cad_entities]
    assert e1 == e2

    exp1 = build_structured_project_export(proj1, rep1)
    assert exp1["schema_version"] == "1.0"
    assert exp1["cad_document"]["source_format"] == "dxf_ascii"

    # Changing extraction options changes deterministic digest cleanly
    proj3, _ = ExtractionPipeline(ExtractionConfig(dxf_enable_rule_classification=False)).run(p)
    assert proj3.deterministic_digest_sha256 != proj1.deterministic_digest_sha256
