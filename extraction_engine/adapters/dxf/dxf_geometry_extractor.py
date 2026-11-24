"""Double-precision DXF geometry extractor preserving native coords, OCS/WCS, bulges, and nested INSERT transforms."""

from __future__ import annotations

import math
from typing import Any

import ezdxf.math
from ezdxf.math import BSpline, Matrix44, Vec3, bulge_to_arc

_KNOWN_SUPPORTED_DXF_TYPES = frozenset(
    {
        "POINT",
        "LINE",
        "RAY",
        "XLINE",
        "CIRCLE",
        "ARC",
        "ELLIPSE",
        "SPLINE",
        "LWPOLYLINE",
        "POLYLINE",
        "VERTEX",
        "SEQEND",
        "3DFACE",
        "SOLID",
        "TRACE",
        "HATCH",
        "MESH",
        "INSERT",
        "TEXT",
        "MTEXT",
        "ATTRIB",
        "ATTDEF",
        "DIMENSION",
        "ARC_DIMENSION",
        "LARGE_RADIAL_DIMENSION",
        "LEADER",
        "MLEADER",
        "MULTILEADER",
        "VIEWPORT",
        "IMAGE",
        "WIPEOUT",
        "REGION",
        "3DSOLID",
        "BODY",
    }
)


def _v3_list(v: Any) -> list[float]:
    if v is None:
        return [0.0, 0.0, 0.0]
    if isinstance(v, (int, float)):
        return [float(v), 0.0, 0.0]
    try:
        return [float(v[0]), float(v[1]), float(v[2]) if len(v) > 2 else 0.0]
    except Exception:
        return [float(getattr(v, "x", 0.0)), float(getattr(v, "y", 0.0)), float(getattr(v, "z", 0.0))]


def _polyline_2d_length_and_area(
    pts_with_bulge: list[tuple[float, float, float]],
    closed: bool,
) -> tuple[float, float | None, bool, int]:
    """Compute exact double-precision 2D polyline length and signed Shoelace + circular bulge area."""
    n = len(pts_with_bulge)
    if n < 2:
        return 0.0, None, False, 0

    total_len = 0.0
    area_shoelace = 0.0
    area_bulge = 0.0
    has_bulge = False
    bulge_segs = 0

    seg_count = n if closed else n - 1
    for i in range(seg_count):
        x1, y1, bulge = pts_with_bulge[i]
        x2, y2, _ = pts_with_bulge[(i + 1) % n]
        chord = math.hypot(x2 - x1, y2 - y1)
        if abs(bulge) > 1e-12 and chord > 1e-12:
            has_bulge = True
            bulge_segs += 1
            theta = 4.0 * math.atan(abs(bulge))
            half_theta = theta / 2.0
            sin_half = math.sin(half_theta)
            if abs(sin_half) > 1e-12:
                radius = chord / (2.0 * sin_half)
                total_len += radius * theta
                # Circular segment area added/subtracted according to bulge sign (positive CCW bulge adds to CCW polygon)
                seg_area = 0.5 * (radius * radius) * (theta - math.sin(theta))
                area_bulge += seg_area if bulge > 0.0 else -seg_area
            else:
                total_len += chord
        else:
            total_len += chord

        if closed:
            area_shoelace += x1 * y2 - x2 * y1

    area: float | None = None
    if closed and n >= 2:
        # In 2D polygon signed area: shoelace_signed = 0.5 * sum(x1*y2 - x2*y1); positive for CCW
        signed_shoelace = 0.5 * area_shoelace
        if abs(signed_shoelace) > 1e-12 or abs(area_bulge) > 1e-12:
            # Handle both CCW (signed_shoelace >= 0) and CW (signed_shoelace < 0) consistently
            area = abs(signed_shoelace + area_bulge)
        else:
            area = 0.0

    return total_len, area, has_bulge, bulge_segs


