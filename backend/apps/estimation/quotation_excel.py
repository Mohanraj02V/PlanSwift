"""Multi-sheet Excel quotation & takeoff workbook generator for EstimationSession."""

from __future__ import annotations

import io
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from apps.estimation.quotation_pdf import _normalize_lines, default_quotation_metadata


def generate_estimation_excel_workbook(session, meta_override: dict[str, Any] | None = None) -> bytes:
    """Create a structured 3-sheet .xlsx workbook (Quotation BOQ, Takeoff Details, Terms & Conditions)."""
    meta = default_quotation_metadata(session)
    if meta_override:
        for k, v in meta_override.items():
            if v is not None and v != "":
                meta[k] = v

    currency = str(meta.get("currency") or "AED").strip()
    rate_label = str(meta.get("rate_column_label") or f"Rate ({currency})")
    vat_pct = float(meta.get("vat_percent") if meta.get("vat_percent") is not None else 5.0)

    wb = Workbook()
    ws = wb.active
    ws.title = "Quotation BOQ"

    thin = Side(border_style="thin", color="1E293B")
    border_all = Border(left=thin, right=thin, top=thin, bottom=thin)
    hdr_fill = PatternFill(start_color="17468C", end_color="17468C", fill_type="solid")
    sub_fill = PatternFill(start_color="EFF6FF", end_color="EFF6FF", fill_type="solid")
    font_title = Font(name="Calibri", size=14, bold=True, color="17468C")
    font_sub = Font(name="Calibri", size=10, bold=True, color="334155")
    font_hdr = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
    font_bold = Font(name="Calibri", size=10, bold=True, color="0F172A")

    ws["A1"] = "VORTEXEN DYNAMICS INDUSTRIAL SOLUTIONS"
    ws["A1"].font = font_title
    ws["A2"] = f"Reference: {meta.get('reference', '')}   |   Date: {meta.get('date', '')}"
    ws["A2"].font = font_sub
    ws["A3"] = f"To: {meta.get('to_client', '')}   |   Contact: {meta.get('contact_person', '')} {meta.get('contact_number', '')}"
    ws["A4"] = f"Location: {meta.get('project_location', '')}"
    ws["A5"] = f"Subject: {meta.get('subject', '')}"
    ws["A5"].font = font_bold

    row_idx = 7
    headers = ["SL : NO", "Description", "Qty", "Unit", rate_label, f"Total Amount ({currency})"]
    for col_i, h in enumerate(headers, start=1):
        cell = ws.cell(row=row_idx, column=col_i, value=h)
        cell.font = font_hdr
        cell.fill = hdr_fill
        cell.border = border_all
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    results = [r for r in session.results.all() if (getattr(r, "native_class", "") or "").strip().lower() != "folder"]
    first_data_row = row_idx + 1
    for i, r in enumerate(results, start=1):
        cur_row = row_idx + i
        qty = float(r.quantity or 0.0)
        rate = float(r.unit_cost) if r.unit_cost is not None else 0.0

        vals = [
            f"A.{i}",
            r.object_name or r.native_class,
            qty,
            r.unit or "",
            rate,
            f"=C{cur_row}*E{cur_row}",
        ]
        for col_i, val in enumerate(vals, start=1):
            c = ws.cell(row=cur_row, column=col_i, value=val)
            c.border = border_all
            c.alignment = Alignment(
                horizontal="center" if col_i in (1, 4) else ("right" if col_i in (3, 5, 6) else "left"),
                vertical="center",
            )
            if col_i in (3, 5, 6):
                c.number_format = "#,##0.00"

    last_data_row = max(first_data_row, row_idx + len(results))
    sub_row = last_data_row + 2
    vat_row = sub_row + 1
    grand_row = sub_row + 2

    ws.cell(row=sub_row, column=3, value="Total Amount (As Discussed)").font = font_bold
    c_sub = ws.cell(row=sub_row, column=6, value=f"=SUM(F{first_data_row}:F{last_data_row})" if results else 0.0)
    c_sub.font = font_bold
    c_sub.number_format = "#,##0.00"
    c_sub.fill = sub_fill

    ws.cell(row=vat_row, column=3, value=f"VAT {vat_pct:g}%").font = font_bold
    c_vat = ws.cell(row=vat_row, column=6, value=f"=F{sub_row}*{vat_pct / 100.0}")
    c_vat.font = font_bold
    c_vat.number_format = "#,##0.00"

    ws.cell(row=grand_row, column=3, value="Total Amount with VAT").font = font_bold
    c_grand = ws.cell(row=grand_row, column=6, value=f"=F{sub_row}+F{vat_row}")
    c_grand.font = font_bold
    c_grand.number_format = "#,##0.00"
    c_grand.fill = sub_fill

    for col_i, w in enumerate((10, 44, 12, 10, 18, 20), start=1):
        ws.column_dimensions[get_column_letter(col_i)].width = w

    # Sheet 2: Full Takeoff Details
    ws2 = wb.create_sheet("Takeoff Details")
    det_headers = ["Object GUID", "Object Name", "Class", "Category", "Sections", "Quantity", "Unit", "Unit Rate", "Total", "Provenance", "Formula"]
    for col_i, h in enumerate(det_headers, start=1):
        c = ws2.cell(row=1, column=col_i, value=h)
        c.font = font_hdr
        c.fill = hdr_fill
    for r_idx, r in enumerate(results, start=2):
        rate = float(r.unit_cost) if r.unit_cost is not None else 0.0
        tot = float(r.total_cost) if r.total_cost is not None else round(float(r.quantity or 0.0) * rate, 2)
        row_vals = [
            r.object_guid,
            r.object_name,
            r.native_class,
            r.category,
            r.section_count,
            float(r.quantity or 0.0),
            r.unit,
            rate,
            tot,
            r.source_status,
            r.formula_raw,
        ]
        for col_i, val in enumerate(row_vals, start=1):
            ws2.cell(row=r_idx, column=col_i, value=val)
    for col_i in range(1, len(det_headers) + 1):
        ws2.column_dimensions[get_column_letter(col_i)].width = 18

    # Sheet 3: Terms & Conditions
    ws3 = wb.create_sheet("Terms & Conditions")
    ws3["A1"] = "Section"
    ws3["B1"] = "Details"
    ws3["A1"].font = font_bold
    ws3["B1"].font = font_bold
    t_row = 2
    for title, items in (
        ("Contract Period", _normalize_lines(meta.get("contract_period"))),
        ("Validity", _normalize_lines(meta.get("validity"))),
        ("General Notes", _normalize_lines(meta.get("general_notes"))),
        ("Payment Terms", _normalize_lines(meta.get("payment_terms"))),
        ("Scope of Work", _normalize_lines(meta.get("scope_includes"))),
        ("Exclusions", _normalize_lines(meta.get("exclusions"))),
        ("Terms & Conditions", _normalize_lines(meta.get("terms_conditions"))),
    ):
        for item in items:
            ws3.cell(row=t_row, column=1, value=title)
            ws3.cell(row=t_row, column=2, value=str(item))
            t_row += 1
    ws3.column_dimensions["A"].width = 22
    ws3.column_dimensions["B"].width = 95

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
