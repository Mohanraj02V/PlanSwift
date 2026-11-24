"""Signature-based source format detection preventing wrong-adapter routing."""

from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Literal

from extraction_engine.core.extraction_context import SecurityValidationError

SourceFormat = Literal[
    "planswift_package",
    "planswift_xml",
    "dxf_ascii",
    "dxf_binary",
    "ifc_step",
]


class UnsupportedFormatError(SecurityValidationError):
    """Raised when a source file does not match any supported PlanSwift, DXF, or IFC format."""


_BINARY_DXF_MAGIC = b"AutoCAD Binary DXF\r\n\x1a\x00"
_DXF_SECTION_NAMES = frozenset({"HEADER", "CLASSES", "TABLES", "BLOCKS", "ENTITIES", "OBJECTS", "THUMBNAILIMAGE", "ACDSDATA"})


def _looks_like_ascii_dxf(head_bytes: bytes) -> bool:
    """Inspect decoded header lines for valid DXF group-code/value structure without trusting extension."""
    if b"\x00" in head_bytes:
        return False
    try:
        text = head_bytes.decode("utf-8-sig", errors="strict")
    except UnicodeDecodeError:
        text = head_bytes.decode("latin-1", errors="ignore")
    lines = [ln.strip() for ln in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    # Skip leading blank lines if any
    idx = 0
    while idx < len(lines) and lines[idx] == "":
        idx += 1
    if idx + 1 >= len(lines):
        return False
    # Allow leading 999 comments before 0 / SECTION
    checked_pairs = 0
    saw_section = False
    while idx + 1 < len(lines) and checked_pairs < 32:
        code = lines[idx]
        val = lines[idx + 1]
        if code == "999":
            idx += 2
            checked_pairs += 1
            continue
        if code == "0" and val.upper() == "SECTION":
            saw_section = True
            if idx + 3 < len(lines) and lines[idx + 2] == "2" and lines[idx + 3].upper() in _DXF_SECTION_NAMES:
                return True
            # Still plausible if truncated right after SECTION inside probe
            return True
        if code == "0" and val.upper() == "EOF" and checked_pairs == 0:
            return True
        break
    return saw_section


def _looks_like_ifc_step(head_bytes: bytes) -> bool:
    """Detect ISO-10303-21 STEP Physical File containing an IFC schema declaration."""
    stripped = head_bytes.lstrip()
    if not stripped.startswith(b"ISO-10303-21;"):
        return False
    upper = stripped.upper()
    if b"FILE_SCHEMA" in upper:
        return b"IFC" in upper
    # If FILE_SCHEMA lies past 4 KiB header read, allow STEP if HEADER; appears
    return b"HEADER;" in upper


def detect_source_format(source_path: Path) -> SourceFormat:
    """Detect true source format via structural & magic-byte signatures, never extension alone."""
    if not source_path.exists():
        raise FileNotFoundError(f"Source path does not exist: {source_path}")

    if source_path.is_dir():
        return "planswift_package"

    file_size = source_path.stat().st_size
    if file_size == 0:
        raise SecurityValidationError(f"Source file '{source_path.name}' is empty (0 bytes).")

    with source_path.open("rb") as fh:
        head = fh.read(8192)

    ext = source_path.suffix.lower()
    magic_prefix = head[:16]
    magic_hex = " ".join(f"{b:02X}" for b in magic_prefix)

    # 1. Binary DXF magic
    if head.startswith(_BINARY_DXF_MAGIC):
        if ext in (".zip", ".swiftjob", ".swift", ".xml", ".ifc"):
            raise UnsupportedFormatError(f"Extension '{ext}' mismatches Binary DXF signature in '{source_path.name}'.")
        return "dxf_binary"

    # 2. PKZIP container (PlanSwift .SwiftJob / .zip)
    if magic_prefix.startswith((b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")) or zipfile.is_zipfile(source_path):
        if ext in (".dxf", ".ifc", ".xml"):
            raise UnsupportedFormatError(f"Extension '{ext}' mismatches PKZIP signature in '{source_path.name}'.")
        return "planswift_package"

    # 3. IFC STEP Physical File
    if _looks_like_ifc_step(head):
        if ext in (".zip", ".swiftjob", ".swift", ".dxf", ".xml"):
            raise UnsupportedFormatError(f"Extension '{ext}' mismatches IFC STEP signature in '{source_path.name}'.")
        return "ifc_step"

    # 4. XML (PlanSwift XMLData.XML)
    stripped = head.lstrip()
    if stripped.startswith((b"\xef\xbb\xbf<?xml", b"<?xml", b"<Item")):
        if ext in (".zip", ".swiftjob", ".swift", ".dxf", ".ifc"):
            raise UnsupportedFormatError(f"Extension '{ext}' mismatches XML signature in '{source_path.name}'.")
        return "planswift_xml"

    # 5. ASCII DXF
    if _looks_like_ascii_dxf(head):
        if ext in (".zip", ".swiftjob", ".swift", ".xml", ".ifc"):
            raise UnsupportedFormatError(f"Extension '{ext}' mismatches ASCII DXF structure in '{source_path.name}'.")
        return "dxf_ascii"

    # 6. Explicit extension mismatch diagnostics before generic unsupported rejection
    if ext in (".zip", ".swiftjob", ".swift"):
        raise SecurityValidationError(
            f"Corrupted or invalid ZIP archive '{source_path.name}' (signature={magic_hex})."
        )
    raise UnsupportedFormatError(
        f"Unsupported or unrecognized file format for '{source_path.name}' (ext={ext!r}, signature={magic_hex})."
    )
