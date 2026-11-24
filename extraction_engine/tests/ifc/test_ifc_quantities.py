"""Verify native Qto_* quantity sets are preserved separately and never overwritten by geometry calculations."""

from __future__ import annotations

from pathlib import Path

import ifcopenshell
import ifcopenshell.api

from extraction_engine.core.extraction_context import ExtractionConfig
from extraction_engine.core.extraction_result import ProvenanceStatus
from extraction_engine.pipeline import ExtractionPipeline


def test_ifc_native_quantities_never_overwritten_by_calculated_geometry(tmp_path: Path) -> None:
    p = tmp_path / "qto_vs_geom.ifc"
    model = ifcopenshell.file(schema="IFC4")
    proj = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcProject", name="Qty Test")
    ifcopenshell.api.run("unit.assign_unit", model, length={"is_metric": True, "raw": "METERS"})
    ctx = ifcopenshell.api.run("context.add_context", model, context_type="Model")
    body = ifcopenshell.api.run("context.add_context", model, context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=ctx)

    storey = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBuildingStorey", name="L1")
    ifcopenshell.api.run("aggregate.assign_object", model, relating_object=proj, products=[storey])

    wall = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcWall", name="Wall-Qto")
    ifcopenshell.api.run("spatial.assign_container", model, relating_structure=storey, products=[wall])
    rep = ifcopenshell.api.run("geometry.add_wall_representation", model, context=body, length=5.0, height=3.0, thickness=0.2)
    ifcopenshell.api.run("geometry.assign_representation", model, product=wall, representation=rep)

    # Deliberately record a distinct native Qto volume (e.g., 2.50 m^3) vs actual BRep box 5 * 3 * 0.2 = 3.00 m^3
    qto = ifcopenshell.api.run("pset.add_qto", model, product=wall, name="Qto_WallBaseQuantities")
    ifcopenshell.api.run("pset.edit_qto", model, qto=qto, properties={"Length": 5.0, "Height": 3.0, "NetVolume": 2.50})
    model.write(str(p))

    project, _ = ExtractionPipeline(ExtractionConfig(ifc_extract_geometry=True, ifc_geometry_threads=1)).run(p)
    wall_el = next(el for el in project.cad_document.ifc_elements if el.global_id == wall.GlobalId)

    # Native Qto remains 2.50 with NATIVE provenance
    qto_set = next(q for q in wall_el.quantity_sets if q.name == "Qto_WallBaseQuantities")
    q_vol = next(qi for qi in qto_set.quantities if qi.name == "NetVolume")
    assert abs(q_vol.raw_value - 2.50) < 1e-9
    assert q_vol.provenance == ProvenanceStatus.NATIVE

    # Calculated geometry remains 3.00 m^3 separately with CALCULATED provenance
    assert wall_el.geometry_summary.status == "calculated"
    assert abs(wall_el.geometry_summary.volume - 3.0) < 1e-4
    assert wall_el.geometry_summary.provenance == ProvenanceStatus.CALCULATED
