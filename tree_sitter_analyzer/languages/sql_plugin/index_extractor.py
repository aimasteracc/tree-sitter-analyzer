"""Enhanced SQL index extraction — extracted from sql_plugin/extractor.py."""

import re
from collections.abc import Callable, Iterator
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import tree_sitter

from ...models import SQLIndex
from ...utils import log_debug
from .identifier_validator import is_valid_identifier


def extract_sql_indexes(
    root_node: "tree_sitter.Node",
    traverse_nodes: Callable[..., Iterator[Any]],
    get_node_text: Callable[..., str],
    source_code: str,
    sql_elements: list[Any],
) -> None:
    """Extract CREATE INDEX statements with enhanced metadata."""
    processed_indexes: set[str] = set()

    for node in traverse_nodes(root_node):
        if node.type == "create_index":
            index_name = None

            raw_text = get_node_text(node)
            index_pattern = re.search(
                r"CREATE\s+(?:UNIQUE\s+)?INDEX\s+([a-zA-Z_][a-zA-Z0-9_]*)\s+ON",
                raw_text,
                re.IGNORECASE,
            )
            if index_pattern:
                extracted_name = index_pattern.group(1)
                if is_valid_identifier(extracted_name):
                    index_name = extracted_name

            if index_name and index_name not in processed_indexes:
                try:
                    start_line = node.start_point[0] + 1
                    end_line = node.end_point[0] + 1
                    raw_text = get_node_text(node)

                    index = SQLIndex(
                        name=index_name,
                        start_line=start_line,
                        end_line=end_line,
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
                    log_debug(
                        f"Extracted index: {index_name} on table {index.table_name}"
                    )
                except Exception as e:
                    log_debug(f"Failed to extract enhanced index {index_name}: {e}")

    _extract_indexes_with_regex(sql_elements, processed_indexes, source_code)


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


def _extract_indexes_with_regex(
    sql_elements: list,
    processed_indexes: set[str],
    source_code: str,
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
        if match:
            is_unique = match.group(1) is not None
            index_name = match.group(2)
            table_name = match.group(3)
            columns_str = match.group(4)

            if index_name in processed_indexes:
                continue

            columns = [col.strip() for col in columns_str.split(",")]

            try:
                index = SQLIndex(
                    name=index_name,
                    start_line=line_num,
                    end_line=line_num,
                    raw_text=line,
                    language="sql",
                    table_name=table_name,
                    indexed_columns=columns,
                    is_unique=is_unique,
                    dependencies=[table_name] if table_name else [],
                )

                sql_elements.append(index)
                processed_indexes.add(index_name)
                log_debug(f"Regex extracted index: {index_name} on table {table_name}")

            except Exception as e:
                log_debug(f"Failed to create regex-extracted index {index_name}: {e}")
