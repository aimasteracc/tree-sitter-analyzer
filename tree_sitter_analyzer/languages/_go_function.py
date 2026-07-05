"""Go function and method extraction helpers."""

from collections.abc import Callable
from typing import Any

from ..models import Function
from ..utils import log_error
from ._go_common import (
    extract_docstring,
    extract_method_receiver,
    extract_parameters,
    extract_return_type,
    go_visibility,
)

# AST node types that each add one decision point to cyclomatic complexity.
# Switch/select constructs count once (matching the Swift plugin's
# count-the-construct-once convention), and the "&&"/"||" leaf tokens count
# the short-circuit boolean operators.
_GO_DECISION_NODE_TYPES: frozenset[str] = frozenset(
    {
        "if_statement",
        "for_statement",
        "expression_switch_statement",
        "type_switch_statement",
        "select_statement",
        "&&",
        "||",
    }
)


def _go_calculate_complexity(node: Any) -> int:
    """Return cyclomatic complexity (1 + decision points) for a Go function node."""
    decisions = 0
    stack = [node]
    while stack:
        cur = stack.pop()
        try:
            children = list(getattr(cur, "children", None) or [])
        except (TypeError, AttributeError):
            children = []
        if getattr(cur, "type", None) in _GO_DECISION_NODE_TYPES:
            decisions += 1
        stack.extend(children)
    return 1 + decisions


def extract_go_function(
    node: Any,
    get_node_text: Callable[..., str],
    content_lines: list[str],
) -> Function | None:
    """Extract Go function declaration."""
    try:
        name = _go_function_name(node, get_node_text)
        if not name:
            return None

        return _build_go_function(name, node, get_node_text, content_lines)
    except Exception as e:
        log_error(f"Error extracting Go function: {e}")
        return None


def extract_go_method(
    node: Any,
    get_node_text: Callable[..., str],
    content_lines: list[str],
) -> Function | None:
    """Extract Go method declaration (function with receiver)."""
    try:
        name = _go_function_name(node, get_node_text)
        if not name:
            return None

        func = _build_go_function(name, node, get_node_text, content_lines)
        receiver, receiver_type = extract_method_receiver(node, get_node_text)
        func.receiver = receiver
        func.receiver_type = receiver_type
        func.is_method = True
        return func
    except Exception as e:
        log_error(f"Error extracting Go method: {e}")
        return None


def extract_go_interface_methods(
    type_spec_node: Any,
    get_node_text: Callable[..., str],
    content_lines: list[str],
) -> list[Function]:
    """Extract interface method signatures as Functions owned by the interface.

    ``type Reader interface { Read(p []byte) (n int, err error) }`` emits
    ``method_elem`` children under ``interface_type``; each carries the same
    ``name``/``parameters``/``result`` fields a function declaration does, so
    the shared builder applies directly.  Ownership follows the receiver_type
    convention used for struct methods (#532/#474): receiver_type = the
    interface name, receiver stays None (signatures have no receiver var).
    Embedded interfaces are ``type_elem`` nodes and are deliberately skipped
    (no phantom methods — issue #588).
    """
    try:
        name_node = type_spec_node.child_by_field_name("name")
        type_node = type_spec_node.child_by_field_name("type")
        if name_node is None or type_node is None:
            return []
        if type_node.type != "interface_type":
            return []
        interface_name = get_node_text(name_node)
        if not interface_name:
            return []

        methods: list[Function] = []
        for child in type_node.children:
            if child.type != "method_elem":
                continue
            method_name = _go_function_name(child, get_node_text)
            if not method_name:
                continue
            func = _build_go_function(method_name, child, get_node_text, content_lines)
            func.receiver_type = interface_name
            func.is_method = True
            func.is_abstract = True  # interface specs have no body (#749)
            methods.append(func)
        return methods
    except Exception as e:
        log_error(f"Error extracting Go interface methods: {e}")
        return []


def _go_function_name(node: Any, get_node_text: Callable[..., str]) -> str | None:
    name_node = node.child_by_field_name("name")
    if not name_node:
        return None
    return get_node_text(name_node) or None


def _build_go_function(
    name: str,
    node: Any,
    get_node_text: Callable[..., str],
    content_lines: list[str],
) -> Function:
    visibility = go_visibility(name)
    return Function(
        name=name,
        start_line=node.start_point[0] + 1,
        end_line=node.end_point[0] + 1,
        raw_text=get_node_text(node),
        language="go",
        parameters=extract_parameters(node, get_node_text),
        return_type=extract_return_type(node, get_node_text),
        visibility=visibility,
        docstring=extract_docstring(node, content_lines),
        is_public=visibility == "public",
        complexity_score=_go_calculate_complexity(node),
    )
