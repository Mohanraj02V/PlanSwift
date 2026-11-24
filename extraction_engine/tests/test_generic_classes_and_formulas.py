"""Unit tests for generic PlanSwift object classes, assemblies, circular formulas, and standalone reconciliation."""

from __future__ import annotations

import io

from extraction_engine.calculators.quantity_engine import compute_project_quantities
from extraction_engine.core.extraction_context import ExtractionContext
from extraction_engine.core.extraction_result import ProvenanceStatus
from extraction_engine.normalizers.geometry_normalizer import normalize_project_geometry
from extraction_engine.parsers.formula_parser import resolve_and_evaluate_formulas
from extraction_engine.parsers.metadata_parser import enrich_project_and_pages
from extraction_engine.parsers.relationship_parser import build_relationships_and_assemblies
from extraction_engine.parsers.xml_parser import parse_xmldata_stream
from extraction_engine.reconciliation.standalone_reconciliation import reconcile_standalone_project

SYNTHETIC_MULTI_CLASS_XML = b"""<?xml version="1.0" encoding="Windows-1252"?>
<Item Class="Item" Name="MultiClassJob" GUID="{00000000-0000-0000-0000-000000000001}">
  <Properties>
    <Property Class="Type" GUID="{00000000-0000-0000-0000-000000000002}" Name="Type">Job</Property>
    <Property Class="Text" GUID="{00000000-0000-0000-0000-000000000003}" Name="Measurement Type">Metric</Property>
  </Properties>
  <Items>
    <Item Class="Page" Name="Floor Plan" GUID="{90000000-0000-0000-0000-000000000001}">
      <Properties>
        <Property Class="Type" GUID="{90000000-0000-0000-0000-000000000002}" Name="Type">.TIFF Page</Property>
        <Property Class="Number" GUID="{90000000-0000-0000-0000-000000000003}" Name="ScaleX">2</Property>
        <Property Class="Number" GUID="{90000000-0000-0000-0000-000000000004}" Name="ScaleY">2</Property>
        <Property Class="Text" GUID="{90000000-0000-0000-0000-000000000005}" Name="Scale Units">M</Property>
      </Properties>
      <Items/>
    </Item>
    <Item Class="Assembly" Name="HVAC Chiller Assembly" GUID="{10000000-0000-0000-0000-000000000001}">
      <Properties>
        <Property Class="Type" GUID="{10000000-0000-0000-0000-000000000002}" Name="Type">Assembly</Property>
        <Property Class="Number" GUID="{10000000-0000-0000-0000-000000000003}" Name="A">[B] + 1</Property>
        <Property Class="Number" GUID="{10000000-0000-0000-0000-000000000004}" Name="B">[A] + 1</Property>
      </Properties>
      <Items>
        <Item Class="Part" Name="Vibration Pad" GUID="{10000000-0000-0000-0000-000000000010}">
          <Properties>
            <Property Class="Type" GUID="{10000000-0000-0000-0000-000000000011}" Name="Type">Part</Property>
            <Property Class="Number" GUID="{10000000-0000-0000-0000-000000000012}" Name="Qty" units="EA">4</Property>
          </Properties>
          <Items/>
        </Item>
      </Items>
    </Item>
    <Item Class="Area" Name="Floor Slab" GUID="{20000000-0000-0000-0000-000000000001}">
      <Properties>
        <Property Class="Type" GUID="{20000000-0000-0000-0000-000000000002}" Name="Type">Area</Property>
        <Property Class="Number" GUID="{20000000-0000-0000-0000-000000000003}" Name="Qty">[Takeoff]</Property>
      </Properties>
      <Items>
        <Item Class="Area Section" Name="Section" GUID="{20000000-0000-0000-0000-000000000010}">
          <Properties>
            <Property Class="Type" GUID="{20000000-0000-0000-0000-000000000011}" Name="Type">Area Section</Property>
            <Property Class="Text" GUID="{20000000-0000-0000-0000-000000000013}" Name="PageGUID">{90000000-0000-0000-0000-000000000001}</Property>
            <Property Class="Text" GUID="{20000000-0000-0000-0000-000000000012}" Name="DigitizerData"><![CDATA[<?xml version="1.0" encoding="UTF-8"?><Points><Point X="0" Y="0" PointType="Normal"/><Point X="20" Y="0" PointType="Normal"/><Point X="20" Y="10" PointType="Normal"/><Point X="0" Y="10" PointType="Normal"/></Points>]]></Property>
          </Properties>
          <Items/>
        </Item>
      </Items>
    </Item>
    <Item Class="FutureCustomClass" Name="Unknown Proprietary Widget" GUID="{30000000-0000-0000-0000-000000000001}">
      <Properties>
        <Property Class="Text" GUID="{30000000-0000-0000-0000-000000000002}" Name="">preserved empty name</Property>
      </Properties>
      <Items/>
    </Item>
  </Items>
</Item>
"""


def test_generic_classes_assembly_area_cycle_and_standalone_reconciliation() -> None:
    ctx = ExtractionContext()
    project = parse_xmldata_stream(io.BytesIO(SYNTHETIC_MULTI_CLASS_XML), "synthetic.xml", ctx)
    enrich_project_and_pages(project, None)
    build_relationships_and_assemblies(project)
    normalize_project_geometry(project)
    resolve_and_evaluate_formulas(project)
    compute_project_quantities(project)

    # Unknown class is preserved with UNSUPPORTED status, never dropped
    unknown_obj = next(o for o in project.objects if o.native_class == "FutureCustomClass")
    assert unknown_obj.is_known_class is False
    assert unknown_obj.provenance == ProvenanceStatus.UNSUPPORTED
    assert unknown_obj.properties[0].name == ""
    assert unknown_obj.properties[0].raw_value == "preserved empty name"
    assert len(project.unsupported_objects) == 1

    # Assembly & Part extracted accurately
    assert len(project.assemblies) == 1
    assert project.assemblies[0].components[0].name == "Vibration Pad"
    assert project.assemblies[0].components[0].calculated_quantity == 4.0

    # Circular formula detection works without eval()
    asm_obj = next(o for o in project.objects if o.native_class == "Assembly")
    assert all(f.has_circular_dependency for f in asm_obj.formulas)
    assert all(f.calculation_reason == "circular_dependency" for f in asm_obj.formulas)

    # Area polygon: raw pixels = 20*10=200 px^2; with ScaleX=2, ScaleY=2 -> 50.0 SQ M calibrated
    area_obj = next(o for o in project.objects if o.native_class == "Area")
    sec_obj = next(o for o in project.objects if o.native_class == "Area Section")
    assert sec_obj.geometries[0].derived_polygon_area == 200.0
    assert sec_obj.geometries[0].calibrated_area == 50.0
    qty_m = next(m for m in area_obj.measurements if m.property_name == "Qty")
    assert qty_m.raw_formula == "[Takeoff]"
    assert qty_m.reconstructed_quantity == 50.0
    assert qty_m.calculated_quantity == 50.0
    assert qty_m.status == ProvenanceStatus.CALCULATED

    # Standalone reconciliation without COM
    rec = reconcile_standalone_project(project)
    assert rec["mode"] == "standalone_zip_verified"
    assert rec["com_available"] is False
    assert rec["matched_objects"] == len(project.objects)
    assert rec["formulas_calculated"] >= 1
    assert rec["geometries_calibrated"] == 1
