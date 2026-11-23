"""Deterministic SQL-backed estimation generation and approval workflow."""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from apps.estimation.models import EstimationResult, EstimationSession
from apps.object_model.models import ProjectObject
from apps.projects.models import Project


@transaction.atomic
def generate_estimation_session(project: Project, user, session_name: str = "") -> EstimationSession:
    """Build deterministic quantity rollups directly from relational Measurement & ProjectObject rows."""
    version = project.versions.filter(is_current=True).first()
    if version is None:
        raise ValueError("Project has no extracted version yet.")

    session = EstimationSession.objects.create(
        project=project,
        project_version=version,
        name=session_name or f"Native Takeoff Summary (v{version.version_number})",
        status=EstimationSession.Status.DRAFT,
        created_by=user,
    )

    takeoff_objs = (
        ProjectObject.objects.filter(
            project_version=version,
            is_page=False,
            is_measurement_section=False,
            depth__gte=2,
        )
        .prefetch_related("measurements", "child_sections")
        .order_by("native_class", "name")
    )

    results = []
    total_qty_by_class: dict[str, float] = {}
    for obj in takeoff_objs:
        qty_m = next((m for m in obj.measurements.all() if m.property_name == "Qty"), None)
        if qty_m and qty_m.planswift_computed_quantity is not None:
            qty = qty_m.planswift_computed_quantity
            source_status = "computed_by_planswift"
        elif qty_m and qty_m.derived_quantity is not None:
            qty = qty_m.derived_quantity
            source_status = "derived"
        else:
            qty = 0.0
            source_status = "unresolved"

        unit = (qty_m.unit if qty_m else "") or ("EA" if obj.native_class == "Count" else "")
        sec_count = obj.child_sections.count()
        total_qty_by_class[obj.native_class] = total_qty_by_class.get(obj.native_class, 0.0) + qty

        results.append(
            EstimationResult(
                session=session,
                project_object=obj,
                object_guid=obj.native_guid,
                object_name=obj.name,
                native_class=obj.native_class,
                category=obj.division or obj.native_type or obj.native_class,
                quantity=qty,
                unit=unit,
                source_status=source_status,
                formula_raw=(qty_m.raw_formula or qty_m.native_stored_value) if qty_m else "",
                section_count=sec_count,
                notes=qty_m.notes if qty_m else "",
            )
        )

    EstimationResult.objects.bulk_create(results, batch_size=500)
    session.summary_json = {
        "total_items": len(results),
        "total_quantity_by_class": total_qty_by_class,
        "unresolved_items": sum(1 for r in results if r.source_status == "unresolved"),
    }
    session.save(update_fields=["summary_json"])
    return session


def approve_estimation_session(session: EstimationSession, user) -> EstimationSession:
    session.status = EstimationSession.Status.APPROVED
    session.approved_by = user
    session.approved_at = timezone.now()
    session.save(update_fields=["status", "approved_by", "approved_at"])
    return session
