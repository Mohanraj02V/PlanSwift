"""Structured geometry coordinate and GeoJSON FeatureCollection exporter (never rasterizes pages)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from extraction_engine.core.extraction_result import CanonicalProject


def project_to_geojson(project: CanonicalProject) -> dict[str, Any]:
    """Represent native DigitizerData coordinate sequences as structured GeoJSON Features."""
    features: list[dict[str, Any]] = []
    obj_lookup = {o.native_guid.upper(): o for o in project.objects}

    for obj in project.objects:
        parent = obj_lookup.get(obj.parent_guid.upper()) if obj.parent_guid else None
        for geom in obj.geometries:
            if not geom.points:
                continue
            coords = [[pt.x, pt.y] for pt in geom.points]
            if geom.geometry_type == "Polygon" and len(coords) >= 3:
                closed = coords if coords[0] == coords[-1] else coords + [coords[0]]
                geom_dict: dict[str, Any] = {"type": "Polygon", "coordinates": [closed]}
            elif geom.geometry_type in ("Polyline", "Segment") and len(coords) >= 2:
                geom_dict = {"type": "LineString", "coordinates": coords}
            elif len(coords) == 1:
                geom_dict = {"type": "Point", "coordinates": coords[0]}
            else:
                geom_dict = {"type": "MultiPoint", "coordinates": coords}

            features.append(
                {
                    "type": "Feature",
                    "id": geom.section_guid,
                    "geometry": geom_dict,
                    "properties": {
                        "section_guid": geom.section_guid,
                        "parent_object_guid": geom.parent_object_guid,
                        "parent_object_name": parent.name if parent else "",
                        "parent_object_class": parent.native_class if parent else "",
                        "page_guid": geom.page_guid,
                        "geometry_type": geom.geometry_type,
                        "coordinate_system": geom.coordinate_system,
                        "point_count": geom.point_count,
                        "provenance": geom.provenance.value,
                    },
                }
            )

    return {
        "type": "FeatureCollection",
        "name": project.name,
        "project_guid": project.native_guid,
        "coordinate_system": "planswift_page_digitizer_raw",
        "features": features,
    }


def export_geometry_geojson(project: CanonicalProject, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(project_to_geojson(project), indent=2), encoding="utf-8")
    return output_path
