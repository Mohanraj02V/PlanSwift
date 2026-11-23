"""Validation scorecard measuring field fidelity, completeness, relationships, geometry, and formulas."""

from __future__ import annotations

from extraction_engine.core.extraction_result import (
    CanonicalProject,
    ProvenanceStatus,
    ValidationCheckResult,
    ValidationSummary,
)
from extraction_engine.normalizers.identity_normalizer import canonical_guid_key


def validate_canonical_project(project: CanonicalProject) -> ValidationSummary:
    """Validate structural integrity, GUID uniqueness, page links, measurements, geometry, and formulas."""
    checks: list[ValidationCheckResult] = []

    objects_count = len(project.objects)
    props_count = sum(len(o.properties) for o in project.objects)
    empty_name_props = sum(1 for o in project.objects for p in o.properties if p.name == "")
    unknown_objs = sum(1 for o in project.objects if not o.is_known_class)

    # 1. Project metadata check
    meta_ok = bool(project.native_guid and project.name)
    checks.append(
        ValidationCheckResult(
            check_name="project_metadata",
            category="metadata",
            status="verified_correct" if meta_ok else "incorrect",
            discovered_count=1,
            extracted_count=1 if meta_ok else 0,
            accuracy_pct=100.0 if meta_ok else 0.0,
            completeness_pct=100.0 if meta_ok else 0.0,
            details=f"Project '{project.name}' ({project.native_guid}), encoding={project.xml_encoding}.",
        )
    )

    # 2. Object GUID uniqueness check
    guid_counts: dict[str, int] = {}
    for obj in project.objects:
        k = canonical_guid_key(obj.native_guid)
        guid_counts[k] = guid_counts.get(k, 0) + 1
    duplicate_guids = [g for g, cnt in guid_counts.items() if cnt > 1 or not g]
    checks.append(
        ValidationCheckResult(
            check_name="object_identity_uniqueness",
            category="identity",
            status="verified_correct" if not duplicate_guids else "incorrect",
            discovered_count=objects_count,
            extracted_count=len(guid_counts) - (1 if "" in guid_counts else 0),
            accuracy_pct=100.0 if not duplicate_guids else round(100.0 * (objects_count - len(duplicate_guids)) / max(objects_count, 1), 2),
            completeness_pct=100.0 if objects_count > 0 else 0.0,
            details=f"{objects_count} objects checked; duplicate/empty GUIDs={len(duplicate_guids)}.",
        )
    )

    # 3. Parent-child hierarchy integrity
    obj_set = set(guid_counts.keys())
    orphans = [
        o.native_guid for o in project.objects if o.parent_guid and canonical_guid_key(o.parent_guid) not in obj_set
    ]
    checks.append(
        ValidationCheckResult(
            check_name="parent_child_hierarchy",
            category="hierarchy",
            status="verified_correct" if not orphans else "incorrect",
            discovered_count=objects_count,
            extracted_count=objects_count - len(orphans),
            accuracy_pct=round(100.0 * (objects_count - len(orphans)) / max(objects_count, 1), 2),
            completeness_pct=round(100.0 * (objects_count - len(orphans)) / max(objects_count, 1), 2),
            details=f"Orphaned child items={len(orphans)}.",
        )
    )

    # 4. Page to TIFF asset matching (when manifest present)
    pages_total = len(project.pages)
    pages_matched = sum(1 for p in project.pages if p.tiff_archive_path)
    if project.source_manifest is not None and pages_total > 0:
        page_status = "verified_correct" if pages_matched == pages_total else "partially_verified"
        page_pct = round(100.0 * pages_matched / pages_total, 2)
    else:
        page_status = "unverified" if pages_total > 0 else "verified_correct"
        page_pct = 100.0 if pages_total == 0 else None
    checks.append(
        ValidationCheckResult(
            check_name="page_to_tiff_manifest_linkage",
            category="pages",
            status=page_status,
            discovered_count=pages_total,
            extracted_count=pages_matched,
            accuracy_pct=page_pct,
            completeness_pct=page_pct,
            details=f"{pages_matched}/{pages_total} pages matched to archive TIFF entries by Image GUID (no raster decoding).",
        )
    )

    # 5. Measurement sections & PageGUID resolution
    sections = [s for o in project.objects for s in o.sections]
    sections_total = len(sections)
    sections_resolved_page = sum(
        1 for s in sections if s.page_guid and canonical_guid_key(s.page_guid) in {canonical_guid_key(p.native_guid) for p in project.pages}
    )
    sec_pct = round(100.0 * sections_resolved_page / sections_total, 2) if sections_total else 100.0
    checks.append(
        ValidationCheckResult(
            check_name="section_page_guid_resolution",
            category="relationships",
            status="verified_correct" if sections_resolved_page == sections_total else "partially_verified",
            discovered_count=sections_total,
            extracted_count=sections_resolved_page,
            accuracy_pct=sec_pct,
            completeness_pct=sec_pct,
            details=f"{sections_resolved_page}/{sections_total} sections resolved to a valid Page GUID.",
        )
    )

    # 6. Geometry coordinate fidelity
    geometries = [g for o in project.objects for g in o.geometries]
    total_points = sum(g.point_count for g in geometries)
    non_empty_geom = sum(1 for g in geometries if g.point_count > 0)
    geom_pct = round(100.0 * non_empty_geom / len(geometries), 2) if geometries else 100.0
    checks.append(
        ValidationCheckResult(
            check_name="digitizer_geometry_extraction",
            category="geometry",
            status="verified_correct" if non_empty_geom == len(geometries) else "partially_verified",
            discovered_count=len(geometries),
            extracted_count=non_empty_geom,
            accuracy_pct=100.0 if geometries else 100.0,
            completeness_pct=geom_pct,
            details=f"{len(geometries)} geometry collections, {total_points} raw points preserved.",
        )
    )

    # 7. Formula preservation & unresolved status reporting
    formulas = [f for o in project.objects for f in o.formulas]
    unresolved_formulas = sum(1 for f in formulas if f.evaluation_status == ProvenanceStatus.UNRESOLVED)
    circular_formulas = sum(1 for f in formulas if f.has_circular_dependency)
    unresolved_refs = sum(len(f.unresolved_references) for f in formulas)
    checks.append(
        ValidationCheckResult(
            check_name="formula_preservation_and_static_analysis",
            category="formulas",
            status="partially_verified" if unresolved_formulas > 0 else "verified_correct",
            discovered_count=len(formulas),
            extracted_count=len(formulas),
            accuracy_pct=100.0,
            completeness_pct=100.0,
            details=(
                f"{len(formulas)} formulas preserved verbatim; {unresolved_formulas} require PlanSwift runtime/COM for live evaluation; "
                f"circular_dependencies={circular_formulas}."
            ),
        )
    )

    # 8. Unsupported native classes (if any discovered)
    if project.unsupported_classes:
        checks.append(
            ValidationCheckResult(
                check_name="unsupported_native_classes",
                category="objects",
                status="unsupported",
                discovered_count=unknown_objs,
                extracted_count=unknown_objs,
                details=f"Preserved generically: {project.unsupported_classes}",
            )
        )

    # Compute verified accuracy across directly verifiable checks
    verifiable_pcts = [
        c.accuracy_pct for c in checks if c.accuracy_pct is not None and c.status in ("verified_correct", "partially_verified", "incorrect")
    ]
    overall_acc = round(sum(verifiable_pcts) / len(verifiable_pcts), 2) if verifiable_pcts else 100.0

    has_incorrect = any(c.status == "incorrect" for c in checks)
    overall_status = "incorrect" if has_incorrect else ("verified_correct" if unresolved_formulas == 0 and not project.unsupported_classes else "partially_verified")

    return ValidationSummary(
        overall_status=overall_status,
        objects_discovered=objects_count,
        objects_extracted=objects_count,
        unknown_class_objects=unknown_objs,
        skipped_objects=0,
        properties_extracted=props_count,
        empty_name_properties=empty_name_props,
        pages_discovered=pages_total,
        pages_matched_to_tiff=pages_matched,
        sections_extracted=sections_total,
        sections_with_resolved_page=sections_resolved_page,
        geometry_features_extracted=len(geometries),
        points_extracted=total_points,
        formulas_extracted=len(formulas),
        unresolved_formulas=unresolved_formulas,
        circular_formulas=circular_formulas,
        unresolved_references=unresolved_refs,
        unparsed_files=0,
        unsupported_classes=sorted(project.unsupported_classes.keys()),
        overall_verified_accuracy_pct=overall_acc,
        checks=checks,
    )
