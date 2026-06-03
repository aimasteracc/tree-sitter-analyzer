"""Hyphae — a CSS-selector-inspired query DSL for the symbol graph.

Ported from the mycelium project (RFC-0003). Lets agents express graph queries
declaratively — ``.method:calls(#IndexShard)`` instead of chaining several
tool calls. The pipeline is the classic three stages:

    text → lexer.tokenize → parser.parse → evaluator.Evaluator.eval → [symbols]

Public entry point: :func:`select`, which wires all three stages against an
``ASTCache`` and returns matching symbols.
"""

from __future__ import annotations

from .ast import (
    AttributeSelector,
    Combined,
    PseudoClass,
    SelectorList,
    SimpleSelector,
)
from .evaluator import Evaluator
from .lexer import Token, tokenize
from .parser import HyphaeSyntaxError, parse

__all__ = [
    "AttributeSelector",
    "Combined",
    "Evaluator",
    "HyphaeSyntaxError",
    "PseudoClass",
    "SelectorList",
    "SimpleSelector",
    "Token",
    "parse",
    "tokenize",
]
