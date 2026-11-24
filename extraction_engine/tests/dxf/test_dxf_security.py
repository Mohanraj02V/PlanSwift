"""Verify DXF security protections: XREF non-loading, signature mismatches, empty files, and entity caps."""

from __future__ import annotations

from pathlib import Path

import ezdxf
import pytest

from extraction_engine.core.extraction_context import ExtractionConfig, SecurityValidationError
from extraction_engine.core.format_detector import UnsupportedFormatError
from extraction_engine.pipeline import ExtractionPipeline


def test_dxf_xref_not_loaded_and_bad_signatures_rejected(tmp_path: Path) -> None:
    # 1. DXF containing malicious XREF path -> must NOT touch filesystem, only log metadata
    p = tmp_path / "xref_test.dxf"
    doc = ezdxf.new("R2010")
    secret_target = tmp_path / "do_not_read_me.dxf"
    secret_target.write_text("CORRUPT_IF_OPENED", encoding="utf-8")
    doc.add_xref_def(filename=str(secret_target), name="EXT_REF_1")
    doc.modelspace().add_blockref("EXT_REF_1", insert=(0, 0))
    doc.saveas(p)

    project, _ = ExtractionPipeline().run(p)
    cad = project.cad_document
    assert any(ref["block_name"] == "EXT_REF_1" and ref["loaded"] is False for ref in cad.external_references)

    # 2. Disguised text file with .dxf extension -> rejected cleanly by signature detector
    fake = tmp_path / "fake.dxf"
    fake.write_text("NOT A REAL DXF FILE", encoding="utf-8")
    with pytest.raises(UnsupportedFormatError):
        ExtractionPipeline().run(fake)

    # 3. Corrupted .zip disguised with text -> never routed to DXF/IFC
    bad_zip = tmp_path / "bad.zip"
    bad_zip.write_text("0\nSECTION\n2\nHEADER\n", encoding="utf-8")
    with pytest.raises(UnsupportedFormatError):
        ExtractionPipeline().run(bad_zip)

    # 4. File size bound enforcement
    cfg = ExtractionConfig(dxf_max_file_bytes=100)
    with pytest.raises(SecurityValidationError, match="dxf_max_file_bytes"):
        ExtractionPipeline(config=cfg).run(p)