def _ellipse_arc_length(
    center: Vec3,
    major_axis: Vec3,
    ratio: float,
    start_param: float,
    end_param: float,
    steps: int = 256,
) -> float:
    """Compute high-precision ellipse arc length via Composite Simpson quadrature over parameter u."""
    a = major_axis.magnitude
    if a <= 1e-12:
        return 0.0
    b = a * abs(ratio)
    # Normalize parameter span
    span = end_param - start_param
    while span <= 0.0:
        span += 2.0 * math.pi
    if span > 2.0 * math.pi + 1e-9:
        span = span % (2.0 * math.pi)
        if span == 0.0:
            span = 2.0 * math.pi

    n = steps if steps % 2 == 0 else steps + 1
    h = span / n

    def speed(u: float) -> float:
        # |d/du (a cos u * U + b sin u * V)| = sqrt((a sin u)^2 + (b cos u)^2)
        sa = a * math.sin(u)
        cb = b * math.cos(u)
        return math.hypot(sa, cb)

    acc = speed(start_param) + speed(start_param + span)
    for k in range(1, n):
        coeff = 4.0 if (k % 2 == 1) else 2.0
        acc += coeff * speed(start_param + k * h)
    return (h / 3.0) * acc


def _triangle_area_3d(p0: Vec3, p1: Vec3, p2: Vec3) -> float:
    return 0.5 * (p1 - p0).cross(p2 - p0).magnitude


def _polygon_area_3d(pts: list[Vec3]) -> float:
    if len(pts) < 3:
        return 0.0
    origin = pts[0]
    total = 0.0
    for i in range(1, len(pts) - 1):
        total += _triangle_area_3d(origin, pts[i], pts[i + 1])
    return total


def _polyline_length_3d(pts: list[Vec3], closed: bool = False) -> float:
    if len(pts) < 2:
        return 0.0
    total = sum((pts[i + 1] - pts[i]).magnitude for i in range(len(pts) - 1))
    if closed and len(pts) >= 2:
        total += (pts[0] - pts[-1]).magnitude
    return total


def _compute_bbox(pts: list[list[float]]) -> dict[str, list[float]] | None:
    if not pts:
        return None
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    zs = [p[2] if len(p) > 2 else 0.0 for p in pts]
    return {
        "min": [min(xs), min(ys), min(zs)],
        "max": [max(xs), max(ys), max(zs)],
    }


def _ocs_needed(entity: Any) -> bool:
    ext = getattr(entity.dxf, "extrusion", None)
    if ext is None:
        return False
    v = Vec3(ext)
    return not (abs(v.x) < 1e-9 and abs(v.y) < 1e-9 and abs(v.z - 1.0) < 1e-9)


