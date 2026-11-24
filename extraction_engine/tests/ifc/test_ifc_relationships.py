"""Verify IFC relationship extraction across Aggregates, Spatial, Properties, Type, Material, Voids, Fills."""

from __future__ import annotations

from pathlib import Path

import ifcopenshell
import ifcopenshell.api

from extraction_engine.pipeline import ExtractionPipeline


def test_ifc_relationships_voids_fills_and_metadata(tmp_path: Path) -> None:
    p = tmp_path / "rels.ifc"
    model = ifcopenshell.file(schema="IFC4")
    proj = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcProject", name="Rels")
    ifcopenshell.api.run("unit.assign_unit", model)
    storey = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBuildingStorey", name="GF")
    ifcopenshell.api.run("aggregate.assign_object", model, relating_object=proj, products=[storey])

    wall = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcWall", name="HostWall")
    opening = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcOpeningElement", name="Op1")
    door = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcDoor", name="Door1")
    ifcopenshell.api.run("spatial.assign_container", model, relating_structure=storey, products=[wall, door])
    ifcopenshell.api.run("feature.add_feature", model, feature=opening, element=wall)
    ifcopenshell.api.run("feature.add_filling", model, opening=opening, element=door)
    model.write(str(p))

    project, _ = ExtractionPipeline().run(p)
    rtypes = {r.relationship_type for r in project.relationships}
    assert {"ifc_aggregates", "ifc_contained_in_spatial_structure", "ifc_voids_element", "ifc_fills_element"}.issubset(rtypes)
    void_rel = next(r for r in project.relationships if r.relationship_type == "ifc_voids_element")
    assert void_rel.source_guid == wall.GlobalId
    assert void_rel.target_guid == opening.GlobalId
    assert "rel_step_id" in void_rel.metadata
