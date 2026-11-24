"""Metadata, Page-to-TIFF matching, scale extraction, SwiftExcel memo parsing, and specialized entity extractors."""

from __future__ import annotations

from extraction_engine.core.extraction_result import (
    CanonicalDenotation,
    CanonicalPage,
    CanonicalProject,
    CanonicalRemark,
    ProvenanceStatus,
)
from extraction_engine.core.source_manifest import SourceManifest


def parse_swift_excel_memo(raw_memo: str) -> dict[str, str]:
    """Parse key=value lines stored inside PlanSwift Swift Excel Memo properties."""
    parsed: dict[str, str] = {}
    for line in raw_memo.splitlines():
        if "=" in line:
            key, val = line.split("=", 1)
            parsed[key.strip()] = val.strip()
    return parsed


def _parse_positive_float(prop) -> float | None:
    if prop is None or not prop.raw_value.strip():
        return None
    try:
        val = float(prop.raw_value.strip())
        return val if val > 0 else None
    except ValueError:
        return None


def enrich_project_and_pages(project: CanonicalProject, manifest: SourceManifest | None) -> None:
    """Populate project-level metadata, build CanonicalPage records, and link TIFF entries by Image GUID."""
    tiff_by_guid: dict[str, tuple[str, int]] = {}
    if manifest is not None:
        if manifest.detected_xml_encoding:
            project.xml_encoding = manifest.detected_xml_encoding
        if manifest.detected_project_version:
            project.native_project_version = manifest.detected_project_version
        for entry in manifest.entries:
            if entry.is_raster_asset and entry.asset_guid:
                tiff_by_guid[entry.asset_guid.upper()] = (entry.relative_path, entry.uncompressed_size)

    root_obj = next((o for o in project.objects if o.depth == 0), None)
    if root_obj is not None:
        desc = root_obj.get_property("Description")
        notes = root_obj.get_property("Notes")
        m_type = root_obj.get_property("Measurement Type")
        excel = root_obj.get_property("ExcelWorkbookConnected")
        job_id = root_obj.get_property("JobId")
        ver_prop = root_obj.get_property("PlanSwift Version") or root_obj.get_property("Version")
        project.description = desc.raw_value if desc else ""
        project.notes = notes.raw_value if notes else ""
        project.measurement_system = m_type.raw_value if m_type else ""
        if ver_prop and ver_prop.raw_value.strip():
            project.native_project_version = ver_prop.raw_value.strip()
        if excel is not None and excel.raw_value.strip():
            low = excel.raw_value.strip().lower()
            project.excel_workbook_connected = True if low in ("true", "-1", "1") else (False if low in ("false", "0") else None)
        project.job_id_raw = job_id.raw_value if job_id else ""
        project.created_by = root_obj.created_by or ""
        project.timestamp_raw = root_obj.timestamp_raw or ""

    pages_by_guid: dict[str, CanonicalPage] = {}
    pages: list[CanonicalPage] = []
    missing_refs: list[str] = []

    for obj in project.objects:
        if obj.is_page:
            img_prop = obj.get_property("Image")
            img_guid = img_prop.native_property_guid.upper() if img_prop else None
            tiff_info = tiff_by_guid.get(img_guid) if img_guid else None

            if manifest is not None and img_guid and tiff_info is not None:
                for entry in manifest.entries:
                    if entry.asset_guid and entry.asset_guid.upper() == img_guid:
                        entry.linked_page_guid = obj.native_guid
            elif manifest is not None and img_guid and tiff_info is None:
                missing_refs.append(f"Page '{obj.name}' ({obj.native_guid}) missing raster image GUID {img_guid}")

            scale_units = obj.get_property("Scale Units")
            scale_x = _parse_positive_float(obj.get_property("ScaleX"))
            scale_y = _parse_positive_float(obj.get_property("ScaleY")) or scale_x
            numeric_scale_factor = scale_x

            pw = obj.get_property("PageWidth")
            ph = obj.get_property("PageHeight")
            pwe = obj.get_property("PagesWindow_Expanded")
            page = CanonicalPage(
                native_guid=obj.native_guid,
                name=obj.name,
                native_class=obj.native_class,
                page_type=obj.native_type or ".TIFF Page",
                order_index=obj.order_index,
                image_property_guid=img_prop.native_property_guid if img_prop else None,
                tiff_archive_path=tiff_info[0] if tiff_info else None,
                tiff_size_bytes=tiff_info[1] if tiff_info else None,
                scale_units=scale_units.raw_value if scale_units else None,
                scale_x=scale_x,
                scale_y=scale_y,
                numeric_scale_factor=numeric_scale_factor,
                page_width_raw=pw.raw_value if pw else None,
                page_height_raw=ph.raw_value if ph else None,
                created_by=obj.created_by,
                timestamp_raw=obj.timestamp_raw,
                pages_window_expanded=bool(pwe.parsed_value) if pwe and isinstance(pwe.parsed_value, bool) else None,
                provenance=ProvenanceStatus.NATIVE,
            )
            pages.append(page)
            pages_by_guid[obj.native_guid.upper()] = page

        _extract_denotations_and_remarks(obj)

    if manifest is not None and missing_refs:
        manifest.missing_referenced_files = missing_refs

    for obj in project.objects:
        if obj.is_measurement_section and obj.page_guid:
            pg = pages_by_guid.get(obj.page_guid.upper())
            if pg is not None:
                pg.section_count += 1

    project.pages = pages


