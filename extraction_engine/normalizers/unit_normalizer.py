"""Canonical unit normalization and SI conversion helpers without altering raw source strings."""

from __future__ import annotations

UNIT_ALIASES: dict[str, tuple[str, bool]] = {
    "m": ("m", False),
    "meter": ("m", False),
    "meters": ("m", False),
    "metre": ("m", False),
    "mm": ("mm", False),
    "cm": ("cm", False),
    "ft": ("ft", False),
    "feet": ("ft", False),
    "foot": ("ft", False),
    "in": ("in", False),
    "inch": ("in", False),
    "inches": ("in", False),
    "yd": ("yd", False),
    "yard": ("yd", False),
    "yards": ("yd", False),
    "ea": ("each", False),
    "each": ("each", False),
    "count": ("each", False),
    "%": ("percent", False),
    "px": ("px", False),
    "m2": ("m^2", False),
    "m^2": ("m^2", False),
    "sq m": ("m^2", False),
    "sq ft": ("ft^2", False),
    "sqft": ("ft^2", False),
    "ft^2": ("ft^2", False),
    "sq yd": ("yd^2", False),
    "sqyd": ("yd^2", False),
    "yd^2": ("yd^2", False),
    "[!cu]": ("currency_unresolved", True),
    "[scaleunits]": ("scale_units_dynamic", True),
    "[scale units]": ("scale_units_dynamic", True),
    "[..\\scale units]": ("scale_units_dynamic", True),
    "[..\\..\\scale units]": ("scale_units_dynamic", True),
}

_LENGTH_TO_METERS: dict[str, float] = {
    "m": 1.0,
    "cm": 0.01,
    "mm": 0.001,
    "ft": 0.3048,
    "in": 0.0254,
    "yd": 0.9144,
}


def normalize_unit(raw_unit: str | None, fallback_scale_unit: str | None = None) -> tuple[str | None, bool]:
    """Return (normalized_unit, is_dynamic_unresolved)."""
    if not raw_unit or not raw_unit.strip():
        return None, False
    key = raw_unit.strip().lower()
    if key in UNIT_ALIASES:
        norm, is_dyn = UNIT_ALIASES[key]
        if norm == "scale_units_dynamic" and fallback_scale_unit:
            resolved, _ = normalize_unit(fallback_scale_unit)
            return resolved or fallback_scale_unit.lower(), False
        return norm, is_dyn
    return raw_unit.strip(), False


def scale_area_unit_label(scale_unit: str | None) -> str:
    """Format the squared area unit label corresponding to a linear scale unit (e.g. FT -> SQ FT)."""
    u = (scale_unit or "").strip().upper()
    if not u:
        return ""
    if u in ("FT", "FEET", "FOOT"):
        return "SQ FT"
    if u in ("IN", "INCH", "INCHES"):
        return "SQ IN"
    if u in ("YD", "YARD", "YARDS"):
        return "SQ YD"
    if u in ("M", "METER", "METERS", "METRE"):
        return "SQ M"
    if u in ("CM", "MM"):
        return f"SQ {u}"
    return f"{u}^2"


def convert_length_to_meters(value: float | None, scale_unit: str | None) -> float | None:
    """Convert a calibrated linear measurement to SI meters when the unit is known."""
    if value is None or not scale_unit:
        return None
    norm, _ = normalize_unit(scale_unit)
    factor = _LENGTH_TO_METERS.get(norm or "")
    return round(value * factor, 6) if factor is not None else None


def convert_area_to_sq_meters(value: float | None, scale_unit: str | None) -> float | None:
    """Convert a calibrated area measurement to SI square meters when the base linear unit is known."""
    if value is None or not scale_unit:
        return None
    norm, _ = normalize_unit(scale_unit)
    factor = _LENGTH_TO_METERS.get(norm or "")
    return round(value * (factor * factor), 6) if factor is not None else None
