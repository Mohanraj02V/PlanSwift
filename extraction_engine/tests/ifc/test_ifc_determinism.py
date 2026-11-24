"""Verify IFC deterministic ordering, repeated-run digest stability, and geometry-option cache busting."""

from __future__ import annotations

from pathlib import Path

import ifcopenshell
import ifcopenshell.api

from extraction_engine.core.extraction_context import ExtractionConfig
from extraction_engine.pipeline import ExtractionPipeline


def test_ifc_deterministic_output_and_option_digest_isolation(tmp_path: Path) -> None:
    p = tmp_path / "det.ifc"
    model = ifcopenshell.file(schema="IFC4")
    proj = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcProject", name="Det")
    ifcopenshell.api.run("unit.assign_unit", model, length={"is_metric": True, "raw": "METERS"})
    ctx = ifcopenshell.api.run("context.add_context", model, context_type="Model")
    body = ifcopenshell.api.run("context.add_context", model, context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=ctx)
    storey = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBuildingStorey", name="L1")
    ifcopenshell.api.run("aggregate.assign_object", model, relating_object=proj, products=[storey])
    wall = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcWall", name="W1")
    ifcopenshell.api.run("spatial.assign_container", model, relating_structure=storey, products=[wall])
    rep = ifcopenshell.api.run("geometry.add_wall_representation", model, context=body, length=3.0, height=3.0, thickness=0.2)
    ifcopenshell.api.run("geometry.assign_representation", model, product=wall, representation=rep)
    model.write(str(p))

    p1, _ = ExtractionPipeline(ExtractionConfig(ifc_extract_geometry=False)).run(p)
    p2, _ = ExtractionPipeline(ExtractionConfig(ifc_extract_geometry=False)).run(p)
    assert p1.deterministic_digest_sha256 == p2.deterministic_digest_sha256

    # Turning on 3D geometry MUST yield a distinct digest so property-only cache is never reused as geometry-enabled
    p3, _ = ExtractionPipeline(ExtractionConfig(ifc_extract_geometry=True, ifc_geometry_threads=1)).run(p)
    assert p3.deterministic_digest_sha256 != p1.deterministic_digest_sha256
