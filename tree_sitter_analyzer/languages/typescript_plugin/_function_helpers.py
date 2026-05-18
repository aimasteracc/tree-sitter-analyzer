"""Function extraction helpers for the TypeScript extractor."""

from __future__ import annotations

import traceback
from collections.abc import Callable
from typing import TYPE_CHECKING, TypeAlias

from ...models import Function
from ...utils import log_debug, log_error
from ._signature_helpers import FunctionSignature, MethodSignature

if TYPE_CHECKING:
    import tree_sitter


TextExtractor: TypeAlias = Callable[["tree_sitter.Node"], str]
ParameterExtractor: TypeAlias = Callable[["tree_sitter.Node"], list[str]]
FunctionSignatureParser: TypeAlias = Callable[
    ["tree_sitter.Node"], FunctionSignature | None
]
MethodSignatureParser: TypeAlias = Callable[
    ["tree_sitter.Node"], MethodSignature | None
]
TsdocExtractor: TypeAlias = Callable[[int], str | None]
ComplexityCalculator: TypeAlias = Callable[["tree_sitter.Node"], int]


def extract_function(
    node: tree_sitter.Node,
    parse_signature: FunctionSignatureParser,
    extract_tsdoc: TsdocExtractor,
    calculate_complexity: ComplexityCalculator,
    content_lines: list[str],
    framework_type: str,
) -> Function | None:
    """Extract regular function information with detailed metadata."""
    try:
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1

        function_info = parse_signature(node)
        if not function_info:
            return None

        name, parameters, is_async, is_generator, return_type, _generics = function_info
        if name is None:
            return None

        start_line_idx = max(0, start_line - 1)
        end_line_idx = min(len(content_lines), end_line)
        raw_text = "\n".join(content_lines[start_line_idx:end_line_idx])

        return Function(
            name=name,
            start_line=start_line,
            end_line=end_line,
            raw_text=raw_text,
            language="typescript",
            parameters=parameters,
            return_type=return_type or "any",
            is_async=is_async,
            is_generator=is_generator,
            docstring=extract_tsdoc(start_line),
            complexity_score=calculate_complexity(node),
            is_arrow=False,
            is_method=False,
            framework_type=framework_type,
        )
    except Exception as e:
        log_error(f"Failed to extract function info: {e}")
        traceback.print_exc()
        return None


def extract_arrow_function(
    node: tree_sitter.Node,
    get_node_text: TextExtractor,
    extract_parameters: ParameterExtractor,
    extract_tsdoc: TsdocExtractor,
    calculate_complexity: ComplexityCalculator,
    framework_type: str,
) -> Function | None:
    """Extract arrow function information."""
    try:
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        name = _arrow_function_name(node, get_node_text)
        parameters, return_type = _arrow_signature_parts(
            node, get_node_text, extract_parameters
        )
        node_text = get_node_text(node)

        return Function(
            name=name,
            start_line=start_line,
            end_line=end_line,
            raw_text=node_text,
            language="typescript",
            parameters=parameters,
            return_type=return_type or "any",
            is_async="async" in node_text,
            is_generator=False,
            docstring=extract_tsdoc(start_line),
            complexity_score=calculate_complexity(node),
            is_arrow=True,
            is_method=False,
            framework_type=framework_type,
        )
    except Exception as e:
        log_debug(f"Failed to extract arrow function info: {e}")
        return None


def extract_method(
    node: tree_sitter.Node,
    parse_signature: MethodSignatureParser,
    extract_tsdoc: TsdocExtractor,
    calculate_complexity: ComplexityCalculator,
    get_node_text: TextExtractor,
    framework_type: str,
) -> Function | None:
    """Extract method information from a class."""
    try:
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1

        method_info = parse_signature(node)
        if not method_info:
            return None

        (
            name,
            parameters,
            is_async,
            is_static,
            _is_getter,
            _is_setter,
            is_constructor,
            return_type,
            visibility,
            _generics,
        ) = method_info
        if name is None:
            return None

        return Function(
            name=name,
            start_line=start_line,
            end_line=end_line,
            raw_text=get_node_text(node),
            language="typescript",
            parameters=parameters,
            return_type=return_type or "any",
            is_async=is_async,
            is_static=is_static,
            is_constructor=is_constructor,
            docstring=extract_tsdoc(start_line),
            complexity_score=calculate_complexity(node),
            is_arrow=False,
            is_method=True,
            framework_type=framework_type,
            visibility=visibility,
        )
    except Exception as e:
        log_debug(f"Failed to extract method info: {e}")
        return None


def extract_method_signature(
    node: tree_sitter.Node,
    parse_signature: MethodSignatureParser,
    extract_tsdoc: TsdocExtractor,
    get_node_text: TextExtractor,
    framework_type: str,
) -> Function | None:
    """Extract method signature information from an interface."""
    try:
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1

        method_info = parse_signature(node)
        if not method_info:
            return None

        (
            name,
            parameters,
            is_async,
            is_static,
            _is_getter,
            _is_setter,
            _is_constructor,
            return_type,
            _visibility,
            _generics,
        ) = method_info
        if name is None:
            return None

        return Function(
            name=name,
            start_line=start_line,
            end_line=end_line,
            raw_text=get_node_text(node),
            language="typescript",
            parameters=parameters,
            return_type=return_type or "any",
            is_async=is_async,
            is_static=is_static,
            docstring=extract_tsdoc(start_line),
            complexity_score=0,
            is_arrow=False,
            is_method=True,
            framework_type=framework_type,
        )
    except Exception as e:
        log_debug(f"Failed to extract method signature info: {e}")
        return None


def _arrow_function_name(node: tree_sitter.Node, get_node_text: TextExtractor) -> str:
    parent = node.parent
    if not parent or parent.type != "variable_declarator":
        return "anonymous"

    for child in parent.children:
        if child.type == "identifier":
            return get_node_text(child)
    return "anonymous"


def _arrow_signature_parts(
    node: tree_sitter.Node,
    get_node_text: TextExtractor,
    extract_parameters: ParameterExtractor,
) -> tuple[list[str], str | None]:
    parameters = []
    return_type = None

    for child in node.children:
        if child.type == "formal_parameters":
            parameters = extract_parameters(child)
        elif child.type == "identifier":
            parameters = [get_node_text(child)]
        elif child.type == "type_annotation":
            return_type = get_node_text(child).lstrip(": ")

    return parameters, return_type
