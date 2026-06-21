"""Shared AST-node-based cyclomatic complexity for the JS/TS plugins.

Replaces the previous keyword-substring *text* counting, which counted any
keyword that merely appeared as a substring of an identifier, string, or
comment (the ``for`` in ``formatter``, the ``if`` in ``notify``, every keyword
inside a ``/* ... */`` comment) and counted each ``switch`` ``case`` arm
separately. This walks the AST and counts each decision construct once,
matching the construct-once convention used by the other language plugins.
"""

from typing import Any

from ._complexity_logical import is_executable_logical_operator

# Decision constructs, counted once each. ``switch_case`` is deliberately
# excluded: the ``switch_statement`` itself is the single decision point
# (construct-once), consistent with #1090 (C/C++) and the other plugins.
# ``for_in_statement`` covers both ``for-in`` and ``for-of``.
_DECISION_NODES = frozenset(
    {
        "if_statement",
        "for_statement",
        "for_in_statement",
        "while_statement",
        "do_statement",
        "switch_statement",
        "catch_clause",
        "ternary_expression",
    }
)

# Short-circuit operators, each a decision point: ``&&`` / ``||`` and the
# nullish-coalescing ``??`` (also short-circuiting; matches the PHP plugin,
# which counts ``??``). In JS/TS these are always boolean/coalescing operators
# (no rvalue-reference form), so there are no non-executable anchors to exclude.
_SHORT_CIRCUIT_OPERATORS = frozenset({"&&", "||", "??"})
_NO_ANCHORS: frozenset[str] = frozenset()


def count_decision_complexity(node: Any) -> int:
    """Return ``1 + decision points`` for a function/method subtree."""
    count = 1
    stack = [node]
    while stack:
        current = stack.pop()
        node_type = getattr(current, "type", None)
        if node_type in _DECISION_NODES:
            count += 1
        elif node_type in _SHORT_CIRCUIT_OPERATORS and is_executable_logical_operator(
            current, _NO_ANCHORS
        ):
            count += 1
        children = getattr(current, "children", None)
        if children:
            stack.extend(children)
    return count
