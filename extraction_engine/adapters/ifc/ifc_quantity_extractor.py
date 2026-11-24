"""Native IFC IfcElementQuantity (Qto_*) extractor preserving raw values separately from derived geometry."""

from __future__ import annotations

from typing import Any

from extraction_engine.core.cad_models import CanonicalIFCQuantityItem, CanonicalIFCQuantitySet
from extraction_engine.core.extraction_result import ProvenanceStatus


def _extract_qto_item(qty: Any, unit_meta: dict[str, Any]) -> CanonicalIFCQuantityItem:
    qclass = qty.is_a()
    qname = getattr(qty, "Name", "") or f"#{qty.id()}"
    formula = getattr(qty, "Formula", "") or ""
    raw_val: float | int | None = None
    raw_unit = ""
    norm_val: float | None = None
    norm_unit = ""

    len_fac = unit_meta.get("unit_to_meter_factor")
    area_fac = unit_meta.get("area_to_m2_factor")
    vol_fac = unit_meta.get("volume_to_m3_factor")

    if qclass == "IfcQuantityLength":
        raw_val = float(qty.LengthValue) if getattr(qty, "LengthValue", None) is not None else None
        raw_unit = unit_meta.get("length_unit", "") or ""
        if raw_val is not None and len_fac is not None:
            norm_val = raw_val * len_fac
            norm_unit = "m"
    elif qclass == "IfcQuantityArea":
        raw_val = float(qty.AreaValue) if getattr(qty, "AreaValue", None) is not None else None
        raw_unit = unit_meta.get("area_unit", "") or ""
        if raw_val is not None and area_fac is not None:
            norm_val = raw_val * area_fac
            norm_unit = "m^2"
    elif qclass == "IfcQuantityVolume":
        raw_val = float(qty.VolumeValue) if getattr(qty, "VolumeValue", None) is not None else None
        raw_unit = unit_meta.get("volume_unit", "") or ""
        if raw_val is not None and vol_fac is not None:
            norm_val = raw_val * vol_fac
            norm_unit = "m^3"
    elif qclass == "IfcQuantityWeight":
        raw_val = float(qty.WeightValue) if getattr(qty, "WeightValue", None) is not None else None
        raw_unit = "weight"
    elif qclass == "IfcQuantityCount":
        raw_val = float(qty.CountValue) if getattr(qty, "CountValue", None) is not None else None
        raw_unit = "EA"
        if raw_val is not None:
            norm_val = raw_val
            norm_unit = "each"
    elif qclass == "IfcQuantityTime":
        raw_val = float(qty.TimeValue) if getattr(qty, "TimeValue", None) is not None else None
        raw_unit = "time"

    return CanonicalIFCQuantityItem(
        name=qname,
        quantity_type=qclass,
        raw_value=raw_val,
        raw_unit=raw_unit,
        normalized_value=norm_val,
        normalized_unit=norm_unit,
        formula=str(formula),
        provenance=ProvenanceStatus.NATIVE,
    )


def extract_element_qsets(
    element: Any,
    psets_by_step_id: dict[int, list[Any]],
    unit_meta: dict[str, Any],
) -> list[CanonicalIFCQuantitySet]:
    """Extract all native IfcElementQuantity sets attached to an element."""
    qsets: list[CanonicalIFCQuantitySet] = []
    seen_ids: set[int] = set()
    for qdef in psets_by_step_id.get(int(element.id()), ()):
        if qdef.is_a("IfcElementQuantity") and int(qdef.id()) not in seen_ids:
            seen_ids.add(int(qdef.id()))
            items = [_extract_qto_item(q, unit_meta) for q in (getattr(qdef, "Quantities", None) or [])]
            qsets.append(
                CanonicalIFCQuantitySet(
                    name=getattr(qdef, "Name", "") or f"#{qdef.id()}",
                    global_id=getattr(qdef, "GlobalId", "") or "",
                    step_id=int(qdef.id()),
                    quantities=items,
                    provenance=ProvenanceStatus.NATIVE,
                )
            )
    qsets.sort(key=lambda q: (q.name, q.step_id or 0))
    return qsets
