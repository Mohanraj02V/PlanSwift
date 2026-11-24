"""DXF entity extractor with nested INSERT matrix composition, XREF safety, and rule-based classification."""

from __future__ import annotations

import logging
from typing import Any

from ezdxf.document import Drawing
from ezdxf.math import Matrix44, Vec3

from extraction_engine.adapters.dxf.dxf_dimension_extractor import extract_dimension_data
from extraction_engine.adapters.dxf.dxf_geometry_extractor import extract_entity_geometry
from extraction_engine.core.cad_models import (
    CADClassificationInfo,
    CanonicalCADBlock,
    CanonicalCADEntity,
    CanonicalCADLayer,
)
from extraction_engine.core.extraction_context import ExtractionConfig
from extraction_engine.core.extraction_result import (
    CanonicalGeometry,
    CanonicalMeasurement,
    CanonicalObject,
    CanonicalPage,
    CanonicalPoint,
    CanonicalProperty,
    CanonicalRelationship,
    ProvenanceRecord,
    ProvenanceStatus,
)

logger = logging.getLogger(__name__)

# Optional configurable rule-based layer/entity semantic hints (ALWAYS tagged provenance="inferred")
_LAYER_CLASSIFICATION_RULES: tuple[tuple[tuple[str, ...], str, str], ...] = (
    (("wall", "a-wall"), "Wall", "Architecture"),
    (("door", "a-door"), "Door", "Architecture"),
    (("wind", "a-glaz", "window"), "Window", "Architecture"),
    (("slab", "floor", "s-slab"), "Slab", "Structure"),
    (("col", "s-cols", "column"), "Column", "Structure"),
    (("beam", "s-beam"), "Beam", "Structure"),
    (("foot", "found", "s-fndn"), "Foundation", "Structure"),
    (("duct", "m-hvac", "hvac"), "HVAC Duct", "MEP-Mechanical"),
    (("pipe", "plumb", "p-"), "Piping", "MEP-Plumbing"),
    (("elec", "e-powr", "e-lite", "cable"), "Electrical", "MEP-Electrical"),
    (("fire", "fp-", "sprink"), "Fire Protection", "MEP-Fire"),
    (("room", "space", "area", "a-area"), "Space", "Architecture"),
    (("dim", "anno", "text"), "Annotation", "Documentation"),
)


def classify_cad_entity_by_rule(
    layer_name: str,
    entity_type: str,
    enabled: bool = True,
) -> CADClassificationInfo:
    """Distinguish native entity_type from inferred layer-name semantic classification."""
    if not enabled or not layer_name:
        return CADClassificationInfo(native_type=entity_type, classification_provenance=ProvenanceStatus.NATIVE)

    low = layer_name.lower()
    for tokens, cat, disc in _LAYER_CLASSIFICATION_RULES:
        if any(tok in low for tok in tokens):
            return CADClassificationInfo(
                native_type=entity_type,
                rule_based_category=cat,
                rule_based_discipline=disc,
                classification_provenance=ProvenanceStatus.INFERRED,
            )
    return CADClassificationInfo(native_type=entity_type, classification_provenance=ProvenanceStatus.NATIVE)


