"""C++ complexity helpers."""

from typing import Any

_DECISION_NODES = frozenset(
    {
        "if_statement",
        "while_statement",
        "for_statement",
        "for_range_loop",
        "switch_statement",
        "case_statement",
        "conditional_expression",
        "catch_clause",
        "do_statement",
    }
)

# Short-circuit boolean operators each add a decision point, matching the
# Go/Rust/Swift convention. They must be counted ONLY as logical operators
# (operands of a binary_expression); in C++ the "&&" token is also the
# rvalue-reference declarator (e.g. ``T&& x``), which is NOT a branch.
_LOGICAL_OPERATORS = frozenset({"&&", "||"})


def _is_logical_operator(node: Any) -> bool:
    """True when ``node`` is a "&&"/"||" used as a boolean operator.

    Filters out the C++ rvalue-reference ``&&`` (parent ``reference_declarator``)
    so move constructors / rvalue-ref parameters do not inflate complexity.
    """
    if getattr(node, "type", None) not in _LOGICAL_OPERATORS:
        return False
    parent = getattr(node, "parent", None)
    return parent is not None and getattr(parent, "type", None) == "binary_expression"


def calculate_complexity(node: Any) -> int:
    """Calculate cyclomatic complexity for a C++ syntax node."""
    count = 1
    stack = [node]

    while stack:
        current = stack.pop()
        if getattr(current, "type", None) in _DECISION_NODES:
            count += 1
        elif _is_logical_operator(current):
            count += 1

        children = getattr(current, "children", None)
        if not children:
            continue

        try:
            stack.extend(children)
        except (TypeError, AttributeError):
            continue

    return count
