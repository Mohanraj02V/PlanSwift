"""Verify IFC unit assignment parsing (Millimeters, Imperial Feet, and missing LENGTHUNIT guard)."""

from __future__ import annotations

from pathlib import Path

import ifcopenshell
import ifcopenshell.api

from extraction_engine.pipeline import ExtractionPipeline


def test_ifc_unit_assignments_mm_and_missing(tmp_path: Path) -> None:
    # 1. Millimeters model: native Qto length=5000 mm -> normalized 5.0 m
    p_mm = tmp_path / "units_mm.ifc"
    m_mm = ifcopenshell.file(schema="IFC4")
    ifcopenshell.api.run("root.create_entity", m_mm, ifc_class="IfcProject", name="MM Proj")
    ifcopenshell.api.run("unit.assign_unit", m_mm, length={"is_metric": True, "raw": "MILLIMETRES"})
    w = ifcopenshell.api.run("root.create_entity", m_mm, ifc_class="IfcWall", name="W-MM")
    qto = ifcopenshell.api.run("pset.add_qto", m_mm, product=w, name="Qto_WallBaseQuantities")
    ifcopenshell.api.run("pset.edit_qto", m_mm, qto=qto, properties={"Length": 5000.0})
    m_mm.write(str(p_mm))

    proj_mm, _ = ExtractionPipeline().run(p_mm)
    assert abs(proj_mm.cad_document.unit_to_meter_factor - 0.001) < 1e-9
    wel = next(el for el in proj_mm.cad_document.ifc_elements if el.global_id == w.GlobalId)
    q = wel.quantity_sets[0].quantities[0]
    assert q.raw_value == 5000.0
    assert abs(q.normalized_value - 5.0) < 1e-9
    assert q.normalized_unit == "m"

    # 2. Model without IfcUnitAssignment -> factor stays None (never fabricated!)
    p_none = tmp_path / "no_units.ifc"
    m_none = ifcopenshell.file(schema="IFC4")
    m_none.create_entity("IfcProject", GlobalId=ifcopenshell.guid.new(), Name="NoUnits")
    m_none.write(str(p_none))

    proj_none, _ = ExtractionPipeline().run(p_none)
    assert proj_none.cad_document.unit_to_meter_factor is None
    assert any("No explicit LENGTHUNIT" in w for w in proj_none.source_manifest.warnings)
