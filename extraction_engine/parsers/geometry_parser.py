"""Safe parser for PlanSwift DigitizerData embedded XML geometry."""

from __future__ import annotations

import math

from lxml import etree

from extraction_engine.core.extraction_context import SecurityValidationError
from extraction_engine.core.extraction_result import CanonicalGeometry, CanonicalPoint, ProvenanceStatus

_SAFE_XML_PARSER = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False, huge_tree=False)


def parse_digitizer_geometry(
    raw_digitizer_xml: str,
    section_guid: str,
    parent_object_guid: str,
    page_guid: str | None,
    native_section_class: str,
) -> CanonicalGeometry:
    """Parse DigitizerData XML cleanly without modifying raw (X, Y) coordinates or rasterizing pages."""
    stripped = raw_digitizer_xml.strip()
    if "<!DOCTYPE" in stripped.upper() or "<!ENTITY" in stripped.upper():
        raise SecurityValidationError("Disallowed DOCTYPE/ENTITY declaration in DigitizerData.")
    if not stripped:
        return CanonicalGeometry(
            section_guid=section_guid,
            parent_object_guid=parent_object_guid,
            page_guid=page_guid,
            geometry_type="Empty",
            point_count=0,
            raw_digitizer_xml=raw_digitizer_xml,
            provenance=ProvenanceStatus.NATIVE,
        )

    try:
        root = etree.fromstring(stripped.encode("utf-8"), parser=_SAFE_XML_PARSER)
    except etree.XMLSyntaxError:
        return CanonicalGeometry(
            section_guid=section_guid,
            parent_object_guid=parent_object_guid,
            page_guid=page_guid,
            geometry_type="Invalid",
            point_count=0,
            raw_digitizer_xml=raw_digitizer_xml,
            validation_warnings=["Malformed DigitizerData XML; raw payload preserved."],
            provenance=ProvenanceStatus.UNRESOLVED,
        )

    points: list[CanonicalPoint] = []
    warnings: list[str] = []
    for idx, pt_el in enumerate(root.iter("Point")):
        raw_x = pt_el.attrib.get("X", "")
        raw_y = pt_el.attrib.get("Y", "")
        pt_type = pt_el.attrib.get("PointType", "Normal")
        try:
            x_val = float(raw_x)
            y_val = float(raw_y)
        except (TypeError, ValueError):
            warnings.append(f"Invalid coordinate pair at point index {idx}: X={raw_x!r}, Y={raw_y!r}")
            continue
        if not (math.isfinite(x_val) and math.isfinite(y_val)):
            warnings.append(f"Non-finite coordinate pair at point index {idx}: X={raw_x!r}, Y={raw_y!r}")
            continue
        points.append(
            CanonicalPoint(
                point_order=len(points),
                x=x_val,
                y=y_val,
                point_type=pt_type,
                raw_x=raw_x,
                raw_y=raw_y,
                provenance=ProvenanceStatus.NATIVE,
            )
        )

    geom_type = _classify_geometry_type(native_section_class, len(points))
    bbox_min_x = min((p.x for p in points), default=None)
    bbox_min_y = min((p.y for p in points), default=None)
    bbox_max_x = max((p.x for p in points), default=None)
    bbox_max_y = max((p.y for p in points), default=None)

    derived_len: float | None = None
    derived_area: float | None = None
    if geom_type == "Segment" and len(points) >= 2:
        derived_len = _compute_segment_pairs_length(points) if "segment" in native_section_class.lower() and len(points) > 2 else _compute_polyline_length(points)
    elif geom_type == "Polyline" and len(points) >= 2:
        derived_len = _compute_polyline_length(points)
    elif geom_type == "Polygon" and len(points) >= 3:
        derived_len = _compute_polyline_length(points, closed=True)
        derived_area = _compute_polygon_area(points)

    return CanonicalGeometry(
        section_guid=section_guid,
        parent_object_guid=parent_object_guid,
        page_guid=page_guid,
        geometry_type=geom_type,
        point_count=len(points),
        points=points,
        bbox_min_x=bbox_min_x,
        bbox_min_y=bbox_min_y,
        bbox_max_x=bbox_max_x,
        bbox_max_y=bbox_max_y,
        derived_polyline_length=derived_len,
        derived_polygon_area=derived_area,
        raw_digitizer_xml=raw_digitizer_xml,
        validation_warnings=warnings,
        provenance=ProvenanceStatus.NATIVE,
        derived_metrics_provenance=ProvenanceStatus.RECONSTRUCTED,
    )


def _classify_geometry_type(native_section_class: str, point_count: int) -> str:
    cls_low = native_section_class.lower()
    if point_count == 0:
        return "Empty"
    if "area" in cls_low or "volume" in cls_low or "perimeter" in cls_low:
        return "Polygon"
    if "segment" in cls_low or "dimension" in cls_low:
        return "Segment"
    if "linear" in cls_low or "markup" in cls_low:
        return "Segment" if point_count == 2 else "Polyline"
    if "count" in cls_low:
        return "PointCollection"
    return "MultiPoint"


def _compute_segment_pairs_length(points: list[CanonicalPoint]) -> float:
    total = 0.0
    for i in range(0, len(points) - 1, 2):
        dx = points[i + 1].x - points[i].x
        dy = points[i + 1].y - points[i].y
        total += math.hypot(dx, dy)
    return round(total, 6)


def _compute_polyline_length(points: list[CanonicalPoint], closed: bool = False) -> float:
    total = 0.0
    for i in range(len(points) - 1):
        dx = points[i + 1].x - points[i].x
        dy = points[i + 1].y - points[i].y
        total += math.hypot(dx, dy)
    if closed and len(points) >= 3:
        dx = points[0].x - points[-1].x
        dy = points[0].y - points[-1].y
        total += math.hypot(dx, dy)
    return round(total, 6)


def _compute_polygon_area(points: list[CanonicalPoint]) -> float:
    area = 0.0
    n = len(points)
    for i in range(n):
        j = (i + 1) % n
        area += points[i].x * points[j].y
        area -= points[j].x * points[i].y
    return round(abs(area) / 2.0, 6)
