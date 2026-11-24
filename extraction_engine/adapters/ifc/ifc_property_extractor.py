"""IFC property set, material, and classification extractor preserving native Pset/type provenance."""

from __future__ import annotations

from typing import Any

from extraction_engine.core.cad_models import CanonicalIFCPropertySet
from extraction_engine.core.extraction_result import ProvenanceStatus


def _unwrap_ifc_value(val: Any) -> Any:
    if val is None:
        return None
    if hasattr(val, "wrappedValue"):
        return val.wrappedValue
    if isinstance(val, (tuple, list)):
        return [_unwrap_ifc_value(v) for v in val]
    if isinstance(val, (int, float, bool, str)):
        return val
    return str(val)


def _extract_single_pset(pset: Any, is_type_inherited: bool = False) -> CanonicalIFCPropertySet:
    props: dict[str, Any] = {}
    for prop in getattr(pset, "HasProperties", None) or []:
        pname = getattr(prop, "Name", "") or f"#{prop.id()}"
        pclass = prop.is_a()
        if pclass == "IfcPropertySingleValue":
            props[pname] = _unwrap_ifc_value(getattr(prop, "NominalValue", None))
        elif pclass == "IfcPropertyEnumeratedValue":
            props[pname] = [_unwrap_ifc_value(v) for v in (getattr(prop, "EnumerationValues", None) or [])]
        elif pclass == "IfcPropertyBoundedValue":
            props[pname] = {
                "upper": _unwrap_ifc_value(getattr(prop, "UpperBoundValue", None)),
                "lower": _unwrap_ifc_value(getattr(prop, "LowerBoundValue", None)),
                "set_point": _unwrap_ifc_value(getattr(prop, "SetPointValue", None)),
            }
        elif pclass == "IfcPropertyListValue":
            props[pname] = [_unwrap_ifc_value(v) for v in (getattr(prop, "ListValues", None) or [])]
        elif pclass == "IfcPropertyTableValue":
            props[pname] = {
                "defining": [_unwrap_ifc_value(v) for v in (getattr(prop, "DefiningValues", None) or [])],
                "defined": [_unwrap_ifc_value(v) for v in (getattr(prop, "DefinedValues", None) or [])],
            }
        else:
            props[pname] = str(prop)

    return CanonicalIFCPropertySet(
        name=getattr(pset, "Name", "") or f"#{pset.id()}",
        global_id=getattr(pset, "GlobalId", "") or "",
        step_id=int(pset.id()),
        is_type_inherited=is_type_inherited,
        properties=props,
        provenance=ProvenanceStatus.NATIVE,
    )


def extract_element_psets(
    element: Any,
    psets_by_step_id: dict[int, list[Any]],
    type_by_elem_step_id: dict[int, Any],
) -> list[CanonicalIFCPropertySet]:
    """Return both direct instance PropertySets and inherited TypeObject PropertySets."""
    result: list[CanonicalIFCPropertySet] = []
    seen_ids: set[int] = set()

    for pdef in psets_by_step_id.get(int(element.id()), ()):
        if pdef.is_a("IfcPropertySet") and int(pdef.id()) not in seen_ids:
            seen_ids.add(int(pdef.id()))
            result.append(_extract_single_pset(pdef, is_type_inherited=False))

    # Also inspect HasPropertySets directly attached on IfcTypeObject
    type_obj = type_by_elem_step_id.get(int(element.id()))
    if type_obj is not None:
        for pdef in getattr(type_obj, "HasPropertySets", None) or []:
            if pdef.is_a("IfcPropertySet") and int(pdef.id()) not in seen_ids:
                seen_ids.add(int(pdef.id()))
                result.append(_extract_single_pset(pdef, is_type_inherited=True))
        for pdef in psets_by_step_id.get(int(type_obj.id()), ()):
            if pdef.is_a("IfcPropertySet") and int(pdef.id()) not in seen_ids:
                seen_ids.add(int(pdef.id()))
                result.append(_extract_single_pset(pdef, is_type_inherited=True))

    result.sort(key=lambda p: (p.name, p.step_id or 0))
    return result


def parse_ifc_material(mat_select: Any) -> list[dict[str, Any]]:
    """Flatten IfcMaterialSelect (Material, LayerSet, LayerSetUsage, ProfileSet, ConstituentSet, List)."""
    if mat_select is None:
        return []
    mtype = mat_select.is_a()
    out: list[dict[str, Any]] = []
    if mtype == "IfcMaterial":
        out.append({"step_id": int(mat_select.id()), "kind": mtype, "name": getattr(mat_select, "Name", "") or ""})
    elif mtype == "IfcMaterialLayerSetUsage":
        ls = getattr(mat_select, "ForLayerSet", None)
        out.extend(parse_ifc_material(ls))
    elif mtype == "IfcMaterialLayerSet":
        ls_name = getattr(mat_select, "LayerSetName", "") or ""
        for idx, layer in enumerate(getattr(mat_select, "MaterialLayers", None) or []):
            mat = getattr(layer, "Material", None)
            out.append(
                {
                    "step_id": int(layer.id()),
                    "kind": "IfcMaterialLayer",
                    "layer_set_name": ls_name,
                    "layer_index": idx,
                    "name": getattr(mat, "Name", "") if mat else (getattr(layer, "Name", "") or ""),
                    "thickness": getattr(layer, "LayerThickness", None),
                }
            )
    elif mtype in ("IfcMaterialList",):
        for mat in getattr(mat_select, "Materials", None) or []:
            out.extend(parse_ifc_material(mat))
    elif mtype == "IfcMaterialConstituentSet":
        for cons in getattr(mat_select, "MaterialConstituents", None) or []:
            mat = getattr(cons, "Material", None)
            out.append(
                {
                    "step_id": int(cons.id()),
                    "kind": "IfcMaterialConstituent",
                    "set_name": getattr(mat_select, "Name", "") or "",
                    "name": getattr(mat, "Name", "") if mat else (getattr(cons, "Name", "") or ""),
                    "fraction": getattr(cons, "Fraction", None),
                }
            )
    elif mtype == "IfcMaterialProfileSetUsage":
        out.extend(parse_ifc_material(getattr(mat_select, "ForProfileSet", None)))
    elif mtype == "IfcMaterialProfileSet":
        for prof in getattr(mat_select, "MaterialProfiles", None) or []:
            mat = getattr(prof, "Material", None)
            out.append(
                {
                    "step_id": int(prof.id()),
                    "kind": "IfcMaterialProfile",
                    "set_name": getattr(mat_select, "Name", "") or "",
                    "name": getattr(mat, "Name", "") if mat else (getattr(prof, "Name", "") or ""),
                }
            )
    else:
        out.append({"step_id": int(mat_select.id()), "kind": mtype, "name": getattr(mat_select, "Name", "") or mtype})
    return out
