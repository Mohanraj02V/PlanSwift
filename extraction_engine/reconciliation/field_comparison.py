"""Field-level comparison between native package properties and COM runtime properties."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class FieldDiff(BaseModel):
    object_guid: str
    field_name: str
    diff_kind: str  # matched | package_only | com_only | computed_vs_formula | value_mismatch
    package_value: Any = None
    com_formula: Any = None
    com_result: Any = None


def compare_object_fields(
    object_guid: str,
    package_props: dict[str, str],
    com_props: dict[str, dict[str, Any]],
) -> list[FieldDiff]:
    """Compare package XML property values against COM formula + evaluated result maps."""
    diffs: list[FieldDiff] = []
    all_keys = sorted(set(package_props.keys()) | set(com_props.keys()))

    for key in all_keys:
        in_pkg = key in package_props
        in_com = key in com_props
        if in_pkg and not in_com:
            diffs.append(
                FieldDiff(
                    object_guid=object_guid,
                    field_name=key,
                    diff_kind="package_only",
                    package_value=package_props[key],
                )
            )
        elif in_com and not in_pkg:
            diffs.append(
                FieldDiff(
                    object_guid=object_guid,
                    field_name=key,
                    diff_kind="com_only",
                    com_formula=com_props[key].get("formula"),
                    com_result=com_props[key].get("result"),
                )
            )
        else:
            pkg_val = package_props[key]
            com_formula = com_props[key].get("formula")
            com_result = com_props[key].get("result")
            if com_result is not None and str(com_result) != str(pkg_val) and ("[" in str(pkg_val) or com_formula == pkg_val):
                kind = "computed_vs_formula"
            elif str(pkg_val) == str(com_result or com_formula or ""):
                kind = "matched"
            else:
                kind = "value_mismatch"
            diffs.append(
                FieldDiff(
                    object_guid=object_guid,
                    field_name=key,
                    diff_kind=kind,
                    package_value=pkg_val,
                    com_formula=com_formula,
                    com_result=com_result,
                )
            )
    return diffs
