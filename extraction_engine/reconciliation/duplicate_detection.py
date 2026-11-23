"""Duplicate object and duplicate file detection helpers."""

from __future__ import annotations

from extraction_engine.core.extraction_result import CanonicalProject
from extraction_engine.normalizers.identity_normalizer import canonical_guid_key


def detect_duplicate_guids_and_names(project: CanonicalProject) -> dict[str, object]:
    """Identify any duplicate native GUIDs (error) vs benign duplicate display names (normal in PlanSwift)."""
    by_guid: dict[str, list[str]] = {}
    by_name: dict[str, list[str]] = {}
    for obj in project.objects:
        gk = canonical_guid_key(obj.native_guid)
        by_guid.setdefault(gk, []).append(obj.name)
        by_name.setdefault(obj.name, []).append(obj.native_guid)

    duplicate_guids = {k: v for k, v in by_guid.items() if len(v) > 1}
    shared_display_names = {k: v for k, v in by_name.items() if len(v) > 1}
    return {
        "duplicate_guid_count": len(duplicate_guids),
        "duplicate_guids": duplicate_guids,
        "shared_display_name_count": len(shared_display_names),
        "shared_display_names_sample": dict(list(shared_display_names.items())[:25]),
    }
