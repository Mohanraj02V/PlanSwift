"""Relational normalization helper exporting flat, deterministic record bundles for Django persistence."""

from __future__ import annotations

from typing import Any

from extraction_engine.core.extraction_result import CanonicalProject


def project_to_relational_bundle(project: CanonicalProject) -> dict[str, list[dict[str, Any]]]:
    """Flatten CanonicalProject into keyed relational tables preserving exact foreign keys."""
    pages = [p.model_dump(mode="json") for p in project.pages]
    objects = []
    properties = []
    measurements = []
    sections = []
    geometries = []
    points = []
    formulas = []
    formula_dependencies = []
    denotations = []
    remarks = []

    for obj in project.objects:
        objects.append(
            {
                "native_guid": obj.native_guid,
                "native_class": obj.native_class,
                "native_type": obj.native_type,
                "name": obj.name,
                "parent_guid": obj.parent_guid,
                "root_path": obj.root_path,
                "depth": obj.depth,
                "order_index": obj.order_index,
                "is_known_class": obj.is_known_class,
                "is_measurement_section": obj.is_measurement_section,
                "is_page": obj.is_page,
                "page_guid": obj.page_guid,
                "group_id": obj.group_id,
                "division": obj.division,
                "subdivision": obj.subdivision,
                "phase": obj.phase,
                "cost_code": obj.cost_code,
                "location": obj.location,
                "zone": obj.zone,
                "created_by": obj.created_by,
                "timestamp_raw": obj.timestamp_raw,
                "provenance": obj.provenance.value,
                "raw_attributes": obj.raw_attributes,
            }
        )
        for prop in obj.properties:
            d = prop.model_dump(mode="json")
            d["object_guid"] = obj.native_guid
            properties.append(d)
        for meas in obj.measurements:
            measurements.append(meas.model_dump(mode="json"))
        for sec in obj.sections:
            sd = sec.model_dump(mode="json", exclude={"geometry"})
            sections.append(sd)
        for geom in obj.geometries:
            gd = geom.model_dump(mode="json", exclude={"points"})
            geometries.append(gd)
            for pt in geom.points:
                pd = pt.model_dump(mode="json")
                pd["section_guid"] = geom.section_guid
                points.append(pd)
        for form in obj.formulas:
            fd = form.model_dump(mode="json", exclude={"dependencies"})
            formulas.append(fd)
            for dep in form.dependencies:
                dd = dep.model_dump(mode="json")
                dd["formula_key"] = form.formula_key
                formula_dependencies.append(dd)
        for den in obj.denotations:
            denotations.append(den.model_dump(mode="json"))
        for rem in obj.remarks:
            remarks.append(rem.model_dump(mode="json"))

    return {
        "pages": pages,
        "objects": objects,
        "properties": properties,
        "measurements": measurements,
        "sections": sections,
        "geometries": geometries,
        "points": points,
        "formulas": formulas,
        "formula_dependencies": formula_dependencies,
        "relationships": [r.model_dump(mode="json") for r in project.relationships],
        "assemblies": [a.model_dump(mode="json") for a in project.assemblies],
        "denotations": denotations,
        "remarks": remarks,
    }
