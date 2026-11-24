"""CSV and Excel (.xlsx) tabular exporters preserving PlanSwift GUIDs and standalone calculations."""

from __future__ import annotations

import csv
from pathlib import Path

from openpyxl import Workbook

from extraction_engine.core.extraction_result import CanonicalProject


def export_takeoff_csv(project: CanonicalProject, output_path: Path) -> Path:
    """Export takeoff objects summary CSV with native GUIDs, formulas, calculated qty, and provenance."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            [
                "project_guid",
                "object_guid",
                "native_class",
                "native_type",
                "name",
                "parent_guid",
                "sections_count",
                "raw_qty_formula",
                "reconstructed_quantity",
                "calculated_quantity",
                "unit",
                "provenance",
            ]
        )
        for obj in project.objects:
            if obj.is_page or obj.is_measurement_section or obj.depth <= 1:
                continue
            qty_m = next((m for m in obj.measurements if m.property_name == "Qty"), None)
            writer.writerow(
                [
                    project.native_guid,
                    obj.native_guid,
                    obj.native_class,
                    obj.native_type,
                    obj.name,
                    obj.parent_guid or "",
                    len(obj.child_guids),
                    qty_m.raw_formula if qty_m else "",
                    qty_m.reconstructed_quantity if qty_m else "",
                    qty_m.calculated_quantity if qty_m else "",
                    qty_m.unit if qty_m else "",
                    qty_m.status.value if qty_m else obj.provenance.value,
                ]
            )
    return output_path


def export_project_excel(project: CanonicalProject, output_path: Path) -> Path:
    """Export multi-sheet Excel workbook (Takeoff Objects, Pages, Sections Geometry, Formulas)."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()

    ws_items = wb.active
    ws_items.title = "Takeoff_Objects"
    ws_items.append(
        [
            "Project GUID",
            "Object GUID",
            "Native Class",
            "Name",
            "Division",
            "Phase",
            "Cost Code",
            "Raw Qty Formula",
            "Reconstructed Qty",
            "Calculated Qty",
            "Unit",
            "Provenance",
        ]
    )
    for obj in project.objects:
        if obj.depth < 2 or obj.is_page or obj.is_measurement_section:
            continue
        qty_m = next((m for m in obj.measurements if m.property_name == "Qty"), None)
        ws_items.append(
            [
                project.native_guid,
                obj.native_guid,
                obj.native_class,
                obj.name,
                obj.division or "",
                obj.phase or "",
                obj.cost_code or "",
                qty_m.raw_formula if qty_m else "",
                qty_m.reconstructed_quantity if qty_m else "",
                qty_m.calculated_quantity if qty_m else "",
                qty_m.unit if qty_m else "",
                qty_m.status.value if qty_m else obj.provenance.value,
            ]
        )

    ws_pages = wb.create_sheet("Pages")
    ws_pages.append(["Page GUID", "Name", "Page Type", "OrderIndex", "ScaleX", "ScaleY", "Scale Units", "TIFF Archive Path", "Section Count"])
    for pg in project.pages:
        ws_pages.append(
            [
                pg.native_guid,
                pg.name,
                pg.page_type,
                pg.order_index,
                pg.scale_x,
                pg.scale_y,
                pg.scale_units or "",
                pg.tiff_archive_path or "",
                pg.section_count,
            ]
        )

    ws_sec = wb.create_sheet("Sections_Geometry")
    ws_sec.append(["Section GUID", "Parent Object GUID", "Class", "Page GUID", "Geometry Type", "Point Count", "Calibrated", "Derived Qty", "Unit", "Provenance"])
    for obj in project.objects:
        for sec in obj.sections:
            ws_sec.append(
                [
                    sec.native_guid,
                    sec.parent_object_guid,
                    sec.native_class,
                    sec.page_guid or "",
                    sec.geometry.geometry_type if sec.geometry else "",
                    sec.point_count,
                    sec.geometry.is_calibrated if sec.geometry else False,
                    sec.derived_quantity,
                    sec.derived_unit or "",
                    sec.provenance.value,
                ]
            )

    ws_form = wb.create_sheet("Formulas")
    ws_form.append(["Object GUID", "Property GUID", "Property Name", "Raw Expression", "PascalScript", "Has Cycle", "Status", "Calculated Value", "Reason"])
    for obj in project.objects:
        for f in obj.formulas:
            ws_form.append(
                [
                    f.object_guid,
                    f.property_guid,
                    f.property_name,
                    f.raw_expression,
                    f.is_pascal_script,
                    f.has_circular_dependency,
                    f.evaluation_status.value,
                    f.calculated_value or "",
                    f.calculation_reason or "",
                ]
            )

    wb.save(output_path)
    return output_path
