"""Verify nested IFC ObjectPlacement world coordinate composition and cyclic placement guard."""

from __future__ import annotations

from pathlib import Path

import ifcopenshell
import ifcopenshell.api
import numpy as np

from extraction_engine.pipeline import ExtractionPipeline


def test_ifc_nested_placements_and_cycle_guard(tmp_path: Path) -> None:
    p = tmp_path / "placements.ifc"
    model = ifcopenshell.file(schema="IFC4")
    proj = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcProject", name="Placements")
    ifcopenshell.api.run("unit.assign_unit", model, length={"is_metric": True, "raw": "METERS"})
    bldg = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBuilding", name="B1")
    storey = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBuildingStorey", name="F2")
    col = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcColumn", name="C1")
    ifcopenshell.api.run("aggregate.assign_object", model, relating_object=proj, products=[bldg])
    ifcopenshell.api.run("aggregate.assign_object", model, relating_object=bldg, products=[storey])
    ifcopenshell.api.run("spatial.assign_container", model, relating_structure=storey, products=[col])

    # Explicit nested relative ObjectPlacements:
    # Building at (10, 0, 0) -> Storey relative (0, 5, 3.5) -> Column relative (2, 1, 0) => world (12, 6, 3.5)
    lp_b = model.create_entity(
        "IfcLocalPlacement",
        RelativePlacement=model.create_entity(
            "IfcAxis2Placement3D",
            Location=model.create_entity("IfcCartesianPoint", Coordinates=(10.0, 0.0, 0.0)),
        ),
    )
    lp_s = model.create_entity(
        "IfcLocalPlacement",
        PlacementRelTo=lp_b,
        RelativePlacement=model.create_entity(
            "IfcAxis2Placement3D",
            Location=model.create_entity("IfcCartesianPoint", Coordinates=(0.0, 5.0, 3.5)),
        ),
    )
    lp_c = model.create_entity(
        "IfcLocalPlacement",
        PlacementRelTo=lp_s,
        RelativePlacement=model.create_entity(
            "IfcAxis2Placement3D",
            Location=model.create_entity("IfcCartesianPoint", Coordinates=(2.0, 1.0, 0.0)),
        ),
    )
    bldg.ObjectPlacement = lp_b
    storey.ObjectPlacement = lp_s
    col.ObjectPlacement = lp_c

    # Second element with cyclic PlacementRelTo -> must produce warning without crashing or hanging
    cyc = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcWall", name="CyclicPlacement")
    ifcopenshell.api.run("spatial.assign_container", model, relating_structure=storey, products=[cyc])
    lp1 = model.create_entity("IfcLocalPlacement", RelativePlacement=model.create_entity("IfcAxis2Placement3D", Location=model.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, 0.0))))
    lp2 = model.create_entity("IfcLocalPlacement", PlacementRelTo=lp1, RelativePlacement=model.create_entity("IfcAxis2Placement3D", Location=model.create_entity("IfcCartesianPoint", Coordinates=(1.0, 0.0, 0.0))))
    lp1.PlacementRelTo = lp2
    cyc.ObjectPlacement = lp1
    model.write(str(p))

    project, _ = ExtractionPipeline().run(p)
    col_el = next(el for el in project.cad_document.ifc_elements if el.global_id == col.GlobalId)
    assert [round(v, 4) for v in col_el.world_origin] == [12.0, 6.0, 3.5]

    cyc_el = next(el for el in project.cad_document.ifc_elements if el.global_id == cyc.GlobalId)
    assert any("Circular PlacementRelTo" in w for w in cyc_el.warnings)
