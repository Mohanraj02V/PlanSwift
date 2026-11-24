"""DXF document inspection, header/unit parsing, and safe ezdxf reader."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import ezdxf
import ezdxf.recover

from extraction_engine.core.extraction_context import ExtractionConfig, SecurityValidationError
from extraction_engine.core.format_detector import detect_source_format
from extraction_engine.core.source_manifest import SourceFileEntry, SourceManifest, compute_file_sha256
from extraction_engine.parsers.archive_parser import validate_source_path_allowed

logger = logging.getLogger(__name__)

# AutoCAD $INSUNITS mapping (code -> (unit_label, factor_to_meters or None))
INSUNITS_MAP: dict[int, tuple[str, float | None]] = {
    0: ("unitless", None),
    1: ("in", 0.0254),
    2: ("ft", 0.3048),
    3: ("mi", 1609.344),
    4: ("mm", 0.001),
    5: ("cm", 0.01),
    6: ("m", 1.0),
    7: ("km", 1000.0),
    8: ("uin", 0.0000254),
    9: ("mil", 0.0000254),
    10: ("yd", 0.9144),
    11: ("angstrom", 1e-10),
    12: ("nm", 1e-9),
    13: ("um", 1e-6),
    14: ("dm", 0.1),
    15: ("dam", 10.0),
    16: ("hm", 100.0),
    17: ("gm", 1e9),
    18: ("au", 1.495978707e11),
    19: ("ly", 9.4607304725808e15),
    20: ("pc", 3.085677581491367e16),
    21: ("us_ft", 1200.0 / 3937.0),
}

_HEADER_KEYS = (
    "$ACADVER",
    "$DWGCODEPAGE",
    "$INSUNITS",
    "$MEASUREMENT",
    "$LUNITS",
    "$LUPREC",
    "$AUNITS",
    "$AUPREC",
    "$CLAYER",
    "$EXTMIN",
    "$EXTMAX",
    "$LIMMIN",
    "$LIMMAX",
    "$UCSORG",
    "$UCSXDIR",
    "$UCSYDIR",
    "$TEXTSIZE",
    "$DIMSCALE",
)


def _json_safe_header_val(val: Any) -> Any:
    if isinstance(val, (str, int, float, bool)) or val is None:
        return val
    if hasattr(val, "__iter__"):
        return [float(x) if isinstance(x, (int, float)) else str(x) for x in val]
    return str(val)


def inspect_dxf_manifest(source_path: Path, config: ExtractionConfig | None = None) -> SourceManifest:
    """Validate signature, size bounds, and inspect DXF header metadata without loading full blocks into DB."""
    cfg = config or ExtractionConfig()
    resolved = validate_source_path_allowed(source_path, cfg)
    file_size = resolved.stat().st_size
    if file_size > cfg.dxf_max_file_bytes:
        raise SecurityValidationError(
            f"DXF file size ({file_size} bytes) exceeds dxf_max_file_bytes={cfg.dxf_max_file_bytes}."
        )

    fmt = detect_source_format(resolved)
    if fmt not in ("dxf_ascii", "dxf_binary"):
        raise SecurityValidationError(f"Expected DXF file, detected '{fmt}'.")

    with resolved.open("rb") as fh:
        magic = fh.read(64)
    magic_hex = " ".join(f"{b:02X}" for b in magic[:16])
    sha256 = compute_file_sha256(resolved, chunk_size=cfg.hash_chunk_size)

    # Probe $ACADVER quickly from header bytes for ASCII DXF or fallback tag for binary DXF
    detected_ver = ""
    detected_enc = "binary" if fmt == "dxf_binary" else "utf-8"
    if fmt == "dxf_ascii":
        with resolved.open("rb") as fh:
            head_chunk = fh.read(32768).decode("latin-1", errors="ignore")
        idx = head_chunk.find("$ACADVER")
        if idx != -1:
            tail_lines = [ln.strip() for ln in head_chunk[idx : idx + 256].replace("\r\n", "\n").split("\n")]
            for i in range(len(tail_lines) - 2):
                if tail_lines[i] == "$ACADVER" and tail_lines[i + 1] == "1":
                    detected_ver = tail_lines[i + 2]
                    break
        codepage_idx = head_chunk.find("$DWGCODEPAGE")
        if codepage_idx != -1:
            cp_lines = [ln.strip() for ln in head_chunk[codepage_idx : codepage_idx + 256].replace("\r\n", "\n").split("\n")]
            for i in range(len(cp_lines) - 2):
                if cp_lines[i] == "$DWGCODEPAGE" and cp_lines[i + 1] == "3":
                    detected_enc = cp_lines[i + 2]
                    break

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
        container_format=fmt,
        file_size_bytes=file_size,
        source_sha256=sha256,
        total_entries=1,
        total_compressed_bytes=file_size,
        total_uncompressed_bytes=file_size,
        detected_xml_encoding=detected_enc,
        detected_project_version=detected_ver or fmt.upper(),
        entries=[entry],
    )


def open_dxf_document(
    source_path: Path,
    config: ExtractionConfig,
) -> tuple[ezdxf.document.Drawing, list[str], dict[str, Any]]:
    """Open a DXF file once using ezdxf (recover fallback for syntax anomalies) and extract header metadata."""
    warnings: list[str] = []
    try:
        doc = ezdxf.readfile(str(source_path))
    except (ezdxf.DXFStructureError, UnicodeDecodeError, ValueError) as first_exc:
        warnings.append(f"Standard DXF read encountered structure/encoding issue ({first_exc}); used ezdxf.recover.")
        try:
            doc, auditor = ezdxf.recover.readfile(str(source_path))
            for err in auditor.errors[:50]:
                warnings.append(f"DXF recover error: {err.message}")
            if len(auditor.errors) > 50:
                warnings.append(f"... plus {len(auditor.errors) - 50} additional DXF recover errors.")
        except Exception as rec_exc:
            raise SecurityValidationError(f"Failed to parse DXF '{source_path.name}': {rec_exc}") from rec_exc
    except OSError as os_exc:
        raise SecurityValidationError(f"Cannot read DXF '{source_path.name}': {os_exc}") from os_exc

    header_vars: dict[str, Any] = {}
    for key in _HEADER_KEYS:
        if key in doc.header:
            try:
                header_vars[key] = _json_safe_header_val(doc.header[key])
            except Exception:
                continue

    insunits_raw = doc.header.get("$INSUNITS", 0)
    try:
        insunits_code = int(insunits_raw)
    except (TypeError, ValueError):
        insunits_code = 0

    unit_label, unit_factor = INSUNITS_MAP.get(insunits_code, (f"insunits_{insunits_code}", None))
    # Do not fabricate unit when $INSUNITS == 0; check $MEASUREMENT only as contextual metadata
    if insunits_code == 0:
        header_vars["_units_note"] = "$INSUNITS is 0 (unitless); metric factor intentionally left None."

    meta = {
        "dxfversion": doc.dxfversion,
        "acad_release": getattr(doc, "acad_release", ""),
        "encoding": getattr(doc, "encoding", "utf-8"),
        "insunits_code": insunits_code,
        "source_units": unit_label,
        "unit_to_meter_factor": unit_factor,
        "header_variables": header_vars,
    }
    return doc, warnings, meta
