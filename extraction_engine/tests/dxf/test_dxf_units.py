"""Verify DXF $INSUNITS handling and strict non-fabrication when unitless ($INSUNITS=0)."""

from __future__ import annotations

from pathlib import Path

import ezdxf

from extraction_engine.pipeline import ExtractionPipeline


def test_dxf_unit_conversions_and_unitless_guard(tmp_path: Path) -> None:
    # 1. Feet ($INSUNITS = 2) -> 10 ft = 3.048 m
    p_ft = tmp_path / "feet.dxf"
    d_ft = ezdxf.new("R2010")
    d_ft.header["$INSUNITS"] = 2
    d_ft.modelspace().add_line((0.0, 0.0), (10.0, 0.0))
    d_ft.saveas(p_ft)

    proj_ft, _ = ExtractionPipeline().run(p_ft)
    ent_ft = next(e for e in proj_ft.cad_document.cad_entities if e.entity_type == "LINE")
    assert proj_ft.cad_document.source_units == "ft"
    assert abs(ent_ft.geometry_metrics["length"] - 10.0) < 1e-9
    assert abs(ent_ft.geometry_metrics["normalized_length_m"] - 3.048) < 1e-9

    # 2. Unitless ($INSUNITS = 0) -> must preserve raw length=10.0 and leave normalized_length_m=None
    p_ul = tmp_path / "unitless.dxf"
    d_ul = ezdxf.new("R2010")
    d_ul.header["$INSUNITS"] = 0
    d_ul.modelspace().add_line((0.0, 0.0), (10.0, 0.0))
    d_ul.saveas(p_ul)

    proj_ul, _ = ExtractionPipeline().run(p_ul)
    ent_ul = next(e for e in proj_ul.cad_document.cad_entities if e.entity_type == "LINE")
    assert proj_ul.cad_document.source_units == "unitless"
    assert abs(ent_ul.geometry_metrics["length"] - 10.0) < 1e-9
    assert ent_ul.geometry_metrics["normalized_length_m"] is None
