"""Enhanced SQL function extraction — extracted from sql_plugin/extractor.py."""

import re
from collections.abc import Callable, Iterator
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import tree_sitter

from ...models import SQLFunction, SQLParameter
from ...utils import log_debug
from .identifier_validator import is_valid_identifier
from .procedure_extractor import extract_procedure_parameters


# Extract elements from AST: extract_sql_functions_enhanced
# Section: imports and module configuration
# Section: main class definition
def extract_sql_functions_enhanced(
    root_node: "tree_sitter.Node",
    traverse_nodes: Callable[..., Iterator[Any]],
    get_node_text: Callable[..., str],
    source_code: str,
    sql_elements: list[Any],
) -> None:
    """Extract CREATE FUNCTION statements with enhanced metadata."""
    lines = source_code.split("\n")

    function_pattern = re.compile(
        r"^\s*CREATE\s+FUNCTION\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(",
        re.IGNORECASE,
    )

    i = 0
    inside_function = False

    while i < len(lines):
        if inside_function:
            if lines[i].strip().upper() in ["END;", "END$"] or lines[
                i
            ].strip().upper().startswith("END;"):
                inside_function = False
            i += 1
            continue

        match = function_pattern.match(lines[i])
        if match:
            func_name = match.group(1)

            if not is_valid_identifier(func_name):
                i += 1
                continue

            start_line = i + 1
            inside_function = True

            end_line = start_line
            nesting_level = 0

            for j in range(i + 1, len(lines)):
                line_stripped = lines[j].strip().upper()

                if line_stripped.startswith("--") or line_stripped.startswith("#"):
                    continue

                if re.search(r"\bBEGIN\b", line_stripped):
                    nesting_level += 1

                is_end = False
                if line_stripped in ["END;", "END$", "END"]:
                    is_end = True
                elif line_stripped.startswith("END;"):
                    is_end = True

                if is_end:
                    if nesting_level > 0:
                        nesting_level -= 1

                    if nesting_level == 0:
                        end_line = j + 1
                        inside_function = False
                        break

            func_lines = lines[i:end_line]
            raw_text = "\n".join(func_lines)

            parameters: list[SQLParameter] = []
            dependencies: list[str] = []
            return_type = None

            extract_procedure_parameters(raw_text, parameters)

            returns_match = re.search(
                r"RETURNS\s+([A-Z]+(?:\([^)]*\))?)", raw_text, re.IGNORECASE
            )
            if returns_match:
                return_type = returns_match.group(1)

            try:
                function = SQLFunction(
                    name=func_name,
                    start_line=start_line,
                    end_line=end_line,
                    raw_text=raw_text,
                    language="sql",
                    parameters=parameters,
                    dependencies=dependencies,
                    return_type=return_type,
                )
                sql_elements.append(function)
                log_debug(
                    f"Extracted function: {func_name} at lines {start_line}-{end_line}"
                )
            except Exception as e:
                log_debug(f"Failed to extract enhanced function: {e}")

            i = end_line
        else:
            i += 1

    # Also try the original tree-sitter approach as fallback
    for node in traverse_nodes(root_node):
        if node.type == "create_function":
            func_name = None
            return_type = None

            found_first_object_ref = False
            for child in node.children:
                if child.type == "object_reference" and not found_first_object_ref:
                    found_first_object_ref = True
                    for subchild in child.children:
                        if subchild.type == "identifier":
                            func_name = get_node_text(subchild).strip()
                            if func_name and is_valid_identifier(func_name):
                                break
                            else:
                                func_name = None
                    if func_name:
                        break

            if func_name:
                already_extracted = any(
                    hasattr(elem, "name") and elem.name == func_name
                    for elem in sql_elements
                    if hasattr(elem, "sql_element_type")
                    and elem.sql_element_type.value == "function"
                )

                if not already_extracted:
                    ts_parameters: list[SQLParameter] = []
                    ts_dependencies: list[str] = []

                    _extract_function_metadata(
                        node, ts_parameters, return_type, ts_dependencies, get_node_text
                    )

                    try:
                        start_line = node.start_point[0] + 1
                        end_line = node.end_point[0] + 1
                        raw_text = get_node_text(node)

                        function = SQLFunction(
                            name=func_name,
                            start_line=start_line,
                            end_line=end_line,
                            raw_text=raw_text,
                            language="sql",
                            parameters=ts_parameters,
                            dependencies=ts_dependencies,
                            return_type=return_type,
                        )
                        sql_elements.append(function)
                    except Exception as e:
                        log_debug(f"Failed to extract enhanced function: {e}")


# Extract elements from AST: _extract_function_metadata
def _extract_function_metadata(
    func_node: "tree_sitter.Node",
    parameters: list[SQLParameter],
    return_type: str | None,
    dependencies: list[str],
    get_node_text: Callable[..., str],
) -> None:
    """Extract function metadata including parameters and return type."""
    func_text = get_node_text(func_node)

    returns_match = re.search(
        r"RETURNS\s+([A-Z]+(?:\([^)]*\))?)", func_text, re.IGNORECASE
    )
    if returns_match:
        _return_type = returns_match.group(1)

    extract_procedure_parameters(func_text, parameters)

    from .procedure_extractor import _extract_procedure_dependencies

    _extract_procedure_dependencies(
        func_node, dependencies, _traverse_nodes_default, get_node_text
    )


# Process: _traverse_nodes_default
def _traverse_nodes_default(node: Any) -> Iterator[Any]:
    """Default traverse implementation."""
    yield node
    if hasattr(node, "children"):
        for child in node.children:
            yield from _traverse_nodes_default(child)