def _extract_entity_attributes(entity: Any, doc: Drawing) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Extract entity-specific non-geometric attributes safely (ATTRIBs, text, hatch pattern, IMAGE path metadata)."""
    dxf = entity.dxf
    etype = entity.dxftype()
    attrs: dict[str, Any] = {}
    ext_refs: list[dict[str, Any]] = []

    if etype in ("TEXT", "ATTRIB", "ATTDEF"):
        attrs["text"] = getattr(dxf, "text", "") or ""
        attrs["style"] = getattr(dxf, "style", "") or ""
        if etype in ("ATTRIB", "ATTDEF"):
            attrs["tag"] = getattr(dxf, "tag", "") or ""
    elif etype == "MTEXT":
        attrs["text"] = entity.plain_text() if hasattr(entity, "plain_text") else (getattr(entity, "text", "") or "")
        attrs["raw_text"] = getattr(entity, "text", "") or ""
        attrs["style"] = getattr(dxf, "style", "") or ""
    elif etype == "INSERT":
        attrs["block_name"] = getattr(dxf, "name", "") or ""
        attribs: dict[str, str] = {}
        for att in getattr(entity, "attribs", []):
            attribs[getattr(att.dxf, "tag", "")] = getattr(att.dxf, "text", "") or ""
        if attribs:
            attrs["block_attribs"] = attribs
    elif etype == "HATCH":
        attrs["pattern_name"] = getattr(dxf, "pattern_name", "") or ""
        attrs["solid_fill"] = bool(getattr(dxf, "solid_fill", 0))
        attrs["pattern_scale"] = float(getattr(dxf, "pattern_scale", 1.0) or 1.0)
        attrs["pattern_angle"] = float(getattr(dxf, "pattern_angle", 0.0) or 0.0)
    elif etype in ("MLEADER", "MULTILEADER"):
        ctx = getattr(entity, "context", None)
        if ctx and getattr(ctx, "mtext", None):
            attrs["mtext_content"] = getattr(ctx.mtext, "default_content", "") or ""
    elif etype == "IMAGE":
        img_def_handle = getattr(dxf, "image_def_handle", "") or ""
        img_path = ""
        if img_def_handle and img_def_handle in doc.entitydb:
            img_def = doc.entitydb.get(img_def_handle)
            img_path = getattr(img_def.dxf, "filename", "") if img_def else ""
        attrs["image_def_handle"] = img_def_handle
        attrs["image_path"] = img_path
        ext_refs.append(
            {
                "kind": "dxf_image_def",
                "handle": getattr(dxf, "handle", "") or "",
                "path": img_path,
                "loaded": False,
                "security_note": "IMAGE metadata preserved; external raster never loaded.",
            }
        )
    elif etype == "VIEWPORT":
        attrs["viewport_id"] = getattr(dxf, "id", None)
        attrs["status"] = getattr(dxf, "status", None)

    return attrs, ext_refs


def _resolve_insert_summary(
    doc: Drawing,
    insert_entity: Any,
    max_depth: int,
    unit_factor_m: float | None,
) -> dict[str, Any]:
    """Resolve nested INSERT transforms recursively with depth limit and circular block-reference protection."""
    warnings: list[str] = []
    expanded_count = 0
    total_line_length = 0.0
    total_area = 0.0
    visited_stack: list[str] = []

    def _walk(ins_ent: Any, parent_matrix: Matrix44, depth: int) -> None:
        nonlocal expanded_count, total_line_length, total_area
        bname = getattr(ins_ent.dxf, "name", "") or ""
        if not bname or bname not in doc.blocks:
            warnings.append(f"INSERT references missing block '{bname}'.")
            return
        if bname in visited_stack:
            warnings.append(f"Circular block reference detected: {' -> '.join(visited_stack + [bname])}")
            return
        if depth > max_depth:
            warnings.append(f"Block nesting depth exceeded max_block_depth={max_depth} at '{bname}'.")
            return

        blk = doc.blocks.get(bname)
        if getattr(blk, "is_xref", False) or getattr(blk.block.dxf, "xref_path", ""):
            # Do not attempt external XREF resolution
            return

        # Compute local matrix of this INSERT and compose with parent transform
        local_mat = ins_ent.matrix44()
        composed = local_mat @ parent_matrix
        visited_stack.append(bname)
        try:
            for sub in blk:
                sub_type = sub.dxftype()
                if sub_type == "INSERT":
                    _walk(sub, composed, depth + 1)
                else:
                    expanded_count += 1
                    geom = extract_entity_geometry(sub, matrix=composed, unit_factor_m=unit_factor_m)
                    gm = geom["geometry_metrics"]
                    if gm.get("length") is not None:
                        total_line_length += float(gm["length"])
                    if gm.get("area") is not None:
                        total_area += float(gm["area"])
        finally:
            visited_stack.pop()

    _walk(insert_entity, Matrix44(), 1)
    res: dict[str, Any] = {
        "expanded_child_count": expanded_count,
        "resolved_total_length": total_line_length if expanded_count else None,
        "resolved_total_area": total_area if total_area > 0 else None,
        "warnings": warnings,
    }
    if unit_factor_m is not None and res["resolved_total_length"] is not None:
        res["resolved_total_length_m"] = res["resolved_total_length"] * unit_factor_m
    if unit_factor_m is not None and res["resolved_total_area"] is not None:
        res["resolved_total_area_m2"] = res["resolved_total_area"] * (unit_factor_m * unit_factor_m)
    return res


def extract_all_dxf_entities(
    doc: Drawing,
    doc_hash: str,
    source_name: str,
    source_units: str,
    unit_factor_m: float | None,
    layers: list[CanonicalCADLayer],
    layers_by_name: dict[str, CanonicalCADLayer],
    blocks: list[CanonicalCADBlock],
    blocks_by_name: dict[str, CanonicalCADBlock],
    ext_refs: list[dict[str, Any]],
    config: ExtractionConfig,
) -> dict[str, Any]:
    """Extract all entities from Modelspace, Paperspace layouts, and non-layout Blocks in a single pass."""
    hash_prefix = doc_hash[:12]
    cad_entities: list[CanonicalCADEntity] = []
    canonical_pages: list[CanonicalPage] = []
    canonical_objects: list[CanonicalObject] = []
    relationships: list[CanonicalRelationship] = []
    provenance_records: list[ProvenanceRecord] = []
    discovered_classes: dict[str, int] = {}
    unsupported_classes: dict[str, int] = {}
    unsupported_objects: list[dict[str, Any]] = []
    warnings: list[str] = []

    seen_handles: set[str] = set()
    rel_keys_seen: set[str] = set()

    def _add_rel(rtype: str, src: str, tgt: str, order_idx: int | None = None, meta: dict[str, Any] | None = None) -> None:
        rkey = f"{rtype}:{src}->{tgt}"
        if rkey in rel_keys_seen:
            return
        rel_keys_seen.add(rkey)
        relationships.append(
            CanonicalRelationship(
                relationship_key=rkey,
                relationship_type=rtype,  # type: ignore[arg-type]
                source_guid=src,
                target_guid=tgt,
                order_index=order_idx,
                metadata=meta or {},
                provenance=ProvenanceStatus.NATIVE,
            )
        )

    # 1. Represent DXF Layouts cleanly as CanonicalPage records
    layout_objs = sorted(doc.layouts, key=lambda l: (0 if l.name.lower() == "model" else 1, l.name.lower()))
    for l_idx, layout in enumerate(layout_objs):
        l_handle = getattr(layout.dxf, "handle", "") or layout.name
        l_guid = f"dxf:{hash_prefix}:layout:{l_handle}"
        canonical_pages.append(
            CanonicalPage(
                native_guid=l_guid,
                name=layout.name,
                native_class="DXF_LAYOUT",
                page_type="Modelspace" if layout.is_modelspace else "Paperspace",
                order_index=l_idx,
                scale_units=source_units or None,
                scale_x=1.0,
                scale_y=1.0,
                numeric_scale_factor=unit_factor_m,
                provenance=ProvenanceStatus.NATIVE,
            )
        )

    layout_guid_by_name = {p.name: p.native_guid for p in canonical_pages}

    def _process_container(container: Any, layout_name: str, block_name: str, is_layout_space: bool) -> None:
        nonlocal cad_entities
        for entity in container:
            if len(cad_entities) >= config.dxf_max_entities:
                warnings.append(f"Reached DXF entity safety cap dxf_max_entities={config.dxf_max_entities}; remaining truncated.")
                return

            etype = entity.dxftype()
            dxf = entity.dxf
            handle = (getattr(dxf, "handle", "") or "").upper()
            if not handle:
                handle = f"NOHANDLE_{len(cad_entities) + 1}"
            if handle in seen_handles:
                # Guarantee unique entity key if damaged DXF reuses handle
                entity_key = f"dxf:{hash_prefix}:{handle}:{len(cad_entities) + 1}"
                warnings.append(f"Duplicate DXF handle '{handle}' disambiguated inside document '{source_name}'.")
            else:
                entity_key = f"dxf:{hash_prefix}:{handle}"
            seen_handles.add(handle)

            owner_handle = (getattr(dxf, "owner", "") or "").upper()
            layer_name = getattr(dxf, "layer", "0") or "0"
            linetype = getattr(dxf, "linetype", "BYLAYER") or "BYLAYER"
            color = getattr(dxf, "color", None)
            true_color = getattr(dxf, "true_color", None)
            lineweight = getattr(dxf, "lineweight", None)
            invisible = bool(getattr(dxf, "invisible", 0))
            flags = getattr(dxf, "flags", None)
            thickness = getattr(dxf, "thickness", None)
            elevation_raw = getattr(dxf, "elevation", None)
            elevation = float(elevation_raw[2] if hasattr(elevation_raw, "__len__") and len(elevation_raw) > 2 else elevation_raw) if elevation_raw is not None and not isinstance(elevation_raw, str) else None
            ext_vec = getattr(dxf, "extrusion", (0.0, 0.0, 1.0))
            extrusion = [float(ext_vec[0]), float(ext_vec[1]), float(ext_vec[2])] if hasattr(ext_vec, "__len__") and len(ext_vec) >= 3 else [0.0, 0.0, 1.0]

            geom_info = extract_entity_geometry(entity, matrix=None, unit_factor_m=unit_factor_m)
            ent_attrs, ent_xrefs = _extract_entity_attributes(entity, doc)
            if ent_xrefs:
                ext_refs.extend(ent_xrefs)

            dim_data: dict[str, Any] = {}
            if etype in ("DIMENSION", "ARC_DIMENSION", "LARGE_RADIAL_DIMENSION"):
                dim_data = extract_dimension_data(entity)

            if etype == "INSERT" and config.dxf_resolve_inserts and is_layout_space:
                ins_summary = _resolve_insert_summary(doc, entity, config.dxf_max_block_depth, unit_factor_m)
                ent_attrs["resolved_insert_summary"] = ins_summary
                geom_info["warnings"].extend(ins_summary.get("warnings", []))

            classification = classify_cad_entity_by_rule(
                layer_name=layer_name,
                entity_type=etype,
                enabled=config.dxf_enable_rule_classification,
            )

            is_supported = bool(geom_info["is_supported"])
            ent_warnings = list(geom_info["warnings"])

            cad_ent = CanonicalCADEntity(
                entity_key=entity_key,
                handle=handle,
                entity_type=etype,
                owner_handle=owner_handle,
                layer=layer_name,
                layout_name=layout_name,
                block_name=block_name,
                linetype=linetype,
                color=int(color) if color is not None else None,
                true_color=int(true_color) if true_color is not None else None,
                lineweight=int(lineweight) if lineweight is not None else None,
                invisible=invisible,
                flags=int(flags) if flags is not None else None,
                extrusion=extrusion,
                elevation=elevation,
                thickness=float(thickness) if thickness is not None else None,
                ocs_applied=bool(geom_info["ocs_applied"]),
                is_supported=is_supported,
                native_coordinates=geom_info["native_coordinates"],
                world_coordinates=geom_info["world_coordinates"],
                geometry_metrics=geom_info["geometry_metrics"],
                dimension_data=dim_data,
                attributes=ent_attrs,
                classification=classification,
                warnings=ent_warnings,
                raw_metadata={
                    "dxftype": etype,
                    "handle": handle,
                    "owner_handle": owner_handle,
                },
                provenance=ProvenanceStatus.NATIVE if is_supported else ProvenanceStatus.UNSUPPORTED,
            )
            cad_entities.append(cad_ent)

            # Counters & unsupported tracking
            discovered_classes[etype] = discovered_classes.get(etype, 0) + 1
            lyr_obj = layers_by_name.get(layer_name) or layers_by_name.get(layer_name.lower())
            if lyr_obj is not None:
                if is_layout_space:
                    lyr_obj.entity_count += 1
                _add_rel("layer_member", entity_key, lyr_obj.layer_id)

            if layout_name and layout_name in layout_guid_by_name:
                _add_rel("layout_member", entity_key, layout_guid_by_name[layout_name])

            if block_name and block_name in blocks_by_name:
                _add_rel("block_member", entity_key, blocks_by_name[block_name].block_id)

            if etype == "INSERT":
                tgt_blk = blocks_by_name.get(ent_attrs.get("block_name", ""))
                if tgt_blk is not None:
                    _add_rel("block_insert", entity_key, tgt_blk.block_id)

            if not is_supported:
                unsupported_classes[etype] = unsupported_classes.get(etype, 0) + 1
                unsupported_objects.append(
                    {
                        "native_guid": entity_key,
                        "handle": handle,
                        "native_class": etype,
                        "layer": layer_name,
                        "layout": layout_name,
                        "block_name": block_name,
                        "reason": ent_warnings[0] if ent_warnings else "unsupported_dxf_entity_type",
                    }
                )

            # Populate shared CanonicalObject, CanonicalMeasurement, CanonicalGeometry for unified Explorer compatibility
            parent_guid = layout_guid_by_name.get(layout_name) if layout_name else (blocks_by_name[block_name].block_id if block_name in blocks_by_name else None)
            props = [
                CanonicalProperty(
                    native_property_guid=f"{entity_key}:handle",
                    name="Handle",
                    property_class="Text",
                    raw_value=handle,
                    parsed_value=handle,
                    provenance=ProvenanceStatus.NATIVE,
                ),
                CanonicalProperty(
                    native_property_guid=f"{entity_key}:layer",
                    name="Layer",
                    property_class="Text",
                    raw_value=layer_name,
                    parsed_value=layer_name,
                    provenance=ProvenanceStatus.NATIVE,
                ),
                CanonicalProperty(
                    native_property_guid=f"{entity_key}:linetype",
                    name="Linetype",
                    property_class="Text",
                    raw_value=linetype,
                    parsed_value=linetype,
                    provenance=ProvenanceStatus.NATIVE,
                ),
            ]
            if color is not None:
                props.append(
                    CanonicalProperty(
                        native_property_guid=f"{entity_key}:color",
                        name="Color",
                        property_class="Number",
                        raw_value=str(color),
                        parsed_value=int(color),
                        provenance=ProvenanceStatus.NATIVE,
                    )
                )
            for k_idx, (ak, av) in enumerate(ent_attrs.items()):
                if ak == "resolved_insert_summary":
                    continue
                props.append(
                    CanonicalProperty(
                        native_property_guid=f"{entity_key}:attr:{k_idx}",
                        name=ak,
                        property_class="Text",
                        raw_value=str(av),
                        parsed_value=av,
                        provenance=ProvenanceStatus.NATIVE,
                    )
                )

            gm = geom_info["geometry_metrics"]
            measurements: list[CanonicalMeasurement] = []
            if gm.get("length") is not None:
                measurements.append(
                    CanonicalMeasurement(
                        measurement_key=f"{entity_key}:length",
                        object_guid=entity_key,
                        page_guid=layout_guid_by_name.get(layout_name),
                        measurement_type=etype,
                        property_name="Length",
                        calculated_quantity=gm["length"],
                        reconstructed_quantity=gm["length"],
                        derived_quantity=gm["length"],
                        unit=source_units,
                        normalized_quantity=gm.get("normalized_length_m"),
                        normalized_unit="m" if gm.get("normalized_length_m") is not None else "",
                        provenance_classification=ProvenanceStatus.CALCULATED.value,
                        status=ProvenanceStatus.CALCULATED,
                    )
                )
            if gm.get("area") is not None:
                measurements.append(
                    CanonicalMeasurement(
                        measurement_key=f"{entity_key}:area",
                        object_guid=entity_key,
                        page_guid=layout_guid_by_name.get(layout_name),
                        measurement_type=etype,
                        property_name="Area",
                        calculated_quantity=gm["area"],
                        reconstructed_quantity=gm["area"],
                        derived_quantity=gm["area"],
                        unit=f"sq {source_units}" if source_units and source_units != "unitless" else "",
                        normalized_quantity=gm.get("normalized_area_m2"),
                        normalized_unit="m^2" if gm.get("normalized_area_m2") is not None else "",
                        provenance_classification=ProvenanceStatus.CALCULATED.value,
                        status=ProvenanceStatus.CALCULATED,
                    )
                )
            if dim_data:
                if dim_data.get("actual_measurement") is not None:
                    measurements.append(
                        CanonicalMeasurement(
                            measurement_key=f"{entity_key}:dim_actual",
                            object_guid=entity_key,
                            page_guid=layout_guid_by_name.get(layout_name),
                            measurement_type="DIMENSION",
                            property_name="DimensionActualMeasurement",
                            native_stored_value=str(dim_data["actual_measurement"]),
                            derived_quantity=dim_data["actual_measurement"],
                            unit=source_units,
                            provenance_classification=ProvenanceStatus.NATIVE.value,
                            status=ProvenanceStatus.NATIVE,
                            notes=f"override={dim_data.get('text_override')!r}" if dim_data.get("has_text_override") else "",
                        )
                    )
                if dim_data.get("geometry_measured") is not None:
                    measurements.append(
                        CanonicalMeasurement(
                            measurement_key=f"{entity_key}:dim_geometry",
                            object_guid=entity_key,
                            page_guid=layout_guid_by_name.get(layout_name),
                            measurement_type="DIMENSION",
                            property_name="DimensionGeometryMeasured",
                            calculated_quantity=dim_data["geometry_measured"],
                            derived_quantity=dim_data["geometry_measured"],
                            unit=source_units,
                            provenance_classification=ProvenanceStatus.CALCULATED.value,
                            status=ProvenanceStatus.CALCULATED,
                        )
                    )

            # Map world points into CanonicalGeometry if point sequence exists
            geoms: list[CanonicalGeometry] = []
            raw_pts_list = (
                geom_info["world_coordinates"].get("points")
                or geom_info["world_coordinates"].get("vertices")
                or geom_info["world_coordinates"].get("control_points")
            )
            if not raw_pts_list and "start" in geom_info["world_coordinates"] and "end" in geom_info["world_coordinates"]:
                raw_pts_list = [geom_info["world_coordinates"]["start"], geom_info["world_coordinates"]["end"]]
            elif not raw_pts_list and "location" in geom_info["world_coordinates"]:
                raw_pts_list = [geom_info["world_coordinates"]["location"]]

            if raw_pts_list:
                cpts = [
                    CanonicalPoint(
                        point_order=idx,
                        x=float(pt[0]),
                        y=float(pt[1]),
                        point_type="Normal",
                        raw_x=str(pt[0]),
                        raw_y=str(pt[1]),
                        normalized_x=float(pt[0]) * unit_factor_m if unit_factor_m is not None else None,
                        normalized_y=float(pt[1]) * unit_factor_m if unit_factor_m is not None else None,
                        provenance=ProvenanceStatus.NATIVE,
                    )
                    for idx, pt in enumerate(raw_pts_list)
                ]
                bbox = gm.get("bbox") or {}
                bmin = bbox.get("min") or [None, None]
                bmax = bbox.get("max") or [None, None]
                geoms.append(
                    CanonicalGeometry(
                        section_guid=entity_key,
                        parent_object_guid=entity_key,
                        page_guid=layout_guid_by_name.get(layout_name),
                        geometry_type=str(gm.get("geometry_type") or etype),
                        coordinate_system="dxf_wcs",
                        point_count=len(cpts),
                        points=cpts,
                        bbox_min_x=bmin[0],
                        bbox_min_y=bmin[1],
                        bbox_max_x=bmax[0],
                        bbox_max_y=bmax[1],
                        derived_polyline_length=gm.get("length"),
                        derived_polygon_area=gm.get("area"),
                        scale_x=1.0,
                        scale_y=1.0,
                        scale_unit=source_units,
                        is_calibrated=unit_factor_m is not None,
                        calibrated_length=gm.get("length"),
                        calibrated_area=gm.get("area"),
                        calibrated_unit=source_units,
                        normalized_length_m=gm.get("normalized_length_m"),
                        normalized_area_m2=gm.get("normalized_area_m2"),
                        provenance=ProvenanceStatus.NATIVE,
                        derived_metrics_provenance=ProvenanceStatus.CALCULATED,
                    )
                )

            obj_name = ent_attrs.get("block_name") or ent_attrs.get("tag") or ent_attrs.get("text") or f"{etype} #{handle}"
            canonical_objects.append(
                CanonicalObject(
                    native_guid=entity_key,
                    native_class=etype,
                    native_type=classification.rule_based_category or etype,
                    name=str(obj_name)[:500],
                    parent_guid=parent_guid,
                    root_path=f"DXF/{layout_name or block_name}/{etype}/{handle}",
                    depth=2,
                    is_known_class=is_supported,
                    page_guid=layout_guid_by_name.get(layout_name),
                    properties=props,
                    measurements=measurements,
                    geometries=geoms,
                    provenance=ProvenanceStatus.NATIVE if is_supported else ProvenanceStatus.UNSUPPORTED,
                    raw_attributes={"handle": handle, "owner_handle": owner_handle, "layer": layer_name},
                )
            )
            provenance_records.append(
                ProvenanceRecord(
                    source_system="DXF",
                    source_adapter="dxf_ezdxf",
                    source_file=source_name,
                    source_location=layout_name or block_name,
                    source_object_guid=entity_key,
                    source_class=etype,
                    status=ProvenanceStatus.NATIVE if is_supported else ProvenanceStatus.UNSUPPORTED,
                )
            )

    # Traverse all layouts (Model + Paperspaces) deterministically
    for layout in layout_objs:
        _process_container(layout, layout_name=layout.name, block_name="", is_layout_space=True)

    # Traverse non-layout Block definitions separately (preserving block_name without mixing with modelspace!)
    non_layout_blocks = sorted(
        (b for b in doc.blocks if not getattr(b, "is_any_layout", False)),
        key=lambda b: (b.name or "").lower(),
    )
    for blk in non_layout_blocks:
        _process_container(blk, layout_name="", block_name=blk.name, is_layout_space=False)

    # Deterministic ordering of entities by (layout, block, handle)
    cad_entities.sort(key=lambda e: (e.layout_name, e.block_name, e.handle, e.entity_key))

    return {
        "cad_entities": cad_entities,
        "pages": canonical_pages,
        "objects": canonical_objects,
        "relationships": relationships,
        "provenance_records": provenance_records,
        "discovered_classes": discovered_classes,
        "unsupported_classes": unsupported_classes,
        "unsupported_objects": unsupported_objects,
        "warnings": warnings,
    }
