"""Dynamic, auto-paginating Vector PDF Quotation generator matching Vortexen Dynamics Industrial Solutions."""

from __future__ import annotations

import io
from datetime import datetime, timezone
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

DEFAULT_GENERAL_NOTES = [
    "Any additional scope will be considered a variation.",
    "Unforeseen issues revealed during work will be quoted separately.",
    "Commencement of the job will be expedited upon official order confirmation, advance payment, mandatory approvals, and approval of UL System or Engineering Judgement.",
]

DEFAULT_PAYMENT_TERMS = [
    "80% Advance Payment as CDC/cash.",
    "1 Year Warranty will be provided by the Applicator / Vortexen.",
    "Re-Measurable Contract.",
]

DEFAULT_TERMS_AND_CONDITIONS = [
    "Products and services are subject to the terms and conditions outlined by Vortexen Dynamics Industrial Solution - sole proprietorship LLC.",
    "Estimates include all applicable taxes based on current provisions; any changes will be applied as per prevailing laws.",
    "Payments to be made in favor of Vortexen - Dynamics Industrial Solution - sole proprietorship LLC.",
    "This quote is based on client-provided requirements; any changes in the scope will require re-Quotation.",
    "MEP and Civil defense-related works are excluded from our offer.",
    "Electricity and water charges at the site are to be borne by the client.",
    "Agency/Authority approvals, site access passes, and third-party fees are the responsibility of the client.",
    "Pricing for Rectification/reinstalling from both sides of the wall.",
    "Scaffolding or A-Ladder provided by Client, including removal of cable trays cover.",
    "Cable Tray Cover will be removed by the client.",
    "All the above items are passing through concrete/block wall/assembly.",
]


def _normalize_lines(val: Any) -> list[str]:
    if isinstance(val, list):
        return [str(x).strip() for x in val if str(x).strip()]
    if isinstance(val, str):
        return [ln.lstrip("-• ").strip() for ln in val.splitlines() if ln.strip()]
    return []


def default_quotation_metadata(session) -> dict[str, Any]:
    """Return structured Vortexen quotation defaults merged cleanly with saved overrides."""
    saved = dict((session.summary_json or {}).get("quotation") or {})
    project_name = getattr(session.project, "name", "") or "Project"
    today_str = datetime.now(timezone.utc).strftime("%d-%m-%Y")
    short_id = str(session.id).split("-")[0].upper()
    year_str = datetime.now(timezone.utc).strftime("%Y")

    defaults: dict[str, Any] = {
        "date": today_str,
        "reference": f"VDIS/FM/{year_str}/{short_id}",
        "to_client": project_name,
        "contact_person": "",
        "contact_number": "",
        "project_location": project_name,
        "subject": f"Commercial Quotation for {project_name} ({session.name})",
        "intro_text": (
            "We appreciate the opportunity to submit our quotation based on the extracted "
            "Bill of Quantities (BOQ). Our offer is presented below:"
        ),
        "contract_period": "The contract period will be determined based on the quantity and site clearance.",
        "currency": "AED",
        "rate_column_label": "Rate (AED)",
        "vat_percent": 5.0,
        "general_notes": list(DEFAULT_GENERAL_NOTES),
        "payment_terms": list(DEFAULT_PAYMENT_TERMS),
        "validity": "15-Days from the quotation date.",
        "scope_includes": [
            f"Supply and execution of items detailed in the BOQ for {project_name}.",
        ],
        "exclusions": [
            "Anything not quoted/described above.",
            "Civil defense inspection compliance is excluded from this quote unless specified.",
        ],
        "terms_conditions": list(DEFAULT_TERMS_AND_CONDITIONS),
        "closing_note": (
            "We trust the above aligns with your requirements. For any clarification, please feel "
            "free to contact the undersigned. We look forward to receiving your valuable order."
        ),
        "signatory_name": "Authorized Estimator",
        "signatory_title": "Sales / Estimation Engineer",
        "signatory_phone": "",
    }
    for k, v in saved.items():
        if v is not None and v != "":
            defaults[k] = v
    return defaults


