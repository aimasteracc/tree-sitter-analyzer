"""Language-specific constant and documentation extraction."""

from __future__ import annotations

from typing import Any

from ._symbol_rules import (
    _CONST_STYLE_NAME,
    _PY_CONST_STYLE_NAME,
    _PY_DUNDER_NAME,
)
from ._symbol_syntax import _node_text

_DOCSTRING_MAX_CHARS = 500


def _go_package_constants(node: Any, source: str) -> list[dict[str, Any]]:
    """Return package-scope Go constants and conventionally constant vars."""
    require_const_style = node.type == "var_declaration"
    specs: list[Any] = []
    for child in node.children:
        if child.type in ("const_spec", "var_spec"):
            specs.append(child)
        elif child.type == "var_spec_list":
            specs.extend(c for c in child.children if c.type == "var_spec")
    symbols: list[dict[str, Any]] = []
    for spec in specs:
        symbols.extend(_go_spec_constants(spec, source, require_const_style))
    return symbols


def _go_spec_constants(
    spec: Any, source: str, require_const_style: bool
) -> list[dict[str, Any]]:
    symbols: list[dict[str, Any]] = []
    for ident in spec.children_by_field_name("name"):
        symbol = _go_constant_symbol(ident, spec, source, require_const_style)
        if symbol is not None:
            symbols.append(symbol)
    return symbols


def _go_constant_symbol(
    ident: Any, spec: Any, source: str, require_const_style: bool
) -> dict[str, Any] | None:
    if ident.type != "identifier":
        return None
    name = _node_text(ident, source)
    if name == "_" or (require_const_style and not _CONST_STYLE_NAME.match(name)):
        return None
    return {
        "kind": "constant",
        "name": name,
        "line": spec.start_point[0] + 1,
        "end_line": spec.end_point[0] + 1,
        "language": "go",
    }


def _php_constants(node: Any, source: str) -> list[dict[str, Any]]:
    """Return one symbol per PHP ``const_element``."""
    symbols: list[dict[str, Any]] = []
    for child in node.children:
        if child.type != "const_element":
            continue
        name_node = next((c for c in child.children if c.type == "name"), None)
        if name_node is None:
            continue
        symbols.append(
            {
                "kind": "constant",
                "name": _node_text(name_node, source),
                "line": child.start_point[0] + 1,
                "end_line": child.end_point[0] + 1,
                "language": "php",
            }
        )
    return symbols


def _python_module_constant(node: Any, source: str) -> dict[str, Any] | None:
    """Return a symbol for a qualifying module-scope Python assignment."""
    left = node.child_by_field_name("left")
    if left is None or left.type != "identifier":
        return None
    if node.child_by_field_name("right") is None:
        return None
    name = _node_text(left, source)
    annotated = node.child_by_field_name("type") is not None
    if not (
        annotated or _PY_CONST_STYLE_NAME.match(name) or _PY_DUNDER_NAME.match(name)
    ):
        return None
    return {
        "kind": "constant",
        "name": name,
        "line": node.start_point[0] + 1,
        "end_line": node.end_point[0] + 1,
        "language": "python",
    }


def _python_docstring(node: Any, source: str) -> str | None:
    """Return the PEP 257 docstring of a Python function or class."""
    body = node.child_by_field_name("body")
    if body is None or not body.named_children:
        return None
    first = body.named_children[0]
    if first.type != "expression_statement" or not first.named_children:
        return None
    string_parts = _docstring_parts(first.named_children[0])
    if string_parts is None:
        return None
    content = "".join(
        _node_text(child, source)
        for part in string_parts
        for child in part.children
        if child.type == "string_content"
    ).strip()
    return content[:_DOCSTRING_MAX_CHARS] if content else None


def _docstring_parts(string_node: Any) -> list[Any] | None:
    if string_node.type == "string":
        return [string_node]
    if string_node.type == "concatenated_string":
        return [c for c in string_node.named_children if c.type == "string"]
    return None
