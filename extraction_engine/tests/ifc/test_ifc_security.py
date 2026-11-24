"""Verify IFC security bounds: signature mismatch, malformed STEP, size limit, and cyclic spatial relationships."""

from __future__ import annotations

from pathlib import Path

import ifcopenshell
import pytest

from extraction_engine.core.extraction_context import ExtractionConfig, SecurityValidationError
from extraction_engine.core.format_detector import UnsupportedFormatError
from extraction_engine.pipeline import ExtractionPipeline


def test_ifc_security_guards_and_cyclic_hierarchy(tmp_path: Path) -> None:
    # 1. Invalid .ifc content rejected cleanly
    bad = tmp_path / "fake.ifc"
    bad.write_text("Not an ISO-10303 STEP file", encoding="utf-8")
    with pytest.raises(UnsupportedFormatError):
        ExtractionPipeline().run(bad)

    # 2. Cyclic IfcRelAggregates caught gracefully without infinite recursion
    cyc_path = tmp_path / "cyclic_rel.ifc"
    model = ifcopenshell.file(schema="IFC4")
    a = model.create_entity("IfcBuilding", GlobalId=ifcopenshell.guid.new(), Name="A")
    b = model.create_entity("IfcBuilding", GlobalId=ifcopenshell.guid.new(), Name="B")
    model.create_entity("IfcRelAggregates", GlobalId=ifcopenshell.guid.new(), RelatingObject=a, RelatedObjects=[b])
    model.create_entity("IfcRelAggregates", GlobalId=ifcopenshell.guid.new(), RelatingObject=b, RelatedObjects=[a])
    model.write(str(cyc_path))

    project, _ = ExtractionPipeline().run(cyc_path)
    assert any("Cycle detected" in w for w in project.source_manifest.warnings)

    # 3. File size bound enforcement
    cfg = ExtractionConfig(ifc_max_file_bytes=50)
    with pytest.raises(SecurityValidationError, match="ifc_max_file_bytes"):
        ExtractionPipeline(cfg).run(cyc_path)
