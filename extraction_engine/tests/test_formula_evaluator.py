"""Unit tests for the safe AST PlanSwift formula lexer, parser, and evaluator."""

from __future__ import annotations

import io
import pytest

from extraction_engine.core.extraction_context import ExtractionContext
from extraction_engine.core.extraction_result import ProvenanceStatus
from extraction_engine.formulas.evaluator import FormulaEvaluator
from extraction_engine.formulas.parser import FormulaSyntaxError, parse_formula_ast
from extraction_engine.normalizers.geometry_normalizer import normalize_project_geometry
from extraction_engine.parsers.formula_parser import resolve_and_evaluate_formulas
from extraction_engine.parsers.metadata_parser import enrich_project_and_pages
from extraction_engine.parsers.relationship_parser import build_relationships_and_assemblies
from extraction_engine.parsers.xml_parser import parse_xmldata_stream

FORMULA_TEST_XML = rb"""<?xml version="1.0" encoding="Windows-1252"?>
<Item Class="Item" Name="Job" GUID="{00000000-0000-0000-0000-000000000001}">
  <Properties>
    <Property Class="Type" GUID="{00000000-0000-0000-0000-000000000002}" Name="Type">Job</Property>
    <Property Class="Number" GUID="{00000000-0000-0000-0000-000000000003}" Name="Sales Tax 1">8.25</Property>
  </Properties>
  <Items>
    <Item Class="Page" Name="Main Plan" GUID="{10000000-0000-0000-0000-000000000001}">
      <Properties>
        <Property Class="Type" GUID="{10000000-0000-0000-0000-000000000002}" Name="Type">.TIFF Page</Property>
        <Property Class="Number" GUID="{10000000-0000-0000-0000-000000000003}" Name="ScaleX">10</Property>
        <Property Class="Number" GUID="{10000000-0000-0000-0000-000000000004}" Name="ScaleY">10</Property>
        <Property Class="Text" GUID="{10000000-0000-0000-0000-000000000005}" Name="Scale Units">FT</Property>
        <Property Class="Number" GUID="{10000000-0000-0000-0000-000000000006}" Name="PageWidth">[!PageWidth]</Property>
      </Properties>
      <Items/>
    </Item>
    <Item Class="Folder" Name="Takeoff" GUID="{20000000-0000-0000-0000-000000000001}">
      <Properties/>
      <Items>
        <Item Class="Area" Name="Slab Area" GUID="{30000000-0000-0000-0000-000000000001}">
          <Properties>
            <Property Class="Type" GUID="{30000000-0000-0000-0000-000000000002}" Name="Type">Area</Property>
            <Property Class="Number" GUID="{30000000-0000-0000-0000-000000000003}" Name="Waste %">10</Property>
            <Property Class="CheckBox" GUID="{30000000-0000-0000-0000-000000000004}" Name="Round Qtys">True</Property>
            <Property Class="Number" GUID="{30000000-0000-0000-0000-000000000005}" Name="Multiply">1</Property>
            <Property Class="Number" GUID="{30000000-0000-0000-0000-000000000006}" Name="Qty Formula">[Area]</Property>
            <Property Class="Number" GUID="{30000000-0000-0000-0000-000000000007}" Name="Qty" units="SQ FT">(RoundUp([Qty Formula] * ([Waste %]/100+1))) * ([Round Qtys]) * [Multiply] + ([Qty Formula] * ([Waste %]/100+1)) * (1-[Round Qtys]) * [Multiply]</Property>
            <Property Class="Number" GUID="{30000000-0000-0000-0000-000000000008}" Name="Pitch">5</Property>
            <Property Class="Number" GUID="{30000000-0000-0000-0000-000000000009}" Name="PitchFactor">Sqrt([Pitch]*[Pitch]+144)/12</Property>
            <Property Class="Number" GUID="{30000000-0000-0000-0000-000000000010}" Name="DivZero">10 / [Zero]</Property>
            <Property Class="Number" GUID="{30000000-0000-0000-0000-000000000011}" Name="Zero">0</Property>
            <Property Class="Number" GUID="{30000000-0000-0000-0000-000000000012}" Name="MissingSetting">[\Settings\DefaultColor]</Property>
            <Property Class="Text" GUID="{30000000-0000-0000-0000-000000000013}" Name="Folder">[!TakeoffFolder]</Property>
            <Property Class="Text" GUID="{30000000-0000-0000-0000-000000000014}" Name="CustomScript" Expression="-1">Begin
  Result := CustomUnknownPascal();
End;</Property>
          </Properties>
          <Items>
            <Item Class="Area Section" Name="Sec 1" GUID="{31000000-0000-0000-0000-000000000001}">
              <Properties>
                <Property Class="Text" GUID="{31000000-0000-0000-0000-000000000002}" Name="PageGUID">{10000000-0000-0000-0000-000000000001}</Property>
                <Property Class="Text" GUID="{31000000-0000-0000-0000-000000000003}" Name="PageName">[[PageGUID]\Name]</Property>
                <Property Class="Text" GUID="{31000000-0000-0000-0000-000000000004}" Name="DigitizerData"><![CDATA[<?xml version="1.0"?><Points><Point X="0" Y="0"/><Point X="100" Y="0"/><Point X="100" Y="50"/><Point X="0" Y="50"/></Points>]]></Property>
              </Properties>
              <Items/>
            </Item>
            <Item Class="Item" Name="Rebar" GUID="{32000000-0000-0000-0000-000000000001}">
              <Properties>
                <Property Class="Type" GUID="{32000000-0000-0000-0000-000000000002}" Name="Type">Material</Property>
                <Property Class="Number" GUID="{32000000-0000-0000-0000-000000000003}" Name="Material Coverage">10 * 10</Property>
                <Property Class="Number" GUID="{32000000-0000-0000-0000-000000000004}" Name="Qty" units="EA">RoundUp([Area] / [Material Coverage])</Property>
                <Property Class="Number" GUID="{32000000-0000-0000-0000-000000000005}" Name="TaxRate">[\Job\Sales Tax 1]</Property>
                <Property Class="Text" GUID="{32000000-0000-0000-0000-000000000006}" Name="Label">[..\Name] ([Qty] EA)</Property>
              </Properties>
              <Items/>
            </Item>
          </Items>
        </Item>
      </Items>
    </Item>
  </Items>
</Item>
"""


