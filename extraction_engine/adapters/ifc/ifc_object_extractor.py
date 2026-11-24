"""IFC object extractor building spatial hierarchy, properties, native Qto_*, placements, and canonical objects."""

from __future__ import annotations

from typing import Any

import ifcopenshell
import ifcopenshell.util.placement

from extraction_engine.adapters.ifc.ifc_geometry_extractor import extract_ifc_geometries_bulk
from extraction_engine.adapters.ifc.ifc_property_extractor import extract_element_psets
from extraction_engine.adapters.ifc.ifc_quantity_extractor import extract_element_qsets
from extraction_engine.adapters.ifc.ifc_relationship_extractor import extract_ifc_relationships_and_indexes
from extraction_engine.core.cad_models import CanonicalIFCElement, CanonicalIFCGeometrySummary
from extraction_engine.core.extraction_context import ExtractionConfig
from extraction_engine.core.extraction_result import (
    CanonicalMeasurement,
    CanonicalObject,
    CanonicalPage,
    CanonicalProperty,
    ProvenanceRecord,
    ProvenanceStatus,
)


def _safe_placement_matrix(ent: Any, depth_limit: int = 64) -> tuple[list[list[float]] | None, list[float] | None, str | None]:
    """Compute world placement matrix with recursion/cycle protection around ObjectPlacement chain."""
    placement = getattr(ent, "ObjectPlacement", None)
    if placement is None:
        return None, None, None
    # Detect placement cycles explicitly before calling get_local_placement
    cur = placement
    seen: set[int] = set()
    hops = 0
    while cur is not None:
        pid = int(cur.id())
        if pid in seen:
            return None, None, f"Circular PlacementRelTo detected on STEP #{ent.id()}"
        seen.add(pid)
        hops += 1
        if hops > depth_limit:
            return None, None, f"ObjectPlacement depth exceeded {depth_limit} on STEP #{ent.id()}"
        cur = getattr(cur, "PlacementRelTo", None)
    try:
        mat = ifcopenshell.util.placement.get_local_placement(placement)
        rows = [[float(mat[r][c]) for c in range(4)] for r in range(4)]
        origin = [rows[0][3], rows[1][3], rows[2][3]]
        return rows, origin, None
    except Exception as exc:
        return None, None, f"Placement evaluation error on STEP #{ent.id()}: {exc}"


def _resolve_storey_name(
    sid: int,
    spatial_parent_by_step_id: dict[int, int],
    ent_by_step_id: dict[int, Any],
) -> str:
    cur = sid
    seen: set[int] = set()
    while cur in spatial_parent_by_step_id and cur not in seen:
        seen.add(cur)
        cur = spatial_parent_by_step_id[cur]
        parent = ent_by_step_id.get(cur)
        if parent is not None and parent.is_a("IfcBuildingStorey"):
            return getattr(parent, "Name", "") or f"Storey #{cur}"
    return ""


