"""Enhanced SQL view extraction — extracted from sql_plugin/extractor.py."""

import re
from collections.abc import Callable, Iterator
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import tree_sitter

from ...models import SQLView
from ...utils import log_debug
from .identifier_validator import is_valid_identifier


# Extract elements from AST: extract_sql_views
# Section: imports and module configuration
# Section: main class definition
# Section: helper functions
# Section: data processing methods
# Section: output formatting methods
# Section: validation and error handling
def extract_sql_views(
    root_node: "tree_sitter.Node",
    traverse_nodes: Callable[..., Iterator[Any]],
    get_node_text: Callable[..., str],
    source_code: str,
    content_lines: list[str],
    sql_elements: list[Any],
) -> None:
    """Extract CREATE VIEW statements with enhanced metadata."""
    for node in traverse_nodes(root_node):
        if node.type == "ERROR":
            raw_text = get_node_text(node)
            if not raw_text:
                continue

            # Find all views in this error node
            view_matches = re.finditer(
                r"CREATE\s+VIEW\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)\s+AS",
                raw_text,
                re.IGNORECASE,
            )

            for match in view_matches:
                view_name = match.group(1).strip()
                if not is_valid_identifier(view_name):
                    continue

                if any(
                    e.name == view_name and isinstance(e, SQLView) for e in sql_elements
                ):
                    continue

                start_line = node.start_point[0] + 1
                end_line = node.end_point[0] + 1

                view_context = raw_text[match.end() :]
                semicolon_match = re.search(r";", view_context)
                if semicolon_match:
                    view_context = view_context[: semicolon_match.end()]

                source_tables = []
                table_matches = re.findall(
                    r"(?:FROM|JOIN)\s+([a-zA-Z_][a-zA-Z0-9_]*)",
                    view_context,
                    re.IGNORECASE,
                )
                source_tables.extend(table_matches)

                view = SQLView(
                    name=view_name,
                    start_line=start_line,
                    end_line=end_line,
                    raw_text=f"CREATE VIEW {view_name} ...",
                    language="sql",
                    source_tables=sorted(set(source_tables)),
                    dependencies=sorted(set(source_tables)),
                )
                sql_elements.append(view)

        elif node.type == "create_view":
            view_name = None
            source_tables = []

            raw_text = get_node_text(node)

            if raw_text:
                view_match = re.search(
                    r"CREATE\s+VIEW\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)\s+AS",
                    raw_text,
                    re.IGNORECASE,
                )
                if view_match:
                    potential_name = view_match.group(1).strip()
                    if is_valid_identifier(potential_name):
                        view_name = potential_name

            if not view_name:
                for child in node.children:
                    if child.type == "object_reference":
                        for subchild in child.children:
                            if subchild.type == "identifier":
                                potential_name = get_node_text(subchild).strip()
                                if (
                                    potential_name
                                    and is_valid_identifier(potential_name)
                                    and potential_name.upper()
                                    not in (
                                        "SELECT",
                                        "FROM",
                                        "WHERE",
                                        "AS",
                                        "IF",
                                        "NOT",
                                        "EXISTS",
                                        "NULL",
                                        "CURRENT_TIMESTAMP",
                                        "NOW",
                                        "SYSDATE",
                                        "COUNT",
                                        "SUM",
                                        "AVG",
                                        "MAX",
                                        "MIN",
                                    )
                                ):
                                    view_name = potential_name
                                    break
                        if view_name:
                            break

            _extract_view_sources(node, source_tables, traverse_nodes, get_node_text)

            if view_name:
                try:
                    start_line = node.start_point[0] + 1
                    end_line = node.end_point[0] + 1
                    raw_text = get_node_text(node)

                    view = SQLView(
                        name=view_name,
                        start_line=start_line,
                        end_line=end_line,
                        raw_text=raw_text,
                        language="sql",
                        source_tables=source_tables,
                        dependencies=source_tables,
                    )
                    sql_elements.append(view)
                except Exception as e:
                    log_debug(f"Failed to extract enhanced view: {e}")


# Extract elements from AST: _extract_view_sources
def _extract_view_sources(
    view_node: "tree_sitter.Node",
    source_tables: list[str],
    traverse_nodes: Callable[..., Iterator[Any]],
    get_node_text: Callable[..., str],
) -> None:
    """Extract source tables from view definition."""
    for node in traverse_nodes(view_node):
        if node.type == "from_clause":
            for child in traverse_nodes(node):
                if child.type == "object_reference":
                    for subchild in child.children:
                        if subchild.type == "identifier":
                            table_name = get_node_text(child).strip()
                            if table_name and table_name not in source_tables:
                                source_tables.append(table_name)