def _extract_denotations_and_remarks(obj) -> None:
    for prop in obj.properties:
        if prop.name == "Item #" and prop.raw_value.strip():
            obj.denotations.append(
                CanonicalDenotation(
                    denotation_key=f"{obj.native_guid}:item_number",
                    object_guid=obj.native_guid,
                    kind="item_number",
                    label="Item #",
                    value=prop.raw_value.strip(),
                    provenance=ProvenanceStatus.NATIVE,
                )
            )
        elif prop.name == "GroupId" and prop.raw_value.strip():
            obj.denotations.append(
                CanonicalDenotation(
                    denotation_key=f"{obj.native_guid}:group_id",
                    object_guid=obj.native_guid,
                    kind="group_id",
                    label="GroupId",
                    value=prop.raw_value.strip(),
                    provenance=ProvenanceStatus.NATIVE,
                )
            )
        elif prop.name == "Cost Code" and prop.raw_value.strip():
            obj.denotations.append(
                CanonicalDenotation(
                    denotation_key=f"{obj.native_guid}:cost_code",
                    object_guid=obj.native_guid,
                    kind="cost_code",
                    label="Cost Code",
                    value=prop.raw_value.strip(),
                    provenance=ProvenanceStatus.NATIVE,
                )
            )
        elif prop.group == "Swift Excel" and prop.property_class == "Memo" and "TokenGuid=" in prop.raw_value:
            meta = parse_swift_excel_memo(prop.raw_value)
            obj.denotations.append(
                CanonicalDenotation(
                    denotation_key=f"{obj.native_guid}:swift_excel:{prop.native_property_guid}",
                    object_guid=obj.native_guid,
                    kind="swift_excel_token",
                    label=prop.name or prop.native_property_guid,
                    value=meta.get("TokenGuid", prop.name),
                    metadata=meta,
                    provenance=ProvenanceStatus.NATIVE,
                )
            )
        elif prop.name in ("Description", "Notes", "Remarks") and prop.raw_value.strip():
            obj.remarks.append(
                CanonicalRemark(
                    remark_key=f"{obj.native_guid}:{prop.name}",
                    object_guid=obj.native_guid,
                    field_name=prop.name,
                    text=prop.raw_value.strip(),
                    provenance=ProvenanceStatus.NATIVE,
                )
            )
