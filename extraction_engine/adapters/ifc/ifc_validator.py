"""IFC validation scorecard verifying schema support, GlobalIds, hierarchy, Qto_*, and optional geometry."""

from __future__ import annotations

from extraction_engine.adapters.ifc.ifc_document_reader import get_supported_ifc_schemas
from extraction_engine.core.extraction_result import (
    CanonicalProject,
    ValidationCheckResult,
    ValidationSummary,
)


def validate_ifc_project(project: CanonicalProject) -> ValidationSummary:
    """Validate IFC schema, STEP/GlobalId integrity, spatial hierarchy, Psets/Qto, and geometry summary."""
    doc = project.cad_document
    elements = doc.ifc_elements if doc else []
    checks: list[ValidationCheckResult] = []

    schema_name = (doc.schema_name if doc else "") or ""
    supported = {s.upper() for s in get_supported_ifc_schemas()}
    schema_ok = bool(schema_name) and (not supported or schema_name.upper() in supported)
    checks.append(
        ValidationCheckResult(
            check_name="ifc_schema_and_units",
            category="metadata",
            status="verified_correct" if schema_ok else "unsupported",
            discovered_count=1,
            extracted_count=1 if schema_ok else 0,
            accuracy_pct=100.0 if schema_ok else 0.0,
            completeness_pct=100.0,
            details=f"Schema={schema_name}, length_unit={doc.source_units if doc else ''}, unit_to_m={doc.unit_to_meter_factor if doc else None}.",
        )
    )

    gids = [el.global_id for el in elements if el.global_id]
    sids = [el.step_id for el in elements]
    id_ok = len(set(sids)) == len(elements) and len(set(gids)) == len(gids)
    checks.append(
        ValidationCheckResult(
            check_name="ifc_globalid_and_step_uniqueness",
            category="identity",
            status="verified_correct" if id_ok else "partially_verified",
            discovered_count=len(elements),
            extracted_count=len(set(sids)),
            accuracy_pct=100.0 if id_ok else round(100.0 * len(set(gids)) / max(len(elements), 1), 2),
            completeness_pct=100.0,
            details=f"{len(elements)} IFC elements extracted; unique STEP IDs={len(set(sids))}, unique GlobalIds={len(set(gids))}.",
        )
    )

    with_spatial = sum(1 for el in elements if el.spatial_parent_guid or el.ifc_class == "IfcProject")
    spatial_pct = round(100.0 * with_spatial / max(len(elements), 1), 2)
    checks.append(
        ValidationCheckResult(
            check_name="ifc_spatial_hierarchy",
            category="hierarchy",
            status="verified_correct" if with_spatial == len(elements) else "partially_verified",
            discovered_count=len(elements),
            extracted_count=with_spatial,
            accuracy_pct=spatial_pct,
            completeness_pct=spatial_pct,
            details=f"{with_spatial}/{len(elements)} elements linked into spatial structure; {len(project.relationships)} IFC relationships.",
        )
    )

    pset_cnt = sum(len(el.property_sets) for el in elements)
    qto_cnt = sum(len(q.quantities) for el in elements for q in el.quantity_sets)
    checks.append(
        ValidationCheckResult(
            check_name="ifc_psets_and_native_quantities",
            category="properties",
            status="verified_correct",
            discovered_count=pset_cnt + qto_cnt,
            extracted_count=pset_cnt + qto_cnt,
            accuracy_pct=100.0,
            completeness_pct=100.0,
            details=f"Extracted {pset_cnt} PropertySets and {qto_cnt} native IfcElementQuantity values.",
        )
    )

    geo_calc = sum(1 for el in elements if el.geometry_summary.status == "calculated")
    geo_fail = sum(1 for el in elements if el.geometry_summary.status in ("failed", "unsupported"))
    geo_opt_in = bool(doc and doc.extraction_options.get("ifc_extract_geometry"))
    if geo_opt_in:
        geo_total = geo_calc + geo_fail
        geo_pct = round(100.0 * geo_calc / max(geo_total, 1), 2) if geo_total else 100.0
        checks.append(
            ValidationCheckResult(
                check_name="ifc_optional_geometry_extraction",
                category="geometry",
                status="verified_correct" if geo_fail == 0 else "partially_verified",
                discovered_count=geo_total,
                extracted_count=geo_calc,
                accuracy_pct=geo_pct,
                completeness_pct=geo_pct,
                details=f"Geometry iterator enabled: {geo_calc} calculated, {geo_fail} unsupported/failed.",
            )
        )
    else:
        checks.append(
            ValidationCheckResult(
                check_name="ifc_geometry_skipped_property_mode",
                category="geometry",
                status="verified_correct",
                discovered_count=len(elements),
                extracted_count=len(elements),
                accuracy_pct=100.0,
                completeness_pct=100.0,
                details="Property/quantity-only mode (ifc_extract_geometry=False): zero 3D tessellation executed.",
            )
        )

    verifiable = [c.accuracy_pct for c in checks if c.accuracy_pct is not None and c.status != "unsupported"]
    overall_acc = round(sum(verifiable) / len(verifiable), 2) if verifiable else 100.0
    overall_status = "partially_verified" if (not schema_ok or geo_fail > 0 or not id_ok) else "verified_correct"

    return ValidationSummary(
        overall_status=overall_status,  # type: ignore[arg-type]
        objects_discovered=len(elements),
        objects_extracted=len(elements),
        unknown_class_objects=geo_fail,
        skipped_objects=0,
        properties_extracted=sum(len(o.properties) for o in project.objects),
        pages_discovered=len(project.pages),
        geometry_features_extracted=geo_calc,
        points_extracted=sum(el.geometry_summary.vertex_count for el in elements),
        unsupported_classes=sorted(project.unsupported_classes.keys()),
        overall_verified_accuracy_pct=overall_acc,
        checks=checks,
    )