def _draw_v_ribbon(c: canvas.Canvas, x: float, y: float, size: float, watermark: bool = False) -> None:
    """Draw the signature Vortexen interlocking blue/cyan V emblem in pure vector graphics."""
    c.saveState()
    if watermark:
        navy = colors.Color(0.84, 0.94, 0.99, alpha=0.55)
        azure = colors.Color(0.82, 0.93, 0.99, alpha=0.55)
        cyan = colors.Color(0.86, 0.95, 1.0, alpha=0.55)
        notch = colors.white
    else:
        navy = colors.HexColor("#17468C")
        azure = colors.HexColor("#1E88E5")
        cyan = colors.HexColor("#35C2F6")
        notch = colors.white

    s = size
    p1 = c.beginPath()
    p1.moveTo(x + 0.00 * s, y + 0.88 * s)
    p1.lineTo(x + 0.27 * s, y + 0.88 * s)
    p1.lineTo(x + 0.56 * s, y + 0.16 * s)
    p1.lineTo(x + 0.43 * s, y + 0.00 * s)
    p1.close()
    c.setFillColor(navy)
    c.drawPath(p1, stroke=0, fill=1)

    p2 = c.beginPath()
    p2.moveTo(x + 0.00 * s, y + 0.88 * s)
    p2.lineTo(x + 0.27 * s, y + 0.88 * s)
    p2.lineTo(x + 0.36 * s, y + 0.64 * s)
    p2.lineTo(x + 0.17 * s, y + 0.64 * s)
    p2.close()
    c.setFillColor(cyan)
    c.drawPath(p2, stroke=0, fill=1)

    p3 = c.beginPath()
    p3.moveTo(x + 0.43 * s, y + 0.00 * s)
    p3.lineTo(x + 0.62 * s, y + 0.00 * s)
    p3.lineTo(x + 0.98 * s, y + 0.88 * s)
    p3.lineTo(x + 0.72 * s, y + 0.88 * s)
    p3.close()
    c.setFillColor(azure)
    c.drawPath(p3, stroke=0, fill=1)

    p4 = c.beginPath()
    p4.moveTo(x + 0.46 * s, y + 0.34 * s)
    p4.lineTo(x + 0.58 * s, y + 0.64 * s)
    p4.lineTo(x + 0.70 * s, y + 0.34 * s)
    p4.lineTo(x + 0.55 * s, y + 0.15 * s)
    p4.close()
    c.setFillColor(cyan)
    c.drawPath(p4, stroke=0, fill=1)

    p5 = c.beginPath()
    p5.moveTo(x + 0.78 * s, y + 0.42 * s)
    p5.lineTo(x + 0.92 * s, y + 0.55 * s)
    p5.lineTo(x + 0.86 * s, y + 0.68 * s)
    p5.close()
    c.setFillColor(notch)
    c.drawPath(p5, stroke=0, fill=1)

    c.restoreState()


