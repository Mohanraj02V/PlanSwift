"""Optimized, bounded multicore IfcOpenShell geometry extractor (runs ONLY when enabled)."""

from __future__ import annotations

import logging
import math
import time
from typing import Any

import ifcopenshell
import ifcopenshell.geom

from extraction_engine.core.cad_models import CanonicalIFCGeometrySummary
from extraction_engine.core.extraction_context import ExtractionConfig
from extraction_engine.core.extraction_result import ProvenanceStatus

logger = logging.getLogger(__name__)


def _compute_mesh_metrics(verts_flat: Any, faces_flat: Any) -> dict[str, Any]:
    """Compute exact double-precision BBox, surface area, watertight check, and signed volume."""
    n_verts = len(verts_flat) // 3
    n_faces = len(faces_flat) // 3
    if n_verts == 0 or n_faces == 0:
        return {
            "bbox_min": None,
            "bbox_max": None,
            "dimensions_xyz": None,
            "surface_area": None,
            "volume": None,
            "is_watertight": False,
            "vertex_count": n_verts,
            "face_count": n_faces,
        }

    # Build vertex triples cleanly
    verts = [(float(verts_flat[3 * i]), float(verts_flat[3 * i + 1]), float(verts_flat[3 * i + 2])) for i in range(n_verts)]
    xs = [v[0] for v in verts]
    ys = [v[1] for v in verts]
    zs = [v[2] for v in verts]
    bmin = [min(xs), min(ys), min(zs)]
    bmax = [max(xs), max(ys), max(zs)]
    dims = [bmax[0] - bmin[0], bmax[1] - bmin[1], bmax[2] - bmin[2]]

    surface_area = 0.0
    signed_vol_6 = 0.0
    directed_edges: dict[tuple[int, int], int] = {}

    for f in range(n_faces):
        i0 = int(faces_flat[3 * f])
        i1 = int(faces_flat[3 * f + 1])
        i2 = int(faces_flat[3 * f + 2])
        if i0 >= n_verts or i1 >= n_verts or i2 >= n_verts:
            continue
        x0, y0, z0 = verts[i0]
        x1, y1, z1 = verts[i1]
        x2, y2, z2 = verts[i2]

        # Cross product (v1 - v0) x (v2 - v0)
        ux, uy, uz = x1 - x0, y1 - y0, z1 - z0
        vx, vy, vz = x2 - x0, y2 - y0, z2 - z0
        cx = uy * vz - uz * vy
        cy = uz * vx - ux * vz
        cz = ux * vy - uy * vx
        surface_area += 0.5 * math.sqrt(cx * cx + cy * cy + cz * cz)

        # Signed tetrahedron volume * 6 = v0 . (v1 x v2)
        c12x = y1 * z2 - z1 * y2
        c12y = z1 * x2 - x1 * z2
        c12z = x1 * y2 - y1 * x2
        signed_vol_6 += x0 * c12x + y0 * c12y + z0 * c12z

        for a, b in ((i0, i1), (i1, i2), (i2, i0)):
            directed_edges[(a, b)] = directed_edges.get((a, b), 0) + 1

    # Watertightness check: every directed half-edge (a, b) has matching reverse half-edge (b, a)
    is_watertight = n_faces >= 4 and len(directed_edges) > 0
    if is_watertight:
        for (a, b), cnt in directed_edges.items():
            if directed_edges.get((b, a), 0) != cnt:
                is_watertight = False
                break

    volume = abs(signed_vol_6) / 6.0 if is_watertight else None
    return {
        "bbox_min": bmin,
        "bbox_max": bmax,
        "dimensions_xyz": dims,
        "surface_area": surface_area,
        "volume": volume,
        "is_watertight": is_watertight,
        "vertex_count": n_verts,
        "face_count": n_faces,
    }


