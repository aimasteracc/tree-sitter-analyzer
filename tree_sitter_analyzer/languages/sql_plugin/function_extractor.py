"""Enhanced SQL function extraction — extracted from sql_plugin/extractor.py."""

import re
from collections.abc import Callable, Iterator
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import tree_sitter

from ...models import Function, SQLFunction, SQLParameter
from ...utils import log_debug
from .identifier_validator import is_valid_identifier
from .procedure_extractor import extract_procedure_parameters

_FUNCTION_PATTERN = re.compile(
    r"^\s*CREATE\s+FUNCTION\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(",
    re.IGNORECASE,
)


# Extract elements from AST: extract_sql_functions_enhanced
def extract_sql_functions_enhanced(
    root_node: "tree_sitter.Node",
    traverse_nodes: Callable[..., Iterator[Any]],
    get_node_text: Callable[..., str],
    source_code: str,
    sql_elements: list[Any],
) -> None:
    """Extract CREATE FUNCTION statements with enhanced metadata."""
    lines = source_code.split("\n")
    _extract_functions_from_source(lines, sql_elements)
    _extract_functions_from_ast(root_node, traverse_nodes, get_node_text, sql_elements)


def _extract_functions_from_source(lines: list[str], sql_elements: list[Any]) -> None:
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

        match = _FUNCTION_PATTERN.match(lines[i])
        if match:
            func_name = match.group(1)

            if not is_valid_identifier(func_name):
                i += 1
                continue

            start_line = i + 1
            inside_function = True

            end_line, inside_function = _scan_function_end(lines, i + 1, start_line)

            func_lines = lines[i:end_line]
            raw_text = "\n".join(func_lines)

            _append_source_function(
                sql_elements, func_name, start_line, end_line, raw_text
            )

            i = end_line
        else:
            i += 1


def _scan_function_end(
    lines: list[str], search_start: int, default_end_line: int
) -> tuple[int, bool]:
    nesting_level = 0

    for j in range(search_start, len(lines)):
        line_stripped = lines[j].strip().upper()
        if _is_sql_comment_line(line_stripped):
            continue

        if re.search(r"\bBEGIN\b", line_stripped):
            nesting_level += 1

        if not _is_function_end_line(line_stripped):
            continue

        if nesting_level > 0:
            nesting_level -= 1

        if nesting_level == 0:
            return j + 1, False

    return default_end_line, True


def _is_sql_comment_line(line_stripped: str) -> bool:
    return line_stripped.startswith("--") or line_stripped.startswith("#")


def _is_function_end_line(line_stripped: str) -> bool:
    return line_stripped in ["END;", "END$", "END"] or line_stripped.startswith("END;")


def _append_source_function(
    sql_elements: list[Any],
    func_name: str,
    start_line: int,
    end_line: int,
    raw_text: str,
) -> None:
    parameters: list[SQLParameter] = []
    dependencies: list[str] = []
    return_type = _extract_return_type(raw_text)

    extract_procedure_parameters(raw_text, parameters)

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
        log_debug(f"Extracted function: {func_name} at lines {start_line}-{end_line}")
    except Exception as e:
        log_debug(f"Failed to extract enhanced function: {e}")


def _extract_return_type(raw_text: str) -> str | None:
    returns_match = re.search(
        r"RETURNS\s+([A-Z]+(?:\([^)]*\))?)", raw_text, re.IGNORECASE
    )
    return returns_match.group(1) if returns_match else None


def _extract_functions_from_ast(
    root_node: "tree_sitter.Node",
    traverse_nodes: Callable[..., Iterator[Any]],
    get_node_text: Callable[..., str],
    sql_elements: list[Any],
) -> None:
    for node in traverse_nodes(root_node):
        if node.type != "create_function":
            continue

        func_name = _function_name_from_ast(node, get_node_text)
        if not func_name or _function_already_extracted(sql_elements, func_name):
            continue

        _append_ast_function(node, func_name, get_node_text, sql_elements)


