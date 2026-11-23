"""Security tests for archive inspection, XML XXE prevention, and unsafe eval prohibition."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from extraction_engine.core.extraction_context import ExtractionConfig, ExtractionContext, SecurityValidationError
from extraction_engine.parsers.archive_parser import inspect_archive_manifest, validate_source_path_allowed
from extraction_engine.parsers.geometry_parser import parse_digitizer_geometry
from extraction_engine.parsers.xml_parser import parse_xmldata_stream


def test_rejects_zip_slip_traversal(tmp_path: Path) -> None:
    zpath = tmp_path / "slip.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("../../evil.xml", "<Item/>")
    with pytest.raises(SecurityValidationError, match="path traversal"):
        inspect_archive_manifest(zpath)


def test_rejects_absolute_archive_path(tmp_path: Path) -> None:
    zpath = tmp_path / "abs.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("/etc/passwd", "x")
    with pytest.raises(SecurityValidationError, match="absolute path"):
        inspect_archive_manifest(zpath)


def test_rejects_unexpected_executable(tmp_path: Path) -> None:
    zpath = tmp_path / "exe.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("payload.exe", b"MZ")
    with pytest.raises(SecurityValidationError, match="executable"):
        inspect_archive_manifest(zpath)


def test_rejects_nested_archive(tmp_path: Path) -> None:
    zpath = tmp_path / "nested.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("inner.zip", b"PK\x03\x04")
    with pytest.raises(SecurityValidationError, match="nested archive"):
        inspect_archive_manifest(zpath)


def test_rejects_symlink_in_zip(tmp_path: Path) -> None:
    zpath = tmp_path / "symlink.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        info = zipfile.ZipInfo("link.txt")
        info.create_system = 3
        info.external_attr = (0o120777 << 16)
        zf.writestr(info, "/etc/passwd")
    with pytest.raises(SecurityValidationError, match="symlink"):
        inspect_archive_manifest(zpath)


def test_rejects_zip_bomb_compression_ratio(tmp_path: Path) -> None:
    zpath = tmp_path / "bomb.zip"
    # 12 MB of zeros compresses > 500x under deflate
    with zipfile.ZipFile(zpath, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("XMLData.XML", b"A" * (12 * 1024 * 1024))
    cfg = ExtractionConfig(max_compression_ratio=50.0)
    with pytest.raises(SecurityValidationError, match="ZIP bomb"):
        inspect_archive_manifest(zpath, config=cfg)


def test_allowed_source_roots_enforcement(tmp_path: Path) -> None:
    allowed_dir = tmp_path / "allowed"
    allowed_dir.mkdir()
    outside = tmp_path / "outside.xml"
    outside.write_text("<Item/>", encoding="utf-8")
    cfg = ExtractionConfig(allowed_source_roots=(allowed_dir,))
    with pytest.raises(SecurityValidationError, match="ALLOWED_SOURCE_ROOTS"):
        validate_source_path_allowed(outside, cfg)


def test_xxe_entity_expansion_blocked() -> None:
    xxe_xml = b"""<?xml version="1.0" encoding="Windows-1252"?>
    <!DOCTYPE Item [<!ENTITY xxe SYSTEM "file:///C:/Windows/win.ini">]>
    <Item Class="Item" Name="&xxe;" GUID="{11111111-1111-1111-1111-111111111111}">
      <Properties/>
      <Items/>
    </Item>"""
    ctx = ExtractionContext()
    with pytest.raises(SecurityValidationError):
        parse_xmldata_stream(io.BytesIO(xxe_xml), "xxe.xml", ctx)


def test_digitizer_xxe_blocked() -> None:
    malicious_dd = '<!DOCTYPE Points [<!ENTITY e "boom">]><Points><Point X="1" Y="2" PointType="Normal"/></Points>'
    with pytest.raises(Exception):
        parse_digitizer_geometry(malicious_dd, "{SEC}", "{OBJ}", "{PG}", "Count Section")