def extract_entity_geometry(
    entity: Any,
    matrix: Matrix44 | None = None,
    unit_factor_m: float | None = None,
) -> dict[str, Any]:
    """Extract native coordinates, WCS-transformed coordinates, and exact double-precision geometric metrics."""
    etype = entity.dxftype()
    dxf = entity.dxf
    warnings: list[str] = []
    native_coords: dict[str, Any] = {}
    world_coords: dict[str, Any] = {}
    metrics: dict[str, Any] = {
        "length": None,
        "area": None,
        "perimeter": None,
        "point_count": 0,
        "is_closed": None,
        "bbox": None,
        "has_bulge": False,
        "bulge_segment_count": 0,
        "normalized_length_m": None,
        "normalized_area_m2": None,
        "geometry_type": etype,
    }
    is_supported = etype in _KNOWN_SUPPORTED_DXF_TYPES
    ocs_applied = False

    def xform(pt: Vec3) -> Vec3:
        return matrix.transform(pt) if matrix is not None else pt

    def xform_dir(vec: Vec3) -> Vec3:
        return matrix.transform_direction(vec) if matrix is not None else vec

    try:
        if etype == "POINT":
            loc = Vec3(dxf.location)
            w_loc = xform(loc)
            native_coords = {"location": _v3_list(loc)}
            world_coords = {"location": _v3_list(w_loc)}
            metrics["point_count"] = 1
            metrics["geometry_type"] = "Point"
            metrics["bbox"] = _compute_bbox([world_coords["location"]])

        elif etype == "LINE":
            s = Vec3(dxf.start)
            e = Vec3(dxf.end)
            ws, we = xform(s), xform(e)
            native_coords = {"start": _v3_list(s), "end": _v3_list(e)}
            world_coords = {"start": _v3_list(ws), "end": _v3_list(we)}
            metrics["length"] = (we - ws).magnitude
            metrics["point_count"] = 2
            metrics["is_closed"] = False
            metrics["geometry_type"] = "Segment"
            metrics["bbox"] = _compute_bbox([world_coords["start"], world_coords["end"]])

        elif etype in ("RAY", "XLINE"):
            s = Vec3(dxf.start)
            u = Vec3(dxf.unit_vector)
            ws = xform(s)
            wu = xform_dir(u)
            if wu.magnitude > 0:
                wu = wu.normalize()
            native_coords = {"start": _v3_list(s), "unit_vector": _v3_list(u)}
            world_coords = {"start": _v3_list(ws), "unit_vector": _v3_list(wu)}
            metrics["point_count"] = 1
            metrics["length"] = None  # Infinite geometry; never fabricate length
            metrics["geometry_type"] = etype

        elif etype == "CIRCLE":
            c_ocs = Vec3(dxf.center)
            r = float(dxf.radius)
            ocs = entity.ocs()
            ocs_applied = _ocs_needed(entity)
            c_wcs = xform(ocs.to_wcs(c_ocs))
            # Handle possible uniform/non-uniform scaling when transformed through INSERT
            if matrix is not None:
                ux = xform_dir(ocs.to_wcs(Vec3(r, 0.0, 0.0)))
                uy = xform_dir(ocs.to_wcs(Vec3(0.0, r, 0.0)))
                rx = ux.magnitude
                ry = uy.magnitude
                circ = _ellipse_arc_length(c_wcs, ux, (ry / rx) if rx > 1e-12 else 1.0, 0.0, 2.0 * math.pi)
                area = math.pi * rx * ry
            else:
                rx = ry = r
                circ = 2.0 * math.pi * r
                area = math.pi * r * r
            native_coords = {"center": _v3_list(c_ocs), "radius": r}
            world_coords = {"center": _v3_list(c_wcs), "radius_x": rx, "radius_y": ry}
            metrics["length"] = circ
            metrics["perimeter"] = circ
            metrics["area"] = area
            metrics["is_closed"] = True
            metrics["geometry_type"] = "Circle"
            metrics["bbox"] = {
                "min": [c_wcs.x - rx, c_wcs.y - ry, c_wcs.z],
                "max": [c_wcs.x + rx, c_wcs.y + ry, c_wcs.z],
            }

        elif etype == "ARC":
            c_ocs = Vec3(dxf.center)
            r = float(dxf.radius)
            sa_deg = float(dxf.start_angle)
            ea_deg = float(dxf.end_angle)
            ocs = entity.ocs()
            ocs_applied = _ocs_needed(entity)
            c_wcs = xform(ocs.to_wcs(c_ocs))
            sp_ocs = Vec3(c_ocs.x + r * math.cos(math.radians(sa_deg)), c_ocs.y + r * math.sin(math.radians(sa_deg)), c_ocs.z)
            ep_ocs = Vec3(c_ocs.x + r * math.cos(math.radians(ea_deg)), c_ocs.y + r * math.sin(math.radians(ea_deg)), c_ocs.z)
            sp_wcs = xform(ocs.to_wcs(sp_ocs))
            ep_wcs = xform(ocs.to_wcs(ep_ocs))

            sa_rad = math.radians(sa_deg)
            ea_rad = math.radians(ea_deg)
            delta = (ea_rad - sa_rad) % (2.0 * math.pi)
            if delta == 0.0 and abs(ea_deg - sa_deg) > 1e-9:
                delta = 2.0 * math.pi

            if matrix is not None:
                ux = xform_dir(ocs.to_wcs(Vec3(r, 0.0, 0.0)))
                uy = xform_dir(ocs.to_wcs(Vec3(0.0, r, 0.0)))
                rx = ux.magnitude
                ry = uy.magnitude
                arc_len = _ellipse_arc_length(c_wcs, ux, (ry / rx) if rx > 1e-12 else 1.0, sa_rad, sa_rad + delta)
            else:
                arc_len = r * delta

            native_coords = {
                "center": _v3_list(c_ocs),
                "radius": r,
                "start_angle_deg": sa_deg,
                "end_angle_deg": ea_deg,
            }
            world_coords = {
                "center": _v3_list(c_wcs),
                "start_point": _v3_list(sp_wcs),
                "end_point": _v3_list(ep_wcs),
                "sweep_deg": math.degrees(delta),
            }
            metrics["length"] = arc_len
            metrics["chord_length"] = (ep_wcs - sp_wcs).magnitude
            metrics["is_closed"] = False
            metrics["point_count"] = 2
            metrics["geometry_type"] = "Arc"

        elif etype == "ELLIPSE":
            c = Vec3(dxf.center)
            maj = Vec3(dxf.major_axis)
            ratio = float(dxf.ratio)
            sp = float(dxf.start_param)
            ep = float(dxf.end_param)
            wc = xform(c)
            wmaj = xform_dir(maj)
            length = _ellipse_arc_length(wc, wmaj, ratio, sp, ep)
            span = (ep - sp) % (2.0 * math.pi)
            is_closed = abs(ep - sp - 2.0 * math.pi) < 1e-6 or abs(span) < 1e-6
            a = wmaj.magnitude
            b = a * abs(ratio)
            native_coords = {
                "center": _v3_list(c),
                "major_axis": _v3_list(maj),
                "ratio": ratio,
                "start_param": sp,
                "end_param": ep,
            }
            world_coords = {
                "center": _v3_list(wc),
                "major_axis": _v3_list(wmaj),
                "semi_major": a,
                "semi_minor": b,
            }
            metrics["length"] = length
            metrics["perimeter"] = length if is_closed else None
            metrics["area"] = (math.pi * a * b) if is_closed else None
            metrics["is_closed"] = is_closed
            metrics["geometry_type"] = "Ellipse"

        elif etype == "SPLINE":
            ctrl_pts = [Vec3(p) for p in entity.control_points]
            fit_pts = [Vec3(p) for p in entity.fit_points]
            knots = [float(k) for k in entity.knots]
            weights = [float(w) for w in entity.weights] if entity.has_weights else []
            degree = int(dxf.degree)
            is_closed = bool(entity.closed)
            w_ctrl = [xform(p) for p in ctrl_pts]
            w_fit = [xform(p) for p in fit_pts]
            native_coords = {
                "degree": degree,
                "control_points": [_v3_list(p) for p in ctrl_pts],
                "fit_points": [_v3_list(p) for p in fit_pts],
                "knots": knots,
                "weights": weights,
            }
            world_coords = {
                "control_points": [_v3_list(p) for p in w_ctrl],
                "fit_points": [_v3_list(p) for p in w_fit],
            }
            # Flatten spline using ezdxf BSpline for accurate curve length (marked calculated)
            spline_len: float | None = None
            all_w_pts = w_ctrl or w_fit
            if len(w_ctrl) >= 2:
                try:
                    bs = BSpline(w_ctrl, order=degree + 1, knots=knots or None, weights=weights or None)
                    flat = list(bs.flattening(1e-4))
                    spline_len = _polyline_length_3d(flat, closed=False)
                except Exception as exc:
                    warnings.append(f"Spline flattening fallback ({exc}); length left None.")
            metrics["length"] = spline_len
            metrics["point_count"] = len(all_w_pts)
            metrics["is_closed"] = is_closed
            metrics["geometry_type"] = "Spline"
            metrics["bbox"] = _compute_bbox([_v3_list(p) for p in all_w_pts])

        elif etype == "LWPOLYLINE":
            ocs = entity.ocs()
            ocs_applied = _ocs_needed(entity)
            elev = float(getattr(dxf, "elevation", 0.0) or 0.0)
            is_closed = bool(entity.closed)
            pts_raw = list(entity.get_points("xyb"))
            pts_2d = [(float(x), float(y), float(b)) for x, y, b in pts_raw]
            ocs_pts = [Vec3(x, y, elev) for x, y, _ in pts_2d]
            wcs_pts = [xform(ocs.to_wcs(p)) for p in ocs_pts]

            if matrix is not None or ocs_applied:
                # Project WCS points onto local plane for planar length/area or compute 3D with bulge flattening
                if any(abs(b) > 1e-12 for _, _, b in pts_2d):
                    length, area, has_b, b_cnt = _lwpoly_transformed_with_bulge(pts_2d, elev, ocs, xform, is_closed)
                else:
                    length = _polyline_length_3d(wcs_pts, closed=is_closed)
                    area = _polygon_area_3d(wcs_pts) if is_closed and len(wcs_pts) >= 3 else None
                    has_b, b_cnt = False, 0
            else:
                length, area, has_b, b_cnt = _polyline_2d_length_and_area(pts_2d, closed=is_closed)

            native_coords = {
                "points_xyb": [[x, y, b] for x, y, b in pts_2d],
                "elevation": elev,
                "closed": is_closed,
            }
            w_list = [_v3_list(p) for p in wcs_pts]
            world_coords = {"points": w_list}
            metrics["length"] = length
            metrics["perimeter"] = length if is_closed else None
            metrics["area"] = area
            metrics["point_count"] = len(pts_2d)
            metrics["is_closed"] = is_closed
            metrics["has_bulge"] = has_b
            metrics["bulge_segment_count"] = b_cnt
            metrics["geometry_type"] = "Polygon" if is_closed else "Polyline"
            metrics["bbox"] = _compute_bbox(w_list)

        elif etype == "POLYLINE":
            is_closed = bool(entity.is_closed)
            is_3d = bool(entity.is_3d_polyline)
            is_mesh = bool(entity.is_polygon_mesh or entity.is_poly_face_mesh)
            ocs = entity.ocs()
            ocs_applied = (not is_3d and not is_mesh) and _ocs_needed(entity)
            vertices = list(entity.vertices)

            if is_mesh:
                mesh_pts = [xform(Vec3(v.dxf.location)) for v in vertices if not v.is_face_record]
                face_area = 0.0
                if entity.is_poly_face_mesh:
                    try:
                        _, faces = entity.indexed_faces()
                        # Calculate total mesh area from faces
                        for face in entity.virtual_entities():
                            if face.dxftype() == "3DFACE":
                                fpts = [xform(Vec3(p)) for p in face.wcs_vertices(close=False)]
                                face_area += _polygon_area_3d(fpts)
                    except Exception:
                        pass
                w_list = [_v3_list(p) for p in mesh_pts]
                native_coords = {"vertices": [_v3_list(v.dxf.location) for v in vertices]}
                world_coords = {"vertices": w_list}
                metrics["point_count"] = len(mesh_pts)
                metrics["area"] = face_area if face_area > 0 else None
                metrics["geometry_type"] = "PolyMesh"
                metrics["bbox"] = _compute_bbox(w_list)
            elif is_3d:
                pts_3d = [Vec3(v.dxf.location) for v in vertices]
                wcs_pts = [xform(p) for p in pts_3d]
                w_list = [_v3_list(p) for p in wcs_pts]
                native_coords = {"points": [_v3_list(p) for p in pts_3d], "closed": is_closed}
                world_coords = {"points": w_list}
                metrics["length"] = _polyline_length_3d(wcs_pts, closed=is_closed)
                metrics["perimeter"] = metrics["length"] if is_closed else None
                metrics["point_count"] = len(wcs_pts)
                metrics["is_closed"] = is_closed
                metrics["geometry_type"] = "Polyline3D"
                metrics["bbox"] = _compute_bbox(w_list)
            else:
                pts_2d = [
                    (float(v.dxf.location.x), float(v.dxf.location.y), float(getattr(v.dxf, "bulge", 0.0) or 0.0))
                    for v in vertices
                ]
                elev = float(vertices[0].dxf.location.z) if vertices else 0.0
                wcs_pts = [xform(ocs.to_wcs(Vec3(x, y, elev))) for x, y, _ in pts_2d]
                if matrix is not None or ocs_applied:
                    length, area, has_b, b_cnt = _lwpoly_transformed_with_bulge(pts_2d, elev, ocs, xform, is_closed)
                else:
                    length, area, has_b, b_cnt = _polyline_2d_length_and_area(pts_2d, closed=is_closed)
                w_list = [_v3_list(p) for p in wcs_pts]
                native_coords = {"points_xyb": [[x, y, b] for x, y, b in pts_2d], "elevation": elev, "closed": is_closed}
                world_coords = {"points": w_list}
                metrics["length"] = length
                metrics["perimeter"] = length if is_closed else None
                metrics["area"] = area
                metrics["point_count"] = len(pts_2d)
                metrics["is_closed"] = is_closed
                metrics["has_bulge"] = has_b
                metrics["bulge_segment_count"] = b_cnt
                metrics["geometry_type"] = "Polygon" if is_closed else "Polyline2D"
                metrics["bbox"] = _compute_bbox(w_list)

        elif etype in ("3DFACE", "SOLID", "TRACE"):
            if etype == "3DFACE":
                pts = [Vec3(p) for p in entity.wcs_vertices(close=False)]
            else:
                ocs = entity.ocs()
                ocs_applied = _ocs_needed(entity)
                pts = [ocs.to_wcs(Vec3(p)) for p in entity.vertices()]
            # AutoCAD SOLID/TRACE swaps vertices 2 and 3 in bowtie order (v0, v1, v2, v3 -> v0, v1, v3, v2)
            if etype in ("SOLID", "TRACE") and len(pts) == 4:
                ordered = [pts[0], pts[1], pts[3], pts[2]]
            else:
                ordered = pts
            wcs_pts = [xform(p) for p in ordered]
            # Deduplicate repeated 4th vertex common in DXF 3DFACE/SOLID triangles
            unique_pts = wcs_pts[:-1] if len(wcs_pts) == 4 and (wcs_pts[3] - wcs_pts[2]).magnitude < 1e-12 else wcs_pts
            w_list = [_v3_list(p) for p in unique_pts]
            native_coords = {"vertices": [_v3_list(p) for p in pts]}
            world_coords = {"vertices": w_list}
            metrics["area"] = _polygon_area_3d(unique_pts)
            metrics["perimeter"] = _polyline_length_3d(unique_pts, closed=True)
            metrics["point_count"] = len(unique_pts)
            metrics["is_closed"] = True
            metrics["geometry_type"] = etype
            metrics["bbox"] = _compute_bbox(w_list)

        elif etype == "HATCH":
            ocs = entity.ocs()
            ocs_applied = _ocs_needed(entity)
            elev = float(getattr(dxf, "elevation", (0.0, 0.0, 0.0))[2] if hasattr(getattr(dxf, "elevation", None), "__len__") else 0.0)
            total_area = 0.0
            total_perim = 0.0
            path_summaries: list[dict[str, Any]] = []
            for p_idx, path in enumerate(entity.paths):
                # Convert Hatch paths into uniform polyline/edge calculation via ezdxf Path API when available
                path_type = type(path).__name__
                if hasattr(path, "vertices"):  # PolylinePath
                    pts_2d = [(float(v[0]), float(v[1]), float(v[2])) for v in path.vertices]
                    plen, parea, has_b, b_cnt = _lwpoly_transformed_with_bulge(
                        pts_2d, elev, ocs, xform, bool(getattr(path, "is_closed", True))
                    )
                    total_perim += plen
                    if parea is not None:
                        total_area += parea
                    path_summaries.append({"index": p_idx, "kind": "PolylinePath", "vertices": len(pts_2d), "has_bulge": has_b, "area": parea, "perimeter": plen})
                else:  # EdgePath
                    try:
                        ez_path = ezdxf.path.from_hatch_edge_path(path, ocs=ocs, elevation=elev)
                        flat_pts = [xform(Vec3(p)) for p in ez_path.flattening(1e-3)]
                        plen = _polyline_length_3d(flat_pts, closed=True)
                        parea = _polygon_area_3d(flat_pts)
                        total_perim += plen
                        total_area += parea
                        path_summaries.append({"index": p_idx, "kind": "EdgePath", "edges": len(getattr(path, "edges", [])), "area": parea, "perimeter": plen})
                    except Exception as exc:
                        warnings.append(f"Hatch EdgePath {p_idx} geometry warning: {exc}")
                        path_summaries.append({"index": p_idx, "kind": path_type, "error": str(exc)})

            native_coords = {
                "pattern_name": getattr(dxf, "pattern_name", ""),
                "solid_fill": bool(getattr(dxf, "solid_fill", 0)),
                "associative": bool(getattr(dxf, "associative", 0)),
                "path_count": len(entity.paths),
            }
            world_coords = {"paths": path_summaries}
            metrics["area"] = total_area if path_summaries else None
            metrics["perimeter"] = total_perim if path_summaries else None
            metrics["length"] = total_perim if path_summaries else None
            metrics["is_closed"] = True
            metrics["geometry_type"] = "Hatch"

        elif etype == "MESH":
            verts = [xform(Vec3(v)) for v in entity.vertices]
            faces = [list(f) for f in entity.faces]
            area = 0.0
            for f in faces:
                if len(f) >= 3:
                    fpts = [verts[i] for i in f if 0 <= i < len(verts)]
                    area += _polygon_area_3d(fpts)
            w_list = [_v3_list(v) for v in verts]
            native_coords = {"vertex_count": len(verts), "face_count": len(faces)}
            world_coords = {"bbox": _compute_bbox(w_list)}
            metrics["area"] = area
            metrics["point_count"] = len(verts)
            metrics["geometry_type"] = "Mesh"
            metrics["bbox"] = world_coords["bbox"]

        elif etype == "INSERT":
            ins = Vec3(dxf.insert)
            ocs = entity.ocs()
            ocs_applied = _ocs_needed(entity)
            wins = xform(ocs.to_wcs(ins))
            native_coords = {
                "insert": _v3_list(ins),
                "xscale": float(getattr(dxf, "xscale", 1.0)),
                "yscale": float(getattr(dxf, "yscale", 1.0)),
                "zscale": float(getattr(dxf, "zscale", 1.0)),
                "rotation_deg": float(getattr(dxf, "rotation", 0.0)),
            }
            world_coords = {"insert": _v3_list(wins)}
            metrics["point_count"] = 1
            metrics["geometry_type"] = "Insert"
            metrics["bbox"] = _compute_bbox([world_coords["insert"]])

        elif etype in ("TEXT", "ATTRIB", "ATTDEF"):
            ins = Vec3(dxf.insert)
            ocs = entity.ocs()
            ocs_applied = _ocs_needed(entity)
            wins = xform(ocs.to_wcs(ins))
            native_coords = {"insert": _v3_list(ins), "height": float(getattr(dxf, "height", 0.0)), "rotation": float(getattr(dxf, "rotation", 0.0))}
            world_coords = {"insert": _v3_list(wins)}
            metrics["point_count"] = 1
            metrics["geometry_type"] = "AnnotationText"

        elif etype == "MTEXT":
            ins = Vec3(dxf.insert)
            wins = xform(ins)
            native_coords = {"insert": _v3_list(ins), "char_height": float(getattr(dxf, "char_height", 0.0)), "width": float(getattr(dxf, "width", 0.0))}
            world_coords = {"insert": _v3_list(wins)}
            metrics["point_count"] = 1
            metrics["geometry_type"] = "AnnotationMText"

        elif etype == "LEADER":
            verts = [Vec3(v) for v in entity.vertices]
            wverts = [xform(v) for v in verts]
            w_list = [_v3_list(v) for v in wverts]
            native_coords = {"vertices": [_v3_list(v) for v in verts]}
            world_coords = {"vertices": w_list}
            metrics["length"] = _polyline_length_3d(wverts, closed=False)
            metrics["point_count"] = len(wverts)
            metrics["geometry_type"] = "Leader"
            metrics["bbox"] = _compute_bbox(w_list)

        elif etype in ("MLEADER", "MULTILEADER"):
            ctx = getattr(entity, "context", None)
            base_pt = getattr(ctx, "base_point", None) if ctx else None
            native_coords = {"has_context": ctx is not None, "base_point": _v3_list(base_pt) if base_pt else None}
            if base_pt is not None:
                wb = xform(Vec3(base_pt))
                world_coords = {"base_point": _v3_list(wb)}
                metrics["point_count"] = 1
            metrics["geometry_type"] = "MLeader"

        elif etype == "VIEWPORT":
            c = Vec3(getattr(dxf, "center", (0.0, 0.0, 0.0)))
            w = float(getattr(dxf, "width", 0.0) or 0.0)
            h = float(getattr(dxf, "height", 0.0) or 0.0)
            native_coords = {"center": _v3_list(c), "width": w, "height": h, "view_height": float(getattr(dxf, "view_height", 0.0) or 0.0)}
            world_coords = {"center": _v3_list(c)}
            metrics["area"] = w * h
            metrics["geometry_type"] = "Viewport"

        elif etype == "IMAGE":
            ins = Vec3(getattr(dxf, "insert", (0.0, 0.0, 0.0)))
            native_coords = {"insert": _v3_list(ins), "image_size": _v3_list(getattr(dxf, "image_size", (0.0, 0.0)))}
            world_coords = {"insert": _v3_list(xform(ins))}
            metrics["geometry_type"] = "ImageReferenceMetadata"

        elif etype in ("REGION", "3DSOLID", "BODY"):
            metrics["geometry_type"] = etype
            warnings.append(f"ACIS entity '{etype}' metadata preserved; proprietary ACIS BREP geometry not tessellated.")

        else:
            is_supported = False
            metrics["geometry_type"] = etype
            warnings.append(f"Unsupported DXF entity type '{etype}' preserved verbatim without geometric computation.")

    except Exception as exc:
        warnings.append(f"Geometry extraction error on {etype} handle={getattr(dxf, 'handle', '')}: {exc}")

    # Convert length and area to SI meters / m^2 ONLY if $INSUNITS defines a valid scale factor
    if unit_factor_m is not None:
        if metrics["length"] is not None:
            metrics["normalized_length_m"] = metrics["length"] * unit_factor_m
        if metrics["area"] is not None:
            metrics["normalized_area_m2"] = metrics["area"] * (unit_factor_m * unit_factor_m)

    return {
        "native_coordinates": native_coords,
        "world_coordinates": world_coords,
        "geometry_metrics": metrics,
        "ocs_applied": ocs_applied,
        "is_supported": is_supported,
        "warnings": warnings,
    }


