"""Merge COM-extracted runtime values into a native CanonicalProject without overwriting original data."""

from __future__ import annotations

from typing import Any

from extraction_engine.core.extraction_result import CanonicalProject, ProvenanceStatus
from extraction_engine.normalizers.identity_normalizer import canonical_guid_key
from extraction_engine.reconciliation.duplicate_detection import detect_duplicate_guids_and_names
from extraction_engine.reconciliation.field_comparison import FieldDiff, compare_object_fields


def reconcile_package_and_com(
    package_project: CanonicalProject,
    com_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    """Reconcile native package CanonicalProject with optional Windows COM connector output."""
    dup_report = detect_duplicate_guids_and_names(package_project)
    if not com_payload:
        return {
            "mode": "package_only",
            "com_available": False,
            "duplicate_detection": dup_report,
            "matched_objects": 0,
            "package_only_objects": len(package_project.objects),
            "com_only_objects": 0,
            "computed_values_applied": 0,
            "diffs_sample": [],
        }

    pkg_by_guid = {canonical_guid_key(o.native_guid): o for o in package_project.objects}
    com_objects = com_payload.get("objects", [])
    com_by_guid = {canonical_guid_key(o.get("native_guid", "")): o for o in com_objects if o.get("native_guid")}

    matched = 0
    computed_applied = 0
    all_diffs: list[FieldDiff] = []

    for guid_key, pkg_obj in pkg_by_guid.items():
        com_obj = com_by_guid.get(guid_key)
        if com_obj is None:
            continue
        matched += 1
        pkg_props = pkg_obj.properties_dict()
        com_props = com_obj.get("properties", {})
        all_diffs.extend(compare_object_fields(pkg_obj.native_guid, pkg_props, com_props))

        # Apply COM-computed Qty / formula evaluations onto CanonicalFormula & CanonicalMeasurement WITHOUT replacing raw formula
        for formula in pkg_obj.formulas:
            com_prop_entry = com_props.get(formula.property_name)
            if com_prop_entry and com_prop_entry.get("result") not in (None, ""):
                formula.planswift_evaluated_value = str(com_prop_entry["result"])
                formula.evaluation_status = ProvenanceStatus.COMPUTED_BY_PLANSWIFT
                computed_applied += 1

        qty_entry = com_props.get("Qty")
        if qty_entry and qty_entry.get("result") not in (None, ""):
            try:
                qty_val = float(qty_entry["result"])
                for meas in pkg_obj.measurements:
                    if meas.property_name == "Qty":
                        meas.planswift_computed_quantity = qty_val
                        meas.status = ProvenanceStatus.COMPUTED_BY_PLANSWIFT
                        computed_applied += 1
            except (TypeError, ValueError):
                pass

    pkg_only = len(set(pkg_by_guid.keys()) - set(com_by_guid.keys()))
    com_only = len(set(com_by_guid.keys()) - set(pkg_by_guid.keys()))
    diff_counts: dict[str, int] = {}
    for d in all_diffs:
        diff_counts[d.diff_kind] = diff_counts.get(d.diff_kind, 0) + 1

    return {
        "mode": "package_and_com_reconciled",
        "com_available": True,
        "com_planswift_version": com_payload.get("planswift_version"),
        "com_progid": com_payload.get("prog_id"),
        "duplicate_detection": dup_report,
        "matched_objects": matched,
        "package_only_objects": pkg_only,
        "com_only_objects": com_only,
        "computed_values_applied": computed_applied,
        "field_diff_counts": diff_counts,
        "diffs_sample": [d.model_dump() for d in all_diffs[:50]],
    }