def _draw_page_chrome(
    c: canvas.Canvas,
    page_w: float,
    page_h: float,
    reference: str,
    draw_header_rule: bool,
) -> None:
    """Render Vortexen top header logo, center watermark, and bottom Abu Dhabi footer."""
    _draw_v_ribbon(c, (page_w - 300) / 2.0, (page_h - 270) / 2.0 - 20, size=300, watermark=True)

    logo_size = 44
    logo_x = page_w / 2.0 - 110
    logo_y = page_h - 68
    _draw_v_ribbon(c, logo_x, logo_y, size=logo_size, watermark=False)

    c.saveState()
    c.setFillColor(colors.HexColor("#111827"))
    c.setFont("Helvetica-Bold", 21)
    c.drawString(logo_x + logo_size + 10, logo_y + 18, "V O R T E X E N")
    c.setFont("Helvetica-Bold", 7.2)
    c.drawString(logo_x + logo_size + 11, logo_y + 6, "D Y N A M I C S   I N D U S T R I A L   S O L U T I O N S")

    if draw_header_rule:
        c.setStrokeColor(colors.HexColor("#2563EB"))
        c.setLineWidth(1.3)
        c.line(0, page_h - 90, page_w, page_h - 90)

    c.setFillColor(colors.HexColor("#111827"))
    c.setFont("Helvetica", 9.0)
    c.drawString(54, 70, f"Reference: {reference}")

    email_txt = "office@vortexen.com"
    sep_txt = "   |   "
    web_txt = "www.vortexen.com"
    c.setFont("Helvetica-Bold", 9.5)
    w_email = c.stringWidth(email_txt, "Helvetica-Bold", 9.5)
    w_sep = c.stringWidth(sep_txt, "Helvetica", 9.5)
    w_web = c.stringWidth(web_txt, "Helvetica-Bold", 9.5)
    start_x = (page_w - (w_email + w_sep + w_web)) / 2.0
    foot_y = 44

    c.setFillColor(colors.HexColor("#1D4ED8"))
    c.setFont("Helvetica-Bold", 9.5)
    c.drawString(start_x, foot_y, email_txt)
    c.setStrokeColor(colors.HexColor("#1D4ED8"))
    c.setLineWidth(0.7)
    c.line(start_x, foot_y - 1.5, start_x + w_email, foot_y - 1.5)

    c.setFillColor(colors.HexColor("#111827"))
    c.setFont("Helvetica", 9.5)
    c.drawString(start_x + w_email, foot_y, sep_txt)
    c.setFont("Helvetica-Bold", 9.5)
    c.drawString(start_x + w_email + w_sep, foot_y, web_txt)

    c.setFont("Helvetica-Bold", 9.5)
    c.drawCentredString(page_w / 2.0, foot_y - 14, "Abu Dhabi | U.A.E.")
    c.restoreState()


