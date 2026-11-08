"""Which listed caller a grep hit belongs to.

TSA attributes a call to the *innermost* enclosing definition (smallest span,
``cache/call_edges.py``). Definitions are named functions, methods, named
arrow functions / function expressions (their own name or the ``const`` they
initialize) in TS/JS, methods / constructors in Java, including those of
an anonymous class body, and every named ``fun`` in Kotlin (member, top-level,
extension, local). Anonymous callbacks, lambdas and initializer blocks
are not definitions, so their calls belong to the enclosing definition, or to
the ``<module>`` pseudo-caller at the call line when there is none.

The oracle derives the owner from the tree-sitter parse itself and never from
the answer's ``end_line``: a hit counts as ``caller`` only when exactly that
owner (name and start line) is listed. A different attribution rule in the
code under test can therefore only turn a hit residual, never hide one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .oracle_syntax import is_field, text

MODULE = "<module>"
TS_DEFINITIONS = {
    "function_declaration",
    "method_definition",
    "arrow_function",
    "function_expression",
}
JAVA_DEFINITIONS = {"method_declaration", "constructor_declaration"}
#: Kotlin: every named ``fun`` (member, top-level, extension, local, or inside an
#: object expression). Lambdas, anonymous functions, ``init`` blocks, secondary
#: constructors, getters / setters and property initializers are not
#: definitions: their calls belong to the enclosing ``fun`` or to ``<module>``.
KOTLIN_DEFINITIONS = {"function_declaration"}
_DECLARATION_WRAPPERS = (
    "lexical_declaration",
    "variable_declaration",
    "export_statement",
)


@dataclass(frozen=True)
class Owner:
    """The definition a position belongs to: its name and the lines its entry may start on."""

    name: str
    starts: frozenset[int]


def _ts_name(node: Any) -> str | None:
    if node.type in ("arrow_function", "function_expression"):
        own = node.child_by_field_name("name")
        if own is not None:
            return text(own)
        current, parent = node, node.parent
        while parent is not None and parent.type == "parenthesized_expression":
            current, parent = parent, parent.parent
        if (
            parent is not None
            and parent.type == "variable_declarator"
            and is_field(current, parent, "value")
        ):
            name = parent.child_by_field_name("name")
            if name is not None and name.type == "identifier":
                return text(name)
        return None
    name = node.child_by_field_name("name")
    if name is None:
        return None
    value = text(name)
    if name.type == "string" or (value[:1] in "'\"`" and len(value) >= 2):
        return value[1:-1]
    if name.type in ("identifier", "property_identifier"):
        return value
    return None  # computed / #private names: TSA's walk records no definition


def _java_name(node: Any) -> str | None:
    name = node.child_by_field_name("name")
    return text(name) if name is not None else None


def _starts(node: Any) -> frozenset[int]:
    lines = {node.start_point[0] + 1}
    name = node.child_by_field_name("name")
    if name is not None:
        lines.add(name.start_point[0] + 1)
    outer = node.parent
    while outer is not None and outer.type in (
        "parenthesized_expression",
        "variable_declarator",
        *_DECLARATION_WRAPPERS,
    ):
        lines.add(outer.start_point[0] + 1)
        outer = outer.parent
    return frozenset(lines)


def definition_name(node: Any, fam: str) -> str | None:
    """TSA's name for ``node`` when it is a definition, else None."""
    if fam == "java":
        return _java_name(node) if node.type in JAVA_DEFINITIONS else None
    if fam == "kotlin":
        return _java_name(node) if node.type in KOTLIN_DEFINITIONS else None
    return _ts_name(node) if node.type in TS_DEFINITIONS else None


def owner_at(node: Any, fam: str, line: int) -> Owner:
    """The innermost named definition around ``node`` (or ``<module>`` at ``line``)."""
    current = node.parent
    while current is not None:
        name = definition_name(current, fam)
        if name:
            return Owner(name, _starts(current))
        current = current.parent
    return Owner(MODULE, frozenset({line}))


def listed(callers: list[dict[str, Any]], rel: str, owner: Owner) -> bool:
    return any(
        c.get("file") == rel
        and c.get("name") == owner.name
        and c.get("line") in owner.starts
        for c in callers
    )
