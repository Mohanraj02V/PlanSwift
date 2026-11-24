"""DXF DIMENSION extractor keeping actual_measurement, text overrides, and calculated geometry separate."""

from __future__ import annotations

import math
from typing import Any


def _pt_list(pt: Any) -> list[float] | None:
    if pt is None:
        return None
    try:
        return [float(pt[0]), float(pt[1]), float(pt[2]) if len(pt) > 2 else 0.0]
    except Exception:
        return None


def extract_dimension_data(entity: Any) -> dict[str, Any]:
    """Extract DIMENSION fields strictly separating native actual_measurement, text override, and geometry."""
    dxf = entity.dxf
    raw_text = getattr(dxf, "text", "") or ""
    # In DXF, "" or "<>" means dynamic default measurement text; any other value is an explicit override
    has_override = bool(raw_text.strip() and "<>" not in raw_text)

    actual_measurement: float | None = None
    if hasattr(entity, "get_measurement"):
        try:
            m = entity.get_measurement()
            if m is not None and math.isfinite(float(m)):
                actual_measurement = float(m)
        except Exception:
            actual_measurement = None
    if actual_measurement is None:
        raw_act = getattr(dxf, "actual_measurement", None)
        if raw_act is not None:
            try:
                f = float(raw_act)
                if math.isfinite(f):
                    actual_measurement = f
            except (TypeError, ValueError):
                pass

    defpoint = _pt_list(getattr(dxf, "defpoint", None))
    defpoint2 = _pt_list(getattr(dxf, "defpoint2", None))
    defpoint3 = _pt_list(getattr(dxf, "defpoint3", None))
    defpoint4 = _pt_list(getattr(dxf, "defpoint4", None))
    defpoint5 = _pt_list(getattr(dxf, "defpoint5", None))
    text_midpoint = _pt_list(getattr(dxf, "text_midpoint", None))

    dimtype_code = int(getattr(dxf, "dimtype", 0))
    base_type = dimtype_code & 0x0F
    dimtype_names = {
        0: "rotated_linear",
        1: "aligned",
        2: "angular_2line",
        3: "diameter",
        4: "radius",
        5: "angular_3point",
        6: "ordinate",
    }

    # Compute independent geometric distance between defpoint2 and defpoint3 for linear/aligned dimensions
    geom_measured: float | None = None
    if base_type in (0, 1) and defpoint2 is not None and defpoint3 is not None:
        if base_type == 1:
            geom_measured = math.dist(defpoint2, defpoint3)
        else:
            angle_deg = float(getattr(dxf, "angle", 0.0) or 0.0)
            rad = math.radians(angle_deg)
            dx = defpoint3[0] - defpoint2[0]
            dy = defpoint3[1] - defpoint2[1]
            geom_measured = abs(dx * math.cos(rad) + dy * math.sin(rad))

    discrepancy: float | None = None
    if actual_measurement is not None and geom_measured is not None:
        discrepancy = abs(actual_measurement - geom_measured)

    return {
        "dimtype_raw": dimtype_code,
        "dimension_kind": dimtype_names.get(base_type, f"unknown_{base_type}"),
        "dimstyle": getattr(dxf, "dimstyle", "") or "",
        "actual_measurement": actual_measurement,
        "geometry_measured": geom_measured,
        "discrepancy": discrepancy,
        "raw_text_field": raw_text,
        "has_text_override": has_override,
        "text_override": raw_text if has_override else "",
        "defpoint": defpoint,
        "defpoint2": defpoint2,
        "defpoint3": defpoint3,
        "defpoint4": defpoint4,
        "defpoint5": defpoint5,
        "text_midpoint": text_midpoint,
        "rotation_deg": float(getattr(dxf, "angle", 0.0) or 0.0),
    }
