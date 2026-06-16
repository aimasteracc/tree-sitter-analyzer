"""Variable extraction helpers for the TypeScript extractor."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, TypeAlias

from ...models import Variable
from ...utils import log_debug

if TYPE_CHECKING:
    import tree_sitter


TextExtractor: TypeAlias = Callable[["tree_sitter.Node"], str]
TsdocExtractor: TypeAlias = Callable[[int], str | None]
TypeInferer: TypeAlias = Callable[[str | None], str]


@dataclass
class _PropertyParts:
    name: str | None = None
    type_name: str | None = None
    value: str | None = None
    is_static: bool = False
    visibility: str = "public"


@dataclass
class _VariableParts:
    name: str | None = None
    type_name: str | None = None
    value: str | None = None


def extract_property(
    node: tree_sitter.Node,
    get_node_text: TextExtractor,
) -> Variable | None:
    """Extract class property definition."""
    try:
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        parts = _parse_property_parts(node, get_node_text)

        if not parts.name:
            return None

        return Variable(
            name=parts.name,
            start_line=start_line,
            end_line=end_line,
            raw_text=get_node_text(node),
            language="typescript",
            variable_type=parts.type_name or "any",
            initializer=parts.value,
            is_static=parts.is_static,
            is_constant=False,
            visibility=parts.visibility,
            decorators=_extract_direct_decorator_names(node),
        )
    except Exception as e:
        log_debug(f"Failed to extract property info: {e}")
        return None


def extract_property_signature(
    node: tree_sitter.Node,
    get_node_text: TextExtractor,
) -> Variable | None:
    """Extract property signature from an interface."""
    try:
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1

        prop_name = None
        prop_type = None
        for child in node.children:
            if child.type == "property_identifier":
                prop_name = get_node_text(child)
            elif child.type == "type_annotation":
                prop_type = get_node_text(child).lstrip(": ")

        if not prop_name:
            return None

        return Variable(
            name=prop_name,
            start_line=start_line,
            end_line=end_line,
            raw_text=get_node_text(node),
            language="typescript",
            variable_type=prop_type or "any",
            is_constant=False,
            visibility="public",
        )
    except Exception as e:
        log_debug(f"Failed to extract property signature info: {e}")
        return None


def extract_variables_from_declaration(
    node: tree_sitter.Node,
    kind: str,
    get_node_text: TextExtractor,
    parse_declarator: Callable,
    extract_tsdoc: TsdocExtractor,
) -> list[Variable]:
    """Extract variables from a declaration node."""
    variables: list[Variable] = []
    try:
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1

        for child in node.children:
            if child.type == "variable_declarator":
                var_info = parse_declarator(child, kind, start_line, end_line)
                if var_info:
                    variables.append(var_info)
    except Exception as e:
        log_debug(f"Failed to extract variables from declaration: {e}")
    return variables


def is_framework_component(
    framework_type: str,
    source_code: str,
    get_node_text: TextExtractor,
    node: tree_sitter.Node,
) -> bool:
    """Check if class is a framework component."""
    if framework_type == "react":
        node_text = get_node_text(node)
        return "extends" in node_text and (
            "Component" in node_text or "PureComponent" in node_text
        )
    if framework_type == "angular":
        return "@Component" in source_code
    if framework_type == "vue":
        return "Vue" in source_code or "@Component" in source_code
    return False


def is_exported_class(class_name: str, source_code: str) -> bool:
    """Check if a TypeScript type-like symbol is exported."""
    export_prefixes = (
        "class",
        "abstract class",
        "interface",
        "type",
        "enum",
        "const enum",
    )
    return (
        any(
            f"export {prefix} {class_name}" in source_code for prefix in export_prefixes
        )
        or f"export default {class_name}" in source_code
        or _is_named_reexport(class_name, source_code)
    )


def _is_named_reexport(class_name: str, source_code: str) -> bool:
    """Detect ``export { ... }`` re-export of ``class_name``.

    Matches the name as a whole word inside any ``export { ... }`` block,
    tolerating inner spacing (``export {Local}``), multiple names
    (``export { Local, Other }``), and aliases (``export { Local as Foo }``).
    The name is matched on its own (word-boundary) so ``Local`` does not match
    ``LocalThing``; an aliased name matches the LHS only (``{ Local as Foo }``
    exports ``Local``, not ``Foo``).
    """
    pattern = r"export\s*\{[^}]*\b" + re.escape(class_name) + r"\b(?!\s+as\s)[^}]*\}"
    if re.search(pattern, source_code):
        return True
    # Aliased form: `{ Local as Foo }` — class_name is the LHS of `as`.
    alias_pattern = (
        r"export\s*\{[^}]*\b" + re.escape(class_name) + r"\s+as\s+\w+[^}]*\}"
    )
    return bool(re.search(alias_pattern, source_code))


def infer_type_from_value(value: str | None) -> str:
    """Infer TypeScript type from a value literal."""
    if not value:
        return "any"

    value = value.strip()

    if value.startswith('"') or value.startswith("'") or value.startswith("`"):
        return "string"
    if value in ("true", "false"):
        return "boolean"
    if value == "null":
        return "null"
    if value == "undefined":
        return "undefined"
    if value.startswith("[") and value.endswith("]"):
        return "array"
    if value.startswith("{") and value.endswith("}"):
        return "object"
    if value.replace(".", "").replace("-", "").isdigit():
        return "number"
    if "function" in value or "=>" in value:
        return "function"
    return "any"


def parse_variable_declarator(
    node: tree_sitter.Node,
    kind: str,
    start_line: int,
    end_line: int,
    get_node_text: TextExtractor,
    infer_type_from_value: TypeInferer,
    extract_tsdoc: TsdocExtractor,
) -> Variable | None:
    """Parse an individual variable declarator with TypeScript type annotations."""
    try:
        parts = _parse_variable_parts(node, get_node_text)
        if not parts.name or _has_arrow_function_child(node):
            return None

        return Variable(
            name=parts.name,
            start_line=start_line,
            end_line=end_line,
            raw_text=get_node_text(node),
            language="typescript",
            variable_type=parts.type_name or infer_type_from_value(parts.value),
            is_static=False,
            is_constant=(kind == "const"),
            docstring=extract_tsdoc(start_line),
            initializer=parts.value,
            visibility="public",
        )
    except Exception as e:
        log_debug(f"Failed to parse variable declarator: {e}")
        return None


def _parse_property_parts(
    node: tree_sitter.Node,
    get_node_text: TextExtractor,
) -> _PropertyParts:
    parts = _PropertyParts()

    if hasattr(node, "children") and node.children:
        for child in node.children:
            if hasattr(child, "type"):
                _apply_property_child(parts, child, get_node_text)

    node_text = get_node_text(node)
    parts.is_static = "static" in node_text
    parts.visibility = _visibility_from_text(node_text)
    return parts


def _apply_property_child(
    parts: _PropertyParts,
    child: tree_sitter.Node,
    get_node_text: TextExtractor,
) -> None:
    if child.type == "property_identifier":
        parts.name = get_node_text(child)
    elif child.type == "type_annotation":
        parts.type_name = get_node_text(child).lstrip(": ")
    elif child.type in ["string", "number", "true", "false", "null"]:
        parts.value = get_node_text(child)


def _extract_direct_decorator_names(node: tree_sitter.Node) -> list[str]:
    names: list[str] = []
    for child in node.children:
        if child.type != "decorator":
            continue
        name = _decorator_name(child)
        if name:
            names.append(name)
    return names


def _decorator_name(node: tree_sitter.Node) -> str | None:
    for child in node.children:
        if child.type == "identifier":
            return _node_text(child)
        if child.type == "call_expression":
            for grandchild in child.children:
                if grandchild.type == "identifier":
                    return _node_text(grandchild)
    return None


def _node_text(node: tree_sitter.Node) -> str:
    text = node.text
    if isinstance(text, bytes):
        return text.decode("utf-8", errors="replace")
    return str(text or "")


def _parse_variable_parts(
    node: tree_sitter.Node,
    get_node_text: TextExtractor,
) -> _VariableParts:
    parts = _VariableParts()

    for child in node.children:
        if child.type == "identifier":
            parts.name = get_node_text(child)
        elif child.type == "type_annotation":
            parts.type_name = get_node_text(child).lstrip(": ")
        elif child.type == "=" and child.next_sibling:
            parts.value = get_node_text(child.next_sibling)

    return parts


def _has_arrow_function_child(node: tree_sitter.Node) -> bool:
    return any(child.type == "arrow_function" for child in node.children)


def _visibility_from_text(node_text: str) -> str:
    if "private" in node_text:
        return "private"
    if "protected" in node_text:
        return "protected"
    return "public"
