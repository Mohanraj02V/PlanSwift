"""Verify IFC unsupported/open/broken geometry preservation and explicit status reporting."""

from __future__ import annotations

from pathlib import Path

import ifcopenshell
import ifcopenshell.api

from extraction_engine.core.extraction_context import ExtractionConfig
from extraction_engine.pipeline import ExtractionPipeline


def test_ifc_open_shell_non_watertight_and_empty_rep_handling(tmp_path: Path) -> None:
    p = tmp_path / "open_geom.ifc"
    model = ifcopenshell.file(schema="IFC4")
    proj = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcProject", name="OpenGeom")
    ifcopenshell.api.run("unit.assign_unit", model, length={"is_metric": True, "raw": "METERS"})
    ctx = ifcopenshell.api.run("context.add_context", model, context_type="Model")
    body = ifcopenshell.api.run("context.add_context", model, context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=ctx)
    storey = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBuildingStorey", name="L1")
    ifcopenshell.api.run("aggregate.assign_object", model, relating_object=proj, products=[storey])

    # Open planar face (IfcFaceBasedSurfaceModel) -> has surface_area=4.0 m^2, volume MUST be None (not watertight!)
    plate = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcPlate", name="OpenSheet")
    ifcopenshell.api.run("spatial.assign_container", model, relating_structure=storey, products=[plate])
    pts = [model.create_entity("IfcCartesianPoint", Coordinates=c) for c in [(0.0, 0.0, 0.0), (2.0, 0.0, 0.0), (2.0, 2.0, 0.0), (0.0, 2.0, 0.0)]]
    loop = model.create_entity("IfcPolyLoop", Polygon=pts)
    bound = model.create_entity("IfcFaceOuterBound", Bound=loop, Orientation=True)
    face = model.create_entity("IfcFace", Bounds=[bound])
    cface = model.create_entity("IfcConnectedFaceSet", CfsFaces=[face])
    fbsm = model.create_entity("IfcFaceBasedSurfaceModel", FbsmFaces=[cface])
    srep = model.create_entity("IfcShapeRepresentation", ContextOfItems=body, RepresentationIdentifier="Body", RepresentationType="SurfaceModel", Items=[fbsm])
    plate.Representation = model.create_entity("IfcProductDefinitionShape", Representations=[srep])

    # Element with empty Representation
    proxy_no_rep = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBuildingElementProxy", name="EmptyProxy")
    ifcopenshell.api.run("spatial.assign_container", model, relating_structure=storey, products=[proxy_no_rep])
    model.write(str(p))

    project, _ = ExtractionPipeline(ExtractionConfig(ifc_extract_geometry=True, ifc_geometry_threads=1)).run(p)
    el_plate = next(el for el in project.cad_document.ifc_elements if el.global_id == plate.GlobalId)
    assert el_plate.geometry_summary.status == "calculated"
    assert el_plate.geometry_summary.is_watertight is False
    assert el_plate.geometry_summary.volume is None
    assert abs(el_plate.geometry_summary.surface_area - 4.0) < 1e-4

    el_empty = next(el for el in project.cad_document.ifc_elements if el.global_id == proxy_no_rep.GlobalId)
    assert el_empty.geometry_summary.status == "no_representation"
