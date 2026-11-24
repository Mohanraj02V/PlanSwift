"""Safe, dependency-aware PlanSwift formula evaluator with cycle & unresolved provenance tracking."""

from __future__ import annotations

from dataclasses import dataclass, field
import math
import re
from typing import Any

from extraction_engine.core.extraction_result import (
    CanonicalFormula,
    CanonicalObject,
    CanonicalPage,
    CanonicalProject,
    CanonicalProperty,
    ProvenanceStatus,
)
from extraction_engine.formulas.parser import (
    ASTNode,
    BinaryOp,
    BoolLit,
    BracketRef,
    CompareOp,
    FormulaSyntaxError,
    FuncCall,
    LogicOp,
    NumberLit,
    StringLit,
    TemplateExpr,
    UnaryOp,
    parse_formula_ast,
)
from extraction_engine.normalizers.unit_normalizer import normalize_unit

_NUMERIC_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")
_CROSS_OBJ_RE = re.compile(r"^\[([^\[\]]+)\]\\(.+)$", re.DOTALL)
_SYSTEM_FUNC_RE = re.compile(r"^!([A-Za-z_][A-Za-z0-9_]*)\((.*)\)$", re.DOTALL)
_PATH_PREFIX_RE = re.compile(r"^((?:\.\.\\)+)(.+)$", re.DOTALL)
_TAKEOFF_CLASSES = frozenset({"count", "linear", "segment", "area", "perimeter", "volume"})
_CHILD_INHERIT_FROM_TAKEOFF_CLASSES = frozenset({"item", "part", "component"})

# Known deterministic PlanSwift template scripts (recognized structurally without PascalScript execution)
_SEP_SCRIPT_MARKER = "if '[septest]' = 'error - invalid expression' then"
_TEXT_HEIGHT_SCRIPT_MARKER = "item.getpropertyresultasfloat('[pageguid]\\scalex')"


class FormulaEvalError(Exception):
    """Structured non-fatal evaluation failure preserving unresolved/unsupported reason."""

    def __init__(self, reason: str, message: str = "") -> None:
        super().__init__(message or reason)
        self.reason = reason
        self.message = message or reason


@dataclass
class EvalResult:
    status: ProvenanceStatus
    value: Any = None
    numeric: float | None = None
    unit: str = ""
    reason: str = ""
    inputs: dict[str, Any] = field(default_factory=dict)

    @property
    def display_str(self) -> str:
        if self.value is None:
            return ""
        if isinstance(self.value, bool):
            return "True" if self.value else "False"
        if isinstance(self.value, float):
            if math.isfinite(self.value) and abs(self.value - round(self.value)) < 1e-9:
                return str(int(round(self.value)))
            return f"{self.value:.6f}".rstrip("0").rstrip(".")
        return str(self.value)


def _format_num(val: float) -> Any:
    if abs(val - round(val)) < 1e-9:
        return int(round(val))
    return round(val, 6)


def _to_number(val: Any) -> float:
    if val is None or val == "":
        return 0.0
    if isinstance(val, bool):
        return 1.0 if val else 0.0
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        s = val.strip()
        if s == "":
            return 0.0
        low = s.lower()
        if low == "true":
            return 1.0
        if low == "false":
            return 0.0
        if _NUMERIC_RE.match(s):
            return float(s)
    raise FormulaEvalError("non_numeric_operand", f"Cannot coerce {val!r} to number.")


def _to_bool(val: Any) -> bool:
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return val != 0.0
    if isinstance(val, str):
        low = val.strip().lower()
        if low in ("true", "-1", "1", "yes"):
            return True
        if low in ("false", "0", "no", ""):
            return False
    return bool(val)


def _split_top_level_args(arg_str: str) -> list[str]:
    args: list[str] = []
    cur: list[str] = []
    paren = 0
    bracket = 0
    in_sq = False
    for ch in arg_str:
        if ch == "'":
            in_sq = not in_sq
            cur.append(ch)
            continue
        if not in_sq:
            if ch == "(":
                paren += 1
            elif ch == ")":
                paren = max(0, paren - 1)
            elif ch == "[":
                bracket += 1
            elif ch == "]":
                bracket = max(0, bracket - 1)
            elif ch == "," and paren == 0 and bracket == 0:
                args.append("".join(cur).strip())
                cur.clear()
                continue
        cur.append(ch)
    if cur or args:
        args.append("".join(cur).strip())
    return args


