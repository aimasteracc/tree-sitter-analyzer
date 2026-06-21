"""Shared helper for counting short-circuit boolean operators in cyclomatic
complexity across the C-family plugins (C / C++ / C# / Java).

Each ``&&`` / ``||`` adds one decision point — but ONLY when it drives
executable control flow. A boolean token can also appear in non-executable
contexts (C++ ``noexcept`` / ``requires`` specifiers, preprocessor ``#if``
conditions, default parameter values, attributes / annotations). Counting
those would inflate the complexity of an otherwise branch-free function, so
the anchor of the logical expression is checked against a per-language set of
non-executable anchor node types.
"""

from typing import Any

# Ancestors that are skipped when locating a logical expression's "anchor"
# (the first ancestor that is not part of the same boolean expression).
_TRANSPARENT_ANCESTORS = frozenset({"binary_expression", "parenthesized_expression"})


def is_executable_logical_operator(
    node: Any, non_executable_anchors: frozenset[str]
) -> bool:
    """Return True when a ``&&`` / ``||`` token is an executable branch.

    ``node`` must be the ``&&`` / ``||`` leaf. It counts as a decision point
    only when it is an operand of a ``binary_expression`` (filtering out the
    C++ rvalue-reference ``&&`` declarator) AND the expression's anchor — the
    first ancestor above the chained ``binary_expression`` / parenthesis nodes
    — is not one of ``non_executable_anchors`` (e.g. ``noexcept``,
    ``requires_clause``, ``preproc_if``, a parameter default, an attribute).
    """
    parent = getattr(node, "parent", None)
    if parent is None or getattr(parent, "type", None) != "binary_expression":
        return False

    anchor: Any = parent
    while (
        anchor is not None and getattr(anchor, "type", None) in _TRANSPARENT_ANCESTORS
    ):
        anchor = getattr(anchor, "parent", None)

    return (
        anchor is not None
        and getattr(anchor, "type", None) not in non_executable_anchors
    )
