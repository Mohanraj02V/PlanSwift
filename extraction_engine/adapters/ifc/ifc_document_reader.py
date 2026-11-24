"""IFC STEP inspection, schema verification, unit extraction, and single-open reader."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import ifcopenshell
import ifcopenshell.ifcopenshell_wrapper
import ifcopenshell.util.unit

from extraction_engine.core.extraction_context import ExtractionConfig, SecurityValidationError
from extraction_engine.core.format_detector import detect_source_format
from extraction_engine.core.source_manifest import SourceFileEntry, SourceManifest, compute_file_sha256
from extraction_engine.parsers.archive_parser import validate_source_path_allowed

_FILE_SCHEMA_RE = re.compile(r"FILE_SCHEMA\s*\(\s*\(\s*['\"]([^'\"]+)['\"]", re.IGNORECASE)


def get_supported_ifc_schemas() -> tuple[str, ...]:
    """Return schemas genuinely supported by the installed IfcOpenShell release."""
    try:
        return tuple(sorted(ifcopenshell.ifcopenshell_wrapper.schema_names()))
    except Exception:
        return ()


def _probe_ifc_header(source_path: Path) -> tuple[str, str]:
    """Extract FILE_SCHEMA and rough encoding from IFC STEP header without full parse."""
    with source_path.open("rb") as fh:
        head = fh.read(16384)
    text = head.decode("utf-8", errors="replace")
    m = _FILE_SCHEMA_RE.search(text)
    schema = m.group(1).strip() if m else ""
    return schema, "utf-8"


def inspect_ifc_manifest(source_path: Path, config: ExtractionConfig | None = None) -> SourceManifest:
    """Validate signature, size bounds, and STEP schema before full IfcOpenShell load."""
    cfg = config or ExtractionConfig()
    resolved = validate_source_path_allowed(source_path, cfg)
    file_size = resolved.stat().st_size
    if file_size > cfg.ifc_max_file_bytes:
        raise SecurityValidationError(
            f"IFC file size ({file_size} bytes) exceeds ifc_max_file_bytes={cfg.ifc_max_file_bytes}."
        )

    fmt = detect_source_format(resolved)
    if fmt != "ifc_step":
        raise SecurityValidationError(f"Expected IFC STEP file, detected '{fmt}'.")

    with resolved.open("rb") as fh:
        magic = fh.read(32)
    magic_hex = " ".join(f"{b:02X}" for b in magic[:16])
    sha256 = compute_file_sha256(resolved, chunk_size=cfg.hash_chunk_size)
    schema_name, enc = _probe_ifc_header(resolved)

    warnings: list[str] = []
    supported_schemas = get_supported_ifc_schemas()
    if schema_name and supported_schemas and schema_name.upper() not in {s.upper() for s in supported_schemas}:
        warnings.append(
            f"IFC FILE_SCHEMA '{schema_name}' is not in installed IfcOpenShell schema set {list(supported_schemas)}."
        )

    entry = SourceFileEntry(
        relative_path=resolved.name,
        file_name=resolved.name,
        extension=resolved.suffix.lower(),
        compressed_size=file_size,
        uncompressed_size=file_size,
        compression_ratio=1.0,
        content_sha256=sha256,
        security_status="safe",
    )
    return SourceManifest(
        source_path=str(resolved),
        source_name=resolved.name,
        actual_extension=resolved.suffix.lower(),
        magic_bytes_hex=magic_hex,
        container_format="ifc_step",
        file_size_bytes=file_size,
        source_sha256=sha256,
        total_entries=1,
        total_compressed_bytes=file_size,
        total_uncompressed_bytes=file_size,
        detected_xml_encoding=enc,
        detected_project_version=schema_name or "IFC",
        warnings=warnings,
        entries=[entry],
    )


def _describe_unit(unit_ent: Any) -> str:
    if unit_ent is None:
        return ""
    if hasattr(unit_ent, "Name"):
        prefix = getattr(unit_ent, "Prefix", None)
        name = getattr(unit_ent, "Name", "") or ""
        return f"{prefix}_{name}" if prefix else str(name)
    return str(unit_ent.is_a())


def open_ifc_model(
    source_path: Path,
    config: ExtractionConfig,
) -> tuple[ifcopenshell.file, dict[str, Any], list[str]]:
    """Open an IFC STEP model once and extract schema + unit assignments without inventing defaults."""
    warnings: list[str] = []
    supported = get_supported_ifc_schemas()
    schema_hint, _ = _probe_ifc_header(source_path)
    if schema_hint and supported and schema_hint.upper() not in {s.upper() for s in supported}:
        raise SecurityValidationError(
            f"Unsupported IFC schema '{schema_hint}'. Supported by IfcOpenShell {ifcopenshell.version}: {list(supported)}"
        )

    try:
        model = ifcopenshell.open(str(source_path))
    except Exception as exc:
        raise SecurityValidationError(f"Failed to parse IFC file '{source_path.name}': {exc}") from exc

    schema_name = str(getattr(model, "schema_identifier", None) or getattr(model, "schema", schema_hint) or "")
    header_meta: dict[str, Any] = {"schema": schema_name, "supported_schemas": list(supported)}
    try:
        fn = model.header.file_name
        fd = model.header.file_description
        header_meta["author"] = list(getattr(fn, "author", []) or [])
        header_meta["organization"] = list(getattr(fn, "organization", []) or [])
        header_meta["originating_system"] = getattr(fn, "originating_system", "") or ""
        header_meta["time_stamp"] = getattr(fn, "time_stamp", "") or ""
        header_meta["description"] = list(getattr(fd, "description", []) or [])
    except Exception:
        pass

    # Extract explicit IFC unit assignments without guessing
    length_factor: float | None = None
    area_factor: float | None = None
    volume_factor: float | None = None
    length_label = ""
    area_label = ""
    volume_label = ""
    unit_details: dict[str, str] = {}

    try:
        unit_assign = model.by_type("IfcUnitAssignment")
        has_explicit_length = False
        if unit_assign:
            for u in getattr(unit_assign[0], "Units", []) or []:
                utype = getattr(u, "UnitType", None)
                desc = _describe_unit(u)
                if utype:
                    unit_details[str(utype)] = desc
                if str(utype) == "LENGTHUNIT":
                    has_explicit_length = True
                    length_label = desc
                elif str(utype) == "AREAUNIT":
                    area_label = desc
                elif str(utype) == "VOLUMEUNIT":
                    volume_label = desc
        if has_explicit_length:
            length_factor = float(ifcopenshell.util.unit.calculate_unit_scale(model, "LENGTHUNIT"))
            area_factor = length_factor * length_factor
            volume_factor = length_factor * length_factor * length_factor
        else:
            warnings.append("No explicit LENGTHUNIT in IfcUnitAssignment; SI normalization left None.")
    except Exception as exc:
        warnings.append(f"IFC unit parsing warning: {exc}")

    header_meta["unit_assignments"] = unit_details
    meta = {
        "schema_name": schema_name,
        "header_variables": header_meta,
        "length_unit": length_label,
        "area_unit": area_label,
        "volume_unit": volume_label,
        "unit_to_meter_factor": length_factor,
        "area_to_m2_factor": area_factor,
        "volume_to_m3_factor": volume_factor,
    }
    return model, meta, warnings