def extract_ifc_geometries_bulk(
    model: ifcopenshell.file,
    elements: list[Any],
    config: ExtractionConfig,
    unit_meta: dict[str, Any],
) -> tuple[dict[int, CanonicalIFCGeometrySummary], list[str]]:
    """Run bounded multicore ifcopenshell.geom.iterator ONLY across elements with Representation."""
    summaries: dict[int, CanonicalIFCGeometrySummary] = {}
    warnings: list[str] = []

    if not config.ifc_extract_geometry:
        for ent in elements:
            summaries[int(ent.id())] = CanonicalIFCGeometrySummary(
                status="skipped_property_only",
                provenance=ProvenanceStatus.CALCULATED,
            )
        return summaries, warnings

    # Separate elements with representations vs spatial/logical nodes without representations
    geo_entities: list[Any] = []
    for ent in elements:
        rep = getattr(ent, "Representation", None)
        if rep is None or ent.is_a("IfcOpeningElement") and not getattr(rep, "Representations", None):
            summaries[int(ent.id())] = CanonicalIFCGeometrySummary(
                status="no_representation",
                provenance=ProvenanceStatus.NATIVE,
            )
        else:
            geo_entities.append(ent)

    if not geo_entities:
        return summaries, warnings

    # Bounded threads (1..4) so concurrent Celery workers never oversubscribe CPU
    num_threads = max(1, min(int(config.ifc_geometry_threads or 1), 4))
    settings = ifcopenshell.geom.settings()
    settings.set(settings.USE_WORLD_COORDS, True)

    t0 = time.perf_counter()
    # Note: IfcOpenShell geometry coordinates are ALREADY in SI meters by default in C++ iterator
    # (convert_back_units=False) -> surface_area is in m^2, volume is in m^3!
    len_fac = unit_meta.get("unit_to_meter_factor")
    display_unit = "m"

    iterator = ifcopenshell.geom.iterator(
        settings,
        model,
        num_threads=num_threads,
        include=geo_entities,
    )

    processed_ids: set[int] = set()
    try:
        if iterator.initialize():
            while True:
                if (time.perf_counter() - t0) > config.ifc_geometry_timeout_seconds:
                    warnings.append(
                        f"IFC geometry iterator exceeded timeout ({config.ifc_geometry_timeout_seconds}s); remaining shapes skipped safely."
                    )
                    break
                try:
                    shape = iterator.get()
                    sid = int(shape.id)
                    processed_ids.add(sid)
                    geom = shape.geometry
                    metrics = _compute_mesh_metrics(geom.verts, geom.faces)
                    sa_m2 = metrics["surface_area"]
                    vol_m3 = metrics["volume"]
                    summaries[sid] = CanonicalIFCGeometrySummary(
                        status="calculated",
                        bbox_min=metrics["bbox_min"],
                        bbox_max=metrics["bbox_max"],
                        dimensions_xyz=metrics["dimensions_xyz"],
                        surface_area=sa_m2,
                        volume=vol_m3,
                        is_watertight=metrics["is_watertight"],
                        vertex_count=metrics["vertex_count"],
                        face_count=metrics["face_count"],
                        unit=display_unit if len_fac else "si_m",
                        normalized_surface_area_m2=sa_m2,
                        normalized_volume_m3=vol_m3,
                        provenance=ProvenanceStatus.CALCULATED,
                    )
                except Exception as exc:
                    warnings.append(f"Geometry iterator item error: {exc}")
                if not iterator.next():
                    break
    except Exception as exc:
        warnings.append(f"IfcOpenShell iterator halted cleanly: {exc}")

    # Mark any entity with a representation that failed/timed out individually rather than omitting it
    for ent in geo_entities:
        sid = int(ent.id())
        if sid not in summaries:
            # Try single-element check if it had representation but produced empty/unsupported geometry
            summaries[sid] = CanonicalIFCGeometrySummary(
                status="unsupported",
                error="No triangulated solid produced by IfcOpenShell geometry kernel or iterator timed out.",
                provenance=ProvenanceStatus.UNSUPPORTED,
            )

    return summaries, warnings
