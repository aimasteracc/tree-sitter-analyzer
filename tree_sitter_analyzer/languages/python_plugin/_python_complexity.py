"""AST-node-based cyclomatic complexity for Python.

Replaces a ``re.findall(r"\\bkeyword\\b", text)`` counter that counted Python
keywords appearing as whole words inside comments, docstrings, and strings (a
function whose only body was a comment listing keywords scored 6), counted
``match`` arms per-``case``, and counted ``with`` (not a branch). This walks the
AST and counts each decision construct once, matching the construct-once
convention used by the other language plugins.
"""

from typing import Any

# Decision constructs, counted once each. ``match_statement`` (not each
# ``case_clause``) keeps a ``match`` construct-once; ``boolean_operator`` counts
# each ``and`` / ``or`` (Python's short-circuit operators); ``for_in_clause`` /
# ``if_clause`` count comprehension loops and filters. ``else`` / ``with`` are
# NOT decisions.
_PYTHON_DECISION_NODES = frozenset(
    {
        "if_statement",
        "elif_clause",
        "for_statement",
        "while_statement",
        "except_clause",
        "conditional_expression",  # ternary  a if c else b
        "match_statement",
        "boolean_operator",  # `and` / `or`
        "for_in_clause",  # comprehension loop
        "if_clause",  # comprehension filter
    }
)


def python_cyclomatic_complexity(node: Any) -> int:
    """Return ``1 + decision points`` for a Python function/method subtree."""
    count = 1
    stack = [node]
    while stack:
        current = stack.pop()
        if getattr(current, "type", None) in _PYTHON_DECISION_NODES:
            count += 1
        children = getattr(current, "children", None)
        if children:
            stack.extend(children)
    return count
