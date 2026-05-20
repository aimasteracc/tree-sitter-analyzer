"""AST node helpers for the Python language extractor."""

from __future__ import annotations

from typing import Any

_PARAMETER_NODE_TYPES = frozenset(
    {
        "identifier",
        "typed_parameter",
        "default_parameter",
    }
)


def validate_node(node: Any) -> bool:
    """Validate that a node has required attributes."""
    required_attrs = ["start_byte", "end_byte", "start_point", "end_point"]
    for attr in required_attrs:
        if not hasattr(node, attr) or getattr(node, attr) is None:
            return False
    return True


def extract_name_from_node(node: Any, source_code: str) -> str | None:
    """Extract a node identifier name."""
    for child in node.children:
        if child.type == "identifier":
            return source_code[child.start_byte : child.end_byte]
    return None


def extract_parameters_from_node(node: Any, source_code: str) -> list[str]:
    """Extract function parameters from a node."""
    parameters: list[str] = []
    for child in node.children:
        if child.type == "parameters":
            parameters.extend(_extract_parameter_children(child, source_code))
    return parameters


def _extract_parameter_children(parameters_node: Any, source_code: str) -> list[str]:
    parameters = []
    for param_child in parameters_node.children:
        if param_child.type in _PARAMETER_NODE_TYPES:
            param_text = source_code[param_child.start_byte : param_child.end_byte]
            parameters.append(param_text)
    return parameters


def extract_decorators_from_node(node: Any, source_code: str) -> list[str]:
    """Extract decorators from a node."""
    if not hasattr(node, "parent") or not node.parent:
        return []

    decorators: list[str] = []
    for sibling in node.parent.children:
        if sibling.type != "decorator" or sibling.end_point[0] >= node.start_point[0]:
            continue
        decorators.append(_normalize_decorator_text(_source_text(sibling, source_code)))
    return decorators


def extract_function_body(node: Any, source_code: str) -> str:
    """Extract a function body from a function node."""
    for child in node.children:
        if child.type == "block":
            return source_code[child.start_byte : child.end_byte]
    return ""


def extract_superclasses_from_node(node: Any, source_code: str) -> list[str]:
    """Extract superclass names from a class node."""
    superclasses: list[str] = []
    for child in node.children:
        if child.type == "argument_list":
            superclasses.extend(_extract_superclass_arguments(child, source_code))
    return superclasses


def _extract_superclass_arguments(
    argument_list_node: Any, source_code: str
) -> list[str]:
    superclasses = []
    for arg in argument_list_node.children:
        if arg.type == "identifier":
            superclasses.append(source_code[arg.start_byte : arg.end_byte])
    return superclasses


def calculate_complexity(body: str) -> int:
    """Calculate simplified cyclomatic complexity."""
    complexity = 1
    keywords = ["if", "elif", "for", "while", "try", "except", "with", "and", "or"]
    for keyword in keywords:
        complexity += body.count(f" {keyword} ") + body.count(f"\n{keyword} ")
    return complexity


def _normalize_decorator_text(decorator_text: str) -> str:
    if decorator_text.startswith("@"):
        return decorator_text[1:].strip()
    return decorator_text


def _source_text(node: Any, source_code: str) -> str:
    return source_code[node.start_byte : node.end_byte]
