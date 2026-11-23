"""Streaming memory-efficient XMLData.XML parser with XXE/DTD protection."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import BinaryIO

from lxml import etree

from extraction_engine.core.extraction_context import ExtractionContext, SecurityValidationError
from extraction_engine.core.extraction_registry import ExtractionRegistry
from extraction_engine.core.extraction_result import (
    CanonicalGeometry,
    CanonicalMeasurement,
    CanonicalMeasurementSection,
    CanonicalObject,
    CanonicalProject,
    CanonicalProperty,
    ProvenanceRecord,
    ProvenanceStatus,
)
from extraction_engine.parsers.formula_parser import parse_property_formula
from extraction_engine.parsers.geometry_parser import parse_digitizer_geometry
from extraction_engine.parsers.property_parser import parse_property_element


@dataclass
class _ItemFrame:
    native_guid: str
    native_class: str
    name: str
    parent_guid: str | None
    root_path: str
    depth: int
    raw_attributes: dict[str, str]
    properties: list[CanonicalProperty] = field(default_factory=list)
    child_guids: list[str] = field(default_factory=list)
    child_sections: list[CanonicalMeasurementSection] = field(default_factory=list)


def parse_xmldata_stream(
    xml_stream: BinaryIO,
    source_file_label: str,
    ctx: ExtractionContext,
    registry: ExtractionRegistry | None = None,
) -> CanonicalProject:
    """Stream-parse XMLData.XML using lxml.etree.iterparse without DTD/entity expansion."""
    reg = registry or ExtractionRegistry()
    objects: list[CanonicalObject] = []
    discovered_classes: dict[str, int] = {}
    unsupported_classes: dict[str, int] = {}
    provenance_records: list[ProvenanceRecord] = []

    stack: list[_ItemFrame] = []
    item_ordinal = 0
    in_properties = False

    # iterparse supports streaming huge XML trees while rejecting DTD/entities/network access
    context = etree.iterparse(
        xml_stream,
        events=("start", "end"),
        resolve_entities=False,
        no_network=True,
        load_dtd=False,
        huge_tree=False,
    )

    try:
        for event, elem in context:
            tag = elem.tag
            if event == "start":
                if tag == "Item":
                    item_ordinal += 1
                    if item_ordinal % 250 == 0:
                        ctx.check_cancelled()
                    attrs = dict(elem.attrib)
                    guid = attrs.get("GUID", "")
                    cls_name = attrs.get("Class", "Unknown")
                    name = attrs.get("Name", "")
                    parent_guid = stack[-1].native_guid if stack else None
                    depth = len(stack)
                    parent_path = stack[-1].root_path if stack else ""
                    item_path = f"{parent_path}/{name or guid}" if parent_path else (name or guid)

                    frame = _ItemFrame(
                        native_guid=guid,
                        native_class=cls_name,
                        name=name,
                        parent_guid=parent_guid,
                        root_path=item_path,
                        depth=depth,
                        raw_attributes=attrs,
                    )
                    if stack:
                        stack[-1].child_guids.append(guid)
                    stack.append(frame)
                elif tag == "Properties":
                    in_properties = True
            elif event == "end":
                if tag == "Property" and in_properties and stack:
                    frame = stack[-1]
                    prop_attrs = dict(elem.attrib)
                    raw_text = elem.text if elem.text is not None else ""
                    prop_loc = f"{source_file_label}#{frame.native_guid}/{prop_attrs.get('Name', '') or prop_attrs.get('GUID', '')}"
                    c_prop = parse_property_element(prop_attrs, raw_text, prop_loc)
                    frame.properties.append(c_prop)
                    elem.clear()
                elif tag == "Properties":
                    in_properties = False
                    elem.clear()
                elif tag == "Item" and stack:
                    frame = stack.pop()
                    c_obj, obj_prov = _finalize_item_frame(
                        frame,
                        source_file_label=source_file_label,
                        ctx=ctx,
                        registry=reg,
                    )
                    objects.append(c_obj)
                    discovered_classes[c_obj.native_class] = discovered_classes.get(c_obj.native_class, 0) + 1
                    if not c_obj.is_known_class:
                        unsupported_classes[c_obj.native_class] = unsupported_classes.get(c_obj.native_class, 0) + 1
                    provenance_records.append(obj_prov)

                    # Attach finalized measurement section onto parent takeoff item frame if still open
                    if c_obj.is_measurement_section and stack and c_obj.sections:
                        stack[-1].child_sections.extend(c_obj.sections)

                    elem.clear()
                    while elem.getprevious() is not None:
                        del elem.getparent()[0]
    except etree.XMLSyntaxError as exc:
        raise SecurityValidationError(f"Unsafe or malformed XML in '{source_file_label}': {exc}") from exc

    if not objects:
        raise SecurityValidationError(f"No PlanSwift <Item> elements found in '{source_file_label}'.")

    # iterparse finishes children before parents; sort deterministically with depth=0 root first while keeping discovery index?
    # Better: reverse/order by tree order using root->children order! Let's restore top-down document order cleanly:
    ordered_objects = _restore_document_order(objects)
    root_obj = ordered_objects[0]

    return CanonicalProject(
        native_guid=root_obj.native_guid,
        name=root_obj.name,
        project_type=root_obj.native_type or "Job",
        xml_encoding="Windows-1252",
        objects=ordered_objects,
        discovered_classes=discovered_classes,
        unsupported_classes=unsupported_classes,
        provenance_records=provenance_records,
    )


def _restore_document_order(postorder_objects: list[CanonicalObject]) -> list[CanonicalObject]:
    by_guid = {obj.native_guid.upper(): obj for obj in postorder_objects}
    roots = [obj for obj in postorder_objects if obj.parent_guid is None]
    ordered: list[CanonicalObject] = []
    visited: set[str] = set()

    def walk(node: CanonicalObject) -> None:
        key = node.native_guid.upper()
        if key in visited:
            return
        visited.add(key)
        ordered.append(node)
        for ch_guid in node.child_guids:
            child = by_guid.get(ch_guid.upper())
            if child is not None:
                walk(child)

    for r in roots:
        walk(r)
    # Include any stray nodes if malformed hierarchy
    for obj in postorder_objects:
        if obj.native_guid.upper() not in visited:
            ordered.append(obj)
    return ordered


def _finalize_item_frame(
    frame: _ItemFrame,
    source_file_label: str,
    ctx: ExtractionContext,
    registry: ExtractionRegistry,
) -> tuple[CanonicalObject, ProvenanceRecord]:
    props_by_name = {p.name: p for p in frame.properties if p.name}
    type_prop = props_by_name.get("Type")
    native_type = type_prop.raw_value if type_prop else ""
    behavior = registry.describe_class(frame.native_class, native_type)

    order_prop = props_by_name.get("OrderIndex")
    order_index = order_prop.parsed_value if order_prop and isinstance(order_prop.parsed_value, int) else None

    page_guid_prop = props_by_name.get("PageGUID")
    page_guid = page_guid_prop.raw_value.strip() if page_guid_prop and page_guid_prop.raw_value.strip() else None

    group_prop = props_by_name.get("GroupId")
    created_prop = props_by_name.get("Created By")
    ts_prop = props_by_name.get("Time Stamp")

    is_page = behavior.role == "page" or frame.native_class == "Page"
    is_section = behavior.role == "measurement_section"

    formulas = []
    for p in frame.properties:
        f = parse_property_formula(frame.native_guid, p)
        if f is not None:
            formulas.append(f)

    geometries: list[CanonicalGeometry] = []
    sections: list[CanonicalMeasurementSection] = []
    measurements: list[CanonicalMeasurement] = []

    if is_section:
        dd_prop = props_by_name.get("DigitizerData")
        raw_dd = dd_prop.raw_value if dd_prop else ""
        geom = parse_digitizer_geometry(
            raw_digitizer_xml=raw_dd,
            section_guid=frame.native_guid,
            parent_object_guid=frame.parent_guid or "",
            page_guid=page_guid,
            native_section_class=frame.native_class,
        )
        geometries.append(geom)

        z_prop = props_by_name.get("ZOrder")
        z_order = z_prop.parsed_value if z_prop and isinstance(z_prop.parsed_value, int) else None
        vis_prop = props_by_name.get("Visible")
        visible = bool(vis_prop.parsed_value) if vis_prop and isinstance(vis_prop.parsed_value, bool) else None
        box_prop = props_by_name.get("Box Mode")
        page_name_prop = props_by_name.get("Page")

        derived_qty, derived_unit = _derive_section_quantity(frame.native_class, geom)
        section = CanonicalMeasurementSection(
            native_guid=frame.native_guid,
            parent_object_guid=frame.parent_guid or "",
            native_class=frame.native_class,
            name=frame.name,
            order_index=order_index,
            z_order=z_order,
            page_guid=page_guid,
            page_name_formula=page_name_prop.raw_value if page_name_prop else None,
            visible=visible,
            box_mode=box_prop.raw_value if box_prop else None,
            point_count=geom.point_count,
            derived_quantity=derived_qty,
            derived_unit=derived_unit,
            geometry=geom,
            provenance=ProvenanceStatus.ORIGINAL,
        )
        sections.append(section)

        measurements.append(
            CanonicalMeasurement(
                measurement_key=f"{frame.native_guid}:section_geometry",
                object_guid=frame.parent_guid or frame.native_guid,
                section_guid=frame.native_guid,
                page_guid=page_guid,
                measurement_type=frame.native_class,
                property_name="DigitizerData",
                raw_formula=None,
                native_stored_value=f"{geom.point_count} points",
                derived_quantity=derived_qty,
                unit=derived_unit,
                status=ProvenanceStatus.DERIVED,
                notes="Derived strictly from native DigitizerData coordinates (no rasterization).",
            )
        )

    elif behavior.role == "takeoff_item":
        # Aggregate derived quantities from finalized child sections WITHOUT replacing raw Qty formula!
        qty_prop = props_by_name.get("Qty")
        raw_qty = qty_prop.raw_value if qty_prop else None
        is_takeoff_formula = raw_qty is not None and "[" in raw_qty
        derived_total = _aggregate_sections_quantity(frame.native_class, frame.child_sections)
        unit_val = qty_prop.input_units or qty_prop.units if qty_prop else None
        if unit_val is None and frame.native_class == "Count":
            unit_val = "EA"

        measurements.append(
            CanonicalMeasurement(
                measurement_key=f"{frame.native_guid}:Qty",
                object_guid=frame.native_guid,
                section_guid=None,
                page_guid=None,
                measurement_type=frame.native_class,
                property_name="Qty",
                raw_formula=raw_qty if is_takeoff_formula else None,
                native_stored_value=raw_qty,
                derived_quantity=derived_total,
                unit=unit_val,
                precision=qty_prop.decimal_places if qty_prop else None,
                status=ProvenanceStatus.ORIGINAL if raw_qty is not None else ProvenanceStatus.UNRESOLVED,
                notes=(
                    f"Raw formula '{raw_qty}' preserved; derived_quantity={derived_total} summed from {len(frame.child_sections)} child sections."
                    if is_takeoff_formula
                    else None
                ),
            )
        )

        # Record dimensional template properties explicitly flagged when object is Count (not a measured length)
        for dim_name in ("Length", "Width", "Depth", "Wall Height"):
            dp = props_by_name.get(dim_name)
            if dp is not None and dp.raw_value.strip() != "":
                is_template_default = frame.native_class == "Count" and dp.raw_value.strip() == "1"
                measurements.append(
                    CanonicalMeasurement(
                        measurement_key=f"{frame.native_guid}:{dim_name}",
                        object_guid=frame.native_guid,
                        measurement_type=frame.native_class,
                        property_name=dim_name,
                        raw_formula=dp.raw_value if dp.is_formula else None,
                        native_stored_value=dp.raw_value,
                        derived_quantity=float(dp.parsed_value)
                        if isinstance(dp.parsed_value, (int, float)) and not is_template_default
                        else None,
                        unit=dp.units or dp.input_units,
                        precision=dp.decimal_places,
                        is_default_template_value=is_template_default,
                        status=ProvenanceStatus.ORIGINAL,
                        notes="Count default property template value; not a measured line length."
                        if is_template_default
                        else None,
                    )
                )

    obj = CanonicalObject(
        native_guid=frame.native_guid,
        native_class=frame.native_class,
        native_type=native_type,
        name=frame.name,
        parent_guid=frame.parent_guid,
        root_path=frame.root_path,
        depth=frame.depth,
        order_index=order_index,
        child_guids=frame.child_guids,
        is_known_class=behavior.known,
        is_measurement_section=is_section,
        is_page=is_page,
        page_guid=page_guid,
        group_id=group_prop.raw_value.strip() if group_prop and group_prop.raw_value.strip() else None,
        division=_prop_text(props_by_name, "Division"),
        subdivision=_prop_text(props_by_name, "SubDivision"),
        phase=_prop_text(props_by_name, "Phase"),
        cost_code=_prop_text(props_by_name, "Cost Code"),
        location=_prop_text(props_by_name, "Location"),
        zone=_prop_text(props_by_name, "Zone"),
        created_by=created_prop.raw_value if created_prop else None,
        timestamp_raw=ts_prop.raw_value if ts_prop else None,
        properties=frame.properties,
        measurements=measurements,
        sections=sections,
        geometries=geometries,
        formulas=formulas,
        provenance=ProvenanceStatus.ORIGINAL if behavior.known else ProvenanceStatus.UNSUPPORTED,
        raw_attributes=frame.raw_attributes,
    )

    prov = ProvenanceRecord(
        source_adapter="planswift_xml_stream_parser",
        source_file=source_file_label,
        source_location=frame.root_path,
        source_object_guid=frame.native_guid,
        source_class=frame.native_class,
        status=ProvenanceStatus.ORIGINAL if behavior.known else ProvenanceStatus.UNSUPPORTED,
        parser_version=ctx.config.parser_version,
        extraction_run_id=ctx.run_id,
    )
    return obj, prov


def _prop_text(props_by_name: dict[str, CanonicalProperty], name: str) -> str | None:
    prop = props_by_name.get(name)
    if prop is None:
        return None
    val = prop.raw_value.strip()
    return val if val else None


def _derive_section_quantity(native_section_class: str, geom: CanonicalGeometry) -> tuple[float | None, str | None]:
    cls_low = native_section_class.lower()
    if "count" in cls_low:
        return float(geom.point_count), "EA"
    if ("linear" in cls_low or "segment" in cls_low) and geom.derived_polyline_length is not None:
        return geom.derived_polyline_length, "raw_page_units"
    if ("area" in cls_low or "volume" in cls_low or "perimeter" in cls_low) and geom.derived_polygon_area is not None:
        return geom.derived_polygon_area, "raw_page_units_sq"
    return None, None


def _aggregate_sections_quantity(
    native_class: str,
    child_sections: list[CanonicalMeasurementSection],
) -> float | None:
    if not child_sections:
        return 0.0 if native_class == "Count" else None
    vals = [s.derived_quantity for s in child_sections if s.derived_quantity is not None]
    if not vals:
        return None
    return round(sum(vals), 6)
