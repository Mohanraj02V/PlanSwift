"""Standalone self-reconciliation and cross-consistency checker (replaces COM reconciliation)."""

from __future__ import annotations

from typing import Any

from extraction_engine.core.extraction_result import CanonicalProject, ProvenanceStatus
from extraction_engine.reconciliation.duplicate_detection import detect_duplicate_guids_and_names


def reconcile_standalone_project(package_project: CanonicalProject) -> dict[str, Any]:
    """Validate internal consistency across parsed XML objects, calibrated geometry, formulas, and quantities."""
    dup_report = detect_duplicate_guids_and_names(package_project)

    formulas = [f for o in package_project.objects for f in o.formulas]
    calculated_formulas = sum(1 for f in formulas if f.evaluation_status == ProvenanceStatus.CALCULATED)
    unresolved_formulas = sum(1 for f in formulas if f.evaluation_status == ProvenanceStatus.UNRESOLVED)
    unsupported_formulas = sum(1 for f in formulas if f.evaluation_status == ProvenanceStatus.UNSUPPORTED)

    geoms = [g for o in package_project.objects for g in o.geometries]
    calibrated_geoms = sum(1 for g in geoms if g.is_calibrated)

    reconstructed_meas = 0
    calculated_meas = 0
    discrepancies: list[dict[str, Any]] = []

    for obj in package_project.objects:
        for m in obj.measurements:
            if m.reconstructed_quantity is not None:
                reconstructed_meas += 1
            if m.calculated_quantity is not None:
                calculated_meas += 1
            if (
                m.property_name == "Qty"
                and m.calculated_quantity is not None
                and m.reconstructed_quantity is not None
                and m.raw_formula in ("[Takeoff]", "[Area]", "[Linear Total]")
            ):
                diff = abs(m.calculated_quantity - m.reconstructed_quantity)
                tol = max(1e-4, 0.01 * max(abs(m.calculated_quantity), abs(m.reconstructed_quantity)))
                if diff > tol:
                    discrepancies.append(
                        {
                            "object_guid": obj.native_guid,
                            "object_name": obj.name,
                            "property_name": m.property_name,
                            "calculated_quantity": m.calculated_quantity,
                            "reconstructed_quantity": m.reconstructed_quantity,
                            "difference": round(diff, 6),
                        }
                    )

    return {
        "mode": "standalone_zip_verified",
        "com_available": False,
        "duplicate_detection": dup_report,
        "matched_objects": len(package_project.objects),
        "package_only_objects": len(package_project.objects),
        "com_only_objects": 0,
        "computed_values_applied": calculated_formulas + calculated_meas,
        "formulas_total": len(formulas),
        "formulas_calculated": calculated_formulas,
        "formulas_unresolved": unresolved_formulas,
        "formulas_unsupported": unsupported_formulas,
        "geometries_calibrated": calibrated_geoms,
        "geometries_total": len(geoms),
        "measurements_calculated": calculated_meas,
        "measurements_reconstructed": reconstructed_meas,
        "discrepancy_count": len(discrepancies),
        "diffs_sample": discrepancies[:50],
    }
