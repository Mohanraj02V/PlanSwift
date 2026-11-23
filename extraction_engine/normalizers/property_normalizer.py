"""Property normalization preserving raw_value and parsed_value."""

from __future__ import annotations

from extraction_engine.core.extraction_result import CanonicalProject, ProvenanceStatus
from extraction_engine.normalizers.unit_normalizer import normalize_unit


def normalize_project_properties(project: CanonicalProject) -> None:
    """Populate normalized_value and normalized_unit on properties & measurements without mutating raw values."""
    page_scale_by_guid: dict[str, str | None] = {
        p.native_guid.upper(): p.scale_units for p in project.pages
    }

    for obj in project.objects:
        obj_scale = None
        su_prop = obj.get_property("Scale Units")
        if su_prop and su_prop.raw_value.strip():
            obj_scale = su_prop.raw_value.strip()
        elif obj.page_guid:
            obj_scale = page_scale_by_guid.get(obj.page_guid.upper())

        for prop in obj.properties:
            if prop.units:
                norm_u, is_dyn = normalize_unit(prop.units, fallback_scale_unit=obj_scale)
                prop.normalized_unit = norm_u
                if prop.parsed_value is not None and not prop.is_formula and not is_dyn:
                    prop.normalized_value = prop.parsed_value
                    prop.normalization_provenance = ProvenanceStatus.NORMALIZED
            elif not prop.is_formula and prop.parsed_value is not None:
                prop.normalized_value = prop.parsed_value
                prop.normalization_provenance = ProvenanceStatus.NORMALIZED

        for meas in obj.measurements:
            if meas.unit:
                norm_u, _ = normalize_unit(meas.unit, fallback_scale_unit=obj_scale)
                meas.normalized_unit = norm_u
            if meas.derived_quantity is not None and not meas.is_default_template_value:
                meas.normalized_quantity = meas.derived_quantity