def generate_vortexen_quotation_pdf(session, meta_override: dict[str, Any] | None = None) -> bytes:
    """Generate a dynamic, multi-page A4 Vortexen Commercial Quotation PDF with clean pagination."""
    meta = default_quotation_metadata(session)
    if meta_override:
        for k, v in meta_override.items():
            if v is not None and v != "":
                meta[k] = v

    currency = str(meta.get("currency") or "AED").strip()
    rate_label = str(meta.get("rate_column_label") or f"Rate ({currency})")
    vat_pct = float(meta.get("vat_percent") if meta.get("vat_percent") is not None else 5.0)
    reference = str(meta.get("reference") or "")

    buf = io.BytesIO()
    page_w, page_h = A4
    margin_x = 54

    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=margin_x,
        rightMargin=margin_x,
        topMargin=102,
        bottomMargin=94,
        title=f"Vortexen Quotation - {reference}",
        author="Vortexen Dynamics Industrial Solutions",
    )

    style_body = ParagraphStyle("vx_body", fontName="Helvetica", fontSize=9.5, leading=13, textColor=colors.HexColor("#111827"))
    style_bold = ParagraphStyle("vx_bold", fontName="Helvetica-Bold", fontSize=9.5, leading=13, textColor=colors.HexColor("#111827"))
    style_tbl = ParagraphStyle("vx_tbl", fontName="Helvetica", fontSize=8.5, leading=10.5, textColor=colors.HexColor("#111827"))
    style_tbl_c = ParagraphStyle("vx_tbl_c", parent=style_tbl, alignment=TA_CENTER)
    style_tbl_r = ParagraphStyle("vx_tbl_r", parent=style_tbl, alignment=TA_RIGHT)
    style_tbl_hdr = ParagraphStyle("vx_tbl_hdr", fontName="Helvetica-Bold", fontSize=8.5, leading=10.5, alignment=TA_CENTER)
    style_tbl_bold_r = ParagraphStyle("vx_tbl_br", fontName="Helvetica-Bold", fontSize=9, leading=11, alignment=TA_RIGHT)
    style_tbl_bold = ParagraphStyle("vx_tbl_b", fontName="Helvetica-Bold", fontSize=9, leading=11, alignment=TA_LEFT)
    style_bullet = ParagraphStyle("vx_bul", fontName="Helvetica", fontSize=9, leading=12.5, leftIndent=14, firstLineIndent=-14, textColor=colors.HexColor("#111827"))

    story: list[Any] = []

    # Cover / client header block
    if meta.get("date"):
        story.append(Paragraph(f"<u><b>Date: {escape(str(meta['date']))}</b></u>", style_body))
        story.append(Spacer(1, 8))

    if meta.get("to_client"):
        story.append(Paragraph(f"<b>To:</b> {escape(str(meta['to_client']))}", style_body))
    if meta.get("contact_person"):
        story.append(Paragraph(f"Project Contact Person: {escape(str(meta['contact_person']))}", style_body))
    if meta.get("contact_number"):
        story.append(Paragraph(f"Contact Number: {escape(str(meta['contact_number']))}", style_body))
    if meta.get("project_location"):
        story.append(Paragraph(f"Project Location: {escape(str(meta['project_location']))}", style_body))

    if reference:
        story.append(Spacer(1, 7))
        story.append(Paragraph(f"Reference: {escape(reference)}", style_body))
    if meta.get("subject"):
        story.append(Spacer(1, 7))
        story.append(Paragraph(f"<u><b>Subject: {escape(str(meta['subject']))}</b></u>", style_body))

    story.append(Spacer(1, 7))
    story.append(Paragraph("Dear Sir,", style_body))
    if meta.get("intro_text"):
        story.append(Spacer(1, 5))
        story.append(Paragraph(escape(str(meta["intro_text"])), style_body))
    if meta.get("contract_period"):
        story.append(Spacer(1, 7))
        story.append(Paragraph("<b>Contract Period:</b>", style_bold))
        story.append(Paragraph(escape(str(meta["contract_period"])), style_body))
    story.append(Spacer(1, 10))

    # 5-column dynamic BOQ Table (Opening Size removed, auto-paginates cleanly)
    results = [
        r for r in session.results.all()
        if (getattr(r, "native_class", "") or "").strip().lower() != "folder"
    ]
    col_widths = [46, 225, 62, 74, 80]  # Sum = 487pt == (595 - 2*54)

    table_data: list[list[Any]] = [
        [
            Paragraph("SL : NO", style_tbl_hdr),
            Paragraph("Description", style_tbl_hdr),
            Paragraph("Unit /Qty", style_tbl_hdr),
            Paragraph(escape(rate_label), style_tbl_hdr),
            Paragraph(f"Total Amount({escape(currency)})", style_tbl_hdr),
        ]
    ]

    subtotal = 0.0
    for idx, r in enumerate(results, start=1):
        qty = float(r.quantity or 0.0)
        rate = float(r.unit_cost) if r.unit_cost is not None else 0.0
        line_total = float(r.total_cost) if r.total_cost is not None else round(qty * rate, 2)
        subtotal += line_total
        qty_display = f"{qty:,.2f}".rstrip("0").rstrip(".") if qty != int(qty) else str(int(qty))
        if r.unit:
            qty_display = f"{qty_display} {r.unit}"
        desc_text = f"<b>{escape(r.object_name or r.native_class)}</b>"
        if r.category and r.category != r.object_name:
            desc_text += f"<br/><font size='7.5' color='#475569'>{escape(r.category)}</font>"

        table_data.append(
            [
                Paragraph(f"A.{idx}", style_tbl_c),
                Paragraph(desc_text, style_tbl),
                Paragraph(escape(qty_display), style_tbl_c),
                Paragraph(f"{rate:,.2f}", style_tbl_c),
                Paragraph(f"{line_total:,.2f}", style_tbl_r),
            ]
        )

    if not results:
        table_data.append(["-", Paragraph("No takeoff items in session.", style_tbl), "0", "0.00", "0.00"])

    vat_amt = round(subtotal * (vat_pct / 100.0), 3)
    grand_total = round(subtotal + vat_amt, 2)

    spacer_row_idx = len(table_data)
    table_data.append(["", "", "", "", ""])
    sum_start_idx = len(table_data)
    table_data.append(["", "", Paragraph("Total Amount (As Discussed)", style_tbl_bold), "", Paragraph(f"{subtotal:,.2f}", style_tbl_bold_r)])
    table_data.append(["", "", Paragraph(f"VAT {vat_pct:g}%", style_tbl_bold), "", Paragraph(f"{vat_amt:,.3f}".rstrip("0").rstrip("."), style_tbl_bold_r)])
    table_data.append(["", "", Paragraph("Total Amount with VAT", style_tbl_bold), "", Paragraph(f"{grand_total:,.2f}", style_tbl_bold_r)])

    tbl = Table(table_data, colWidths=col_widths, repeatRows=1)
    tbl.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.75, colors.black),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("BACKGROUND", (0, 0), (-1, 0), colors.Color(0.97, 0.98, 1.0, alpha=0.6)),
                ("SPAN", (2, sum_start_idx), (3, sum_start_idx)),
                ("SPAN", (2, sum_start_idx + 1), (3, sum_start_idx + 1)),
                ("SPAN", (2, sum_start_idx + 2), (3, sum_start_idx + 2)),
                ("TOPPADDING", (0, spacer_row_idx), (-1, spacer_row_idx), 3),
                ("BOTTOMPADDING", (0, spacer_row_idx), (-1, spacer_row_idx), 3),
                ("NOSPLIT", (0, spacer_row_idx), (-1, -1)),
            ]
        )
    )
    story.append(tbl)

    # Commercial Terms & Signatory section on clean continuation page
    section_defs = [
        ("General Notes:", _normalize_lines(meta.get("general_notes")), True),
        ("Payment Terms:", _normalize_lines(meta.get("payment_terms")), True),
        ("Validity:", _normalize_lines(meta.get("validity")), False),
        ("Scope of Work Includes:", _normalize_lines(meta.get("scope_includes")), True),
        ("Exclusions:", _normalize_lines(meta.get("exclusions")), True),
        ("Terms & Conditions:", _normalize_lines(meta.get("terms_conditions")), True),
    ]
    has_terms = any(lines for _, lines, _ in section_defs) or bool(meta.get("closing_note") or meta.get("signatory_name"))
    if has_terms:
        story.append(PageBreak())
        for title, lines, bullet in section_defs:
            if not lines:
                continue
            block: list[Any] = [Paragraph(f"<b>{escape(title)}</b>", style_bold), Spacer(1, 3)]
            for idx, line in enumerate(lines):
                txt = f"- &nbsp;&nbsp; {escape(line)}" if bullet else escape(line)
                para = Paragraph(txt, style_bullet if bullet else style_body)
                if idx == 0:
                    block.append(para)
                    story.append(KeepTogether(block))
                else:
                    story.append(para)
            story.append(Spacer(1, 7))

        sig_block: list[Any] = []
        if meta.get("closing_note"):
            sig_block.append(Paragraph(escape(str(meta["closing_note"])), style_body))
            sig_block.append(Spacer(1, 12))
        sig_block.append(Paragraph("<b>Thank you &amp; best regards,</b>", style_bold))
        sig_block.append(Spacer(1, 8))
        if meta.get("signatory_name"):
            sig_block.append(Paragraph(f"<b>{escape(str(meta['signatory_name']))}</b>", style_bold))
        sig_sub = " ".join(
            x for x in (str(meta.get("signatory_title") or "").strip(), str(meta.get("signatory_phone") or "").strip()) if x
        )
        if sig_sub:
            sig_block.append(Paragraph(f"<b>{escape(sig_sub)}</b>", style_bold))
        story.append(KeepTogether(sig_block))

    doc.build(
        story,
        onFirstPage=lambda c_obj, _d: _draw_page_chrome(c_obj, page_w, page_h, reference=reference, draw_header_rule=True),
        onLaterPages=lambda c_obj, _d: _draw_page_chrome(c_obj, page_w, page_h, reference=reference, draw_header_rule=False),
    )
    return buf.getvalue()
