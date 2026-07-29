"""Tree-sitter syntax navigation helpers for symbol extraction."""

from __future__ import annotations

from typing import Any

from ._symbol_rules import _CLASS_LIKE, _SCALA_CLASS_LIKE

_C_DECLARATOR_WRAPPERS = (
    "function_declarator",
    "pointer_declarator",
    "array_declarator",
)


def _node_text(node: Any, source: str) -> str:
    """Extract node text while respecting tree-sitter's UTF-8 byte offsets."""
    if node is None:
        return ""
    text_attr = getattr(node, "text", None)
    if isinstance(text_attr, bytes):
        return text_attr.decode("utf-8", errors="replace")
    if isinstance(text_attr, str):
        return text_attr
    try:
        return source.encode("utf-8")[node.start_byte : node.end_byte].decode(
            "utf-8", errors="replace"
        )
    except (IndexError, TypeError, UnicodeDecodeError):
        return ""


def _find_parent_class(node: Any, source: str) -> str | None:
    """Return the innermost enclosing class-like container name."""
    parent = node.parent
    while parent:
        if parent.type == "impl_item":
            type_node = parent.child_by_field_name("type")
            if type_node is not None:
                raw = _node_text(type_node, source)
                return raw.split("<")[0].strip() or None
        elif parent.type in _CLASS_LIKE:
            name_node = parent.child_by_field_name("name")
            if name_node:
                return _node_text(name_node, source)
        parent = parent.parent
    return None


def _extract_parent_classes(node: Any, source: str, language: str) -> list[str]:
    """Extract direct base-class names from a class definition."""
    try:
        extractor = _PARENT_EXTRACTORS.get(language)
        return extractor(node, source) if extractor is not None else []
    except Exception:  # nosec B110 - tolerate incomplete parser nodes
        return []


def _python_parents(node: Any, source: str) -> list[str]:
    return [
        _node_text(arg, source)
        for child in node.children
        if child.type == "argument_list"
        for arg in child.children
        if arg.type in ("identifier", "attribute", "type")
    ]


def _javascript_parents(node: Any, source: str) -> list[str]:
    return [
        _node_text(parent, source)
        for child in node.children
        if child.type == "class_heritage"
        for parent in child.children
        if parent.type in ("identifier", "member_expression")
    ]


def _java_parents(node: Any, source: str) -> list[str]:
    superclass = [
        _node_text(parent, source)
        for child in node.children
        if child.type == "superclass"
        for parent in child.children
        if parent.type == "type_identifier"
    ]
    interfaces = [
        _node_text(parent, source)
        for child in node.children
        if child.type == "super_interfaces"
        for type_list in child.children
        if type_list.type == "type_list"
        for parent in type_list.children
        if parent.type == "type_identifier"
    ]
    return superclass + interfaces


def _cpp_parents(node: Any, source: str) -> list[str]:
    return [
        _node_text(parent, source)
        for child in node.children
        if child.type == "base_class_clause"
        for parent in child.children
        if parent.type in ("type_identifier", "qualified_identifier")
    ]


_PARENT_EXTRACTORS = {
    "python": _python_parents,
    "javascript": _javascript_parents,
    "typescript": _javascript_parents,
    "java": _java_parents,
    "c": _cpp_parents,
    "cpp": _cpp_parents,
}


def _c_function_def_name(node: Any, source: str) -> str | None:
    """Recover a C function name from its declarator chain."""
    return _c_declarator_name(node.child_by_field_name("declarator"), source, 0)


def _c_declarator_name(declarator: Any, source: str, depth: int) -> str | None:
    """Descend a bounded C declarator chain to its innermost identifier."""
    if declarator is None or depth > 16:
        return None
    if declarator.type in ("identifier", "field_identifier", "type_identifier"):
        return _node_text(declarator, source) or None
    if declarator.type == "parenthesized_declarator":
        return _parenthesized_c_declarator_name(declarator, source, depth)
    if declarator.type in _C_DECLARATOR_WRAPPERS:
        return _c_declarator_name(
            declarator.child_by_field_name("declarator"), source, depth + 1
        )
    return None


def _parenthesized_c_declarator_name(
    declarator: Any, source: str, depth: int
) -> str | None:
    for child in declarator.children:
        if child.type in _C_DECLARATOR_WRAPPERS or child.type.endswith("identifier"):
            name = _c_declarator_name(child, source, depth + 1)
            if name is not None:
                return name
    return None


def _bash_subscript_base(subscript: Any) -> Any:
    """Return the base variable node of a Bash subscript assignment."""
    base = subscript.child_by_field_name("name")
    if base is not None:
        return base
    return next(
        (
            child
            for child in subscript.children
            if child.type in ("variable_name", "word")
        ),
        None,
    )


def _scala_symbol_from_node(node: Any, source: str) -> dict[str, Any] | None:
    if node.type not in _SCALA_CLASS_LIKE:
        return None
    name = _scala_symbol_name(node, source)
    if not name:
        return None
    return {
        "kind": "enum" if node.type == "enum_definition" else "class",
        "name": name,
        "line": node.start_point[0] + 1,
        "end_line": node.end_point[0] + 1,
        "language": "scala",
    }


def _scala_symbol_name(node: Any, source: str) -> str | None:
    name_node = node.child_by_field_name("name")
    if name_node is not None:
        return _node_text(name_node, source)
    for child in node.children:
        if child.type in ("identifier", "type_identifier"):
            return _node_text(child, source)
    if node.type != "given_definition":
        return None
    type_name = _scala_given_type_text(node, source)
    return (
        f"given {type_name}"
        if type_name
        else f"anonymous_given_{node.start_point[0] + 1}"
    )


def _scala_given_type_text(node: Any, source: str) -> str | None:
    type_nodes = {
        "generic_type",
        "type_identifier",
        "stable_type_identifier",
        "tuple_type",
        "function_type",
    }
    for child in node.children:
        if child.type in type_nodes:
            return _node_text(child, source)
    return None
