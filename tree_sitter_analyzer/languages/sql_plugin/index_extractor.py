"""Enhanced SQL index extraction — extracted from sql_plugin/extractor.py."""

import re
from collections.abc import Callable, Iterator
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import tree_sitter

from ...models import SQLIndex, Variable
from ...utils import log_debug
from .identifier_validator import is_valid_identifier


def extract_sql_indexes(
    root_node: "tree_sitter.Node",
    traverse_nodes: Callable[..., Iterator[Any]],
    get_node_text: Callable[..., str],
    source_code: str,
    sql_elements: list[Any],
    index_factory: Callable[..., SQLIndex] = SQLIndex,
) -> None:
    """Extract CREATE INDEX statements with enhanced metadata."""
    processed_indexes: set[str] = set()

    for node in traverse_nodes(root_node):
        if node.type != "create_index":
            continue
        _append_sql_index(
            node,
            sql_elements,
            processed_indexes,
            get_node_text,
            index_factory,
        )

    extract_indexes_with_regex(
        sql_elements,
        processed_indexes,
        source_code,
        index_factory=index_factory,
    )


def _append_sql_index(
    node: "tree_sitter.Node",
    sql_elements: list[Any],
    processed_indexes: set[str],
    get_node_text: Callable[..., str],
    index_factory: Callable[..., SQLIndex],
) -> None:
    """Append one enhanced SQLIndex when the AST node yields a new valid name."""
    index_name = _sql_index_name(node, get_node_text)
    if not index_name or index_name in processed_indexes:
        return

    try:
        raw_text = get_node_text(node)
        index = index_factory(
            name=index_name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            raw_text=raw_text,
            language="sql",
            table_name=None,
            indexed_columns=[],
            is_unique=False,
            dependencies=[],
        )

        _extract_index_metadata(node, index, get_node_text)

        sql_elements.append(index)
        processed_indexes.add(index_name)
        log_debug(f"Extracted index: {index_name} on table {index.table_name}")
    except Exception as e:
        log_debug(f"Failed to extract enhanced index {index_name}: {e}")


def _sql_index_name(
    node: "tree_sitter.Node",
    get_node_text: Callable[..., str],
) -> str | None:
    """Return a validated CREATE INDEX name from node text."""
    index_pattern = re.search(
        r"CREATE\s+(?:UNIQUE\s+)?INDEX\s+([a-zA-Z_][a-zA-Z0-9_]*)\s+ON",
        get_node_text(node),
        re.IGNORECASE,
    )
    if not index_pattern:
        return None

    extracted_name = index_pattern.group(1)
    return extracted_name if is_valid_identifier(extracted_name) else None


def extract_legacy_indexes(
    root_node: "tree_sitter.Node",
    variables: list[Variable],
    traverse_nodes: Callable[..., Iterator[Any]],
    get_node_text: Callable[..., str],
) -> None:
    """Extract CREATE INDEX statements as generic Variable elements."""
    for node in traverse_nodes(root_node):
        if node.type != "create_index":
            continue
        _append_legacy_index(node, variables, get_node_text)


def _append_legacy_index(
    node: "tree_sitter.Node",
    variables: list[Variable],
    get_node_text: Callable[..., str],
) -> None:
    """Append one legacy Variable index when an index name is present."""
    index_name = _legacy_index_name(node, get_node_text)
    if not index_name:
        return

    try:
        variables.append(
            Variable(
                name=index_name,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                raw_text=get_node_text(node),
                language="sql",
            )
        )
    except Exception as e:
        log_debug(f"Failed to extract index: {e}")


def _legacy_index_name(
    node: "tree_sitter.Node",
    get_node_text: Callable[..., str],
) -> str | None:
    """Return the first identifier child text used by legacy extraction."""
    for child in node.children:
        if child.type != "identifier":
            continue
        index_name = get_node_text(child).strip()
        if index_name:
            return index_name
    return None


def _extract_index_metadata(
    index_node: "tree_sitter.Node",
    index: "SQLIndex",
    get_node_text: Callable[..., str],
) -> None:
    """Extract index metadata including target table and columns."""
    index_text = get_node_text(index_node)

    if "UNIQUE" in index_text.upper():
        index.is_unique = True

    table_match = re.search(r"ON\s+([a-zA-Z_][a-zA-Z0-9_]*)", index_text, re.IGNORECASE)
    if table_match:
        index.table_name = table_match.group(1)
        if index.table_name and index.table_name not in index.dependencies:
            index.dependencies.append(index.table_name)

    columns_match = re.search(r"\(([^)]+)\)", index_text)
    if columns_match:
        columns_str = columns_match.group(1)
        columns = [col.strip() for col in columns_str.split(",")]
        index.indexed_columns.extend(columns)


def extract_indexes_with_regex(
    sql_elements: list,
    processed_indexes: set[str],
    source_code: str,
    index_factory: Callable[..., SQLIndex] = SQLIndex,
) -> None:
    """Extract CREATE INDEX statements using regex as fallback."""
    lines = source_code.split("\n")

    index_pattern = re.compile(
        r"^\s*CREATE\s+(UNIQUE\s+)?INDEX\s+([a-zA-Z_][a-zA-Z0-9_]*)\s+ON\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(([^)]+)\)",
        re.IGNORECASE | re.MULTILINE,
    )

    for line_num, line in enumerate(lines, 1):
        line = line.strip()
        if not line.upper().startswith("CREATE") or "INDEX" not in line.upper():
            continue

        match = index_pattern.match(line)
        if not match:
            continue

        _append_regex_index(
            match,
            line,
            line_num,
            sql_elements,
            processed_indexes,
            index_factory,
        )


def _append_regex_index(
    match: re.Match[str],
    line: str,
    line_num: int,
    sql_elements: list,
    processed_indexes: set[str],
    index_factory: Callable[..., SQLIndex],
) -> None:
    """Append one regex-extracted SQLIndex when its name is not duplicated."""
    index_name = match.group(2)
    if index_name in processed_indexes:
        return

    table_name = match.group(3)
    columns = [col.strip() for col in match.group(4).split(",")]

    try:
        index = index_factory(
            name=index_name,
            start_line=line_num,
            end_line=line_num,
            raw_text=line,
            language="sql",
            table_name=table_name,
            indexed_columns=columns,
            is_unique=match.group(1) is not None,
            dependencies=[table_name] if table_name else [],
        )

        sql_elements.append(index)
        processed_indexes.add(index_name)
        log_debug(f"Regex extracted index: {index_name} on table {table_name}")

    except Exception as e:
        log_debug(f"Failed to create regex-extracted index {index_name}: {e}")
