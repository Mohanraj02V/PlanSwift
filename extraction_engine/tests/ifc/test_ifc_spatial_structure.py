"""Verify IFC spatial structure tree (IfcProject -> IfcSite -> IfcBuilding -> IfcBuildingStorey -> IfcSpace/Products)."""

from __future__ import annotations

from pathlib import Path

import ifcopenshell
import ifcopenshell.api

from extraction_engine.pipeline import ExtractionPipeline


def test_ifc_spatial_hierarchy_chain(tmp_path: Path) -> None:
    p = tmp_path / "spatial.ifc"
    model = ifcopenshell.file(schema="IFC4")
    proj = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcProject", name="P1")
    site = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcSite", name="S1")
    bldg = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBuilding", name="B1")
    st1 = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBuildingStorey", name="Floor 1")
    space = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcSpace", name="Room 101")
    beam = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBeam", name="Beam A")

    ifcopenshell.api.run("aggregate.assign_object", model, relating_object=proj, products=[site])
    ifcopenshell.api.run("aggregate.assign_object", model, relating_object=site, products=[bldg])
    ifcopenshell.api.run("aggregate.assign_object", model, relating_object=bldg, products=[st1])
    ifcopenshell.api.run("aggregate.assign_object", model, relating_object=st1, products=[space])
    ifcopenshell.api.run("spatial.assign_container", model, relating_structure=st1, products=[beam])
    model.write(str(p))

    project, _ = ExtractionPipeline().run(p)
    by_gid = {el.global_id: el for el in project.cad_document.ifc_elements}
    assert by_gid[site.GlobalId].spatial_parent_guid == proj.GlobalId
    assert by_gid[bldg.GlobalId].spatial_parent_guid == site.GlobalId
    assert by_gid[st1.GlobalId].spatial_parent_guid == bldg.GlobalId
    assert by_gid[space.GlobalId].spatial_parent_guid == st1.GlobalId
    assert by_gid[beam.GlobalId].spatial_parent_guid == st1.GlobalId
    assert by_gid[beam.GlobalId].storey_name == "Floor 1"
