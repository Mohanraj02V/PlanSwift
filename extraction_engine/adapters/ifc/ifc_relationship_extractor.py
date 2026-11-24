"""Single-pass IFC relationship graph builder with GlobalId + STEP ID traceability and cycle guards."""

from __future__ import annotations

from typing import Any

import ifcopenshell

from extraction_engine.adapters.ifc.ifc_property_extractor import parse_ifc_material
from extraction_engine.core.extraction_context import ExtractionConfig
from extraction_engine.core.extraction_result import CanonicalRelationship, ProvenanceStatus


def extract_ifc_relationships_and_indexes(
    model: ifcopenshell.file,
    elem_key_by_step_id: dict[int, str],
    config: ExtractionConfig,
) -> dict[str, Any]:
    """Traverse IFC relationship classes once to build lookup indexes and CanonicalRelationship edges."""
    relationships: list[CanonicalRelationship] = []
    rel_keys_seen: set[str] = set()
    warnings: list[str] = []

    psets_by_step_id: dict[int, list[Any]] = {}
    type_by_elem_step_id: dict[int, Any] = {}
    materials_by_step_id: dict[int, list[dict[str, Any]]] = {}
    classifications_by_step_id: dict[int, list[dict[str, Any]]] = {}
    spatial_parent_by_step_id: dict[int, int] = {}

    def _stable_id(ent: Any) -> str:
        sid = int(ent.id())
        if sid in elem_key_by_step_id:
            return elem_key_by_step_id[sid]
        gid = getattr(ent, "GlobalId", None)
        return str(gid) if gid else f"STEP#{sid}"

    def _add_rel(
        rtype: str,
        rel_ent: Any,
        src_ent: Any,
        tgt_ent: Any,
        order_idx: int | None = None,
        extra_meta: dict[str, Any] | None = None,
    ) -> None:
        src_id = _stable_id(src_ent)
        tgt_id = _stable_id(tgt_ent)
        rel_step = int(rel_ent.id())
        rkey = f"{rtype}:{rel_step}:{src_id}->{tgt_id}"
        if rkey in rel_keys_seen:
            return
        rel_keys_seen.add(rkey)
        meta = {
            "rel_step_id": rel_step,
            "rel_global_id": getattr(rel_ent, "GlobalId", "") or "",
            "rel_class": rel_ent.is_a(),
            "source_step_id": int(src_ent.id()),
            "target_step_id": int(tgt_ent.id()),
        }
        if extra_meta:
            meta.update(extra_meta)
        relationships.append(
            CanonicalRelationship(
                relationship_key=rkey,
                relationship_type=rtype,  # type: ignore[arg-type]
                source_guid=src_id,
                target_guid=tgt_id,
                order_index=order_idx,
                metadata=meta,
                provenance=ProvenanceStatus.NATIVE,
            )
        )

    # 1. IfcRelAggregates (Project -> Site -> Building -> Storey, CurtainWall -> Members, Stair -> Flights)
    for rel in model.by_type("IfcRelAggregates"):
        parent = getattr(rel, "RelatingObject", None)
        if parent is None:
            continue
        p_sid = int(parent.id())
        for idx, child in enumerate(getattr(rel, "RelatedObjects", None) or []):
            if child is None:
                continue
            c_sid = int(child.id())
            if c_sid == p_sid:
                warnings.append(f"Self-referential IfcRelAggregates #{rel.id()} on STEP #{p_sid} skipped.")
                continue
            spatial_parent_by_step_id.setdefault(c_sid, p_sid)
            _add_rel("ifc_aggregates", rel, parent, child, order_idx=idx)

    # 2. IfcRelContainedInSpatialStructure (BuildingStorey/Building/Space -> Building elements)
    for rel in model.by_type("IfcRelContainedInSpatialStructure"):
        container = getattr(rel, "RelatingStructure", None)
        if container is None:
            continue
        c_sid = int(container.id())
        for idx, elem in enumerate(getattr(rel, "RelatedElements", None) or []):
            if elem is None:
                continue
            e_sid = int(elem.id())
            spatial_parent_by_step_id[e_sid] = c_sid
            _add_rel("ifc_contained_in_spatial_structure", rel, container, elem, order_idx=idx)

    # 3. IfcRelDefinesByProperties (PropertySets & ElementQuantities)
    for rel in model.by_type("IfcRelDefinesByProperties"):
        pdef = getattr(rel, "RelatingPropertyDefinition", None)
        if pdef is None:
            continue
        for obj in getattr(rel, "RelatedObjects", None) or []:
            if obj is None:
                continue
            psets_by_step_id.setdefault(int(obj.id()), []).append(pdef)
            _add_rel("ifc_defines_by_properties", rel, obj, pdef)

    # 4. IfcRelDefinesByType
    for rel in model.by_type("IfcRelDefinesByType"):
        tobj = getattr(rel, "RelatingType", None)
        if tobj is None:
            continue
        for obj in getattr(rel, "RelatedObjects", None) or []:
            if obj is None:
                continue
            type_by_elem_step_id[int(obj.id())] = tobj
            _add_rel("ifc_defines_by_type", rel, obj, tobj)

    # 5. IfcRelAssociatesMaterial
    for rel in model.by_type("IfcRelAssociatesMaterial"):
        mat_sel = getattr(rel, "RelatingMaterial", None)
        if mat_sel is None:
            continue
        parsed_mats = parse_ifc_material(mat_sel)
        for obj in getattr(rel, "RelatedObjects", None) or []:
            if obj is None:
                continue
            materials_by_step_id.setdefault(int(obj.id()), []).extend(parsed_mats)
            _add_rel("ifc_associates_material", rel, obj, mat_sel)

    # 6. IfcRelAssociatesClassification
    for rel in model.by_type("IfcRelAssociatesClassification"):
        cls_ref = getattr(rel, "RelatingClassification", None)
        if cls_ref is None:
            continue
        cls_info = {
            "step_id": int(cls_ref.id()),
            "kind": cls_ref.is_a(),
            "name": getattr(cls_ref, "Name", "") or "",
            "identification": getattr(cls_ref, "Identification", getattr(cls_ref, "ItemReference", "")) or "",
            "location": getattr(cls_ref, "Location", "") or "",
        }
        for obj in getattr(rel, "RelatedObjects", None) or []:
            if obj is None:
                continue
            classifications_by_step_id.setdefault(int(obj.id()), []).append(cls_info)
            _add_rel("ifc_associates_classification", rel, obj, cls_ref)

    # 7. IfcRelVoidsElement (Wall/Slab -> OpeningElement)
    for rel in model.by_type("IfcRelVoidsElement"):
        host = getattr(rel, "RelatingBuildingElement", None)
        opening = getattr(rel, "RelatedOpeningElement", None)
        if host is not None and opening is not None:
            _add_rel("ifc_voids_element", rel, host, opening)

    # 8. IfcRelFillsElement (OpeningElement -> Door/Window)
    for rel in model.by_type("IfcRelFillsElement"):
        opening = getattr(rel, "RelatingOpeningElement", None)
        filling = getattr(rel, "RelatedBuildingElement", None)
        if opening is not None and filling is not None:
            _add_rel("ifc_fills_element", rel, opening, filling)

    # 9. IfcRelConnectsElements (Wall <-> Wall, etc.)
    for rel in model.by_type("IfcRelConnectsElements"):
        e1 = getattr(rel, "RelatingElement", None)
        e2 = getattr(rel, "RelatedElement", None)
        if e1 is not None and e2 is not None:
            _add_rel("ifc_connects_elements", rel, e1, e2)

    # Detect cycles in spatial parent hierarchy with depth limit
    for sid in list(spatial_parent_by_step_id.keys()):
        seen_chain: set[int] = set()
        cur: int | None = sid
        steps = 0
        while cur is not None and cur in spatial_parent_by_step_id:
            if cur in seen_chain:
                warnings.append(f"Cycle detected in IFC spatial hierarchy involving STEP #{cur}; breaking cycle.")
                spatial_parent_by_step_id.pop(cur, None)
                break
            seen_chain.add(cur)
            cur = spatial_parent_by_step_id.get(cur)
            steps += 1
            if steps > config.ifc_max_rel_depth:
                warnings.append(f"Spatial hierarchy depth exceeded ifc_max_rel_depth={config.ifc_max_rel_depth} at STEP #{sid}.")
                break

    relationships.sort(key=lambda r: r.relationship_key)
    return {
        "relationships": relationships,
        "psets_by_step_id": psets_by_step_id,
        "type_by_elem_step_id": type_by_elem_step_id,
        "materials_by_step_id": materials_by_step_id,
        "classifications_by_step_id": classifications_by_step_id,
        "spatial_parent_by_step_id": spatial_parent_by_step_id,
        "warnings": warnings,
    }
