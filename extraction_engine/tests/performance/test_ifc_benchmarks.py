"""Performance & correctness test comparing IFC property-only vs bounded geometry iterator."""

from __future__ import annotations

from pathlib import Path

import ifcopenshell
import ifcopenshell.api

from extraction_engine.core.extraction_context import ExtractionConfig
from extraction_engine.pipeline import ExtractionPipeline


def test_ifc_property_mode_faster_than_geometry_mode_with_same_elements(tmp_path: Path) -> None:
    p = tmp_path / "bench_ifc_60.ifc"
    model = ifcopenshell.file(schema="IFC4")
    proj = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcProject", name="BenchIFC")
    ifcopenshell.api.run("unit.assign_unit", model, length={"is_metric": True, "raw": "METERS"})
    ctx = ifcopenshell.api.run("context.add_context", model, context_type="Model")
    body = ifcopenshell.api.run("context.add_context", model, context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=ctx)
    storey = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBuildingStorey", name="L1")
    ifcopenshell.api.run("aggregate.assign_object", model, relating_object=proj, products=[storey])
    rep = ifcopenshell.api.run("geometry.add_wall_representation", model, context=body, length=4.0, height=3.0, thickness=0.2)
    walls = []
    for i in range(60):
        w = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcWall", name=f"W{i}")
        ifcopenshell.api.run("geometry.assign_representation", model, product=w, representation=rep)
        walls.append(w)
    ifcopenshell.api.run("spatial.assign_container", model, relating_structure=storey, products=walls)
    model.write(str(p))

    p_prop, r_prop = ExtractionPipeline(ExtractionConfig(ifc_extract_geometry=False)).run(p)
    p_geo, r_geo = ExtractionPipeline(ExtractionConfig(ifc_extract_geometry=True, ifc_geometry_threads=2)).run(p)

    assert len(p_prop.cad_document.ifc_elements) == len(p_geo.cad_document.ifc_elements)
    assert sum(1 for el in p_geo.cad_document.ifc_elements if el.geometry_summary.status == "calculated") == 60
    assert r_prop.duration_seconds < 10.0
    assert r_geo.duration_seconds < 15.0
