"""Verify IFC geometry extraction (property-only skip vs bounded iterator, curved cylinder, watertight volume)."""

from __future__ import annotations

import math
from pathlib import Path

import ifcopenshell
import ifcopenshell.api

from extraction_engine.core.extraction_context import ExtractionConfig
from extraction_engine.pipeline import ExtractionPipeline


def test_ifc_property_only_vs_geometry_iterator_and_curved_column(tmp_path: Path) -> None:
    p = tmp_path / "geom_curved.ifc"
    model = ifcopenshell.file(schema="IFC4")
    proj = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcProject", name="Geom Test")
    ifcopenshell.api.run("unit.assign_unit", model, length={"is_metric": True, "raw": "METERS"})
    ctx = ifcopenshell.api.run("context.add_context", model, context_type="Model")
    body = ifcopenshell.api.run("context.add_context", model, context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=ctx)
    storey = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBuildingStorey", name="L1")
    ifcopenshell.api.run("aggregate.assign_object", model, relating_object=proj, products=[storey])

    # Exact box wall: 4 * 3 * 0.25 -> volume = 3.0 m^3, area = 2*(4*3 + 4*0.25 + 3*0.25) = 27.5 m^2
    wall = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcWall", name="BoxWall")
    ifcopenshell.api.run("spatial.assign_container", model, relating_structure=storey, products=[wall])
    w_rep = ifcopenshell.api.run("geometry.add_wall_representation", model, context=body, length=4.0, height=3.0, thickness=0.25)
    ifcopenshell.api.run("geometry.assign_representation", model, product=wall, representation=w_rep)

    # Curved cylinder column: radius = 0.5m, height = 4.0m -> exact vol = pi * 0.25 * 4 = pi (~3.1416 m^3)
    col = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcColumn", name="RoundCol")
    ifcopenshell.api.run("spatial.assign_container", model, relating_structure=storey, products=[col])
    circle_prof = model.create_entity("IfcCircleProfileDef", ProfileType="AREA", Radius=0.5)
    pos = model.create_entity("IfcAxis2Placement3D", Location=model.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, 0.0)))
    dir_z = model.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0))
    solid = model.create_entity("IfcExtrudedAreaSolid", SweptArea=circle_prof, Position=pos, ExtrudedDirection=dir_z, Depth=4.0)
    shape_rep = model.create_entity("IfcShapeRepresentation", ContextOfItems=body, RepresentationIdentifier="Body", RepresentationType="SweptSolid", Items=[solid])
    prod_rep = model.create_entity("IfcProductDefinitionShape", Representations=[shape_rep])
    col.Representation = prod_rep

    model.write(str(p))

    # 1. Default property-only mode skips tessellation cleanly
    proj_prop, rep_prop = ExtractionPipeline(ExtractionConfig(ifc_extract_geometry=False)).run(p)
    w_prop = next(el for el in proj_prop.cad_document.ifc_elements if el.global_id == wall.GlobalId)
    assert w_prop.geometry_summary.status == "skipped_property_only"
    assert w_prop.geometry_summary.volume is None

    # 2. Geometry-enabled bounded iterator computes accurate volumes & surface areas
    proj_geo, rep_geo = ExtractionPipeline(ExtractionConfig(ifc_extract_geometry=True, ifc_geometry_threads=2)).run(p)
    w_geo = next(el for el in proj_geo.cad_document.ifc_elements if el.global_id == wall.GlobalId)
    assert w_geo.geometry_summary.status == "calculated"
    assert w_geo.geometry_summary.is_watertight is True
    assert abs(w_geo.geometry_summary.volume - 3.0) < 1e-4
    assert abs(w_geo.geometry_summary.surface_area - 27.5) < 1e-4

    c_geo = next(el for el in proj_geo.cad_document.ifc_elements if el.global_id == col.GlobalId)
    assert c_geo.geometry_summary.status == "calculated"
    assert c_geo.geometry_summary.is_watertight is True
    # Faceted cylinder approximation stays within 2% of exact pi
    assert abs(c_geo.geometry_summary.volume - math.pi) / math.pi < 0.02
