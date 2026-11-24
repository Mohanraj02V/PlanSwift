"""Geometry calibration and coordinate normalizer: preserves raw page pixels while calibrating via ScaleX/ScaleY."""

from __future__ import annotations

import math

from extraction_engine.core.extraction_result import CanonicalPoint, CanonicalProject, ProvenanceStatus
from extraction_engine.normalizers.unit_normalizer import (
    convert_area_to_sq_meters,
    convert_length_to_meters,
    scale_area_unit_label,
)


def _scaled_polyline_length(points: list[CanonicalPoint], sx: float, sy: float, closed: bool = False) -> float:
    total = 0.0
    for i in range(len(points) - 1):
        dx = (points[i + 1].x - points[i].x) / sx
        dy = (points[i + 1].y - points[i].y) / sy
        total += math.hypot(dx, dy)
    if closed and len(points) >= 3:
        dx = (points[0].x - points[-1].x) / sx
        dy = (points[0].y - points[-1].y) / sy
        total += math.hypot(dx, dy)
    return round(total, 6)


def _scaled_segment_pairs_length(points: list[CanonicalPoint], sx: float, sy: float) -> float:
    total = 0.0
    for i in range(0, len(points) - 1, 2):
        dx = (points[i + 1].x - points[i].x) / sx
        dy = (points[i + 1].y - points[i].y) / sy
        total += math.hypot(dx, dy)
    return round(total, 6)


def _scaled_polygon_area(points: list[CanonicalPoint], sx: float, sy: float) -> float:
    area_px2 = 0.0
    n = len(points)
    for i in range(n):
        j = (i + 1) % n
        area_px2 += points[i].x * points[j].y
        area_px2 -= points[j].x * points[i].y
    return round(abs(area_px2) / (2.0 * sx * sy), 6)


def normalize_project_geometry(project: CanonicalProject) -> None:
    """Calibrate geometry strictly using explicit Page ScaleX/ScaleY properties (zero raster guessing)."""
    pages_by_guid = {p.native_guid.upper(): p for p in project.pages}

    for obj in project.objects:
        sec_by_guid = {s.native_guid.upper(): s for s in obj.sections}
        for geom in obj.geometries:
            page = pages_by_guid.get(geom.page_guid.upper()) if geom.page_guid else None
            sx = page.scale_x if page and page.scale_x and page.scale_x > 0 else (page.numeric_scale_factor if page and page.numeric_scale_factor and page.numeric_scale_factor > 0 else None)
            sy = page.scale_y if page and page.scale_y and page.scale_y > 0 else sx
            s_unit = (page.scale_units or "").strip() if page else ""

            if sx is not None and sy is not None and sx > 0 and sy > 0:
                geom.scale_x = sx
                geom.scale_y = sy
                geom.scale_unit = s_unit
                geom.is_calibrated = True
                geom.coordinate_system = "planswift_page_calibrated"
                geom.derived_metrics_provenance = ProvenanceStatus.RECONSTRUCTED

                for pt in geom.points:
                    pt.normalized_x = round(pt.x / sx, 6)
                    pt.normalized_y = round(pt.y / sy, 6)

                if geom.geometry_type == "Segment" and len(geom.points) >= 2:
                    if "segment" in obj.native_class.lower() and len(geom.points) > 2:
                        geom.calibrated_length = _scaled_segment_pairs_length(geom.points, sx, sy)
                    else:
                        geom.calibrated_length = _scaled_polyline_length(geom.points, sx, sy)
                    geom.calibrated_unit = s_unit
                    geom.normalized_length_m = convert_length_to_meters(geom.calibrated_length, s_unit)
                elif geom.geometry_type == "Polyline" and len(geom.points) >= 2:
                    geom.calibrated_length = _scaled_polyline_length(geom.points, sx, sy)
                    geom.calibrated_unit = s_unit
                    geom.normalized_length_m = convert_length_to_meters(geom.calibrated_length, s_unit)
                elif geom.geometry_type == "Polygon" and len(geom.points) >= 3:
                    geom.calibrated_length = _scaled_polyline_length(geom.points, sx, sy, closed=True)
                    geom.calibrated_area = _scaled_polygon_area(geom.points, sx, sy)
                    geom.calibrated_unit = scale_area_unit_label(s_unit) or s_unit
                    geom.normalized_length_m = convert_length_to_meters(geom.calibrated_length, s_unit)
                    geom.normalized_area_m2 = convert_area_to_sq_meters(geom.calibrated_area, s_unit)

                # Update matching MeasurementSection & DigitizerData measurement record to reflect calibrated scale
                sec = sec_by_guid.get(geom.section_guid.upper())
                if sec is not None:
                    if geom.calibrated_area is not None and ("area" in obj.native_class.lower() or "volume" in obj.native_class.lower() or "perimeter" in obj.native_class.lower()):
                        sec.derived_quantity = geom.calibrated_area
                        sec.derived_unit = geom.calibrated_unit
                    elif geom.calibrated_length is not None and ("linear" in obj.native_class.lower() or "segment" in obj.native_class.lower()):
                        sec.derived_quantity = geom.calibrated_length
                        sec.derived_unit = geom.calibrated_unit

                for meas in obj.measurements:
                    if meas.property_name == "DigitizerData" and meas.section_guid == geom.section_guid:
                        if geom.calibrated_area is not None:
                            meas.reconstructed_quantity = geom.calibrated_area
                            meas.derived_quantity = geom.calibrated_area
                            meas.unit = geom.calibrated_unit
                            meas.normalized_quantity = geom.normalized_area_m2
                            meas.normalized_unit = "m^2" if geom.normalized_area_m2 is not None else ""
                        elif geom.calibrated_length is not None:
                            meas.reconstructed_quantity = geom.calibrated_length
                            meas.derived_quantity = geom.calibrated_length
                            meas.unit = geom.calibrated_unit
                            meas.normalized_quantity = geom.normalized_length_m
                            meas.normalized_unit = "m" if geom.normalized_length_m is not None else ""
            else:
                geom.is_calibrated = False
                for pt in geom.points:
                    pt.normalized_x = None
                    pt.normalized_y = None
