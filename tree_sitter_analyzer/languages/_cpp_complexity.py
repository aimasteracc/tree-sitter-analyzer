"""C++ complexity helpers."""

from typing import Any

from ._complexity_logical import is_executable_logical_operator

# A switch counts ONCE (the "switch_statement" node), per the cross-language
# construct-once convention shared by Go/Rust/Swift/Java/C#. "case_statement"
# is deliberately excluded — counting each case (and the default) on top of the
# switch over-counted C/C++ relative to every other language.
_DECISION_NODES = frozenset(
    {
        "if_statement",
        "while_statement",
        "for_statement",
        "for_range_loop",
        "switch_statement",
        "conditional_expression",
        "catch_clause",
        "do_statement",
    }
)

# Short-circuit boolean operators each add a decision point, matching the
# Go/Rust/Swift convention. They are counted ONLY as logical operators
# (operands of a binary_expression) driving executable control flow; "&&" in a
# non-body context — the rvalue-reference declarator ``T&& x`` (parent is not a
# binary_expression), a ``noexcept`` / ``requires`` specifier, a preprocessor
# ``#if`` condition, a default argument, or a ``static_assert`` — is not a
# branch and must not inflate complexity.
_LOGICAL_OPERATORS = frozenset({"&&", "||"})
_NON_EXECUTABLE_ANCHORS = frozenset(
    {
        "noexcept",
        "requires_clause",
        "preproc_if",
        "preproc_elif",
        "optional_parameter_declaration",
        "static_assert_declaration",
    }
)


def _is_logical_operator(node: Any) -> bool:
    """True when ``node`` is a "&&"/"||" used as an executable boolean branch."""
    if getattr(node, "type", None) not in _LOGICAL_OPERATORS:
        return False
    return is_executable_logical_operator(node, _NON_EXECUTABLE_ANCHORS)


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
