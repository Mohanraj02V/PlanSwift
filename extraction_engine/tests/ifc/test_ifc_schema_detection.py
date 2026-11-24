"""Verify IFC schema support detection matching installed IfcOpenShell schemas accurately."""

from __future__ import annotations

from pathlib import Path

import ifcopenshell
import pytest

from extraction_engine.adapters.ifc.ifc_document_reader import get_supported_ifc_schemas
from extraction_engine.core.extraction_context import SecurityValidationError
from extraction_engine.pipeline import ExtractionPipeline


@pytest.mark.parametrize("schema_name", ["IFC2X3", "IFC4", "IFC4X3_ADD2"])
def test_ifc_supported_schemas_detection(tmp_path: Path, schema_name: str) -> None:
    supported = get_supported_ifc_schemas()
    if schema_name not in supported:
        pytest.skip(f"{schema_name} not compiled into installed ifcopenshell {ifcopenshell.version}")

    p = tmp_path / f"model_{schema_name}.ifc"
    f = ifcopenshell.file(schema=schema_name)
    f.create_entity("IfcProject", GlobalId=ifcopenshell.guid.new(), Name=f"Proj_{schema_name}")
    f.write(str(p))

    project, report = ExtractionPipeline().run(p)
    assert report.adapter_used == "ifc_ifcopenshell"
    assert project.cad_document.schema_name == schema_name
    assert report.validation.overall_status == "verified_correct"


def test_ifc_unsupported_schema_rejected_honestly(tmp_path: Path) -> None:
    p = tmp_path / "unsupported_ifc4x2.ifc"
    p.write_text(
        "ISO-10303-21;\nHEADER;\nFILE_DESCRIPTION(('ViewDefinition'),'2;1');\n"
        "FILE_NAME('x.ifc','2026-01-01T00:00:00',('a'),('b'),'c','d','e');\n"
        "FILE_SCHEMA(('IFC99_UNSUPPORTED'));\nENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n",
        encoding="utf-8",
    )
    with pytest.raises(SecurityValidationError, match="Unsupported IFC schema"):
        ExtractionPipeline().run(p)
