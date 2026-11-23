"""Unit tests for generic PlanSwift object classes, assemblies, circular formulas, and COM reconciliation."""

from __future__ import annotations

import io

from extraction_engine.core.extraction_context import ExtractionContext
from extraction_engine.core.extraction_result import ProvenanceStatus
from extraction_engine.parsers.formula_parser import resolve_formula_graph
from extraction_engine.parsers.metadata_parser import enrich_project_and_pages
from extraction_engine.parsers.relationship_parser import build_relationships_and_assemblies
from extraction_engine.parsers.xml_parser import parse_xmldata_stream
from extraction_engine.reconciliation.com_package_reconciliation import reconcile_package_and_com

SYNTHETIC_MULTI_CLASS_XML = b"""<?xml version="1.0" encoding="Windows-1252"?>
<Item Class="Item" Name="MultiClassJob" GUID="{00000000-0000-0000-0000-000000000001}">
  <Properties>
    <Property Class="Type" GUID="{00000000-0000-0000-0000-000000000002}" Name="Type">Job</Property>
    <Property Class="Text" GUID="{00000000-0000-0000-0000-000000000003}" Name="Measurement Type">Metric</Property>
  </Properties>
  <Items>
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
            <Property Class="Text" GUID="{20000000-0000-0000-0000-000000000012}" Name="DigitizerData"><![CDATA[<?xml version="1.0" encoding="UTF-8"?><Points><Point X="0" Y="0" PointType="Normal"/><Point X="10" Y="0" PointType="Normal"/><Point X="10" Y="5" PointType="Normal"/><Point X="0" Y="5" PointType="Normal"/></Points>]]></Property>
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


def test_generic_classes_assembly_area_cycle_and_com_reconciliation() -> None:
    ctx = ExtractionContext()
    project = parse_xmldata_stream(io.BytesIO(SYNTHETIC_MULTI_CLASS_XML), "synthetic.xml", ctx)
    enrich_project_and_pages(project, None)
    build_relationships_and_assemblies(project)
    resolve_formula_graph(project.objects)

    # Unknown class is preserved with UNSUPPORTED status, never dropped
    unknown_obj = next(o for o in project.objects if o.native_class == "FutureCustomClass")
    assert unknown_obj.is_known_class is False
    assert unknown_obj.provenance == ProvenanceStatus.UNSUPPORTED
    assert unknown_obj.properties[0].name == ""
    assert unknown_obj.properties[0].raw_value == "preserved empty name"

    # Assembly & Part extracted accurately
    assert len(project.assemblies) == 1
    assert project.assemblies[0].components[0].name == "Vibration Pad"
    assert project.assemblies[0].components[0].quantity_raw == "4"

    # Circular formula detection works without eval()
    asm_obj = next(o for o in project.objects if o.native_class == "Assembly")
    assert all(f.has_circular_dependency for f in asm_obj.formulas)

    # Area polygon shoelace derived area = 10 * 5 = 50.0 while preserving raw Qty='[Takeoff]'
    area_obj = next(o for o in project.objects if o.native_class == "Area")
    qty_m = next(m for m in area_obj.measurements if m.property_name == "Qty")
    assert qty_m.raw_formula == "[Takeoff]"
    assert qty_m.derived_quantity == 50.0

    # Reconcile COM payload providing PlanSwift evaluated Qty
    com_payload = {
        "source_system": "PlanSwiftCOM",
        "planswift_version": "12.0",
        "prog_id": "PlanSwift.PlanSwift12",
        "objects": [
            {
                "native_guid": "{20000000-0000-0000-0000-000000000001}",
                "native_class": "Area",
                "name": "Floor Slab",
                "properties": {
                    "Qty": {"formula": "[Takeoff]", "result": "50.00"},
                },
            }
        ],
    }
    rec = reconcile_package_and_com(project, com_payload)
    assert rec["com_available"] is True
    assert rec["matched_objects"] == 1
    assert qty_m.planswift_computed_quantity == 50.0
    assert qty_m.status == ProvenanceStatus.COMPUTED_BY_PLANSWIFT
    assert qty_m.raw_formula == "[Takeoff]"
