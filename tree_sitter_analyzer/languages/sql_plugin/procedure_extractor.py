"""Enhanced SQL procedure extraction — extracted from sql_plugin/extractor.py."""

import re
from collections.abc import Callable, Iterator
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import tree_sitter

from ...models import Function, SQLParameter
from ...utils import log_debug
from ._procedure_extractor import (
    append_source_procedures,
    append_tree_sitter_procedures,
)


# Extract elements from AST: extract_sql_procedures
def extract_sql_procedures(
    root_node: "tree_sitter.Node",
    traverse_nodes: Callable[..., Iterator[Any]],
    get_node_text: Callable[..., str],
    source_code: str,
    sql_elements: list[Any],
) -> None:
    """Extract CREATE PROCEDURE statements with enhanced metadata."""
    append_source_procedures(source_code, sql_elements, extract_procedure_parameters)
    append_tree_sitter_procedures(
        root_node,
        traverse_nodes,
        get_node_text,
        sql_elements,
        extract_procedure_parameters,
        _extract_procedure_dependencies,
    )


# Extract elements from AST: extract_procedure_parameters
def extract_procedure_parameters(
    proc_text: str, parameters: list[SQLParameter]
) -> None:
    """Extract parameters from procedure/function definition."""
    param_section = _extract_parameter_section(proc_text)
    if not param_section:
        return

    for param_definition in _split_parameter_definitions(param_section):
        match = re.match(
            r"\s*(?:(INOUT|IN|OUT)\s+)?([a-zA-Z_][a-zA-Z0-9_]*)\s+([A-Z][A-Z0-9_]*(?:\s*\([^)]*\))?)",
            param_definition,
            re.IGNORECASE,
        )
        if not match:
            continue

        direction = (match.group(1) or "IN").upper()
        param_name = match.group(2)
        data_type = match.group(3)

        # Filter out SQL DML keywords that can appear as false-positive param
        # names when the regex matches body text instead of the param list.
        # Keep only unambiguous reserved words — common column names like
        # STATUS, NAME, EMAIL, ID are valid parameter identifiers (#775).
        if param_name.upper() in (
            "SELECT",
            "FROM",
            "WHERE",
            "INTO",
            "VALUES",
            "SET",
            "UPDATE",
            "INSERT",
            "DELETE",
            "IN",
            "OUT",
            "INOUT",
        ):
            continue

        parameter = SQLParameter(
            name=param_name,
            data_type=data_type,
            direction=direction,
        )
        parameters.append(parameter)


def _extract_parameter_section(proc_text: str) -> str:
    """Return the balanced parameter section for a procedure/function.

    Handles both simple names (``FUNCTION foo(``) and schema-qualified names
    (``FUNCTION schema.foo(``).
    """
    header_match = re.search(
        r"(?:PROCEDURE|FUNCTION)\s+(?:[a-zA-Z_][a-zA-Z0-9_]*\.)*[a-zA-Z_][a-zA-Z0-9_]*\s*\(",
        proc_text,
        re.IGNORECASE,
    )
    if not header_match:
        return ""

    start = header_match.end()
    depth = 1
    for index in range(start, len(proc_text)):
        char = proc_text[index]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return proc_text[start:index].strip()

    return ""


def _split_parameter_definitions(param_section: str) -> list[str]:
    """Split parameter definitions while preserving datatype parentheses."""
    definitions = []
    current: list[str] = []
    depth = 0

    for char in param_section:
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1

        if char == "," and depth == 0:
            definition = "".join(current).strip()
            if definition:
                definitions.append(definition)
            current = []
        else:
            current.append(char)

    definition = "".join(current).strip()
    if definition:
        definitions.append(definition)

    return definitions


def extract_legacy_procedures(
    root_node: "tree_sitter.Node",
    functions: list[Function],
    traverse_nodes: Callable[..., Iterator[Any]],
    get_node_text: Callable[..., str],
) -> None:
    """Extract CREATE PROCEDURE statements as generic Function elements."""
    for node in traverse_nodes(root_node):
        if node.type != "ERROR":
            continue
        _append_legacy_procedures_from_error_node(
            node,
            functions,
            get_node_text,
        )


def _append_legacy_procedures_from_error_node(
    node: "tree_sitter.Node",
    functions: list[Function],
    get_node_text: Callable[..., str],
) -> None:
    """Append legacy Function procedure elements from one ERROR node."""
    node_text = get_node_text(node)
    if not _has_create_keyword(node) or "PROCEDURE" not in node_text.upper():
        return

    matches = re.finditer(
        r"CREATE\s+PROCEDURE\s+([a-zA-Z_][a-zA-Z0-9_]*)",
        node_text,
        re.IGNORECASE,
    )
    for match in matches:
        _append_legacy_procedure_match(node, node_text, match, functions)


def _has_create_keyword(node: "tree_sitter.Node") -> bool:
    """Return whether an ERROR node carries a CREATE keyword child."""
    for child in node.children:
        if child.type == "keyword_create":
            return True
    return False


def _append_legacy_procedure_match(
    node: "tree_sitter.Node",
    node_text: str,
    match: re.Match[str],
    functions: list[Function],
) -> None:
    """Append one legacy procedure Function from a regex match."""
    proc_name = match.group(1)
    if not proc_name:
        return

    try:
        newlines_before = node_text[: match.start()].count("\n")
        functions.append(
            Function(
                name=proc_name,
                start_line=node.start_point[0] + 1 + newlines_before,
                end_line=node.end_point[0] + 1,
                raw_text=node_text,
                language="sql",
            )
        )
    except Exception as e:
        log_debug(f"Failed to extract procedure: {e}")


# Extract elements from AST: _extract_procedure_dependencies
def _extract_procedure_dependencies(
    proc_node: "tree_sitter.Node",
    dependencies: list[str],
    traverse_nodes: Callable[..., Iterator[Any]],
    get_node_text: Callable[..., str],
) -> None:
    """Extract table dependencies from procedure body."""
    for node in traverse_nodes(proc_node):
        if node.type == "object_reference":
            # Iterate over child
            for child in node.children:
                if child.type == "identifier":
                    table_name = get_node_text(child).strip()
                    if table_name and table_name not in dependencies:
                        dependencies.append(table_name)