def extract_all_ifc_elements(
    model: ifcopenshell.file,
    doc_hash: str,
    source_name: str,
    unit_meta: dict[str, Any],
    config: ExtractionConfig,
) -> dict[str, Any]:
    """Extract spatial + product + generic IfcObject records cleanly with native vs calculated separation."""
    # Collect IfcProject + IfcContext (IFC4+) + all IfcObject entities deterministically sorted & deduplicated by STEP ID
    seen_sids: dict[int, Any] = {}
    for ent in model.by_type("IfcProject"):
        seen_sids[int(ent.id())] = ent
    try:
        for ent in model.by_type("IfcContext"):
            seen_sids[int(ent.id())] = ent
    except RuntimeError:
        pass
    for ent in model.by_type("IfcObject"):
        seen_sids[int(ent.id())] = ent
    all_raw = [seen_sids[sid] for sid in sorted(seen_sids.keys())]
    if len(all_raw) > config.ifc_max_elements:
        truncated_warn = [f"Reached ifc_max_elements={config.ifc_max_elements}; truncated remaining IFC objects."]
        all_raw = all_raw[: config.ifc_max_elements]
    else:
        truncated_warn = []

    ent_by_step_id: dict[int, Any] = {int(e.id()): e for e in all_raw}
    elem_key_by_step_id: dict[int, str] = {}
    seen_guids: set[str] = set()
    guid_warnings: list[str] = []

    for ent in all_raw:
        sid = int(ent.id())
        raw_gid = str(getattr(ent, "GlobalId", "") or "").strip()
        if not raw_gid:
            key = f"STEP#{sid}"
            guid_warnings.append(f"{ent.is_a()} #{sid} missing GlobalId; using STEP ID key '{key}'.")
        elif raw_gid in seen_guids:
            key = f"{raw_gid}:STEP#{sid}"
            guid_warnings.append(f"Duplicate GlobalId '{raw_gid}' on {ent.is_a()} #{sid}; disambiguated as '{key}'.")
        else:
            key = raw_gid
        seen_guids.add(key)
        elem_key_by_step_id[sid] = key

    rel_bundle = extract_ifc_relationships_and_indexes(model, elem_key_by_step_id, config)
    psets_by_step_id = rel_bundle["psets_by_step_id"]
    type_by_elem_step_id = rel_bundle["type_by_elem_step_id"]
    materials_by_step_id = rel_bundle["materials_by_step_id"]
    classifications_by_step_id = rel_bundle["classifications_by_step_id"]
    spatial_parent_by_step_id = rel_bundle["spatial_parent_by_step_id"]

    # Optional bounded 3D geometry extraction (off by default unless ifc_extract_geometry=True)
    geom_summaries, geom_warnings = extract_ifc_geometries_bulk(model, all_raw, config, unit_meta)

    ifc_elements: list[CanonicalIFCElement] = []
    canonical_pages: list[CanonicalPage] = []
    canonical_objects: list[CanonicalObject] = []
    provenance_records: list[ProvenanceRecord] = []
    discovered_classes: dict[str, int] = {}
    unsupported_classes: dict[str, int] = {}
    unsupported_objects: list[dict[str, Any]] = []
    warnings: list[str] = truncated_warn + guid_warnings + rel_bundle["warnings"] + geom_warnings

    # Represent IfcBuildingStorey nodes as CanonicalPage records for page/storey UI compatibility
    storeys = [e for e in all_raw if e.is_a("IfcBuildingStorey")]
    for idx, st in enumerate(storeys):
        sid = int(st.id())
        canonical_pages.append(
            CanonicalPage(
                native_guid=elem_key_by_step_id[sid],
                name=getattr(st, "Name", "") or f"Storey #{sid}",
                native_class="IfcBuildingStorey",
                page_type="BIM Building Storey",
                order_index=idx,
                scale_units=unit_meta.get("length_unit") or "",
                scale_x=1.0,
                scale_y=1.0,
                numeric_scale_factor=unit_meta.get("unit_to_meter_factor"),
                provenance=ProvenanceStatus.NATIVE,
            )
        )

    for ent in all_raw:
        sid = int(ent.id())
        cls_name = ent.is_a()
        discovered_classes[cls_name] = discovered_classes.get(cls_name, 0) + 1
        key = elem_key_by_step_id[sid]
        raw_gid = str(getattr(ent, "GlobalId", "") or "")
        name = str(getattr(ent, "Name", "") or "")
        desc = str(getattr(ent, "Description", "") or "")
        obj_type = str(getattr(ent, "ObjectType", "") or "")
        pred_type = str(getattr(ent, "PredefinedType", "") or "")
        tag = str(getattr(ent, "Tag", "") or "")

        parent_sid = spatial_parent_by_step_id.get(sid)
        parent_key = elem_key_by_step_id.get(parent_sid) if parent_sid else None
        storey_name = _resolve_storey_name(sid, spatial_parent_by_step_id, ent_by_step_id)

        matrix, origin, p_warn = _safe_placement_matrix(ent, depth_limit=config.ifc_max_rel_depth)
        el_warnings: list[str] = []
        if p_warn:
            el_warnings.append(p_warn)
            warnings.append(p_warn)

        psets = extract_element_psets(ent, psets_by_step_id, type_by_elem_step_id)
        qsets = extract_element_qsets(ent, psets_by_step_id, unit_meta)
        mats = materials_by_step_id.get(sid, [])
        clss = classifications_by_step_id.get(sid, [])

        reps: list[dict[str, Any]] = []
        rep = getattr(ent, "Representation", None)
        if rep is not None:
            for r in getattr(rep, "Representations", None) or []:
                items_info = [it.is_a() for it in (getattr(r, "Items", None) or [])]
                reps.append(
                    {
                        "step_id": int(r.id()),
                        "identifier": getattr(r, "RepresentationIdentifier", "") or "",
                        "type": getattr(r, "RepresentationType", "") or "",
                        "item_classes": items_info,
                    }
                )

        gsummary = geom_summaries.get(sid, CanonicalIFCGeometrySummary(status="skipped_property_only"))
        if gsummary.status == "failed" and gsummary.error:
            el_warnings.append(gsummary.error)

        ifc_el = CanonicalIFCElement(
            global_id=raw_gid or key,
            step_id=sid,
            ifc_class=cls_name,
            name=name,
            description=desc,
            object_type=obj_type,
            predefined_type=pred_type,
            tag=tag,
            spatial_parent_guid=parent_key,
            storey_name=storey_name,
            placement_matrix=matrix,
            world_origin=origin,
            property_sets=psets,
            quantity_sets=qsets,
            materials=mats,
            classifications=clss,
            representations=reps,
            geometry_summary=gsummary,
            warnings=el_warnings,
            raw_attributes={
                "GlobalId": raw_gid,
                "STEP_ID": sid,
                "ifc_class": cls_name,
                "ObjectType": obj_type,
                "PredefinedType": pred_type,
                "Tag": tag,
            },
            provenance=ProvenanceStatus.NATIVE,
        )
        ifc_elements.append(ifc_el)

        # Shared CanonicalObject + Properties + Measurements preserving Native Qto_* vs Calculated Geometry separately!
        props = [
            CanonicalProperty(
                native_property_guid=f"{key}:GlobalId",
                name="GlobalId",
                property_class="Text",
                raw_value=raw_gid,
                parsed_value=raw_gid,
                provenance=ProvenanceStatus.NATIVE,
            ),
            CanonicalProperty(
                native_property_guid=f"{key}:STEP_ID",
                name="STEP_ID",
                property_class="Number",
                raw_value=f"#{sid}",
                parsed_value=sid,
                provenance=ProvenanceStatus.NATIVE,
            ),
        ]
        if obj_type:
            props.append(
                CanonicalProperty(
                    native_property_guid=f"{key}:ObjectType",
                    name="ObjectType",
                    property_class="Text",
                    raw_value=obj_type,
                    parsed_value=obj_type,
                    provenance=ProvenanceStatus.NATIVE,
                )
            )
        if pred_type:
            props.append(
                CanonicalProperty(
                    native_property_guid=f"{key}:PredefinedType",
                    name="PredefinedType",
                    property_class="Text",
                    raw_value=pred_type,
                    parsed_value=pred_type,
                    provenance=ProvenanceStatus.NATIVE,
                )
            )
        for ps in psets:
            for pk, pv in ps.properties.items():
                props.append(
                    CanonicalProperty(
                        native_property_guid=f"{key}:pset:{ps.step_id}:{pk}",
                        name=f"{ps.name}.{pk}",
                        property_class="Number" if isinstance(pv, (int, float)) and not isinstance(pv, bool) else "Text",
                        raw_value="" if pv is None else str(pv),
                        parsed_value=pv,
                        group=ps.name,
                        provenance=ProvenanceStatus.NATIVE,
                    )
                )

        measurements: list[CanonicalMeasurement] = []
        # Native IFC QuantitySet values -> STRICTLY provenance="native" (never overwritten!)
        for qs in qsets:
            for qi in qs.quantities:
                measurements.append(
                    CanonicalMeasurement(
                        measurement_key=f"{key}:qto:{qs.name}.{qi.name}",
                        object_guid=key,
                        measurement_type=qi.quantity_type,
                        property_name=f"{qs.name}.{qi.name}",
                        raw_formula=qi.formula or None,
                        native_stored_value=str(qi.raw_value) if qi.raw_value is not None else "",
                        derived_quantity=float(qi.raw_value) if qi.raw_value is not None else None,
                        unit=qi.raw_unit,
                        normalized_quantity=qi.normalized_value,
                        normalized_unit=qi.normalized_unit,
                        provenance_classification=ProvenanceStatus.NATIVE.value,
                        status=ProvenanceStatus.NATIVE,
                    )
                )
        # Optional 3D geometry derived values -> STRICTLY provenance="calculated" in separate measurement keys!
        if gsummary.status == "calculated":
            if gsummary.surface_area is not None:
                measurements.append(
                    CanonicalMeasurement(
                        measurement_key=f"{key}:geom_calculated:SurfaceArea",
                        object_guid=key,
                        measurement_type="IfcOpenShellMesh",
                        property_name="Geometry.CalculatedSurfaceArea",
                        calculated_quantity=gsummary.surface_area,
                        derived_quantity=gsummary.surface_area,
                        unit="m^2",
                        normalized_quantity=gsummary.normalized_surface_area_m2,
                        normalized_unit="m^2",
                        provenance_classification=ProvenanceStatus.CALCULATED.value,
                        status=ProvenanceStatus.CALCULATED,
                    )
                )
            if gsummary.volume is not None:
                measurements.append(
                    CanonicalMeasurement(
                        measurement_key=f"{key}:geom_calculated:Volume",
                        object_guid=key,
                        measurement_type="IfcOpenShellMesh",
                        property_name="Geometry.CalculatedVolume",
                        calculated_quantity=gsummary.volume,
                        derived_quantity=gsummary.volume,
                        unit="m^3",
                        normalized_quantity=gsummary.normalized_volume_m3,
                        normalized_unit="m^3",
                        provenance_classification=ProvenanceStatus.CALCULATED.value,
                        status=ProvenanceStatus.CALCULATED,
                    )
                )

        if gsummary.status in ("unsupported", "failed"):
            unsupported_classes[f"{cls_name}:Geometry"] = unsupported_classes.get(f"{cls_name}:Geometry", 0) + 1
            unsupported_objects.append(
                {
                    "native_guid": key,
                    "step_id": sid,
                    "native_class": cls_name,
                    "name": name,
                    "reason": gsummary.error or f"geometry_{gsummary.status}",
                }
            )

        canonical_objects.append(
            CanonicalObject(
                native_guid=key,
                native_class=cls_name,
                native_type=obj_type or pred_type or cls_name,
                name=name or f"{cls_name} #{sid}",
                parent_guid=parent_key,
                root_path=f"IFC/{storey_name or 'Model'}/{cls_name}/{key}",
                depth=0 if cls_name == "IfcProject" else (1 if cls_name in ("IfcSite", "IfcBuilding", "IfcBuildingStorey") else 2),
                is_known_class=True,
                is_page=(cls_name == "IfcBuildingStorey"),
                properties=props,
                measurements=measurements,
                provenance=ProvenanceStatus.NATIVE,
                raw_attributes={"GlobalId": raw_gid, "STEP_ID": str(sid), "ifc_class": cls_name},
            )
        )
        provenance_records.append(
            ProvenanceRecord(
                source_system="IFC",
                source_adapter="ifc_ifcopenshell",
                source_file=source_name,
                source_location=f"#{sid}",
                source_object_guid=key,
                source_class=cls_name,
                status=ProvenanceStatus.NATIVE,
            )
        )

    return {
        "ifc_elements": ifc_elements,
        "pages": canonical_pages,
        "objects": canonical_objects,
        "relationships": rel_bundle["relationships"],
        "provenance_records": provenance_records,
        "discovered_classes": discovered_classes,
        "unsupported_classes": unsupported_classes,
        "unsupported_objects": unsupported_objects,
        "warnings": warnings,
    }
