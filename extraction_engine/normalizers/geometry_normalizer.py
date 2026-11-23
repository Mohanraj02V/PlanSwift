"""Geometry coordinate normalizer: preserves raw page coordinates; only normalizes when scale factor exists."""

from __future__ import annotations

from extraction_engine.core.extraction_result import CanonicalProject


def normalize_project_geometry(project: CanonicalProject) -> None:
    """Apply coordinate normalization ONLY if a page exposes an explicit numeric scale factor."""
    page_scale: dict[str, float | None] = {
        p.native_guid.upper(): p.numeric_scale_factor for p in project.pages
    }
    for obj in project.objects:
        for geom in obj.geometries:
            factor = page_scale.get(geom.page_guid.upper()) if geom.page_guid else None
            if factor is not None and factor > 0:
                for pt in geom.points:
                    pt.normalized_x = round(pt.x / factor, 6)
                    pt.normalized_y = round(pt.y / factor, 6)
            else:
                # Never guess pixel-to-real-world scale from drawing pixels
                for pt in geom.points:
                    pt.normalized_x = None
                    pt.normalized_y = None
