"""Relationship graph builder preserving parent-child, PageGUID, OrderIndex_{PageGUID}, GroupId, SwiftExcel, and Assembly edges."""

from __future__ import annotations

from extraction_engine.core.extraction_result import (
    CanonicalAssembly,
    CanonicalAssemblyComponent,
    CanonicalObject,
    CanonicalProject,
    CanonicalRelationship,
    ProvenanceStatus,
)


_COMPONENT_TYPES = frozenset({"material", "labor", "equipment", "subcontract", "part", "component"})
_COMPONENT_CLASSES = frozenset({"part", "component"})
_TAKEOFF_ASSEMBLY_CLASSES = frozenset({"linear", "area", "count", "segment", "volume", "perimeter", "item"})


def build_relationships_and_assemblies(project: CanonicalProject) -> None:
    """Populate CanonicalProject.relationships and CanonicalProject.assemblies deterministically."""
    relationships: list[CanonicalRelationship] = []
    seen_keys: set[str] = set()
    obj_by_guid: dict[str, CanonicalObject] = {o.native_guid.upper(): o for o in project.objects}

    def add_rel(rel: CanonicalRelationship) -> None:
        if rel.relationship_key not in seen_keys:
            seen_keys.add(rel.relationship_key)
            relationships.append(rel)

    for obj in project.objects:
        # 1. Parent -> Child (preserving child OrderIndex)
        if obj.parent_guid:
            add_rel(
                CanonicalRelationship(
                    relationship_key=f"parent_child:{obj.parent_guid}>{obj.native_guid}",
                    relationship_type="parent_child",
                    source_guid=obj.parent_guid,
                    target_guid=obj.native_guid,
                    order_index=obj.order_index,
                    metadata={"child_class": obj.native_class, "child_name": obj.name},
                    provenance=ProvenanceStatus.NATIVE,
                )
            )

        # 2. Section / Object -> Page via PageGUID
        if obj.page_guid:
            add_rel(
                CanonicalRelationship(
                    relationship_key=f"page_reference:{obj.native_guid}>{obj.page_guid}",
                    relationship_type="page_reference",
                    source_guid=obj.native_guid,
                    target_guid=obj.page_guid,
                    order_index=obj.order_index,
                    metadata={"target_exists": obj.page_guid.upper() in obj_by_guid},
                    provenance=ProvenanceStatus.NATIVE,
                )
            )

        # 3. Dynamic per-page ordering OrderIndex_{PAGE-GUID}
        for prop in obj.properties:
            if prop.is_dynamic_page_order and prop.dynamic_page_guid:
                page_order_val = prop.parsed_value if isinstance(prop.parsed_value, int) else None
                add_rel(
                    CanonicalRelationship(
                        relationship_key=f"page_order:{obj.native_guid}>{prop.dynamic_page_guid}",
                        relationship_type="page_order",
                        source_guid=obj.native_guid,
                        target_guid=prop.dynamic_page_guid,
                        order_index=page_order_val,
                        metadata={"property_name": prop.name, "raw_value": prop.raw_value},
                        provenance=ProvenanceStatus.NATIVE,
                    )
                )

        # 4. GroupId membership
        if obj.group_id:
            add_rel(
                CanonicalRelationship(
                    relationship_key=f"group_member:{obj.native_guid}>{obj.group_id}",
                    relationship_type="group_member",
                    source_guid=obj.native_guid,
                    target_guid=obj.group_id,
                    provenance=ProvenanceStatus.NATIVE,
                )
            )

        # 5. SwiftExcel token denotations
        for den in obj.denotations:
            if den.kind == "swift_excel_token":
                add_rel(
                    CanonicalRelationship(
                        relationship_key=f"swift_excel_link:{obj.native_guid}>{den.value}",
                        relationship_type="swift_excel_link",
                        source_guid=obj.native_guid,
                        target_guid=den.value,
                        metadata=den.metadata,
                        provenance=ProvenanceStatus.NATIVE,
                    )
                )

    # 6. Native Assemblies and Components (both explicit Assembly class and Takeoff parents with Material/Labor/Part children)
    assemblies: list[CanonicalAssembly] = []
    for obj in project.objects:
        cls_low = obj.native_class.lower()
        is_explicit_assembly = cls_low == "assembly"
        if not is_explicit_assembly and not (not obj.is_measurement_section and cls_low in _TAKEOFF_ASSEMBLY_CLASSES):
            continue

        components: list[CanonicalAssemblyComponent] = []
        for child_guid in obj.child_guids:
            child = obj_by_guid.get(child_guid.upper())
            if child is None:
                continue
            if not is_explicit_assembly:
                if child.is_measurement_section:
                    continue
                is_component = (
                    child.native_type.lower() in _COMPONENT_TYPES
                    or child.native_class.lower() in _COMPONENT_CLASSES
                )
                if not is_component:
                    continue

            qty_prop = child.get_property("Qty")
            cost_prop = child.get_property("Cost Each")
            unit_str = (qty_prop.units or qty_prop.input_units) if qty_prop else None
            components.append(
                CanonicalAssemblyComponent(
                    native_guid=child.native_guid,
                    assembly_guid=obj.native_guid,
                    name=child.name,
                    native_class=child.native_class,
                    quantity_raw=qty_prop.raw_value if qty_prop else None,
                    unit=unit_str,
                    cost_each_raw=cost_prop.raw_value if cost_prop else None,
                    provenance=ProvenanceStatus.NATIVE,
                )
            )
            add_rel(
                CanonicalRelationship(
                    relationship_key=f"assembly_component:{obj.native_guid}>{child.native_guid}",
                    relationship_type="assembly_component",
                    source_guid=obj.native_guid,
                    target_guid=child.native_guid,
                    order_index=child.order_index,
                    provenance=ProvenanceStatus.NATIVE,
                )
            )

        if is_explicit_assembly or components:
            assemblies.append(
                CanonicalAssembly(
                    native_guid=obj.native_guid,
                    name=obj.name,
                    native_class=obj.native_class,
                    assembly_type=obj.native_type or obj.native_class or None,
                    components=components,
                    provenance=ProvenanceStatus.NATIVE,
                )
            )

    project.relationships = relationships
    project.assemblies = assemblies