def _lwpoly_transformed_with_bulge(
    pts_2d: list[tuple[float, float, float]],
    elev: float,
    ocs: Any,
    xform: Any,
    closed: bool,
) -> tuple[float, float | None, bool, int]:
    """Flatten bulges accurately in WCS/transformed space so non-uniform INSERT scales preserve exact geometry."""
    n = len(pts_2d)
    if n < 2:
        return 0.0, None, False, 0

    sampled_wcs: list[Vec3] = []
    has_bulge = False
    bulge_cnt = 0
    seg_count = n if closed else n - 1
    for i in range(seg_count):
        x1, y1, bulge = pts_2d[i]
        x2, y2, _ = pts_2d[(i + 1) % n]
        p1_wcs = xform(ocs.to_wcs(Vec3(x1, y1, elev)))
        sampled_wcs.append(p1_wcs)
        if abs(bulge) > 1e-12 and math.hypot(x2 - x1, y2 - y1) > 1e-12:
            has_bulge = True
            bulge_cnt += 1
            center_2d, start_a, end_a, radius = bulge_to_arc((x1, y1), (x2, y2), bulge)
            sweep = end_a - start_a
            # Choose shortest directed angle matching bulge sign
            if bulge > 0 and sweep < 0:
                sweep += 2.0 * math.pi
            elif bulge < 0 and sweep > 0:
                sweep -= 2.0 * math.pi
            steps = max(16, min(128, int(abs(sweep) / (math.pi / 32)) + 1))
            for k in range(1, steps):
                ang = start_a + sweep * (k / steps)
                px = center_2d[0] + radius * math.cos(ang)
                py = center_2d[1] + radius * math.sin(ang)
                sampled_wcs.append(xform(ocs.to_wcs(Vec3(px, py, elev))))
    if not closed:
        xn, yn, _ = pts_2d[-1]
        sampled_wcs.append(xform(ocs.to_wcs(Vec3(xn, yn, elev))))

    length = _polyline_length_3d(sampled_wcs, closed=closed)
    area = _polygon_area_3d(sampled_wcs) if closed and len(sampled_wcs) >= 3 else None
    return length, area, has_bulge, bulge_cnt
