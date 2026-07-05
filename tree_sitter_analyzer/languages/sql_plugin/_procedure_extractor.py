"""Helpers for extracting SQL stored procedures."""

import re
from collections.abc import Callable, Iterator
from typing import Any

from ...models import SQLParameter, SQLProcedure
from ...utils import log_debug

PROCEDURE_PATTERN = re.compile(
    r"^\s*CREATE\s+PROCEDURE\s+([a-zA-Z_][a-zA-Z0-9_]*)",
    re.IGNORECASE | re.MULTILINE,
)


def append_source_procedures(
    source_code: str,
    sql_elements: list[Any],
    extract_parameters: Callable[[str, list[SQLParameter]], None],
) -> None:
    """Append procedures found by scanning source lines."""
    lines = source_code.split("\n")
    index = 0
    while index < len(lines):
        if not _is_create_procedure_line(lines[index]):
            index += 1
            continue

        match = PROCEDURE_PATTERN.match(lines[index])
        if not match:
            index += 1
            continue

        end_line = _find_procedure_end_line(lines, index)
        _append_source_procedure(
            match.group(1), index + 1, end_line, lines, sql_elements, extract_parameters
        )
        index = end_line


def append_tree_sitter_procedures(
    root_node: Any,
    traverse_nodes: Callable[..., Iterator[Any]],
    get_node_text: Callable[..., str],
    sql_elements: list[Any],
    extract_parameters: Callable[[str, list[SQLParameter]], None],
    extract_dependencies: Callable[..., None],
) -> None:
    """Append procedures found in tree-sitter ERROR fallback nodes."""
    for node in traverse_nodes(root_node):
        if node.type != "ERROR":
            continue

        node_text = get_node_text(node)
        if not _has_create_procedure(node, node_text):
            continue

        for match in re.finditer(
            r"CREATE\s+PROCEDURE\s+([a-zA-Z_][a-zA-Z0-9_]*)",
            node_text,
            re.IGNORECASE,
        ):
            _append_fallback_procedure(
                node,
                node_text,
                match,
                sql_elements,
                traverse_nodes,
                get_node_text,
                extract_parameters,
                extract_dependencies,
            )


def _is_create_procedure_line(line: str) -> bool:
    normalized = line.strip().upper()
    return normalized.startswith("CREATE") and "PROCEDURE" in normalized


def _find_procedure_end_line(lines: list[str], start_index: int) -> int:
    start_line = start_index + 1
    for index in range(start_index + 1, len(lines)):
        normalized = lines[index].strip().upper()
        if normalized in ["END;", "END$$", "END"] or normalized.startswith("END;"):
            return index + 1
    return start_line


def _append_source_procedure(
    proc_name: str,
    start_line: int,
    end_line: int,
    lines: list[str],
    sql_elements: list[Any],
    extract_parameters: Callable[[str, list[SQLParameter]], None],
) -> None:
    raw_text = "\n".join(lines[start_line - 1 : end_line])
    proc_parameters: list[SQLParameter] = []
    extract_parameters(raw_text, proc_parameters)

    try:
        procedure = SQLProcedure(
            name=proc_name,
            start_line=start_line,
            end_line=end_line,
            raw_text=raw_text,
            language="sql",
            parameters=proc_parameters,
            dependencies=[],
        )
        sql_elements.append(procedure)
        log_debug(f"Extracted procedure: {proc_name} at lines {start_line}-{end_line}")
    except Exception as exc:
        log_debug(f"Failed to extract enhanced procedure: {exc}")


def _has_create_procedure(node: Any, node_text: str) -> bool:
    has_create = any(child.type == "keyword_create" for child in node.children)
    return has_create and "PROCEDURE" in node_text.upper()


def _append_fallback_procedure(
    node: Any,
    node_text: str,
    match: re.Match[str],
    sql_elements: list[Any],
    traverse_nodes: Callable[..., Iterator[Any]],
    get_node_text: Callable[..., str],
    extract_parameters: Callable[[str, list[SQLParameter]], None],
    extract_dependencies: Callable[..., None],
) -> None:
    proc_name = match.group(1)
    if _already_extracted(proc_name, sql_elements):
        return

    current_proc_text = node_text[match.start() :]
    parameters: list[SQLParameter] = []
    dependencies: list[str] = []
    extract_parameters(current_proc_text, parameters)
    extract_dependencies(node, dependencies, traverse_nodes, get_node_text)

    try:
        newlines_before = node_text[: match.start()].count("\n")
        procedure = SQLProcedure(
            name=proc_name,
            start_line=node.start_point[0] + 1 + newlines_before,
            end_line=node.end_point[0] + 1,
            raw_text=current_proc_text,
            language="sql",
            parameters=parameters,
            dependencies=dependencies,
        )
        sql_elements.append(procedure)
    except Exception as exc:
        log_debug(f"Failed to extract enhanced procedure: {exc}")


def _already_extracted(proc_name: str, sql_elements: list[Any]) -> bool:
    return any(
        hasattr(elem, "name")
        and elem.name == proc_name
        and hasattr(elem, "sql_element_type")
        and elem.sql_element_type.value == "procedure"
        for elem in sql_elements
    )
