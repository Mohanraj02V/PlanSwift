"""Verify unsupported DXF entities are preserved verbatim and explicitly reported rather than discarded."""

from __future__ import annotations

from pathlib import Path

import ezdxf

from extraction_engine.core.extraction_result import ProvenanceStatus
from extraction_engine.pipeline import ExtractionPipeline


def test_dxf_acis_and_unsupported_entity_preservation(tmp_path: Path) -> None:
    # Write a minimal valid ASCII DXF containing both a standard LINE and a non-standard vendor entity
    p = tmp_path / "unsupported_vendor.dxf"
    doc = ezdxf.new("R2010")
    doc.modelspace().add_line((0, 0), (5, 0))
    doc.saveas(p)

    # Inject an unregistered/vendor custom DXF entity cleanly before ENDSEC
    raw = p.read_text(encoding="utf-8")
    raw_lines = raw.splitlines()
    # Find ENTITIES section end and inject CUSTOM_VENDOR_ENTITY cleanly before ENDSEC
    out_lines: list[str] = []
    in_entities = False
    injected = False
    i = 0
    while i < len(raw_lines):
        line = raw_lines[i]
        out_lines.append(line)
        if line.strip() == "ENTITIES" and i > 0 and raw_lines[i - 1].strip() == "2":
            in_entities = True
        elif in_entities and not injected and line.strip() == "ENDSEC" and i > 0 and raw_lines[i - 1].strip() == "0":
            # Replace the ENDSEC just appended with CUSTOM_VENDOR_ENTITY then ENDSEC
            out_lines.pop()
            out_lines.extend(
                [
                    "CUSTOM_VENDOR_ENTITY",
                    "  5",
                    "FFFF1",
                    "  8",
                    "0",
                    "100",
                    "AcDbEntity",
                    "  0",
                    "ENDSEC",
                ]
            )
            injected = True
            in_entities = False
        i += 1
    p.write_text("\n".join(out_lines) + "\n", encoding="utf-8")

    project, report = ExtractionPipeline().run(p)
    assert "LINE" in project.discovered_classes
    assert "CUSTOM_VENDOR_ENTITY" in project.discovered_classes
    assert "CUSTOM_VENDOR_ENTITY" in project.unsupported_classes
    assert any(u["native_class"] == "CUSTOM_VENDOR_ENTITY" and u["handle"] == "FFFF1" for u in project.unsupported_objects)
    vendor_ent = next(e for e in project.cad_document.cad_entities if e.entity_type == "CUSTOM_VENDOR_ENTITY")
    assert vendor_ent.is_supported is False
    assert vendor_ent.provenance == ProvenanceStatus.UNSUPPORTED
    assert report.validation.unknown_class_objects == 1
