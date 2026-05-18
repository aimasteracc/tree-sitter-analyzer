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


def calculate_complexity(node: Any) -> int:
    """Calculate cyclomatic complexity for a C++ syntax node."""
    count = 1
    stack = [node]

    while stack:
        current = stack.pop()
        if getattr(current, "type", None) in _DECISION_NODES:
            count += 1

        children = getattr(current, "children", None)
        if not children:
            continue

        try:
            stack.extend(children)
        except (TypeError, AttributeError):
            continue

    return count
