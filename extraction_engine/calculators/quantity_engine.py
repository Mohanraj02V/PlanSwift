"""Independent Quantity & Measurement Calculation Engine preserving native vs reconstructed vs calculated lineage."""

from __future__ import annotations

from extraction_engine.core.extraction_result import (
    CanonicalMeasurement,
    CanonicalObject,
    CanonicalProject,
    ProvenanceStatus,
)
from extraction_engine.formulas.evaluator import FormulaEvaluator
from extraction_engine.normalizers.unit_normalizer import (
    convert_area_to_sq_meters,
    convert_length_to_meters,
    normalize_unit,
    scale_area_unit_label,
)


def _derive_reconstructed_takeoff_qty(obj: CanonicalObject, Evaluator: FormulaEvaluator) -> tuple[float | None, str]:
    cls_low = obj.native_class.lower()
    if cls_low == "count":
        res = Evaluator.evaluate_property(obj.native_guid, "Point Count")
        return res.numeric, res.unit or "EA"
    if cls_low in ("linear", "segment"):
        res = Evaluator.evaluate_property(obj.native_guid, "Linear Total")
        if res.status == ProvenanceStatus.UNRESOLVED:
            return None, ""
        return res.numeric, res.unit or ""
    if cls_low in ("area", "volume", "perimeter"):
        res = Evaluator.evaluate_property(obj.native_guid, "Area")
        if res.status == ProvenanceStatus.UNRESOLVED:
            return None, ""
        return res.numeric, res.unit or ""
    return None, ""


