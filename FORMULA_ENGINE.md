# Independent Formula Interpreter (`FORMULA_ENGINE.md`)

## 1. Design & Security Principles

- **Zero dynamic code execution**: Python `eval()` and `exec()` are never used anywhere in the codebase.
- **Custom lexer + recursive-descent AST parser**: Implemented in `extraction_engine/formulas/lexer.py`, `parser.py`, and `evaluator.py`.
- **Cycle protection & memoization**: Evaluates properties on-demand across the object graph with active recursion stack tracking (`cycle_path`) and memoization cache keyed by `(OBJECT_GUID, property_name_lower)`.
- **Zero quantity fabrication**: Missing job settings, unavailable image dimensions, missing page scale, and arbitrary custom scripts are explicitly reported as `unresolved` or `unsupported` with structured reason codes.

---

## 2. Supported PlanSwift Grammar & Features

### Operators & Precedence (lowest to highest)
1. Logical `OR`, `AND`, unary `NOT`
2. Comparisons `=`, `<>`, `<`, `>`, `<=`, `>=`
3. Addition `+`, Subtraction `-`
4. Multiplication `*`, Division `/` (divides by 0 rejected cleanly as `division_by_zero`)
5. Unary `+`, `-`
6. Exponentiation `^`
7. Parenthesized expressions `( ... )` and numbers (including leading decimals `.91`), single-quoted strings `'...'`, booleans (`True` → `1.0`, `False` → `0.0`, empty numeric property `""` → `0.0`).

### Built-In Functions
`RoundUp(x[, n])`, `RoundDown(x[, n])`, `Round(x[, n])`, `Int(x)`, `Floor(x)`, `Ceiling(x)` / `Ceil(x)`, `Abs(x)`, `Sqrt(x)`, `Min(...)`, `Max(...)`, `Sum(...)`, `Avg(...)`, `If(cond, a, b)` / `IIf(cond, a, b)`, `Sin`, `Cos`, `Tan`.

### PlanSwift Bracket Reference Resolution
- **`[Prop]`**: Case-insensitive property lookup on current object; falls back to implicit built-in virtual class defaults (`Point Count`, `Section Count`, `Segment Count`, `Linear Total`, `Area`, `Takeoff`, `Markup Each`, `Price Each`, `Cost Total`, `Markup Total`, `Price Total`, `Name`, `GUID`, `Type`) or parent Takeoff properties when evaluated on BOM child `Item`/`Part`/`Component`.
- **`[..]`**: Inherits same-named property from parent object.
- **`[..\Prop]`, `[..\..\Prop]`**: Walks N parent hops up the hierarchy.
- **`[\Job\Prop]`**: Resolves property from the root `<Item Name="Job">` node.
- **`[[PageGUID]\Name]`, `[[PageGUID]\Scale Units]`**: Evaluates inner `[PageGUID]` to a GUID and reads `TargetProp` on that target `CanonicalObject`.
- **`[[Shape]]`, `[[Wall Height]]`**: Double-bracket indirect local property lookup.
- **System variables & system functions**:
  - `[!Point Count]`, `[!Section Count]`, `[!Segment Count]`, `[!Linear Total]`, `[!Area]`
  - `[!TakeoffFolder]`, `[!TakeoffPath]`
  - `[!if(cond, a, b)]`, `[!sum(Prop)]`, `[!Units('Prop')]`
- **Label & XML `<Points>` string templates**: Resolves embedded `[...]` tokens into multiline descriptions (`[..\..\Name]\n[..\Takeoff] ...`) and `<Points>` symbol templates after safely evaluating `sep`.
- **Arithmetic literal properties**: Safely parses non-bracket math literals inside `Number` properties (e.g. `Material Coverage = '20 * 100' → 2000.0`).
- **Deterministic template scripts without PascalScript execution**: Recognizes PlanSwift's standard locale decimal-separator probe (`sep → '.'`) and `Note` scaled text-height template (`Result := [Text Size]`); marks any custom script `Expression="-1"` as `unsupported` (`unsupported_pascal_script`).

---

## 3. Structured Unresolved Diagnostics

| `calculation_reason` | Trigger Condition | Real Fixture Examples |
| :--- | :--- | :--- |
| `system_variable_unavailable` | `[!PageWidth]`, `[!PageHeight]`, `[!CU]` (Rule 3/5: no raster header reading or guessing) | `360` page dimension formulas in `project 4`; `84` in `Sample Project` |
| `missing_external_settings` | `[\Settings\...]` references PlanSwift desktop INI/registry settings absent from ZIP | `1,131` transparency/default formulas in `project 4`; `65` in `Sample Project` |
| `missing_dependency` | Referenced property/tax/pitch is absent from object and ancestors (e.g. empty `\Job\Sales Tax 1`) | `Cost Type` / `Tax1` / `Pitch` when omitted from XML |
| `missing_page_scale` | Geometric `[!Area]`/`[!Linear Total]` has points on an uncalibrated page without `ScaleX`/`ScaleY` | Synthetic uncalibrated Linear test & Section quantities |
| `circular_dependency` | Cycle detected via DFS or runtime recursion stack | `[A] -> [B] -> [A]` test case |
| `division_by_zero` | Denominator evaluates within `1e-12` of zero | `10 / [Zero]` test case |
| `unsupported_pascal_script` | Arbitrary `Expression="-1"` script outside recognized static templates | Custom multi-statement PascalScript test |

---

## 4. Verified Accuracy Results

- **`project 4.SwiftJob.zip` vs. Live PlanSwift 11 COM Oracle (`com_snapshot.json`)**: Across all **5,418** directly comparable evaluated formulas (excluding `Count Section.Texture` image-class coercion quirk), standalone AST evaluation matched PlanSwift 11 on **5,418 / 5,418 (100.00%)** expressions with **0 COM calls**.
- **`Sample Project.SwiftJob`**: Evaluated **949 / 1,517** formulas cleanly (the remaining 568 explicitly attributed to missing `PageWidth`/`PageHeight`, `\Settings\`, and omitted job tax/roof pitch properties), producing exact construction takeoff & BOM quantities:
  - `Conference Room` (`Area`): `500.378283 SQ FT`
  - `Carpet (Priced per SQ YD)` (`Material`): `55.597587 SQ YD`
  - `Exterior Walls` (`Linear` `Wall Area`): `264.948289 FT` linear → `2,384.534601 SQ FT` wall area
  - `5/8" Type X Drywall (Priced per EA)` (`Material` with `Round Qtys=True`): `RoundUp(2384.534601 / (4.5 * 8)) = 67 EA`.
