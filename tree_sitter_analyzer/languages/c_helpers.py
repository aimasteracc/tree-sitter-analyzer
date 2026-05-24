"""C include, macro, and utility helpers — extracted from c_plugin.py."""

from collections.abc import Callable
from typing import Any

from ..models import Class, Function, Import, Variable
from ..utils import log_debug
from ._c_comment_helpers import extract_comment_for_line as _extract_comment_impl
from ._c_declaration_helpers import (
    extract_field_declaration as _extract_field_declaration_impl,
)
from ._c_declaration_helpers import (
    extract_variable_declaration as _extract_variable_declaration_impl,
)
from ._c_function_helpers import extract_c_function as _extract_c_function_impl
from ._c_include_helpers import extract_include_info as _extract_include_info_impl
from ._c_include_helpers import (
    extract_includes_fallback as _extract_includes_fallback_impl,
)
from ._c_macro_helpers import extract_macro_function as _extract_macro_function_impl
from ._c_signature_helpers import (
    parse_function_signature as _parse_function_signature_impl,
)
from ._c_traversal_helpers import c_traverse_and_extract as _c_traverse_and_extract_impl
from ._c_type_definition_helpers import (
    extract_enum_definition as _extract_enum_definition_impl,
)
from ._c_type_definition_helpers import (
    extract_struct_definition as _extract_struct_definition_impl,
)


# Extract elements from AST: extract_c_imports
def extract_c_imports(
    tree: Any,
    source_code: str,
    get_node_text: Callable[..., str],
) -> list[Import]:
    """Extract C include directives."""
    imports: list[Import] = []

    for child in tree.root_node.children:
        if child.type == "preproc_include":
            info = _extract_include_info(child, get_node_text)
            if info:
                imports.append(info)

    if not imports and "#include" in source_code:
        log_debug("No includes found via tree-sitter, trying regex fallback")
        imports.extend(_extract_includes_fallback(source_code))

    log_debug(f"Extracted {len(imports)} C includes")
    return imports


# Extract elements from AST: extract_parameters
def extract_parameters(
    params_node: Any,
    get_node_text: Callable[..., str],
) -> list[str]:
    """Extract function parameters."""
    parameters: list[str] = []
    for child in params_node.children:
        if child.type == "parameter_declaration":
            parameters.append(get_node_text(child))
        elif child.type == "variadic_parameter":
            parameters.append("...")
    return parameters


# Parse input into structured data: parse_function_signature
def parse_function_signature(
    node: Any,
    get_node_text: Callable[..., str],
    extract_params_fn: Callable[[Any], list[str]],
) -> tuple[str, str, list[str], list[str]] | None:
    """Parse C function signature."""
    return _parse_function_signature_impl(node, get_node_text, extract_params_fn)


# Extract elements from AST: extract_macro_definition
def extract_macro_definition(
    node: Any,
    get_node_text: Callable[..., str],
) -> list[Variable]:
    """Extract macro definitions as constants."""
    variables: list[Variable] = []
    try:
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1

        name = None
        for child in node.children:
            if child.type == "identifier":
                name = get_node_text(child)
                break

        if name:
            raw_text = get_node_text(node)
            variables.append(
                Variable(
                    name=name,
                    start_line=start_line,
                    end_line=end_line,
                    raw_text=raw_text,
                    language="c",
                    variable_type="macro",
                    modifiers=["const", "macro"],
                    is_constant=True,
                    visibility="public",
                )
            )
    except Exception as e:
        log_debug(f"Failed to extract macro: {e}")

    return variables


# Extract elements from AST: extract_macro_function
def extract_macro_function(
    node: Any,
    get_node_text: Callable[..., str],
) -> Function | None:
    """Extract macro function definition."""
    return _extract_macro_function_impl(node, get_node_text)


def calculate_complexity(node: Any) -> int:
    """Calculate cyclomatic complexity."""
    decision_nodes = {
        "if_statement",
        "while_statement",
        "for_statement",
        "switch_statement",
        "case_statement",
        "conditional_expression",
        "do_statement",
    }

    def count_decisions(n: Any) -> int:
        count = 0
        if hasattr(n, "type") and n.type in decision_nodes:
            count += 1
        if hasattr(n, "children"):
            try:
                for child in n.children:
                    count += count_decisions(child)
            except (TypeError, AttributeError):
                pass
        return count

    return 1 + count_decisions(node)


# Extract elements from AST: extract_field_declaration
def extract_field_declaration(
    node: Any, get_node_text: Callable[..., str]
) -> list[Variable]:
    """Extract struct/union field declarations."""
    return _extract_field_declaration_impl(node, get_node_text)


# Extract elements from AST: extract_variable_declaration
def extract_variable_declaration(
    node: Any, get_node_text: Callable[..., str]
) -> list[Variable]:
    """Extract C variable declarations (not struct members)."""
    return _extract_variable_declaration_impl(node, get_node_text)


# Extract elements from AST: extract_struct_definition
def extract_struct_definition(
    node: Any,
    get_node_text: Callable[..., str],
    content_lines: list[str],
) -> Class | None:
    """Extract struct definition."""
    return _extract_struct_definition_impl(node, get_node_text, content_lines)


# Extract elements from AST: extract_enum_definition
def extract_enum_definition(
    node: Any,
    get_node_text: Callable[..., str],
    content_lines: list[str],
) -> Class | None:
    """Extract enum definition."""
    return _extract_enum_definition_impl(node, get_node_text, content_lines)


# Extract elements from AST: extract_comment_for_line
def extract_comment_for_line(line: int, content_lines: list[str]) -> str | None:
    """Extract comment for a specific line."""
    return _extract_comment_impl(line, content_lines)


# Extract elements from AST: _extract_include_info
def _extract_include_info(
    node: Any,
    get_node_text: Callable[..., str],
) -> Import | None:
    """Extract include directive information."""
    return _extract_include_info_impl(node, get_node_text)


# Extract elements from AST: _extract_includes_fallback
def _extract_includes_fallback(source_code: str) -> list[Import]:
    """Fallback include extraction using regex."""
    return _extract_includes_fallback_impl(source_code)


# Extract elements from AST: c_traverse_and_extract
def c_traverse_and_extract(
    root_node: Any,
    extractors: dict[str, Any],
    results: list[Any],
    element_type: str,
    processed_nodes: set[int],
    element_cache: dict[tuple[int, str], Any],
) -> None:
    """Iterative node traversal and extraction with caching for C."""
    _c_traverse_and_extract_impl(
        root_node,
        extractors,
        results,
        element_type,
        processed_nodes,
        element_cache,
    )


# Extract elements from AST: extract_c_function
def extract_c_function(
    node: Any,
    get_node_text: Callable[..., str],
    content_lines: list[str],
    parse_function_signature: Callable,
    calculate_complexity: Callable,
    extract_comment_for_line: Callable,
) -> Function | None:
    """Extract C function definition."""
    return _extract_c_function_impl(
        node,
        get_node_text,
        content_lines,
        parse_function_signature,
        calculate_complexity,
        extract_comment_for_line,
    )
