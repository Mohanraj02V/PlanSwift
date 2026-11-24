"""Lexical analyzer for native PlanSwift formula expressions (zero eval)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re


class TokenType(str, Enum):
    NUMBER = "NUMBER"
    STRING = "STRING"
    BRACKET = "BRACKET"
    IDENT = "IDENT"
    OP = "OP"
    LPAREN = "LPAREN"
    RPAREN = "RPAREN"
    COMMA = "COMMA"


@dataclass(frozen=True, slots=True)
class Token:
    kind: TokenType
    value: str
    position: int


class FormulaLexError(ValueError):
    """Raised when a formula string contains invalid lexical tokens."""


_NUMBER_RE = re.compile(r"^(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?")
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*")


def tokenize_formula(expr: str) -> list[Token]:
    """Tokenize a PlanSwift expression into typed lexical tokens, preserving nested [...] brackets."""
    tokens: list[Token] = []
    i = 0
    n = len(expr)

    while i < n:
        ch = expr[i]
        if ch.isspace():
            i += 1
            continue

        if ch == "(":
            tokens.append(Token(TokenType.LPAREN, "(", i))
            i += 1
            continue

        if ch == ")":
            tokens.append(Token(TokenType.RPAREN, ")", i))
            i += 1
            continue

        if ch == ",":
            tokens.append(Token(TokenType.COMMA, ",", i))
            i += 1
            continue

        if ch == "[":
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
                raise FormulaLexError(f"Unclosed '[' bracket at position {start}")
            inner = expr[start + 1 : i - 1]
            tokens.append(Token(TokenType.BRACKET, inner, start))
            continue

        if ch == "'":
            start = i
            i += 1
            chars: list[str] = []
            closed = False
            while i < n:
                c = expr[i]
                if c == "'":
                    if i + 1 < n and expr[i + 1] == "'":
                        chars.append("'")
                        i += 2
                        continue
                    closed = True
                    i += 1
                    break
                chars.append(c)
                i += 1
            if not closed:
                raise FormulaLexError(f"Unclosed string literal at position {start}")
            tokens.append(Token(TokenType.STRING, "".join(chars), start))
            continue

        two = expr[i : i + 2]
        if two in ("<>", "<=", ">="):
            tokens.append(Token(TokenType.OP, two, i))
            i += 2
            continue

        if ch in "+-*/^=<>":
            tokens.append(Token(TokenType.OP, ch, i))
            i += 1
            continue

        num_match = _NUMBER_RE.match(expr[i:])
        if num_match:
            val = num_match.group(0)
            tokens.append(Token(TokenType.NUMBER, val, i))
            i += len(val)
            continue

        id_match = _IDENT_RE.match(expr[i:])
        if id_match:
            val = id_match.group(0)
            tokens.append(Token(TokenType.IDENT, val, i))
            i += len(val)
            continue

        raise FormulaLexError(f"Unexpected character {ch!r} at position {i}")

    return tokens
