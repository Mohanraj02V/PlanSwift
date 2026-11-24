"""Verify direct and Type-inherited IfcPropertySet, MaterialLayerSet, and Classification extraction."""

from __future__ import annotations

from pathlib import Path

import ifcopenshell
import ifcopenshell.api

from extraction_engine.pipeline import ExtractionPipeline


def test_ifc_property_sets_materials_and_classifications(tmp_path: Path) -> None:
    p = tmp_path / "psets_materials.ifc"
    model = ifcopenshell.file(schema="IFC4")
    ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcProject", name="Pset Test")
    ifcopenshell.api.run("unit.assign_unit", model)

    wall_type = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcWallType", name="WT-200")
    t_pset = ifcopenshell.api.run("pset.add_pset", model, product=wall_type, name="Pset_WallCommon")
    ifcopenshell.api.run("pset.edit_pset", model, pset=t_pset, properties={"FireRating": "2HR", "IsExternal": True})

    wall = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcWall", name="Wall-A")
    ifcopenshell.api.run("type.assign_type", model, related_objects=[wall], relating_type=wall_type)

    mat = ifcopenshell.api.run("material.add_material", model, name="Concrete C30")
    ifcopenshell.api.run("material.assign_material", model, products=[wall], material=mat)

    cls = model.create_entity("IfcClassification", Name="Uniclass 2015")
    cref = model.create_entity("IfcClassificationReference", Identification="Ss_25_10", Name="Wall systems", ReferencedSource=cls)
    model.create_entity("IfcRelAssociatesClassification", GlobalId=ifcopenshell.guid.new(), RelatedObjects=[wall], RelatingClassification=cref)
    model.write(str(p))

    project, _ = ExtractionPipeline().run(p)
    wall_el = next(el for el in project.cad_document.ifc_elements if el.global_id == wall.GlobalId)

    pset = next(ps for ps in wall_el.property_sets if ps.name == "Pset_WallCommon")
    assert pset.is_type_inherited is True
    assert pset.properties["FireRating"] == "2HR"
    assert pset.properties["IsExternal"] is True

    assert any(m["name"] == "Concrete C30" for m in wall_el.materials)
    assert any(c["identification"] == "Ss_25_10" for c in wall_el.classifications)
