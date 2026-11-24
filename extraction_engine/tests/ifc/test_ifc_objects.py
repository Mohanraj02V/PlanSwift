"""Verify generic IFC object extraction preserving GlobalIds, STEP IDs, classes, and proxy/generic objects."""

from __future__ import annotations

from pathlib import Path

import ifcopenshell
import ifcopenshell.api

from extraction_engine.pipeline import ExtractionPipeline


def test_ifc_object_categories_and_identifiers(tmp_path: Path) -> None:
    p = tmp_path / "objects.ifc"
    model = ifcopenshell.file(schema="IFC4")
    proj = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcProject", name="BIM Sample")
    ifcopenshell.api.run("unit.assign_unit", model)
    site = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcSite", name="Site A")
    bldg = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBuilding", name="Tower 1")
    storey = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBuildingStorey", name="Level 1")
    ifcopenshell.api.run("aggregate.assign_object", model, relating_object=proj, products=[site])
    ifcopenshell.api.run("aggregate.assign_object", model, relating_object=site, products=[bldg])
    ifcopenshell.api.run("aggregate.assign_object", model, relating_object=bldg, products=[storey])

    wall = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcWall", name="W-101")
    slab = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcSlab", name="S-101")
    col = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcColumn", name="C-101")
    beam = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBeam", name="B-101")
    door = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcDoor", name="D-101")
    win = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcWindow", name="WN-101")
    proxy = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBuildingElementProxy", name="Custom Unit")
    ifcopenshell.api.run("spatial.assign_container", model, relating_structure=storey, products=[wall, slab, col, beam, door, win, proxy])
    model.write(str(p))

    project, _ = ExtractionPipeline().run(p)
    cad = project.cad_document
    classes = {el.ifc_class for el in cad.ifc_elements}
    assert {"IfcProject", "IfcSite", "IfcBuilding", "IfcBuildingStorey", "IfcWall", "IfcSlab", "IfcColumn", "IfcBeam", "IfcDoor", "IfcWindow", "IfcBuildingElementProxy"}.issubset(classes)

    wall_el = next(el for el in cad.ifc_elements if el.global_id == wall.GlobalId)
    assert wall_el.step_id == wall.id()
    assert wall_el.name == "W-101"
    assert wall_el.storey_name == "Level 1"
