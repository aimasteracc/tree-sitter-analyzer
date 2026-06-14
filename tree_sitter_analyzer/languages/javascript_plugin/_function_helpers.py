"""Function extraction helpers for the JavaScript extractor."""

from __future__ import annotations

import traceback
from collections.abc import Callable
from typing import TYPE_CHECKING, TypeAlias

from ...models import Function
from ...utils import log_debug, log_error

if TYPE_CHECKING:
    import tree_sitter


TextExtractor: TypeAlias = Callable[["tree_sitter.Node"], str]
ParameterExtractor: TypeAlias = Callable[["tree_sitter.Node"], list[str]]
JsdocExtractor: TypeAlias = Callable[[int], str | None]
ComplexityCalculator: TypeAlias = Callable[["tree_sitter.Node"], int]
FunctionSignature = tuple[str, list[str], bool, bool]
FunctionSignatureParser: TypeAlias = Callable[
    ["tree_sitter.Node"], FunctionSignature | None
]
MethodSignature = tuple[str, list[str], bool, bool, bool, bool, bool]
MethodSignatureParser: TypeAlias = Callable[
    ["tree_sitter.Node"], MethodSignature | None
]


def extract_function(
    node: tree_sitter.Node,
    parse_signature: FunctionSignatureParser,
    extract_jsdoc: JsdocExtractor,
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

        name, parameters, is_async, is_generator = function_info
        return Function(
            name=name,
            start_line=start_line,
            end_line=end_line,
            raw_text=_raw_text_for_lines(content_lines, start_line, end_line),
            language="javascript",
            parameters=parameters,
            return_type="unknown",
            is_async=is_async,
            is_generator=is_generator,
            docstring=extract_jsdoc(start_line),
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
    extract_jsdoc: JsdocExtractor,
    calculate_complexity: ComplexityCalculator,
    framework_type: str,
) -> Function | None:
    """Extract arrow function information."""
    try:
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        node_text = get_node_text(node)

        return Function(
            name=_arrow_function_name(node, get_node_text),
            start_line=start_line,
            end_line=end_line,
            raw_text=node_text,
            language="javascript",
            parameters=_arrow_parameters(node, get_node_text, extract_parameters),
            return_type="unknown",
            is_async="async" in node_text,
            is_generator=False,
            docstring=extract_jsdoc(start_line),
            complexity_score=calculate_complexity(node),
            is_arrow=True,
            is_method=False,
            framework_type=framework_type,
        )
    except Exception as e:
        log_debug(f"Failed to extract arrow function info: {e}")
        return None


def extract_generator_function(
    node: tree_sitter.Node,
    parse_signature: FunctionSignatureParser,
    extract_jsdoc: JsdocExtractor,
    calculate_complexity: ComplexityCalculator,
    get_node_text: TextExtractor,
    framework_type: str,
) -> Function | None:
    """Extract generator function information."""
    try:
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        function_info = parse_signature(node)
        if not function_info:
            return None

        name, parameters, is_async, _is_generator = function_info
        return Function(
            name=name,
            start_line=start_line,
            end_line=end_line,
            raw_text=get_node_text(node),
            language="javascript",
            parameters=parameters,
            return_type="Generator",
            is_async=is_async,
            is_generator=True,
            docstring=extract_jsdoc(start_line),
            complexity_score=calculate_complexity(node),
            is_arrow=False,
            is_method=False,
            framework_type=framework_type,
        )
    except Exception as e:
        log_debug(f"Failed to extract generator function info: {e}")
        return None


def extract_method(
    node: tree_sitter.Node,
    parse_signature: MethodSignatureParser,
    extract_jsdoc: JsdocExtractor,
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
        ) = method_info

        return Function(
            name=name,
            start_line=start_line,
            end_line=end_line,
            raw_text=get_node_text(node),
            language="javascript",
            parameters=parameters,
            return_type="unknown",
            is_async=is_async,
            is_static=is_static,
            is_constructor=is_constructor,
            docstring=extract_jsdoc(start_line),
            complexity_score=calculate_complexity(node),
            is_arrow=False,
            is_method=True,
            framework_type=framework_type,
        )
    except Exception as e:
        log_debug(f"Failed to extract method info: {e}")
        raise


def extract_prototype_method(
    node: tree_sitter.Node,
    extract_parameters: ParameterExtractor,
    extract_jsdoc: JsdocExtractor,
    calculate_complexity: ComplexityCalculator,
    get_node_text: TextExtractor,
    framework_type: str,
) -> Function | None:
    """Extract a prototype-assignment method: ``X.prototype.m = function(){}``.

    AST shape (tree-sitter-javascript):
        assignment_expression
            left:  member_expression          <- X.prototype.m
                       member_expression      <- X.prototype
                           identifier         <- X
                           property_identifier <- prototype
                       property_identifier    <- m  (method name)
            right: function_expression / arrow_function
    """
    try:
        # Must be a top-level assignment_expression
        if node.type != "assignment_expression":
            return None

        left = node.child_by_field_name("left")
        right = node.child_by_field_name("right")

        if not left or not right:
            return None

        # left must be a member_expression (X.prototype.m)
        if left.type != "member_expression":
            return None

        # Its object must itself be a member_expression (X.prototype)
        proto_expr = left.child_by_field_name("object")
        method_prop = left.child_by_field_name("property")

        if not proto_expr or proto_expr.type != "member_expression":
            return None
        if not method_prop or method_prop.type != "property_identifier":
            return None

        # proto_expr.property must be "prototype"
        proto_prop = proto_expr.child_by_field_name("property")
        if not proto_prop or get_node_text(proto_prop) != "prototype":
            return None

        # The class name is proto_expr.object (must be an identifier)
        class_id = proto_expr.child_by_field_name("object")
        if not class_id or class_id.type != "identifier":
            return None

        class_name = get_node_text(class_id)
        method_name = get_node_text(method_prop)

        # Right-hand side must be a function (named or anonymous) or arrow
        if right.type not in ("function_expression", "arrow_function"):
            return None

        # Extract parameters from formal_parameters child
        parameters: list[str] = []
        for child in right.children:
            if child.type == "formal_parameters":
                parameters = extract_parameters(child)
            elif child.type == "identifier" and right.type == "arrow_function":
                # single-param arrow: x => ...
                parameters = [get_node_text(child)]

        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        node_text = get_node_text(node)
        is_async = "async" in node_text

        # If the function_expression has an explicit identifier name (named
        # function expression), prefer that as the canonical method name.
        if right.type == "function_expression":
            for child in right.children:
                if child.type == "identifier":
                    method_name = get_node_text(child)
                    break

        return Function(
            name=method_name,
            start_line=start_line,
            end_line=end_line,
            raw_text=node_text,
            language="javascript",
            parameters=parameters,
            return_type="unknown",
            is_async=is_async,
            is_generator=False,
            is_arrow=right.type == "arrow_function",
            is_method=True,
            is_constructor=False,
            parent_class=class_name,
            docstring=extract_jsdoc(start_line),
            complexity_score=calculate_complexity(right),
            framework_type=framework_type,
        )
    except Exception as e:
        log_debug(f"Failed to extract prototype method: {e}")
        return None


def _raw_text_for_lines(
    content_lines: list[str],
    start_line: int,
    end_line: int,
) -> str:
    start_line_idx = max(0, start_line - 1)
    end_line_idx = min(len(content_lines), end_line)
    return "\n".join(content_lines[start_line_idx:end_line_idx])


def _arrow_function_name(node: tree_sitter.Node, get_node_text: TextExtractor) -> str:
    parent = node.parent
    if not parent or parent.type != "variable_declarator":
        return "anonymous"

    for child in parent.children:
        if child.type == "identifier":
            return get_node_text(child)
    return "anonymous"


def _arrow_parameters(
    node: tree_sitter.Node,
    get_node_text: TextExtractor,
    extract_parameters: ParameterExtractor,
) -> list[str]:
    parameters: list[str] = []
    for child in node.children:
        if child.type == "formal_parameters":
            parameters = extract_parameters(child)
        elif child.type == "identifier":
            parameters = [get_node_text(child)]
    return parameters