def _function_name_from_ast(
    node: "tree_sitter.Node", get_node_text: Callable[..., str]
) -> str | None:
    for child in node.children:
        if child.type != "object_reference":
            continue

        return _function_name_from_object_reference(child, get_node_text)

    return None


def _function_name_from_object_reference(
    node: "tree_sitter.Node", get_node_text: Callable[..., str]
) -> str | None:
    for subchild in node.children:
        if subchild.type != "identifier":
            continue

        func_name = get_node_text(subchild).strip()
        if func_name and is_valid_identifier(func_name):
            return func_name

    return None


def _function_already_extracted(sql_elements: list[Any], func_name: str) -> bool:
    return any(
        hasattr(elem, "name") and elem.name == func_name
        for elem in sql_elements
        if hasattr(elem, "sql_element_type")
        and elem.sql_element_type.value == "function"
    )


def _append_ast_function(
    node: "tree_sitter.Node",
    func_name: str,
    get_node_text: Callable[..., str],
    sql_elements: list[Any],
) -> None:
    return_type = None
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


def extract_legacy_functions(
    root_node: "tree_sitter.Node",
    functions: list[Function],
    traverse_nodes: Callable[..., Iterator[Any]],
    get_node_text: Callable[..., str],
    is_valid_identifier_fn: Callable[[str], bool] = is_valid_identifier,
) -> None:
    """Extract CREATE FUNCTION statements as generic Function elements."""
    for node in traverse_nodes(root_node):
        if node.type != "create_function":
            continue
        _append_legacy_function(
            node,
            functions,
            get_node_text,
            is_valid_identifier_fn,
        )


def _append_legacy_function(
    node: "tree_sitter.Node",
    functions: list[Function],
    get_node_text: Callable[..., str],
    is_valid_identifier_fn: Callable[[str], bool],
) -> None:
    """Append one legacy Function element when a valid name can be found."""
    func_name = _legacy_function_name(node, get_node_text, is_valid_identifier_fn)
    if not func_name:
        return

    try:
        functions.append(
            Function(
                name=func_name,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                raw_text=get_node_text(node),
                language="sql",
            )
        )
    except Exception as e:
        log_debug(f"Failed to extract function: {e}")


def _legacy_function_name(
    node: "tree_sitter.Node",
    get_node_text: Callable[..., str],
    is_valid_identifier_fn: Callable[[str], bool],
) -> str | None:
    """Return a legacy function name from AST children or SQL text."""
    from_children = _legacy_function_name_from_children(
        node,
        get_node_text,
        is_valid_identifier_fn,
    )
    if from_children:
        return from_children
    return _legacy_function_name_from_text(get_node_text(node), is_valid_identifier_fn)


def _legacy_function_name_from_children(
    node: "tree_sitter.Node",
    get_node_text: Callable[..., str],
    is_valid_identifier_fn: Callable[[str], bool],
) -> str | None:
    """Extract a function name from object_reference children."""
    for child in node.children:
        if child.type != "object_reference":
            continue
        for subchild in child.children:
            if subchild.type != "identifier":
                continue
            func_name = get_node_text(subchild).strip()
            if func_name and is_valid_identifier_fn(func_name):
                return func_name
        break
    return None


def _legacy_function_name_from_text(
    raw_text: str,
    is_valid_identifier_fn: Callable[[str], bool],
) -> str | None:
    """Extract a function name with regex fallback."""
    match = re.search(r"CREATE\s+FUNCTION\s+(\w+)\s*\(", raw_text, re.IGNORECASE)
    if not match:
        return None
    potential_name = match.group(1).strip()
    return potential_name if is_valid_identifier_fn(potential_name) else None


def _traverse_nodes_default(node: Any) -> Iterator[Any]:
    """Default traverse implementation."""
    yield node
    if hasattr(node, "children"):
        for child in node.children:
            yield from _traverse_nodes_default(child)