def compute_project_quantities(project: CanonicalProject) -> None:
    """Populate standalone calculated & reconstructed quantities across takeoffs, sections, and BOM items."""
    evaluator = FormulaEvaluator(project)
    obj_by_guid = {o.native_guid.upper(): o for o in project.objects}

    for obj in project.objects:
        cls_low = obj.native_class.lower()
        formulas_by_prop = {f.property_name.lower(): f for f in obj.formulas}

        # 1. Takeoff items (Count, Linear, Segment, Area, Volume, Perimeter)
        if not obj.is_measurement_section and cls_low in ("count", "linear", "segment", "area", "volume", "perimeter"):
            recon_qty, recon_unit = _derive_reconstructed_takeoff_qty(obj, evaluator)
            qty_formula = formulas_by_prop.get("qty")
            qty_prop = obj.get_property("Qty")
            qty_meas = next((m for m in obj.measurements if m.property_name == "Qty"), None)

            calc_qty: float | None = None
            calc_inputs: dict = {}
            calc_unit = ""
            if qty_formula and qty_formula.evaluation_status in (ProvenanceStatus.CALCULATED, ProvenanceStatus.RECONSTRUCTED):
                calc_qty = qty_formula.calculated_numeric
                calc_inputs = qty_formula.calculation_inputs
                calc_unit = qty_formula.calculation_unit
            elif qty_prop and not qty_prop.is_formula and isinstance(qty_prop.parsed_value, (int, float)):
                calc_qty = float(qty_prop.parsed_value)

            final_unit = (
                (qty_prop.input_units or qty_prop.units or "")
                if qty_prop
                else ""
            )
            if final_unit.lower() in ("[scale units]", "[..\\scale units]", ""):
                final_unit = calc_unit or recon_unit or ("EA" if cls_low == "count" else "")

            si_qty, si_unit = _convert_to_si(calc_qty if calc_qty is not None else recon_qty, final_unit, cls_low)

            if qty_meas is not None:
                qty_meas.reconstructed_quantity = recon_qty
                qty_meas.calculated_quantity = calc_qty
                if calc_qty is not None:
                    qty_meas.derived_quantity = calc_qty
                    qty_meas.status = ProvenanceStatus.CALCULATED
                    qty_meas.provenance_classification = ProvenanceStatus.CALCULATED.value
                elif recon_qty is not None:
                    qty_meas.derived_quantity = recon_qty
                    qty_meas.status = ProvenanceStatus.RECONSTRUCTED
                    qty_meas.provenance_classification = ProvenanceStatus.RECONSTRUCTED.value
                else:
                    qty_meas.status = ProvenanceStatus.UNRESOLVED
                    qty_meas.provenance_classification = ProvenanceStatus.UNRESOLVED.value
                if final_unit:
                    qty_meas.unit = final_unit
                if si_qty is not None:
                    qty_meas.normalized_quantity = si_qty
                    qty_meas.normalized_unit = si_unit
                qty_meas.calculation_inputs = calc_inputs

            # Also track Wall Area / Cost Total / Price Total when defined as formulas on Takeoff items
            for extra_prop in ("Wall Area", "Cost Total", "Price Total", "Volume"):
                ef = formulas_by_prop.get(extra_prop.lower())
                if ef and ef.calculated_numeric is not None:
                    if not any(m.property_name == extra_prop for m in obj.measurements):
                        ep = obj.get_property(extra_prop)
                        obj.measurements.append(
                            CanonicalMeasurement(
                                measurement_key=f"{obj.native_guid}:{extra_prop}",
                                object_guid=obj.native_guid,
                                measurement_type=obj.native_class,
                                property_name=extra_prop,
                                raw_formula=ef.raw_expression,
                                native_stored_value=ef.raw_expression,
                                calculated_quantity=ef.calculated_numeric,
                                derived_quantity=ef.calculated_numeric,
                                unit=(ep.input_units or ep.units or "") if ep else "",
                                calculation_formula=ef.raw_expression,
                                calculation_inputs=ef.calculation_inputs,
                                provenance_classification=ProvenanceStatus.CALCULATED.value,
                                status=ProvenanceStatus.CALCULATED,
                            )
                        )

        # 2. Assembly/Material/Labor BOM children (class Item / Part / Component with Qty / Qty Formula)
        elif not obj.is_page and not obj.is_measurement_section and cls_low in ("item", "part", "component") and obj.depth >= 2:
            qty_prop = obj.get_property("Qty")
            if qty_prop is None:
                continue
            qty_formula = formulas_by_prop.get("qty")
            calc_qty = qty_formula.calculated_numeric if qty_formula else None
            if calc_qty is None and not qty_prop.is_formula and isinstance(qty_prop.parsed_value, (int, float)):
                calc_qty = float(qty_prop.parsed_value)
                status = ProvenanceStatus.NATIVE
            elif calc_qty is not None:
                status = ProvenanceStatus.CALCULATED
            elif qty_formula is not None:
                status = qty_formula.evaluation_status
            else:
                continue

            unit_str = (qty_prop.input_units or qty_prop.units or "").strip()
            existing = next((m for m in obj.measurements if m.property_name == "Qty"), None)
            if existing is None:
                obj.measurements.append(
                    CanonicalMeasurement(
                        measurement_key=f"{obj.native_guid}:Qty",
                        object_guid=obj.native_guid,
                        measurement_type=obj.native_type or obj.native_class,
                        property_name="Qty",
                        raw_formula=qty_prop.raw_value if qty_prop.is_formula else None,
                        native_stored_value=qty_prop.raw_value,
                        calculated_quantity=calc_qty,
                        derived_quantity=calc_qty,
                        unit=unit_str,
                        precision=qty_prop.decimal_places,
                        calculation_formula=qty_prop.raw_value if qty_prop.is_formula else "",
                        calculation_inputs=qty_formula.calculation_inputs if qty_formula else {},
                        provenance_classification=status.value,
                        status=status,
                    )
                )

    # 3. Populate AssemblyComponent.calculated_quantity cleanly
    for asm in project.assemblies:
        for comp in asm.components:
            comp_obj = obj_by_guid.get(comp.native_guid.upper())
            if comp_obj is None:
                continue
            m = next((mm for mm in comp_obj.measurements if mm.property_name == "Qty"), None)
            if m and m.calculated_quantity is not None:
                comp.calculated_quantity = m.calculated_quantity


def _convert_to_si(val: float | None, unit: str, cls_low: str) -> tuple[float | None, str]:
    if val is None or not unit:
        return None, ""
    u_low = unit.strip().lower()
    if u_low in ("ea", "each", "count"):
        return round(val, 6), "each"
    if u_low.startswith("sq ") or "ft^2" in u_low or "sqft" in u_low or "m^2" in u_low or cls_low == "area":
        base = u_low.replace("sq ", "").strip() if u_low.startswith("sq ") else u_low.replace("^2", "").replace("sq", "").strip()
        m2 = convert_area_to_sq_meters(val, base)
        if m2 is not None:
            return m2, "m^2"
    m = convert_length_to_meters(val, u_low)
    if m is not None:
        return m, "m"
    norm, is_dyn = normalize_unit(unit)
    if not is_dyn and norm:
        return round(val, 6), norm
    return None, ""
