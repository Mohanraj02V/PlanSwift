"""Adapter for structured payloads emitted by the Windows x64 PlanSwift COM connector."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from extraction_engine.core.extraction_context import ExtractionContext
from extraction_engine.core.extraction_registry import ExtractionRegistry
from extraction_engine.core.extraction_result import (
    CanonicalObject,
    CanonicalProject,
    CanonicalProperty,
    ProvenanceRecord,
    ProvenanceStatus,
)
from extraction_engine.core.source_manifest import SourceManifest


class PlanSwiftCOMPayloadAdapter:
    """Normalizes validated JSON snapshots uploaded by VortexenPlanSwiftConnector.exe."""

    adapter_name = "planswift_com_connector"
    adapter_version = "1.0.0"

    def __init__(self, payload: dict[str, Any] | None = None, registry: ExtractionRegistry | None = None) -> None:
        self.payload = payload or {}
        self.registry = registry or ExtractionRegistry()

    def can_handle(self, source_path: Path | None = None, payload: dict[str, Any] | None = None) -> bool:
        target = payload if payload is not None else self.payload
        return bool(target and target.get("source_system") == "PlanSwiftCOM" and "objects" in target)

    def inspect_source(self, source_path: Path, ctx: ExtractionContext) -> SourceManifest:
        raise NotImplementedError("COM payload adapter operates on JSON connector payloads rather than archive files.")

    def extract(self, ctx: ExtractionContext, manifest: SourceManifest | None = None) -> CanonicalProject:
        if not self.payload:
            raise ValueError("COM connector JSON payload is empty.")
        raw_objects = self.payload.get("objects", [])
        objects: list[CanonicalObject] = []
        discovered_classes: dict[str, int] = {}
        unsupported_classes: dict[str, int] = {}
        provenances: list[ProvenanceRecord] = []

        for item in raw_objects:
            native_guid = item.get("native_guid", "")
            native_class = item.get("native_class", "Unknown")
            behavior = self.registry.describe_class(native_class, item.get("native_type", ""))
            props: list[CanonicalProperty] = []
            for p_name, p_data in item.get("properties", {}).items():
                formula = p_data.get("formula")
                result = p_data.get("result")
                props.append(
                    CanonicalProperty(
                        native_property_guid=p_data.get("property_guid") or f"{native_guid}:{p_name}",
                        name=p_name,
                        property_class=p_data.get("property_class", "Text"),
                        raw_value=str(formula if formula is not None else (result if result is not None else "")),
                        parsed_value=result,
                        is_formula=bool(formula and "[" in str(formula)),
                        provenance=ProvenanceStatus.API_EXTRACTED,
                    )
                )
            obj = CanonicalObject(
                native_guid=native_guid,
                native_class=native_class,
                native_type=item.get("native_type", ""),
                name=item.get("name", ""),
                parent_guid=item.get("parent_guid"),
                depth=int(item.get("depth", 0)),
                child_guids=list(item.get("child_guids", [])),
                is_known_class=behavior.known,
                is_measurement_section=behavior.role == "measurement_section",
                is_page=behavior.role == "page",
                properties=props,
                provenance=ProvenanceStatus.API_EXTRACTED,
            )
            objects.append(obj)
            discovered_classes[native_class] = discovered_classes.get(native_class, 0) + 1
            if not behavior.known:
                unsupported_classes[native_class] = unsupported_classes.get(native_class, 0) + 1
            provenances.append(
                ProvenanceRecord(
                    source_adapter=self.adapter_name,
                    source_file=f"com://{self.payload.get('prog_id', 'PlanSwift')}",
                    source_object_guid=native_guid,
                    source_class=native_class,
                    status=ProvenanceStatus.API_EXTRACTED,
                    extraction_run_id=ctx.run_id,
                )
            )

        proj_meta = self.payload.get("project", {})
        return CanonicalProject(
            native_guid=proj_meta.get("native_guid", objects[0].native_guid if objects else ""),
            name=proj_meta.get("name", objects[0].name if objects else "COM Project"),
            objects=objects,
            discovered_classes=discovered_classes,
            unsupported_classes=unsupported_classes,
            provenance_records=provenances,
        )
