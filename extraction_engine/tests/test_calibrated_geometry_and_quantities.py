"""Unit tests for calibrated DigitizerData geometry, unit conversions, and quantity rollups."""

from __future__ import annotations

import io

from extraction_engine.calculators.quantity_engine import compute_project_quantities
from extraction_engine.core.extraction_context import ExtractionContext
from extraction_engine.core.extraction_result import ProvenanceStatus
from extraction_engine.normalizers.geometry_normalizer import normalize_project_geometry
from extraction_engine.normalizers.unit_normalizer import convert_area_to_sq_meters, convert_length_to_meters
from extraction_engine.parsers.formula_parser import resolve_and_evaluate_formulas
from extraction_engine.parsers.geometry_parser import parse_digitizer_geometry
from extraction_engine.parsers.metadata_parser import enrich_project_and_pages
from extraction_engine.parsers.xml_parser import parse_xmldata_stream


def test_uncalibrated_vs_calibrated_geometry_preserves_raw_pixels() -> None:
    xml_data = b"""<?xml version="1.0" encoding="UTF-8"?>
<Item Class="Item" Name="GeomJob" GUID="{00000000-0000-0000-0000-000000000001}">
  <Properties/>
  <Items>
    <Item Class="Page" Name="CalibratedPage" GUID="{10000000-0000-0000-0000-000000000001}">
      <Properties>
        <Property Class="Number" GUID="{10000000-0000-0000-0000-000000000002}" Name="ScaleX">37.5</Property>
        <Property Class="Number" GUID="{10000000-0000-0000-0000-000000000003}" Name="ScaleY">37.5</Property>
        <Property Class="Text" GUID="{10000000-0000-0000-0000-000000000004}" Name="Scale Units">FT</Property>
      </Properties>
      <Items/>
    </Item>
    <Item Class="Page" Name="UncalibratedPage" GUID="{10000000-0000-0000-0000-000000000010}">
      <Properties>
        <Property Class="Text" GUID="{10000000-0000-0000-0000-000000000011}" Name="Scale Units">FT</Property>
      </Properties>
      <Items/>
    </Item>
    <Item Class="Linear" Name="Wall" GUID="{20000000-0000-0000-0000-000000000001}">
      <Properties>
        <Property Class="Number" GUID="{20000000-0000-0000-0000-000000000002}" Name="Qty" inputunits="FT">[Takeoff]</Property>
      </Properties>
      <Items>
        <Item Class="Linear Section" Name="CalSec" GUID="{21000000-0000-0000-0000-000000000001}">
          <Properties>
            <Property Class="Text" GUID="{21000000-0000-0000-0000-000000000002}" Name="PageGUID">{10000000-0000-0000-0000-000000000001}</Property>
            <Property Class="Text" GUID="{21000000-0000-0000-0000-000000000003}" Name="DigitizerData"><![CDATA[<Points><Point X="0" Y="0"/><Point X="375" Y="0"/></Points>]]></Property>
          </Properties>
          <Items/>
        </Item>
      </Items>
    </Item>
    <Item Class="Linear" Name="UncalWall" GUID="{30000000-0000-0000-0000-000000000001}">
      <Properties>
        <Property Class="Number" GUID="{30000000-0000-0000-0000-000000000002}" Name="Qty">[Takeoff]</Property>
      </Properties>
      <Items>
        <Item Class="Linear Section" Name="UncalSec" GUID="{31000000-0000-0000-0000-000000000001}">
          <Properties>
            <Property Class="Text" GUID="{31000000-0000-0000-0000-000000000002}" Name="PageGUID">{10000000-0000-0000-0000-000000000010}</Property>
            <Property Class="Text" GUID="{31000000-0000-0000-0000-000000000003}" Name="DigitizerData"><![CDATA[<Points><Point X="0" Y="0"/><Point X="100" Y="0"/></Points>]]></Property>
          </Properties>
          <Items/>
        </Item>
      </Items>
    </Item>
  </Items>
</Item>"""

    project = parse_xmldata_stream(io.BytesIO(xml_data), "geom.xml", ExtractionContext())
    enrich_project_and_pages(project, None)
    normalize_project_geometry(project)
    resolve_and_evaluate_formulas(project)
    compute_project_quantities(project)

    cal_sec = next(o for o in project.objects if o.name == "CalSec")
    cg = cal_sec.geometries[0]
    assert cg.is_calibrated is True
    assert cg.derived_polyline_length == 375.0  # Raw pixel length preserved intact
    assert cg.calibrated_length == 10.0  # 375 px / 37.5 px/FT = 10.0 FT
    assert cg.normalized_length_m == 3.048

    wall = next(o for o in project.objects if o.name == "Wall")
    wall_qty = next(m for m in wall.measurements if m.property_name == "Qty")
    assert wall_qty.calculated_quantity == 10.0
    assert wall_qty.unit == "FT"

    # Uncalibrated section MUST NOT invent a calibrated quantity
    uncal_sec = next(o for o in project.objects if o.name == "UncalSec")
    ug = uncal_sec.geometries[0]
    assert ug.is_calibrated is False
    assert ug.calibrated_length is None
    assert ug.derived_polyline_length == 100.0
    uncal_wall = next(o for o in project.objects if o.name == "UncalWall")
    uq = next(m for m in uncal_wall.measurements if m.property_name == "Qty")
    assert uq.calculated_quantity is None
    assert uq.status == ProvenanceStatus.UNRESOLVED


def test_invalid_digitizer_coordinates_handled_safely() -> None:
    geom = parse_digitizer_geometry(
        '<Points><Point X="10" Y="20"/><Point X="NaN" Y="5"/><Point X="bad" Y="1"/></Points>',
        "{SEC}",
        "{PAR}",
        None,
        "Linear Section",
    )
    assert geom.point_count == 1
    assert len(geom.validation_warnings) == 2


def test_unit_si_conversions() -> None:
    assert convert_length_to_meters(10.0, "FT") == 3.048
    assert convert_area_to_sq_meters(100.0, "FT") == 9.290304
