"""Safe recursive-descent AST parser for PlanSwift formulas and templates (zero eval)."""

from __future__ import annotations

from dataclasses import dataclass
import re

from extraction_engine.formulas.lexer import FormulaLexError, Token, TokenType, tokenize_formula


class FormulaSyntaxError(ValueError):
    """Raised when a formula does not conform to supported grammar."""


@dataclass(frozen=True, slots=True)
class NumberLit:
    value: float


@dataclass(frozen=True, slots=True)
class StringLit:
    value: str


@dataclass(frozen=True, slots=True)
class BoolLit:
    value: bool


@dataclass(frozen=True, slots=True)
class BracketRef:
    inner: str


@dataclass(frozen=True, slots=True)
class UnaryOp:
    op: str
    operand: ASTNode


@dataclass(frozen=True, slots=True)
class BinaryOp:
    op: str
    left: ASTNode
    right: ASTNode


@dataclass(frozen=True, slots=True)
class CompareOp:
    op: str
    left: ASTNode
    right: ASTNode


@dataclass(frozen=True, slots=True)
class LogicOp:
    op: str  # AND | OR
    left: ASTNode
    right: ASTNode


@dataclass(frozen=True, slots=True)
class FuncCall:
    name: str
    args: tuple[ASTNode, ...]


@dataclass(frozen=True, slots=True)
class TemplateExpr:
    parts: tuple[tuple[bool, str], ...]  # (is_bracket, text_or_inner)


ASTNode = (
    NumberLit
    | StringLit
    | BoolLit
    | BracketRef
    | UnaryOp
    | BinaryOp
    | CompareOp
    | LogicOp
    | FuncCall
    | TemplateExpr
)

_TEMPLATE_XML_OR_TEXT_RE = re.compile(r"<[A-Za-z/?!]|\n")


class _RecursiveParser:
    def __init__(self, tokens: list[Token]) -> None:
        self.tokens = tokens
        self.pos = 0

    def peek(self) -> Token | None:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def advance(self) -> Token:
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok

    def parse(self) -> ASTNode:
        if not self.tokens:
            raise FormulaSyntaxError("Empty formula expression.")
        node = self.parse_logic_or()
        if self.pos < len(self.tokens):
            tok = self.tokens[self.pos]
            raise FormulaSyntaxError(f"Unexpected trailing token {tok.value!r} at pos {tok.position}")
        return node

    def parse_logic_or(self) -> ASTNode:
        node = self.parse_logic_and()
        while (tok := self.peek()) is not None and tok.kind == TokenType.IDENT and tok.value.lower() == "or":
            self.advance()
            right = self.parse_logic_and()
            node = LogicOp("OR", node, right)
        return node

    def parse_logic_and(self) -> ASTNode:
        node = self.parse_comparison()
        while (tok := self.peek()) is not None and tok.kind == TokenType.IDENT and tok.value.lower() == "and":
            self.advance()
            right = self.parse_comparison()
            node = LogicOp("AND", node, right)
        return node

    def parse_comparison(self) -> ASTNode:
        node = self.parse_additive()
        while (tok := self.peek()) is not None and tok.kind == TokenType.OP and tok.value in ("=", "<>", "<=", ">=", "<", ">"):
            op = self.advance().value
            right = self.parse_additive()
            node = CompareOp(op, node, right)
        return node

    def parse_additive(self) -> ASTNode:
        node = self.parse_multiplicative()
        while (tok := self.peek()) is not None and tok.kind == TokenType.OP and tok.value in ("+", "-"):
            op = self.advance().value
            right = self.parse_multiplicative()
            node = BinaryOp(op, node, right)
        return node

    def parse_multiplicative(self) -> ASTNode:
        node = self.parse_unary()
        while (tok := self.peek()) is not None and tok.kind == TokenType.OP and tok.value in ("*", "/"):
            op = self.advance().value
            right = self.parse_unary()
            node = BinaryOp(op, node, right)
        return node

    def parse_unary(self) -> ASTNode:
        tok = self.peek()
        if tok is not None and tok.kind == TokenType.OP and tok.value in ("+", "-"):
            op = self.advance().value
            return UnaryOp(op, self.parse_unary())
        if tok is not None and tok.kind == TokenType.IDENT and tok.value.lower() == "not":
            self.advance()
            return UnaryOp("not", self.parse_unary())
        return self.parse_power()

    def parse_power(self) -> ASTNode:
        node = self.parse_primary()
        tok = self.peek()
        if tok is not None and tok.kind == TokenType.OP and tok.value == "^":
            self.advance()
            right = self.parse_unary()
            return BinaryOp("^", node, right)
        return node

    def parse_primary(self) -> ASTNode:
        tok = self.peek()
        if tok is None:
            raise FormulaSyntaxError("Unexpected end of expression.")

        if tok.kind == TokenType.NUMBER:
            self.advance()
            return NumberLit(float(tok.value))

        if tok.kind == TokenType.STRING:
            self.advance()
            return StringLit(tok.value)

        if tok.kind == TokenType.BRACKET:
            self.advance()
            return BracketRef(tok.value)

        if tok.kind == TokenType.IDENT:
            ident = self.advance().value
            low = ident.lower()
            if low == "true":
                return BoolLit(True)
            if low == "false":
                return BoolLit(False)
            if (nxt := self.peek()) is not None and nxt.kind == TokenType.LPAREN:
                self.advance()
                args: list[ASTNode] = []
                if (close_tok := self.peek()) is not None and close_tok.kind != TokenType.RPAREN:
                    args.append(self.parse_logic_or())
                    while (comma_tok := self.peek()) is not None and comma_tok.kind == TokenType.COMMA:
                        self.advance()
                        args.append(self.parse_logic_or())
                end_tok = self.peek()
                if end_tok is None or end_tok.kind != TokenType.RPAREN:
                    raise FormulaSyntaxError(f"Expected ')' after arguments to {ident}()")
                self.advance()
                return FuncCall(ident, tuple(args))
            raise FormulaSyntaxError(f"Unknown bare identifier {ident!r} (expected bracket reference or function call)")

        if tok.kind == TokenType.LPAREN:
            self.advance()
            inner = self.parse_logic_or()
            close_tok = self.peek()
            if close_tok is None or close_tok.kind != TokenType.RPAREN:
                raise FormulaSyntaxError("Unclosed '(' parenthesis")
            self.advance()
            return inner

        raise FormulaSyntaxError(f"Unexpected token {tok.value!r} at pos {tok.position}")


