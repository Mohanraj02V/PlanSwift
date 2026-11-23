"""Safe static PlanSwift formula analyzer and dependency cycle detector (NEVER executes eval)."""

from __future__ import annotations

import re

from extraction_engine.core.extraction_result import (
    CanonicalFormula,
    CanonicalFormulaDependency,
    CanonicalObject,
    CanonicalProperty,
    ProvenanceStatus,
)

# Matches bracket tokens including nested cross-object references like [[PageGUID]\Name]
_OUTER_TOKEN_RE = re.compile(r"\[((?:[^\[\]]|\[[^\]]*\])*)\]")
_CROSS_GUID_RE = re.compile(r"^\[([^\]]+)\]\\(.+)$")


def parse_property_formula(
    obj_guid: str,
    prop: CanonicalProperty,
) -> CanonicalFormula | None:
    """Analyze a formula or script property statically without executing code."""
    if not prop.is_formula and not prop.is_expression_script:
        return None

    raw = prop.raw_value
    dependencies: list[CanonicalFormulaDependency] = []
    unresolved: list[str] = []

    if prop.is_expression_script:
        dependencies.append(
            CanonicalFormulaDependency(
                raw_token="Expression=-1",
                reference_kind="pascal_script",
                target_property=prop.name or prop.native_property_guid,
                target_object_guid=obj_guid,
                resolved=False,
            )
        )
        # Also detect bracket references inside the PascalScript body safely
        for match in _OUTER_TOKEN_RE.finditer(raw):
            token = f"[{match.group(1)}]"
            dep = _classify_token(token, match.group(1))
            dependencies.append(dep)
            unresolved.append(token)
        if not unresolved:
            unresolved.append("Expression=-1 (PascalScript)")
    else:
        for match in _OUTER_TOKEN_RE.finditer(raw):
            inner = match.group(1)
            token = f"[{inner}]"
            dep = _classify_token(token, inner)
            dependencies.append(dep)
            unresolved.append(token)

    return CanonicalFormula(
        formula_key=f"{obj_guid}:{prop.native_property_guid}",
        object_guid=obj_guid,
        property_guid=prop.native_property_guid,
        property_name=prop.name if prop.name else prop.native_property_guid,
        raw_expression=raw,
        is_pascal_script=prop.is_expression_script,
        parse_formula_attr=prop.parse_formula,
        expression_attr=prop.expression_flag,
        dependencies=dependencies,
        unresolved_references=unresolved,
        evaluation_status=ProvenanceStatus.UNRESOLVED,
    )


def _classify_token(token: str, inner: str) -> CanonicalFormulaDependency:
    if inner == "Takeoff":
        return CanonicalFormulaDependency(
            raw_token=token,
            reference_kind="takeoff_aggregation",
            target_property="Takeoff",
            resolved=False,
        )
    if inner == "..":
        return CanonicalFormulaDependency(
            raw_token=token,
            reference_kind="parent_inheritance",
            resolved=False,
        )
    if inner.startswith("!"):
        return CanonicalFormulaDependency(
            raw_token=token,
            reference_kind="system_variable",
            target_property=inner[1:],
            resolved=False,
        )
    if inner.startswith("\\"):
        return CanonicalFormulaDependency(
            raw_token=token,
            reference_kind="settings_path",
            target_property=inner,
            resolved=False,
        )
    cross_match = _CROSS_GUID_RE.match(inner)
    if cross_match:
        return CanonicalFormulaDependency(
            raw_token=token,
            reference_kind="cross_object_guid_path",
            target_object_guid=cross_match.group(1),
            target_property=cross_match.group(2),
            resolved=False,
        )
    return CanonicalFormulaDependency(
        raw_token=token,
        reference_kind="property_reference",
        target_property=inner,
        resolved=False,
    )


def resolve_formula_graph(objects: list[CanonicalObject]) -> None:
    """Resolve static property reference metadata and detect circular formula dependencies via DFS."""
    obj_by_guid: dict[str, CanonicalObject] = {o.native_guid.upper(): o for o in objects}
    formula_by_node: dict[str, CanonicalFormula] = {}
    adjacency: dict[str, list[str]] = {}

    for obj in objects:
        obj_key = obj.native_guid.upper()
        prop_names = {p.name for p in obj.properties if p.name}
        for formula in obj.formulas:
            node_id = f"{obj_key}::{formula.property_name}"
            formula_by_node[node_id] = formula
            edges: list[str] = []
            unresolved_remaining: list[str] = []

            for dep in formula.dependencies:
                if dep.reference_kind == "parent_inheritance" and obj.parent_guid:
                    parent = obj_by_guid.get(obj.parent_guid.upper())
                    if parent and parent.get_property(formula.property_name) is not None:
                        dep.target_object_guid = parent.native_guid
                        dep.target_property = formula.property_name
                        dep.resolved = True
                        edges.append(f"{parent.native_guid.upper()}::{formula.property_name}")
                        continue
                elif dep.reference_kind == "cross_object_guid_path" and dep.target_object_guid:
                    ref_prop = obj.get_property(dep.target_object_guid)
                    target_guid = ref_prop.raw_value.strip().upper() if ref_prop else dep.target_object_guid.upper()
                    target_obj = obj_by_guid.get(target_guid)
                    if target_obj and dep.target_property and target_obj.get_property(dep.target_property) is not None:
                        dep.target_object_guid = target_obj.native_guid
                        dep.resolved = True
                        edges.append(f"{target_obj.native_guid.upper()}::{dep.target_property}")
                        continue
                elif dep.reference_kind == "property_reference" and dep.target_property in prop_names:
                    dep.target_object_guid = obj.native_guid
                    dep.resolved = True
                    edges.append(f"{obj_key}::{dep.target_property}")
                    continue

                unresolved_remaining.append(dep.raw_token)

            formula.unresolved_references = unresolved_remaining
            adjacency[node_id] = edges

    # DFS cycle detection
    state: dict[str, int] = {}  # 0=unvisited, 1=visiting, 2=done

    def dfs(node: str, stack: list[str]) -> None:
        state[node] = 1
        stack.append(node)
        for nxt in adjacency.get(node, ()):
            st = state.get(nxt, 0)
            if st == 1:
                cycle_start = stack.index(nxt)
                cycle_path = stack[cycle_start:] + [nxt]
                for cyc_node in stack[cycle_start:]:
                    if cyc_node in formula_by_node:
                        formula_by_node[cyc_node].has_circular_dependency = True
                        formula_by_node[cyc_node].circular_path = cycle_path
            elif st == 0 and nxt in adjacency:
                dfs(nxt, stack)
        stack.pop()
        state[node] = 2

    for node_id in list(adjacency.keys()):
        if state.get(node_id, 0) == 0:
            dfs(node_id, [])
