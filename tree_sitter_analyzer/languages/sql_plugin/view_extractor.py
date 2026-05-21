"""Enhanced SQL view extraction — extracted from sql_plugin/extractor.py.

r37av (dogfood): the project's own ``--code-patterns`` tool flagged this
file as UNSAFE with 2 critical findings — ``extract_sql_views`` at 130
lines (L16) and ``deep_nesting`` depth 9 at L99. Both came from a single
fat function that mixed three concerns: scanning ERROR-node text with a
regex, walking ``create_view`` nodes, and digging for the view name when
the regex on the ``create_view`` body misses. Refactor splits along
those three seams. Behaviour is unchanged — this is structure-only.
"""

import re
from collections.abc import Callable, Iterator
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import tree_sitter

from ...models import SQLView
from ...utils import log_debug
from .identifier_validator import is_valid_identifier

_SQL_KEYWORDS_TO_REJECT_AS_VIEW_NAME = frozenset(
    {
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
    }
)


def extract_sql_views(
    root_node: "tree_sitter.Node",
    traverse_nodes: Callable[..., Iterator[Any]],
    get_node_text: Callable[..., str],
    source_code: str,
    content_lines: list[str],
    sql_elements: list[Any],
) -> None:
    """Extract CREATE VIEW statements with enhanced metadata.

    Dispatches each node to one of two handlers (ERROR-node regex fallback
    vs. structured ``create_view`` walker). Both append discovered views
    into ``sql_elements`` in place. r37av split the body to drop the
    method from 130 lines to ~10 and the worst nesting depth from 9 to 3.
    """
    for node in traverse_nodes(root_node):
        if node.type == "ERROR":
            _extract_views_from_error_node(node, get_node_text, sql_elements)
        elif node.type == "create_view":
            _extract_view_from_create_node(
                node, traverse_nodes, get_node_text, sql_elements
            )


def _extract_views_from_error_node(
    node: "tree_sitter.Node",
    get_node_text: Callable[..., str],
    sql_elements: list[Any],
) -> None:
    """Recover views when tree-sitter falls back to an ERROR node.

    Uses a regex against the raw text — the parser couldn't structure
    the input, but we may still find ``CREATE VIEW <name> AS`` patterns.
    """
    raw_text = get_node_text(node)
    if not raw_text:
        return

    view_matches = re.finditer(
        r"CREATE\s+VIEW\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)\s+AS",
        raw_text,
        re.IGNORECASE,
    )
    start_line = node.start_point[0] + 1
    end_line = node.end_point[0] + 1

    for match in view_matches:
        view_name = match.group(1).strip()
        if not is_valid_identifier(view_name):
            continue
        if any(e.name == view_name and isinstance(e, SQLView) for e in sql_elements):
            continue

        source_tables = _extract_source_tables_from_text(raw_text[match.end() :])
        sql_elements.append(
            SQLView(
                name=view_name,
                start_line=start_line,
                end_line=end_line,
                raw_text=f"CREATE VIEW {view_name} ...",
                language="sql",
                source_tables=sorted(set(source_tables)),
                dependencies=sorted(set(source_tables)),
            )
        )


def _extract_source_tables_from_text(view_body: str) -> list[str]:
    """Pull table names from a ``FROM ...``/``JOIN ...`` regex over text.

    Stops at the first ``;`` so we don't bleed into the next statement.
    """
    body = view_body
    semicolon_match = re.search(r";", body)
    if semicolon_match:
        body = body[: semicolon_match.end()]

    return re.findall(
        r"(?:FROM|JOIN)\s+([a-zA-Z_][a-zA-Z0-9_]*)",
        body,
        re.IGNORECASE,
    )


def _extract_view_from_create_node(
    node: "tree_sitter.Node",
    traverse_nodes: Callable[..., Iterator[Any]],
    get_node_text: Callable[..., str],
    sql_elements: list[Any],
) -> None:
    """Extract a single view from a structured ``create_view`` AST node."""
    raw_text = get_node_text(node)
    view_name = _find_view_name(node, raw_text, get_node_text)
    if not view_name:
        return

    source_tables: list[str] = []
    _extract_view_sources(node, source_tables, traverse_nodes, get_node_text)

    try:
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        sql_elements.append(
            SQLView(
                name=view_name,
                start_line=start_line,
                end_line=end_line,
                raw_text=get_node_text(node),
                language="sql",
                source_tables=source_tables,
                dependencies=source_tables,
            )
        )
    except Exception as e:
        log_debug(f"Failed to extract enhanced view: {e}")


def _find_view_name(
    node: "tree_sitter.Node",
    raw_text: str,
    get_node_text: Callable[..., str],
) -> str | None:
    """Best-effort: regex on raw text first, then AST object_reference walk."""
    name = _find_view_name_via_regex(raw_text)
    if name:
        return name
    return _find_view_name_via_object_reference(node, get_node_text)


def _find_view_name_via_regex(raw_text: str) -> str | None:
    """Match ``CREATE VIEW <name> AS`` on the raw text of the node."""
    if not raw_text:
        return None
    view_match = re.search(
        r"CREATE\s+VIEW\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)\s+AS",
        raw_text,
        re.IGNORECASE,
    )
    if not view_match:
        return None
    potential_name = view_match.group(1).strip()
    return potential_name if is_valid_identifier(potential_name) else None


def _find_view_name_via_object_reference(
    node: "tree_sitter.Node",
    get_node_text: Callable[..., str],
) -> str | None:
    """Walk node.children for the first identifier inside object_reference."""
    for child in node.children:
        if child.type != "object_reference":
            continue
        name = _first_valid_identifier_in(child, get_node_text)
        if name:
            return name
    return None


def _first_valid_identifier_in(
    object_reference: "tree_sitter.Node",
    get_node_text: Callable[..., str],
) -> str | None:
    """First non-keyword, valid-identifier ``identifier`` child."""
    for subchild in object_reference.children:
        if subchild.type != "identifier":
            continue
        potential_name = get_node_text(subchild).strip()
        if not potential_name or not is_valid_identifier(potential_name):
            continue
        if potential_name.upper() in _SQL_KEYWORDS_TO_REJECT_AS_VIEW_NAME:
            continue
        return potential_name
    return None


def _extract_view_sources(
    view_node: "tree_sitter.Node",
    source_tables: list[str],
    traverse_nodes: Callable[..., Iterator[Any]],
    get_node_text: Callable[..., str],
) -> None:
    """Extract source tables from view definition."""
    for node in traverse_nodes(view_node):
        if node.type != "from_clause":
            continue
        for child in traverse_nodes(node):
            if child.type != "object_reference":
                continue
            _record_source_table_if_identifier(child, source_tables, get_node_text)


def _record_source_table_if_identifier(
    object_reference: "tree_sitter.Node",
    source_tables: list[str],
    get_node_text: Callable[..., str],
) -> None:
    """Append the object_reference text to ``source_tables`` if it has an identifier child."""
    for subchild in object_reference.children:
        if subchild.type != "identifier":
            continue
        table_name = get_node_text(object_reference).strip()
        if table_name and table_name not in source_tables:
            source_tables.append(table_name)
        return
