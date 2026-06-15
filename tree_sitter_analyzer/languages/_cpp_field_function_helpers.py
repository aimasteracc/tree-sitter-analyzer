"""C++ field-function and prototype extraction helpers."""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from ..models import Function
from ..utils import log_debug
from ._cpp_signature_helpers import _TYPE_NODES_CPP

_FIELD_FUNCTION_NAME_NODES = frozenset(
    {"field_identifier", "identifier", "destructor_name", "operator_name"}
)


@dataclass
class _FieldFunctionParts:
    name: str | None = None
    return_type: str = "void"
    parameters: list[str] = field(default_factory=list)
    modifiers: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CppFieldFunctionExtractionContext:
    get_node_text: Callable[..., str]
    extract_parameters: Callable[[Any], list[str]]
    is_global_scope: Callable[[Any], bool]
    determine_visibility: Callable[..., str]
    extract_comment_for_line: Callable[[int], str | None]


def extract_function_from_field_declaration(
    node: Any,
    context: CppFieldFunctionExtractionContext | Callable[..., str],
    *legacy_args: Any,
) -> Function | None:
    """Extract a C++ function from a field declaration."""
    try:
        if not any(child.type == "function_declarator" for child in node.children):
            return None

        ctx = _field_function_context(context, *legacy_args)
        parts = _field_function_parts(node, ctx.get_node_text, ctx.extract_parameters)
        if not parts.name:
            return None

        start_line = node.start_point[0] + 1
        is_global = ctx.is_global_scope(node)
        # Header-only constructor DECLARATIONS come through this path too
        # (Codex P2 on #567) — same name-vs-enclosing-class rule.
        from ._cpp_element_helpers import _is_cpp_constructor

        return Function(
            name=parts.name,
            start_line=start_line,
            end_line=node.end_point[0] + 1,
            raw_text=ctx.get_node_text(node),
            language="cpp",
            parameters=parts.parameters,
            return_type=parts.return_type,
            modifiers=parts.modifiers,
            visibility=ctx.determine_visibility(
                parts.modifiers, is_global=is_global, node=node
            ),
            docstring=ctx.extract_comment_for_line(start_line),
            complexity_score=1,
            is_constructor=_is_cpp_constructor(parts.name, node),
        )
    except Exception as exc:
        log_debug(f"Failed to extract function from field declaration: {exc}")
        return None


def _field_function_context(
    context: CppFieldFunctionExtractionContext | Callable[..., str],
    *legacy_args: Any,
) -> CppFieldFunctionExtractionContext:
    if isinstance(context, CppFieldFunctionExtractionContext):
        return context
    if len(legacy_args) != 4:
        raise TypeError(
            "Expected CppFieldFunctionExtractionContext or legacy arguments"
        )
    return CppFieldFunctionExtractionContext(
        get_node_text=context,
        extract_parameters=legacy_args[0],
        is_global_scope=legacy_args[1],
        determine_visibility=legacy_args[2],
        extract_comment_for_line=legacy_args[3],
    )


def _field_function_parts(
    node: Any,
    get_node_text: Callable[..., str],
    extract_params_fn: Callable[[Any], list[str]],
) -> _FieldFunctionParts:
    parts = _FieldFunctionParts()
    for child in node.children:
        _apply_field_function_child(child, parts, get_node_text, extract_params_fn)
    return parts


def _apply_field_function_child(
    child: Any,
    parts: _FieldFunctionParts,
    get_node_text: Callable[..., str],
    extract_params_fn: Callable[[Any], list[str]],
) -> None:
    if child.type == "virtual":
        parts.modifiers.append("virtual")
        return
    if child.type in _TYPE_NODES_CPP:
        parts.return_type = get_node_text(child)
        return
    if child.type == "function_declarator":
        _merge_field_function_declarator(parts, child, get_node_text, extract_params_fn)
        return
    if child.type == "number_literal" and get_node_text(child) == "0":
        _append_unique(parts.modifiers, "pure_virtual")
        return
    if child.type == "delete_method_clause":
        _append_unique(parts.modifiers, "deleted")
        return
    if child.type == "default_method_clause":
        _append_unique(parts.modifiers, "default")


def _merge_field_function_declarator(
    parts: _FieldFunctionParts,
    declarator: Any,
    get_node_text: Callable[..., str],
    extract_params_fn: Callable[[Any], list[str]],
) -> None:
    for child in declarator.children:
        if child.type in _FIELD_FUNCTION_NAME_NODES:
            parts.name = get_node_text(child)
        elif child.type == "parameter_list":
            parts.parameters = extract_params_fn(child)
        elif child.type == "type_qualifier":
            _append_text_modifier(parts.modifiers, child, get_node_text)


def _append_text_modifier(
    modifiers: list[str], node: Any, get_node_text: Callable[..., str]
) -> None:
    modifier = get_node_text(node)
    if modifier:
        modifiers.append(modifier)


def _append_unique(modifiers: list[str], modifier: str) -> None:
    if modifier not in modifiers:
        modifiers.append(modifier)


def extract_function_declaration(
    node: Any,
    get_node_text: Callable[..., str],
    extract_params_fn: Callable[[Any], list[str]],
) -> Function | None:
    """Extract a C++ function declaration or prototype."""
    if node.parent and node.parent.type == "function_definition":
        return None

    try:
        name, parameters = _function_declaration_parts(
            node, get_node_text, extract_params_fn
        )
        if not name:
            return None

        # Header-only constructor declarations reach this path (Codex P2 on
        # #567) — same name-vs-enclosing-class rule as definitions.
        from ._cpp_element_helpers import _is_cpp_constructor

        return Function(
            name=name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            raw_text=get_node_text(node),
            language="cpp",
            parameters=parameters,
            return_type="void",
            modifiers=[],
            is_constructor=_is_cpp_constructor(name, node),
        )
    except Exception as exc:
        log_debug(f"Failed to extract function declaration: {exc}")
        return None


def _function_declaration_parts(
    node: Any,
    get_node_text: Callable[..., str],
    extract_params_fn: Callable[[Any], list[str]],
) -> tuple[str | None, list[str]]:
    name = None
    parameters: list[str] = []
    for child in node.children:
        if child.type in ("identifier", "qualified_identifier"):
            name = get_node_text(child)
        elif child.type == "parameter_list":
            parameters = extract_params_fn(child)
    return name, parameters
