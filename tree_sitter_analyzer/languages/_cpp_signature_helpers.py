"""C++ signature and declaration helpers."""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from ..utils import log_debug

_TYPE_NODES_CPP = frozenset(
    {
        "primitive_type",
        "type_identifier",
        "qualified_identifier",
        "template_type",
    }
)
_FUNCTION_NAME_NODES = frozenset(
    {
        "identifier",
        "qualified_identifier",
        "field_identifier",
        "operator_name",
        "destructor_name",
    }
)


@dataclass
class _SignatureParts:
    name: str | None = None
    return_type: str = "void"
    parameters: list[str] = field(default_factory=list)
    modifiers: list[str] = field(default_factory=list)


def extract_comment_for_line(line: int, content_lines: list[str]) -> str | None:
    """Extract comment documentation for a source line."""
    try:
        for i in range(max(0, line - 5), line):
            if i >= len(content_lines):
                continue
            line_content = content_lines[i].strip()
            if line_content.startswith("/**"):
                return _collect_block_comment(i, line, content_lines)
            if line_content.startswith("///"):
                return line_content
    except Exception as exc:
        log_debug(f"Failed to extract comment: {exc}")
    return None


def _collect_block_comment(start: int, end: int, content_lines: list[str]) -> str:
    comment_lines = []
    for j in range(start, min(len(content_lines), end)):
        doc_line = content_lines[j].strip()
        comment_lines.append(doc_line)
        if doc_line.endswith("*/"):
            break
    return "\n".join(comment_lines)


def extract_parameters(
    params_node: Any,
    get_node_text: Callable[..., str],
) -> list[str]:
    """Extract function parameters.

    Theme E (2026-06-10): ``variadic_parameter_declaration`` now emits the
    full node text (e.g. ``Args... args``) instead of a bare ``"..."``.
    C-style variadic (bare ``...`` token, node type ``"..."``) is also
    captured so that e.g. ``printf(const char* fmt, ...)`` yields two params.
    """
    parameters: list[str] = []
    for child in params_node.children:
        if child.type in (
            "parameter_declaration",
            "optional_parameter_declaration",
        ):
            parameters.append(get_node_text(child))
        elif child.type == "variadic_parameter_declaration":
            parameters.append(get_node_text(child))
        elif child.type == "...":
            parameters.append("...")
    return parameters


def parse_function_signature(
    node: Any,
    get_node_text: Callable[..., str],
    extract_params_fn: Callable[[Any], list[str]],
) -> tuple[str, str, list[str], list[str]] | None:
    """Parse a C++ function signature."""
    try:
        parts = _SignatureParts()
        for child in node.children:
            _apply_signature_child(child, parts, get_node_text, extract_params_fn)

        if not parts.name:
            return None
        return parts.name, parts.return_type, parts.parameters, parts.modifiers
    except Exception:
        return None


def _apply_signature_child(
    child: Any,
    parts: _SignatureParts,
    get_node_text: Callable[..., str],
    extract_params_fn: Callable[[Any], list[str]],
) -> None:
    if child.type == "function_declarator":
        _merge_declarator(parts, child, get_node_text, extract_params_fn)
        return
    if child.type == "operator_cast":
        # Theme-I (2026-06-10): conversion operator (``operator double()``).
        # There is no function_declarator — the cast-target type doubles as
        # both the name suffix and the return type.
        for sub in child.children:
            if sub.type in _TYPE_NODES_CPP:
                type_text = get_node_text(sub)
                parts.name = f"operator {type_text}"
                parts.return_type = type_text
                break
        return
    if child.type == "reference_declarator":
        parts.return_type = _append_declarator_symbol(parts.return_type, "&")
        _merge_nested_declarator(parts, child, get_node_text, extract_params_fn)
        return
    if child.type == "pointer_declarator":
        parts.return_type = _append_declarator_symbol(parts.return_type, "*")
        _merge_nested_declarator(parts, child, get_node_text, extract_params_fn)
        return
    if child.type in _TYPE_NODES_CPP:
        parts.return_type = get_node_text(child)
        return
    if child.type in ("storage_class_specifier", "type_qualifier"):
        _append_text_modifier(parts.modifiers, child, get_node_text)
        return
    if child.type == "virtual":
        parts.modifiers.append("virtual")
        return
    if child.type == "delete_method_clause":
        _append_unique(parts.modifiers, "deleted")
        return
    if child.type == "default_method_clause":
        _append_unique(parts.modifiers, "default")


def _append_declarator_symbol(return_type: str, symbol: str) -> str:
    return return_type + symbol if return_type else symbol


def _merge_nested_declarator(
    parts: _SignatureParts,
    declarator: Any,
    get_node_text: Callable[..., str],
    extract_params_fn: Callable[[Any], list[str]],
) -> None:
    for child in declarator.children:
        if child.type == "function_declarator":
            _merge_declarator(parts, child, get_node_text, extract_params_fn)


def _merge_declarator(
    parts: _SignatureParts,
    declarator: Any,
    get_node_text: Callable[..., str],
    extract_params_fn: Callable[[Any], list[str]],
) -> None:
    for child in declarator.children:
        if child.type in _FUNCTION_NAME_NODES:
            parts.name = get_node_text(child)
        elif child.type == "parameter_list":
            parts.parameters = extract_params_fn(child)


def _append_text_modifier(
    modifiers: list[str], node: Any, get_node_text: Callable[..., str]
) -> None:
    modifier = get_node_text(node)
    if modifier:
        modifiers.append(modifier)


def _append_unique(modifiers: list[str], modifier: str) -> None:
    if modifier not in modifiers:
        modifiers.append(modifier)
