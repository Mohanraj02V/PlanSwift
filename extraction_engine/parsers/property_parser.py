"""Lossless property parser for all 9 PlanSwift <Property> classes and 34+ XML attributes."""

from __future__ import annotations

import hashlib
import re
from typing import Any

from extraction_engine.core.extraction_result import CanonicalProperty, ProvenanceStatus

_ORDER_INDEX_PAGE_RE = re.compile(r"^OrderIndex_(\{[0-9A-Fa-f-]{36}\})$")
_FORMULA_BRACKET_RE = re.compile(r"\[[^\]]+\]")
_NUMERIC_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")


def parse_property_element(
    attrs: dict[str, str],
    raw_value: str,
    source_location: str,
) -> CanonicalProperty:
    """Parse a <Property> element preserving raw_value, empty names, ImageData hashes, and all XML attrs."""
    prop_guid = (attrs.get("GUID") or "").strip()
    name = attrs.get("Name", "")
    prop_class = attrs.get("Class", "Text")
    group = attrs.get("group")
    units = attrs.get("units")
    input_units = attrs.get("inputunits")
    decimal_places = attrs.get("DecimalPlaces")
    parse_formula = attrs.get("ParseFormula")
    expression_flag = attrs.get("Expression")

    order_idx: int | None = None
    raw_order = attrs.get("OrderIndex")
    if raw_order is not None and raw_order.strip() != "":
        try:
            order_idx = int(raw_order)
        except ValueError:
            order_idx = None

    dyn_match = _ORDER_INDEX_PAGE_RE.match(name)
    is_dynamic_page_order = dyn_match is not None
    dynamic_page_guid = dyn_match.group(1).upper() if dyn_match else None

    image_data = attrs.get("ImageData")
    has_image_data = image_data is not None and len(image_data) > 0
    image_data_len = len(image_data) if image_data else 0
    image_data_sha256 = hashlib.sha256(image_data.encode("utf-8", errors="replace")).hexdigest() if has_image_data else None

    # Do not store giant raw base64/hex ImageData inline in attributes JSON if present; keep metadata safely
    stored_attrs = dict(attrs)
    if has_image_data:
        stored_attrs["ImageData"] = f"<binary_attribute len={image_data_len} sha256={image_data_sha256[:12]}>"

    is_expression_script = expression_flag == "-1"
    is_formula = is_expression_script or bool(_FORMULA_BRACKET_RE.search(raw_value))
    if is_expression_script:
        # Never interpret PascalScript literal code as a numeric/boolean parsed value
        parsed_val: Any = raw_value
    elif is_formula:
        parsed_val = raw_value
    else:
        parsed_val = _coerce_scalar_value(prop_class, raw_value)

    return CanonicalProperty(
        native_property_guid=prop_guid,
        name=name,
        property_class=prop_class,
        raw_value=raw_value,
        parsed_value=parsed_val,
        units=units,
        input_units=input_units,
        group=group,
        order_index=order_idx,
        decimal_places=decimal_places,
        parse_formula=parse_formula,
        expression_flag=expression_flag,
        is_formula=is_formula,
        is_expression_script=is_expression_script,
        is_dynamic_page_order=is_dynamic_page_order,
        dynamic_page_guid=dynamic_page_guid,
        has_image_data=has_image_data,
        image_data_length=image_data_len,
        image_data_sha256=image_data_sha256,
        attributes=stored_attrs,
        source_location=source_location,
        provenance=ProvenanceStatus.NATIVE,
    )


def _coerce_scalar_value(prop_class: str, raw_value: str) -> Any:
    trimmed = raw_value.strip()
    if trimmed == "":
        return None
    if prop_class == "CheckBox":
        low = trimmed.lower()
        if low in ("true", "-1", "1", "yes"):
            return True
        if low in ("false", "0", "no"):
            return False
        return raw_value
    if prop_class in ("Number", "Slider", "Color"):
        if _NUMERIC_RE.match(trimmed):
            if "." in trimmed or "e" in trimmed.lower():
                try:
                    return float(trimmed)
                except ValueError:
                    return raw_value
            try:
                return int(trimmed)
            except ValueError:
                return raw_value
    return raw_value