def _extract_template_parts(expr: str) -> TemplateExpr | None:
    """Split a PlanSwift string/XML template (e.g. \"[Width]' x [Length]'\" or '<Points>...</Points>') into parts."""
    parts: list[tuple[bool, str]] = []
    i = 0
    n = len(expr)
    has_bracket = False
    buf: list[str] = []

    while i < n:
        if expr[i] == "[":
            if buf:
                parts.append((False, "".join(buf)))
                buf.clear()
            depth = 1
            start = i
            i += 1
            in_sq = False
            while i < n and depth > 0:
                c = expr[i]
                if c == "'":
                    in_sq = not in_sq
                elif not in_sq:
                    if c == "[":
                        depth += 1
                    elif c == "]":
                        depth -= 1
                i += 1
            if depth != 0:
                return None
            has_bracket = True
            parts.append((True, expr[start + 1 : i - 1]))
        else:
            buf.append(expr[i])
            i += 1

    if buf:
        parts.append((False, "".join(buf)))
    return TemplateExpr(tuple(parts)) if has_bracket else None


def parse_formula_ast(expr: str) -> ASTNode:
    """Parse a native PlanSwift formula string into a safe AST node (or TemplateExpr for XML/label templates)."""
    stripped = expr.strip()
    if not stripped:
        raise FormulaSyntaxError("Empty formula expression.")

    # Direct XML templates (<?xml...>, <Points>...) or multi-line label templates
    if _TEMPLATE_XML_OR_TEXT_RE.search(stripped):
        tpl = _extract_template_parts(expr)
        if tpl is not None:
            return tpl

    try:
        tokens = tokenize_formula(stripped)
        return _RecursiveParser(tokens).parse()
    except (FormulaLexError, FormulaSyntaxError) as exc:
        # Recognize PlanSwift formatted label templates with literal unit words/symbols like
        # "[Width]' W x [Length]' L (Priced per EA)" or "2x[Wall Width]x[Length]' Studs",
        # while STILL rejecting malformed arithmetic like "[A] + * [B]" or "[A] + ("
        tpl = _extract_template_parts(expr)
        if tpl is not None:
            lit_text = "".join(text for is_b, text in tpl.parts if not is_b)
            # Only accept template fallback if literal parts contain descriptive letters/quotes/hash
            # rather than dangling arithmetic operators (+, *, /, ^, unbalanced parens)
            has_desc_words = bool(re.search(r'[A-Za-z]{2,}|["\']', lit_text))
            has_broken_arith = bool(re.search(r"[+\*/^]\s*$|^\s*[*/^]|[(][^)]*$", lit_text.strip()))
            if has_desc_words and not has_broken_arith and lit_text.count("(") == lit_text.count(")"):
                return tpl
        raise FormulaSyntaxError(str(exc)) from exc
