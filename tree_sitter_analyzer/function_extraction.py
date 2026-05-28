"""Shared function-definition and call-site extraction helpers."""

from __future__ import annotations

from typing import Any

_CALL_NODE_TYPES = {
    "python": {"call"},
    "javascript": {"call_expression"},
    "typescript": {"call_expression"},
    "java": {"method_invocation", "class_body"},
    "go": {"call_expression"},
    "c": {"call_expression"},
    "cpp": {"call_expression"},
}

_FUNC_DEF_TYPES = {
    "python": {"function_definition"},
    "javascript": {"function_declaration", "method_definition", "arrow_function"},
    "typescript": {"function_declaration", "method_definition", "arrow_function"},
    "java": {"method_declaration", "constructor_declaration"},
    "go": {"function_declaration", "method_declaration"},
    "c": {"function_definition"},
    "cpp": {"function_definition"},
}


def walk_tree(node: Any, source: str, language: str) -> tuple[list[dict], list[dict]]:
    """Walk an AST and return function definitions plus call sites."""
    definitions: list[dict[str, Any]] = []
    calls: list[dict[str, Any]] = []
    _extract_recursive(node, source, language, definitions, calls, None)
    return definitions, calls


def _extract_recursive(
    node: Any,
    source: str,
    language: str,
    definitions: list[dict[str, Any]],
    calls: list[dict[str, Any]],
    enclosing_class: str | None,
) -> None:
    if not hasattr(node, "type"):
        return

    node_type = node.type
    if node_type in _FUNC_DEF_TYPES.get(language, set()):
        func_name = get_func_name(node, language)
        if func_name:
            parent_class = enclosing_class
            if language == "python":
                parent_class = find_parent_class_python(node) or enclosing_class
            elif language == "java":
                parent_class = find_parent_class_java(node) or enclosing_class
            elif language == "go" and node.type == "method_declaration":
                parent_class = find_receiver_type_go(node) or enclosing_class

            definitions.append(
                {
                    "name": func_name,
                    "start_line": node.start_point[0] + 1,
                    "end_line": node.end_point[0] + 1,
                    "class": parent_class,
                }
            )
            for child in node.children:
                _extract_recursive(
                    child, source, language, definitions, calls, parent_class
                )
            return

    if node_type in _CALL_NODE_TYPES.get(language, set()):
        call_info = extract_call(node, source, language)
        if call_info:
            calls.append(call_info)

    for child in node.children:
        _extract_recursive(child, source, language, definitions, calls, enclosing_class)


def get_func_name(node: Any, language: str) -> str | None:
    """Extract a function or method name from a definition node."""
    try:
        if language == "python":
            for child in node.children:
                if child.type == "identifier":
                    return _node_text_value(child)
        elif language in ("javascript", "typescript"):
            for child in node.children:
                if child.type in ("identifier", "property_identifier"):
                    return _node_text_value(child)
        elif language == "java":
            for child in node.children:
                if child.type == "identifier":
                    return _node_text_value(child)
        elif language == "go":
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                return _node_text_value(name_node)
            for child in node.children:
                if child.type in ("identifier", "field_identifier"):
                    return _node_text_value(child)
        elif language in ("c", "cpp"):
            for child in node.children:
                if child.type in (
                    "identifier",
                    "field_identifier",
                    "destructor_name",
                ):
                    return _node_text_value(child)
                if child.type == "function_declarator":
                    for sub in child.children:
                        if sub.type in ("identifier", "field_identifier"):
                            return _node_text_value(sub)
    except Exception:  # nosec B110
        pass
    return None


def extract_call(node: Any, source: str, language: str) -> dict[str, Any] | None:
    """Extract call target info from a call node."""
    try:
        if language in ("python", "javascript", "typescript", "go"):
            func_node = node.child_by_field_name("function")
            if func_node is None:
                return None
            return _call_from_text(_node_text(func_node, source), node)
        if language == "java":
            for child in node.children:
                if child.type == "identifier":
                    return _call_from_text(_node_text(child, source), node)
                if child.type in ("field_access", "method_reference"):
                    return _call_from_text(_node_text(child, source), node)
            return None
        if language in ("c", "cpp"):
            func_node = node.child_by_field_name("function")
            if func_node is None:
                for child in node.children:
                    if child.type == "identifier":
                        return _call_from_text(_node_text(child, source), node)
                return None
            name = _node_text(func_node, source)
            return {
                "name": name,
                "full_name": name,
                "line": node.start_point[0] + 1,
                "receiver": None,
            }
    except Exception:  # nosec B110
        pass
    return None


def _call_from_text(text: str, node: Any) -> dict[str, Any]:
    receiver = None
    name = text
    if "." in name:
        receiver, name = name.rsplit(".", 1)
    return {
        "name": name,
        "full_name": text,
        "line": node.start_point[0] + 1,
        "receiver": receiver,
    }


def node_text(node: Any, source: str) -> str:
    """Extract text from a node using UTF-8 byte offsets safely."""
    return _node_text(node, source)


def _node_text(node: Any, source: str) -> str:
    if node is None:
        return ""
    text_attr = getattr(node, "text", None)
    if isinstance(text_attr, bytes):
        try:
            return text_attr.decode("utf-8", errors="replace")
        except UnicodeDecodeError:
            return ""
    if isinstance(text_attr, str):
        return text_attr
    try:
        return source.encode("utf-8")[node.start_byte : node.end_byte].decode(
            "utf-8", errors="replace"
        )
    except (IndexError, TypeError, UnicodeDecodeError):
        return ""


def find_parent_class_python(node: Any) -> str | None:
    """Walk up from a Python function node to find an enclosing class."""
    if node is None:
        return None
    current = node.parent
    while current is not None:
        if current.type == "class_definition":
            for child in current.children:
                if child.type == "identifier":
                    return _node_text_value(child)
        current = current.parent
    return None


def find_parent_class_java(node: Any) -> str | None:
    """Walk up from a Java method node to find an enclosing class."""
    if node is None:
        return None
    current = node.parent
    while current is not None:
        if current.type == "class_declaration":
            for child in current.children:
                if child.type == "identifier":
                    return _node_text_value(child)
        current = current.parent
    return None


def find_receiver_type_go(node: Any) -> str | None:
    """Extract the receiver type from a Go method_declaration node."""
    if node is None or node.type != "method_declaration":
        return None
    for child in node.children:
        if child.type == "parameter_list":
            for param in child.children:
                for sub in param.children if hasattr(param, "children") else []:
                    if sub.type in ("type_identifier", "generic_type", "pointer_type"):
                        return _node_text_value(sub).lstrip("*")
                    for leaf in sub.children if hasattr(sub, "children") else []:
                        if leaf.type in ("type_identifier", "generic_type"):
                            return _node_text_value(leaf).lstrip("*")
    return None


def _node_text_value(node: Any) -> str:
    text = node.text
    return text.decode("utf-8") if isinstance(text, bytes) else str(text)