def test_formula_parser_rejects_malformed_syntax() -> None:
    with pytest.raises(FormulaSyntaxError):
        parse_formula_ast("[A] + * [B]")
    with pytest.raises(FormulaSyntaxError):
        parse_formula_ast("[A] + (")


def test_formula_evaluator_full_planswift_semantics() -> None:
    ctx = ExtractionContext()
    project = parse_xmldata_stream(io.BytesIO(FORMULA_TEST_XML), "formula_test.xml", ctx)
    enrich_project_and_pages(project, None)
    build_relationships_and_assemblies(project)
    normalize_project_geometry(project)
    resolve_and_evaluate_formulas(project)

    by_name = {o.name: o for o in project.objects}
    slab = by_name["Slab Area"]
    sec = by_name["Sec 1"]
    rebar = by_name["Rebar"]
    page = by_name["Main Plan"]

    f_slab = {f.property_name: f for f in slab.formulas}
    # 100x50 px at ScaleX=ScaleY=10 -> 10*5 = 50 SQ FT. With 10% waste + RoundUp => RoundUp(55) = 55
    assert f_slab["Qty"].evaluation_status == ProvenanceStatus.CALCULATED
    assert f_slab["Qty"].calculated_numeric == 55.0
    assert f_slab["Qty"].calculation_inputs["[Waste %]"] == 10

    # Sqrt(5*5 + 144) / 12 = 13 / 12 = 1.083333...
    assert f_slab["PitchFactor"].evaluation_status == ProvenanceStatus.CALCULATED
    assert abs(f_slab["PitchFactor"].calculated_numeric - (13.0 / 12.0)) < 1e-5

    # Folder sysvar
    assert f_slab["Folder"].calculated_value == "Takeoff"

    # Explicit non-fabricated unresolved / unsupported errors
    assert f_slab["DivZero"].evaluation_status == ProvenanceStatus.UNRESOLVED
    assert f_slab["DivZero"].calculation_reason == "division_by_zero"
    assert f_slab["MissingSetting"].evaluation_status == ProvenanceStatus.UNRESOLVED
    assert f_slab["MissingSetting"].calculation_reason == "missing_external_settings"
    assert f_slab["CustomScript"].evaluation_status == ProvenanceStatus.UNSUPPORTED
    assert f_slab["CustomScript"].calculation_reason == "unsupported_pascal_script"

    # PageWidth stays unresolved without image reading
    f_page = {f.property_name: f for f in page.formulas}
    assert f_page["PageWidth"].evaluation_status == ProvenanceStatus.UNRESOLVED
    assert f_page["PageWidth"].calculation_reason == "system_variable_unavailable"

    # Cross-object lookup [[PageGUID]\Name]
    f_sec = {f.property_name: f for f in sec.formulas}
    assert f_sec["PageName"].calculated_value == "Main Plan"

    # Child Item arithmetic literal '10 * 10' + parent Area (50) -> RoundUp(50/100) = 1
    f_rebar = {f.property_name: f for f in rebar.formulas}
    assert f_rebar["Qty"].calculated_numeric == 1.0
    assert f_rebar["TaxRate"].calculated_numeric == 8.25
    assert f_rebar["Label"].calculated_value == "Slab Area (1 EA)"

    # Verify Evaluator supports IF / MIN / MAX cleanly
    ev = FormulaEvaluator(project)
    out = ev._eval_expression(slab, "_test", "If([Pitch] > 4, Max(10, 25), Min(1, 2))")
    assert out.numeric == 25.0
