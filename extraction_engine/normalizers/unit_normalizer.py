"""Canonical unit normalization without altering raw source unit strings."""

from __future__ import annotations

UNIT_ALIASES: dict[str, tuple[str, bool]] = {
    "m": ("m", False),
    "meter": ("m", False),
    "meters": ("m", False),
    "metre": ("m", False),
    "mm": ("mm", False),
    "cm": ("cm", False),
    "ft": ("ft", False),
    "in": ("in", False),
    "ea": ("each", False),
    "each": ("each", False),
    "count": ("each", False),
    "%": ("percent", False),
    "px": ("px", False),
    "m2": ("m^2", False),
    "sq m": ("m^2", False),
    "sqft": ("ft^2", False),
    "[!cu]": ("currency_unresolved", True),
    "[scaleunits]": ("scale_units_dynamic", True),
    "[scale units]": ("scale_units_dynamic", True),
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
