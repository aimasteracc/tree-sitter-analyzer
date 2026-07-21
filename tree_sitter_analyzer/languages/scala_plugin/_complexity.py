"""Cyclomatic complexity calculation for Scala."""

from __future__ import annotations

from typing import Any

_SCALA_DECISION_TYPES: frozenset[str] = frozenset(
    {
        "if_expression",
        "match_expression",
        "for_expression",
        "while_expression",
        "catch_clause",
        # A ``case`` guard (``case n if cond =>``) is an extra conditional
        # branch and is counted in addition to the construct.
        "guard",
        # NOTE: ``case_clause`` is deliberately NOT counted. ``match`` counts
        # once via ``match_expression`` and ``catch`` once via ``catch_clause``
        # (construct-once), so counting each ``case_clause`` would over-count
        # both a multi-arm ``match`` and the ``case`` inside a ``catch``. A
        # standalone partial-function ``case_block`` (no enclosing match/catch)
        # is counted once via _scala_is_standalone_case_block. See #1090.
    }
)

# A ``case_block`` that is NOT the body of a ``match``/``catch`` is a partial
# function literal (``{ case ... }``) — itself one branching construct.
_SCALA_CASE_BLOCK_CONSTRUCT_PARENTS: frozenset[str] = frozenset(
    {"match_expression", "catch_clause"}
)

_SCALA_LOGIC_OP_TOKENS: frozenset[str] = frozenset({"&&", "||"})


def _safe_children(node: Any) -> list[Any]:
    """Return children list from a tree-sitter node, empty list on any error."""
    try:
        children = getattr(node, "children", None)
        if children is None:
            return []
        return list(children)
    except (TypeError, AttributeError):
        return []


def calculate_scala_complexity(node: Any) -> int:
    """Return cyclomatic complexity for a Scala function node.

    complexity = 1 + decision_points.
    Decision points: if_expression, match_expression, for_expression,
    while_expression, catch_clause, case_clause (non-leaf nodes),
    and ``&&`` / ``||`` operator_identifier leaf tokens.
    """
    decisions = 0
    stack = [node]
    while stack:
        cur = stack.pop()
        children = _safe_children(cur)
        is_leaf = len(children) == 0
        node_type = getattr(cur, "type", None)
        if not is_leaf and node_type in _SCALA_DECISION_TYPES:
            decisions += 1
        elif not is_leaf and node_type == "case_block":
            # Count a standalone partial-function ``{ case ... }`` once; the
            # ``case_block`` under a match/catch is already covered by
            # ``match_expression`` / ``catch_clause``.
            parent = getattr(cur, "parent", None)
            if (
                parent is None
                or getattr(parent, "type", None)
                not in _SCALA_CASE_BLOCK_CONSTRUCT_PARENTS
            ):
                decisions += 1
        elif is_leaf and node_type == "operator_identifier":
            try:
                text = cur.text.decode("utf-8") if cur.text else ""
            except (AttributeError, UnicodeDecodeError):
                text = ""
            if text in _SCALA_LOGIC_OP_TOKENS:
                decisions += 1
        stack.extend(children)
    return 1 + decisions