class FormulaEvaluator:
    """Evaluates native PlanSwift formulas safely across a CanonicalProject."""

    def __init__(self, project: CanonicalProject) -> None:
        self.project = project
        self.obj_by_guid: dict[str, CanonicalObject] = {o.native_guid.upper(): o for o in project.objects}
        self.props_ci: dict[str, dict[str, CanonicalProperty]] = {}
        self.children_by_guid: dict[str, list[CanonicalObject]] = {}
        self.sections_by_takeoff: dict[str, list[CanonicalObject]] = {}
        self.pages_by_guid: dict[str, CanonicalPage] = {p.native_guid.upper(): p for p in project.pages}
        self.job_obj: CanonicalObject | None = next((o for o in project.objects if o.depth == 0), None)
        self._memo: dict[tuple[str, str], EvalResult] = {}
        self._active_stack: list[tuple[str, str]] = []
        self._ast_cache: dict[str, ASTNode] = {}

        for obj in project.objects:
            gkey = obj.native_guid.upper()
            pmap: dict[str, CanonicalProperty] = {}
            for p in obj.properties:
                if p.name:
                    pmap.setdefault(p.name.lower(), p)
            self.props_ci[gkey] = pmap
            if obj.parent_guid:
                pkey = obj.parent_guid.upper()
                self.children_by_guid.setdefault(pkey, []).append(obj)
                if obj.is_measurement_section:
                    self.sections_by_takeoff.setdefault(pkey, []).append(obj)

    def evaluate_all(self) -> None:
        """Evaluate every CanonicalFormula across all objects in the project."""
        for obj in self.project.objects:
            for formula in obj.formulas:
                res = self.evaluate_property(obj.native_guid, formula.property_name, formula_obj=formula)
                formula.evaluation_status = res.status
                formula.calculated_value = res.display_str if res.status in (ProvenanceStatus.CALCULATED, ProvenanceStatus.RECONSTRUCTED) else None
                formula.calculated_numeric = res.numeric if res.status in (ProvenanceStatus.CALCULATED, ProvenanceStatus.RECONSTRUCTED) else None
                formula.calculation_unit = res.unit
                formula.calculation_reason = res.reason
                formula.calculation_inputs = res.inputs

                # Update dependency resolution flags for UI/DB inspection
                if res.status in (ProvenanceStatus.CALCULATED, ProvenanceStatus.RECONSTRUCTED):
                    for dep in formula.dependencies:
                        dep.resolved = True
                    formula.unresolved_references = []
                elif res.reason == "circular_dependency":
                    formula.has_circular_dependency = True

    def evaluate_property(
        self,
        obj_guid: str,
        prop_name: str,
        formula_obj: CanonicalFormula | None = None,
    ) -> EvalResult:
        """Evaluate a named property (formula, literal, or built-in virtual property) on obj_guid."""
        gkey = obj_guid.upper()
        pkey = prop_name.lower()
        cache_key = (gkey, pkey)

        if cache_key in self._memo:
            return self._memo[cache_key]

        if cache_key in self._active_stack:
            idx = self._active_stack.index(cache_key)
            cyc = [f"{g}::{p}" for g, p in self._active_stack[idx:]] + [f"{gkey}::{pkey}"]
            if formula_obj is not None:
                formula_obj.has_circular_dependency = True
                formula_obj.circular_path = cyc
            return EvalResult(
                status=ProvenanceStatus.UNRESOLVED,
                reason="circular_dependency",
                inputs={"cycle_path": cyc},
            )

        obj = self.obj_by_guid.get(gkey)
        if obj is None:
            return EvalResult(status=ProvenanceStatus.UNRESOLVED, reason="missing_object")

        self._active_stack.append(cache_key)
        try:
            prop = self.props_ci.get(gkey, {}).get(pkey)
            result = self._evaluate_prop_inner(obj, pkey, prop, formula_obj=formula_obj)
        finally:
            self._active_stack.pop()

        self._memo[cache_key] = result
        return result

    def _evaluate_prop_inner(
        self,
        obj: CanonicalObject,
        pkey: str,
        prop: CanonicalProperty | None,
        formula_obj: CanonicalFormula | None = None,
    ) -> EvalResult:
        if prop is not None:
            # 1. Explicit PascalScript Expression=-1
            if prop.is_expression_script:
                res = self._handle_pascal_script(obj, prop)
                return res

            # 2. Explicit Formula property (contains [...])
            if prop.is_formula:
                if formula_obj and formula_obj.has_circular_dependency:
                    return EvalResult(
                        status=ProvenanceStatus.UNRESOLVED,
                        reason="circular_dependency",
                        inputs={"cycle_path": formula_obj.circular_path},
                    )
                res = self._eval_expression(obj, prop.name, prop.raw_value, prop_unit=prop.units or prop.input_units or "")
                # PlanSwift numeric properties coerce empty referenced values (e.g. Line Width='[Width]' when Width='') to 0
                if res.status == ProvenanceStatus.CALCULATED and prop.property_class in ("Number", "Slider") and res.value in ("", None):
                    res = EvalResult(
                        status=ProvenanceStatus.CALCULATED,
                        value=0.0,
                        numeric=0.0,
                        unit=res.unit,
                        inputs=res.inputs,
                    )
                return res

            # 3. Literal property value
            raw = prop.raw_value
            trimmed = raw.strip()
            unit = prop.units or prop.input_units or ""
            if isinstance(prop.parsed_value, bool):
                return EvalResult(
                    status=ProvenanceStatus.NATIVE,
                    value=prop.parsed_value,
                    numeric=1.0 if prop.parsed_value else 0.0,
                    unit=unit,
                )
            if isinstance(prop.parsed_value, (int, float)):
                return EvalResult(
                    status=ProvenanceStatus.NATIVE,
                    value=prop.parsed_value,
                    numeric=float(prop.parsed_value),
                    unit=unit,
                )
            if trimmed == "":
                # Empty literal in PlanSwift behaves as 0 in numeric formulas, "" in text formulas
                return EvalResult(status=ProvenanceStatus.NATIVE, value="", numeric=None, unit=unit)
            if _NUMERIC_RE.match(trimmed):
                num = float(trimmed)
                return EvalResult(status=ProvenanceStatus.NATIVE, value=num, numeric=num, unit=unit)
            # Some numeric properties in PlanSwift XML store pure arithmetic expressions without brackets (e.g. '20 * 100')
            if (prop.property_class in ("Number", "Slider") or prop.parse_formula == "-1") and any(op in trimmed for op in ("+", "-", "*", "/", "^")):
                try:
                    expr_ast = parse_formula_ast(trimmed)
                    if not isinstance(expr_ast, TemplateExpr):
                        inputs_tmp: dict[str, Any] = {}
                        val, _ = self._eval_node(obj, prop.name, expr_ast, inputs_tmp)
                        num = _to_number(val)
                        return EvalResult(
                            status=ProvenanceStatus.CALCULATED,
                            value=num,
                            numeric=num,
                            unit=unit,
                            inputs={"arithmetic_literal": trimmed},
                        )
                except (FormulaSyntaxError, FormulaEvalError):
                    pass
            return EvalResult(status=ProvenanceStatus.NATIVE, value=raw, numeric=None, unit=unit)

        # 4. Implicit PlanSwift virtual class defaults when property is omitted in XML
        virtual = self._eval_virtual_property(obj, pkey)
        if virtual is not None:
            return virtual

        # 5. Child Item/Part/Component inside a Takeoff parent inherits un-overridden takeoff metrics
        if obj.parent_guid and (
            obj.native_class.lower() in _CHILD_INHERIT_FROM_TAKEOFF_CLASSES
            or (obj.native_class.lower() == "linear" and pkey == "area")
        ):
            parent = self.obj_by_guid.get(obj.parent_guid.upper())
            if parent is not None and (
                parent.native_class.lower() in _TAKEOFF_CLASSES
                or parent.native_class.lower() in _CHILD_INHERIT_FROM_TAKEOFF_CLASSES
            ):
                parent_res = self.evaluate_property(parent.native_guid, pkey)
                if parent_res.status != ProvenanceStatus.UNRESOLVED or parent_res.reason not in ("missing_dependency", "missing_object"):
                    return parent_res

        return EvalResult(status=ProvenanceStatus.UNRESOLVED, reason="missing_dependency")

    def _handle_pascal_script(self, obj: CanonicalObject, prop: CanonicalProperty) -> EvalResult:
        low = prop.raw_value.lower()
        if _SEP_SCRIPT_MARKER in low:
            return EvalResult(
                status=ProvenanceStatus.CALCULATED,
                value=".",
                numeric=None,
                inputs={"script_pattern": "planswift_decimal_separator_probe"},
            )
        if _TEXT_HEIGHT_SCRIPT_MARKER in low and "result := [text size]" in low:
            ts = self.evaluate_property(obj.native_guid, "Text Size")
            if ts.status in (ProvenanceStatus.NATIVE, ProvenanceStatus.CALCULATED, ProvenanceStatus.RECONSTRUCTED):
                return EvalResult(
                    status=ProvenanceStatus.CALCULATED,
                    value=ts.value,
                    numeric=ts.numeric,
                    inputs={"[Text Size]": ts.value, "script_pattern": "planswift_note_text_height"},
                )
        return EvalResult(
            status=ProvenanceStatus.UNSUPPORTED,
            reason="unsupported_pascal_script",
        )

    def _eval_virtual_property(self, obj: CanonicalObject, pkey: str) -> EvalResult | None:
        if pkey == "name":
            return EvalResult(status=ProvenanceStatus.NATIVE, value=obj.name)
        if pkey == "guid":
            return EvalResult(status=ProvenanceStatus.NATIVE, value=obj.native_guid)
        if pkey == "type" and obj.native_type:
            return EvalResult(status=ProvenanceStatus.NATIVE, value=obj.native_type)

        cls_low = obj.native_class.lower()
        is_meas_or_takeoff = cls_low in _TAKEOFF_CLASSES or cls_low.endswith("section")

        if is_meas_or_takeoff:
            if pkey == "point count":
                return self._eval_sysvar(obj, "Point Count", {})
            if pkey == "section count":
                return self._eval_sysvar(obj, "Section Count", {})
            if pkey == "segment count":
                return self._eval_sysvar(obj, "Segment Count", {})
            if pkey == "linear total":
                return self._eval_sysvar(obj, "Linear Total", {})
            if pkey == "area" and cls_low in ("area", "area section", "perimeter", "perimeter section", "volume", "volume section"):
                return self._eval_sysvar(obj, "Area", {})
            if pkey == "takeoff":
                if "count" in cls_low:
                    return self.evaluate_property(obj.native_guid, "Point Count")
                if "linear" in cls_low or "segment" in cls_low:
                    return self.evaluate_property(obj.native_guid, "Linear Total")
                if "area" in cls_low or "perimeter" in cls_low or "volume" in cls_low:
                    return self.evaluate_property(obj.native_guid, "Area")

        # Built-in financial & estimating chain when omitted from XML
        is_est_obj = cls_low in _TAKEOFF_CLASSES or cls_low in _CHILD_INHERIT_FROM_TAKEOFF_CLASSES
        if is_est_obj:
            if pkey == "cost each":
                return EvalResult(status=ProvenanceStatus.CALCULATED, value=0.0, numeric=0.0, inputs={"default": 0.0})
            if pkey == "markup %":
                return EvalResult(status=ProvenanceStatus.CALCULATED, value=0.0, numeric=0.0, inputs={"default": 0.0})
            if pkey == "markup each":
                return self._eval_expression(obj, "Markup Each", "[Cost Each] * ([Markup %] / 100)")
            if pkey == "price each":
                return self._eval_expression(obj, "Price Each", "[Cost Each] + [Markup Each]")
            if pkey == "cost total":
                return self._eval_expression(obj, "Cost Total", "[Qty] * [Cost Each]")
            if pkey == "markup total":
                return self._eval_expression(obj, "Markup Total", "[Qty] * [Markup Each]")
            if pkey == "price total":
                return self._eval_expression(obj, "Price Total", "[Qty] * [Price Each]")

        return None

    def _eval_expression(
        self,
        obj: CanonicalObject,
        current_prop_name: str,
        raw_expr: str,
        prop_unit: str = "",
    ) -> EvalResult:
        ast_node = self._ast_cache.get(raw_expr)
        if ast_node is None:
            try:
                ast_node = parse_formula_ast(raw_expr)
                self._ast_cache[raw_expr] = ast_node
            except FormulaSyntaxError as exc:
                return EvalResult(status=ProvenanceStatus.UNRESOLVED, reason="syntax_error", inputs={"detail": str(exc)})

        collected_inputs: dict[str, Any] = {}
        try:
            val, used_reconstructed = self._eval_node(obj, current_prop_name, ast_node, collected_inputs)
        except FormulaEvalError as exc:
            return EvalResult(status=ProvenanceStatus.UNRESOLVED, reason=exc.reason, inputs=collected_inputs)

        num: float | None = None
        if isinstance(val, bool):
            num = 1.0 if val else 0.0
        elif isinstance(val, (int, float)):
            num = float(val)
        elif isinstance(val, str) and _NUMERIC_RE.match(val.strip()):
            num = float(val.strip())

        resolved_unit = self._resolve_unit_string(obj, prop_unit)
        status = ProvenanceStatus.CALCULATED
        return EvalResult(
            status=status,
            value=val,
            numeric=num,
            unit=resolved_unit,
            inputs=collected_inputs,
        )

    def _resolve_unit_string(self, obj: CanonicalObject, raw_unit: str) -> str:
        if not raw_unit or "[" not in raw_unit:
            return raw_unit
        if raw_unit.strip().lower() == "[!cu]":
            return ""
        tpl_res = self._eval_expression(obj, "_unit", raw_unit)
        return tpl_res.display_str if tpl_res.status == ProvenanceStatus.CALCULATED else raw_unit

    def _eval_node(
        self,
        obj: CanonicalObject,
        current_prop_name: str,
        node: ASTNode,
        inputs: dict[str, Any],
    ) -> tuple[Any, bool]:
        if isinstance(node, NumberLit):
            return node.value, False
        if isinstance(node, StringLit):
            return node.value, False
        if isinstance(node, BoolLit):
            return node.value, False

        if isinstance(node, TemplateExpr):
            out_parts: list[str] = []
            any_recon = False
            for is_bracket, text in node.parts:
                if not is_bracket:
                    out_parts.append(text)
                else:
                    res = self._resolve_bracket(obj, current_prop_name, text, inputs)
                    if res.status == ProvenanceStatus.RECONSTRUCTED:
                        any_recon = True
                    out_parts.append(res.display_str)
            return "".join(out_parts), any_recon

        if isinstance(node, BracketRef):
            res = self._resolve_bracket(obj, current_prop_name, node.inner, inputs)
            return res.value, (res.status == ProvenanceStatus.RECONSTRUCTED)

        if isinstance(node, UnaryOp):
            operand, r1 = self._eval_node(obj, current_prop_name, node.operand, inputs)
            if node.op == "not":
                return not _to_bool(operand), r1
            num = _to_number(operand)
            return (-num if node.op == "-" else +num), r1

        if isinstance(node, BinaryOp):
            left, r1 = self._eval_node(obj, current_prop_name, node.left, inputs)
            right, r2 = self._eval_node(obj, current_prop_name, node.right, inputs)
            lnum = _to_number(left)
            rnum = _to_number(right)
            if node.op == "+":
                res_val = lnum + rnum
            elif node.op == "-":
                res_val = lnum - rnum
            elif node.op == "*":
                res_val = lnum * rnum
            elif node.op == "/":
                if abs(rnum) < 1e-12:
                    raise FormulaEvalError("division_by_zero", "Division by zero in formula.")
                res_val = lnum / rnum
            elif node.op == "^":
                res_val = math.pow(lnum, rnum)
            else:
                raise FormulaEvalError("unsupported_operator", f"Unsupported operator {node.op!r}")
            if not math.isfinite(res_val):
                raise FormulaEvalError("non_finite_result", "Calculation produced non-finite value.")
            return res_val, (r1 or r2)

        if isinstance(node, CompareOp):
            left, r1 = self._eval_node(obj, current_prop_name, node.left, inputs)
            right, r2 = self._eval_node(obj, current_prop_name, node.right, inputs)
            cmp_res = self._compare_values(node.op, left, right)
            return cmp_res, (r1 or r2)

        if isinstance(node, LogicOp):
            left, r1 = self._eval_node(obj, current_prop_name, node.left, inputs)
            lb = _to_bool(left)
            if node.op == "AND" and not lb:
                return False, r1
            if node.op == "OR" and lb:
                return True, r1
            right, r2 = self._eval_node(obj, current_prop_name, node.right, inputs)
            rb = _to_bool(right)
            return (lb and rb if node.op == "AND" else lb or rb), (r1 or r2)

        if isinstance(node, FuncCall):
            return self._eval_func(obj, current_prop_name, node, inputs)

        raise FormulaEvalError("unsupported_ast", f"Unsupported AST node {type(node).__name__}")

    def _compare_values(self, op: str, left: Any, right: Any) -> bool:
        # Compare numerically if both coerce or one is bool/number, otherwise case-insensitive string compare
        try:
            ln = _to_number(left) if not isinstance(left, str) or left.strip() == "" or _NUMERIC_RE.match(left.strip()) or left.strip().lower() in ("true", "false") else None
            rn = _to_number(right) if not isinstance(right, str) or right.strip() == "" or _NUMERIC_RE.match(right.strip()) or right.strip().lower() in ("true", "false") else None
        except FormulaEvalError:
            ln = rn = None

        if ln is not None and rn is not None:
            a, b = ln, rn
        else:
            a, b = str(left or "").strip().lower(), str(right or "").strip().lower()

        if op == "=":
            return a == b
        if op in ("<>", "!="):
            return a != b
        if op == "<":
            return a < b
        if op == ">":
            return a > b
        if op == "<=":
            return a <= b
        if op == ">=":
            return a >= b
        return False

    def _eval_func(
        self,
        obj: CanonicalObject,
        current_prop_name: str,
        node: FuncCall,
        inputs: dict[str, Any],
    ) -> tuple[Any, bool]:
        fname = node.name.lower()
        if fname in ("if", "iif"):
            if len(node.args) != 3:
                raise FormulaEvalError("syntax_error", f"{node.name} requires 3 arguments.")
            cond, r1 = self._eval_node(obj, current_prop_name, node.args[0], inputs)
            branch = node.args[1] if _to_bool(cond) else node.args[2]
            val, r2 = self._eval_node(obj, current_prop_name, branch, inputs)
            return val, (r1 or r2)

        vals_flags = [self._eval_node(obj, current_prop_name, a, inputs) for a in node.args]
        vals = [vf[0] for vf in vals_flags]
        any_r = any(vf[1] for vf in vals_flags)

        if fname == "roundup":
            v = _to_number(vals[0])
            digits = int(_to_number(vals[1])) if len(vals) > 1 else 0
            factor = 10.0 ** digits
            # Small epsilon guards IEEE-754 boundary like 67.000000000001
            return (math.ceil(v * factor - 1e-12) / factor if v >= 0 else math.floor(v * factor + 1e-12) / factor), any_r
        if fname == "rounddown":
            v = _to_number(vals[0])
            digits = int(_to_number(vals[1])) if len(vals) > 1 else 0
            factor = 10.0 ** digits
            return (math.floor(v * factor + 1e-12) / factor if v >= 0 else math.ceil(v * factor - 1e-12) / factor), any_r
        if fname == "round":
            v = _to_number(vals[0])
            digits = int(_to_number(vals[1])) if len(vals) > 1 else 0
            return (round(v, digits) if digits > 0 else float(round(v))), any_r
        if fname == "int":
            return float(int(_to_number(vals[0]))), any_r
        if fname == "floor":
            return float(math.floor(_to_number(vals[0]) + 1e-12)), any_r
        if fname in ("ceil", "ceiling"):
            return float(math.ceil(_to_number(vals[0]) - 1e-12)), any_r
        if fname == "abs":
            return abs(_to_number(vals[0])), any_r
        if fname == "sqrt":
            v = _to_number(vals[0])
            if v < 0:
                raise FormulaEvalError("domain_error", "Square root of negative number.")
            return math.sqrt(v), any_r
        if fname == "min":
            return min(_to_number(x) for x in vals), any_r
        if fname == "max":
            return max(_to_number(x) for x in vals), any_r
        if fname == "sum":
            return sum(_to_number(x) for x in vals), any_r
        if fname == "avg":
            if not vals:
                raise FormulaEvalError("division_by_zero", "Avg of 0 arguments.")
            return sum(_to_number(x) for x in vals) / len(vals), any_r
        if fname == "sin":
            return math.sin(_to_number(vals[0])), any_r
        if fname == "cos":
            return math.cos(_to_number(vals[0])), any_r
        if fname == "tan":
            return math.tan(_to_number(vals[0])), any_r

        raise FormulaEvalError("unsupported_function", f"Unsupported function {node.name!r}")

    def _resolve_bracket(
        self,
        obj: CanonicalObject,
        current_prop_name: str,
        inner: str,
        inputs: dict[str, Any],
    ) -> EvalResult:
        token_key = f"[{inner}]"
        res = self._resolve_bracket_inner(obj, current_prop_name, inner, inputs)
        if res.status == ProvenanceStatus.UNRESOLVED or res.status == ProvenanceStatus.UNSUPPORTED:
            raise FormulaEvalError(res.reason or "missing_dependency", f"Unresolved token {token_key}")
        inputs[token_key] = _format_num(res.numeric) if res.numeric is not None and not isinstance(res.value, bool) else res.value
        return res

    def _resolve_bracket_inner(
        self,
        obj: CanonicalObject,
        current_prop_name: str,
        inner: str,
        inputs: dict[str, Any],
    ) -> EvalResult:
        # 1. Parent self-property inheritance: [..]
        if inner == "..":
            if not obj.parent_guid:
                return EvalResult(status=ProvenanceStatus.UNRESOLVED, reason="missing_dependency")
            return self.evaluate_property(obj.parent_guid, current_prop_name)

        # 2. Ancestor property path: [..\Prop] or [..\..\Prop] or [..\..\!Units('Takeoff')]
        path_m = _PATH_PREFIX_RE.match(inner)
        if path_m:
            prefix, target_part = path_m.group(1), path_m.group(2)
            hops = prefix.count("..\\")
            cur = obj
            for _ in range(hops):
                if not cur.parent_guid:
                    return EvalResult(status=ProvenanceStatus.UNRESOLVED, reason="missing_dependency")
                cur = self.obj_by_guid.get(cur.parent_guid.upper())
                if cur is None:
                    return EvalResult(status=ProvenanceStatus.UNRESOLVED, reason="missing_dependency")
            if target_part.startswith("!"):
                return self._eval_sysvar(cur, target_part[1:], inputs)
            return self.evaluate_property(cur.native_guid, target_part)

        # 3. Absolute project paths: [\Job\...] or [\Settings\...]
        if inner.startswith("\\"):
            parts = [p for p in inner.split("\\") if p]
            if not parts:
                return EvalResult(status=ProvenanceStatus.UNRESOLVED, reason="missing_dependency")
            root_seg = parts[0].lower()
            if root_seg == "settings":
                return EvalResult(status=ProvenanceStatus.UNRESOLVED, reason="missing_external_settings")
            if root_seg == "job" and len(parts) >= 2 and self.job_obj is not None:
                cur = self.job_obj
                for seg in parts[1:-1]:
                    kids = self.children_by_guid.get(cur.native_guid.upper(), [])
                    nxt = next((k for k in kids if k.name.lower() == seg.lower()), None)
                    if nxt is None:
                        return EvalResult(status=ProvenanceStatus.UNRESOLVED, reason="missing_dependency")
                    cur = nxt
                return self.evaluate_property(cur.native_guid, parts[-1])
            return EvalResult(status=ProvenanceStatus.UNRESOLVED, reason="missing_dependency")

        # 4. System variable or system function: [!...]
        if inner.startswith("!"):
            return self._eval_sysvar(obj, inner[1:], inputs)

        # 5. Cross-object indirection: [[PageGUID]\Name]
        cross_m = _CROSS_OBJ_RE.match(inner)
        if cross_m:
            guid_expr, target_prop = cross_m.group(1), cross_m.group(2)
            # First resolve guid_expr on current object (or treat as direct GUID literal)
            if guid_expr.startswith("{"):
                target_guid = guid_expr
            else:
                g_res = self.evaluate_property(obj.native_guid, guid_expr)
                if g_res.status == ProvenanceStatus.UNRESOLVED:
                    return g_res
                target_guid = str(g_res.value or "").strip()
            if not target_guid or target_guid.upper() not in self.obj_by_guid:
                return EvalResult(status=ProvenanceStatus.UNRESOLVED, reason="missing_dependency")
            return self.evaluate_property(target_guid, target_prop)

        # 6. Double-bracket local property indirection: [[Shape]], [[Wall Height]]
        if inner.startswith("[") and inner.endswith("]"):
            ref_name_res = self._resolve_bracket_inner(obj, current_prop_name, inner[1:-1], inputs)
            if ref_name_res.status in (ProvenanceStatus.UNRESOLVED, ProvenanceStatus.UNSUPPORTED):
                return ref_name_res
            target_name = str(ref_name_res.value or "").strip()
            if not target_name:
                return EvalResult(status=ProvenanceStatus.UNRESOLVED, reason="missing_dependency")
            return self.evaluate_property(obj.native_guid, target_name)

        # 7. Standard property reference on current object
        return self.evaluate_property(obj.native_guid, inner)

    def _eval_sysvar(
        self,
        obj: CanonicalObject,
        sys_body: str,
        inputs: dict[str, Any],
    ) -> EvalResult:
        low = sys_body.strip().lower()

        if low in ("pagewidth", "pageheight"):
            # Rule 3 & Rule 5: XML does not store image pixel width/height; never read raster TIFFs
            return EvalResult(status=ProvenanceStatus.UNRESOLVED, reason="system_variable_unavailable")

        if low == "cu":
            return EvalResult(status=ProvenanceStatus.UNRESOLVED, reason="system_variable_unavailable")

        if low == "point count":
            if obj.is_measurement_section:
                cnt = sum(g.point_count for g in obj.geometries)
            else:
                secs = self.sections_by_takeoff.get(obj.native_guid.upper(), [])
                cnt = sum(g.point_count for s in secs for g in s.geometries)
            return EvalResult(status=ProvenanceStatus.RECONSTRUCTED, value=float(cnt), numeric=float(cnt), unit="EA")

        if low == "section count":
            secs = self.sections_by_takeoff.get(obj.native_guid.upper(), [])
            cnt = len(secs)
            return EvalResult(status=ProvenanceStatus.RECONSTRUCTED, value=float(cnt), numeric=float(cnt), unit="EA")

        if low == "segment count":
            def _sec_segs(s: CanonicalObject) -> int:
                pts = sum(g.point_count for g in s.geometries)
                if "segment" in s.native_class.lower():
                    return pts // 2
                return max(pts - 1, 0)

            cnt = _sec_segs(obj) if obj.is_measurement_section else sum(_sec_segs(s) for s in self.sections_by_takeoff.get(obj.native_guid.upper(), []))
            return EvalResult(status=ProvenanceStatus.RECONSTRUCTED, value=float(cnt), numeric=float(cnt), unit="EA")

        if low == "linear total":
            return self._aggregate_geometry_metric(obj, kind="length")

        if low == "area":
            return self._aggregate_geometry_metric(obj, kind="area")

        if low == "takeofffolder":
            # Immediate folder under Job root in root_path (e.g. Job/Takeoff/Item -> Takeoff)
            parts = [p for p in obj.root_path.split("/") if p]
            folder = parts[1] if len(parts) >= 2 else ""
            return EvalResult(status=ProvenanceStatus.CALCULATED, value=folder, numeric=None)

        if low == "takeoffpath":
            # Subfolder path beneath Takeoff folder before object name
            parts = [p for p in obj.root_path.split("/") if p]
            subpath = "/".join(parts[2:-1]) if len(parts) >= 4 else ""
            return EvalResult(status=ProvenanceStatus.CALCULATED, value=subpath, numeric=None)

        func_m = _SYSTEM_FUNC_RE.match("!" + sys_body.strip())
        if func_m:
            fname = func_m.group(1).lower()
            raw_args = _split_top_level_args(func_m.group(2))
            if fname == "if" and len(raw_args) == 3:
                cond_res = self._eval_expression(obj, "_if_cond", raw_args[0])
                if cond_res.status == ProvenanceStatus.UNRESOLVED:
                    return cond_res
                chosen = raw_args[1] if _to_bool(cond_res.value) else raw_args[2]
                return self._eval_expression(obj, "_if_branch", chosen)
            if fname == "sum" and len(raw_args) == 1:
                prop_target = raw_args[0].strip().strip("'\"")
                children = self.children_by_guid.get(obj.native_guid.upper(), [])
                total = 0.0
                for ch in children:
                    ch_res = self.evaluate_property(ch.native_guid, prop_target)
                    if ch_res.numeric is not None:
                        total += ch_res.numeric
                return EvalResult(status=ProvenanceStatus.CALCULATED, value=total, numeric=total)
            if fname == "units" and len(raw_args) == 1:
                target_p = raw_args[0].strip().strip("'\"")
                p = self.props_ci.get(obj.native_guid.upper(), {}).get(target_p.lower())
                raw_u = (p.units or p.input_units or "") if p else ""
                if not raw_u and obj.parent_guid:
                    # Try page Scale Units fallback for Takeoff units
                    pg_u = self.evaluate_property(obj.native_guid, "Scale Units")
                    if pg_u.value:
                        raw_u = str(pg_u.value)
                resolved_u = self._resolve_unit_string(obj, raw_u)
                return EvalResult(status=ProvenanceStatus.CALCULATED, value=resolved_u, numeric=None)

        return EvalResult(status=ProvenanceStatus.UNRESOLVED, reason="system_variable_unavailable")

    def _aggregate_geometry_metric(self, obj: CanonicalObject, kind: str) -> EvalResult:
        target_secs = [obj] if obj.is_measurement_section else self.sections_by_takeoff.get(obj.native_guid.upper(), [])
        total = 0.0
        unit_label = ""
        for sec in target_secs:
            for g in sec.geometries:
                if g.point_count == 0:
                    continue
                if not g.is_calibrated:
                    return EvalResult(status=ProvenanceStatus.UNRESOLVED, reason="missing_page_scale")
                if kind == "length" and g.calibrated_length is not None:
                    total += g.calibrated_length
                    unit_label = g.scale_unit or unit_label
                elif kind == "area" and g.calibrated_area is not None:
                    total += g.calibrated_area
                    unit_label = g.calibrated_unit or unit_label
        total = round(total, 6)
        return EvalResult(
            status=ProvenanceStatus.RECONSTRUCTED,
            value=total,
            numeric=total,
            unit=unit_label,
        )


def evaluate_project_formulas(project: CanonicalProject) -> None:
    """Resolve dependency metadata and run safe topological AST evaluation on a CanonicalProject."""
    FormulaEvaluator(project).evaluate_all()
