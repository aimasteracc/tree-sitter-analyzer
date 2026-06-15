"""Enhanced SQL table extraction — extracted from sql_plugin/extractor.py."""

import re
from collections.abc import Callable, Iterator
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import tree_sitter

from ...models import SQLColumn, SQLConstraint, SQLTable
from ...utils import log_debug
from .identifier_validator import is_valid_identifier

# ---------------------------------------------------------------------------
# Regex fallback for CREATE TABLE inside ERROR nodes (#808)
# ---------------------------------------------------------------------------

# Matches: CREATE [TEMPORARY] TABLE [IF NOT EXISTS] [schema.]table_name
# Handles bare identifiers plus ANSI ("name"), MySQL (`name`), SQL Server ([name]) quoting.
# Group 1 = optional schema name, Group 2 = table name
_QUOTED_OR_BARE = r'(?:[a-zA-Z_][a-zA-Z0-9_]*|"[^"]+"|`[^`]+`|\[[^\]]+\])'
_CREATE_TABLE_RE = re.compile(
    r"CREATE\s+(?:TEMPORARY\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?"
    rf"(?:({_QUOTED_OR_BARE})\.)?"
    rf"({_QUOTED_OR_BARE})",
    re.IGNORECASE,
)


def _strip_sql_delimiters(name: str) -> str:
    """Strip ANSI/MySQL/SQL Server identifier delimiters from a quoted name."""
    if len(name) >= 2 and name[0] in ('"', "`", "["):
        return name[1:-1]
    return name


def extract_sql_tables(
    root_node: "tree_sitter.Node",
    traverse_nodes: Callable[..., Iterator[Any]],
    get_node_text: Callable[..., str],
    sql_elements: list[Any],
) -> None:
    """Extract CREATE TABLE statements with enhanced metadata.

    r37by (dogfood): tool flagged this at nesting depth 8 (L34). The
    table-name discovery loop now lives in ``_find_table_name``.
    """
    for node in traverse_nodes(root_node):
        if node.type != "create_table":
            continue
        table_name, schema_name = _find_table_name(node, get_node_text)
        columns: list[SQLColumn] = []
        constraints: list[SQLConstraint] = []
        extract_table_columns(node, columns, constraints, traverse_nodes, get_node_text)
        if not table_name:
            continue
        try:
            sql_elements.append(
                SQLTable(
                    name=table_name,
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    raw_text=get_node_text(node),
                    language="sql",
                    columns=columns,
                    constraints=constraints,
                    schema_name=schema_name,
                )
            )
        except Exception as e:
            log_debug(f"Failed to extract enhanced table: {e}")


def _find_table_name(
    create_table_node: "tree_sitter.Node",
    get_node_text: Callable[..., str],
) -> tuple[str | None, str | None]:
    """Walk a ``create_table`` AST node and return (table_name, schema_name).

    For ``schema.table`` patterns the object_reference node contains two
    identifiers separated by a dot.  The LAST identifier is the table name;
    any preceding identifier is the schema name.

    r37by: extracted from ``extract_sql_tables`` so the per-object_reference
    inner loop reads as a focused helper instead of a depth-8 nested block.
    """
    for child in create_table_node.children:
        if child.type != "object_reference":
            continue
        name, schema = _last_valid_identifier(child, get_node_text)
        if name:
            return name, schema
    return None, None


def _last_valid_identifier(
    object_reference: "tree_sitter.Node",
    get_node_text: Callable[..., str],
) -> tuple[str | None, str | None]:
    """Return (table_name, schema_name) from an ``object_reference`` node.

    When the reference is ``schema.table`` there are two identifier children.
    We return the LAST valid identifier as the table name and the second-to-last
    as the schema name.  For a simple ``table`` reference, schema_name is None.
    """
    identifiers = [
        get_node_text(subchild).strip()
        for subchild in object_reference.children
        if subchild.type == "identifier"
    ]
    valid = [t for t in identifiers if t and is_valid_identifier(t)]
    if not valid:
        return None, None
    table_name = valid[-1]
    schema_name = valid[-2] if len(valid) >= 2 else None
    return table_name, schema_name


def _process_column_node(
    node: Any,
    columns: list[SQLColumn],
    get_node_text: Callable[..., str],
) -> None:
    """Process one tree-sitter ``column_definition`` node into *columns*."""
    column_name: str | None = None
    data_type: str | None = None
    nullable = True
    is_primary_key = False

    for child in node.children:
        child_upper = get_node_text(child).upper()
        if child.type == "identifier" and column_name is None:
            column_name = get_node_text(child).strip()
        elif child.type in ("data_type", "type_name"):
            data_type = get_node_text(child).strip()
        elif child.type == "not_null" or "NOT NULL" in child_upper:
            nullable = False
        elif child.type == "primary_key" or "PRIMARY KEY" in child_upper:
            is_primary_key = True

    if column_name and data_type and not any(c.name == column_name for c in columns):
        columns.append(
            SQLColumn(
                name=column_name,
                data_type=data_type,
                nullable=nullable,
                is_primary_key=is_primary_key,
            )
        )


def extract_table_columns(
    table_node: "tree_sitter.Node",
    columns: list[SQLColumn],
    constraints: list[SQLConstraint],
    traverse_nodes: Callable[..., Iterator[Any]],
    get_node_text: Callable[..., str],
) -> None:
    """Extract column definitions from CREATE TABLE statement."""
    table_text = get_node_text(table_node)

    # Parse the table definition using regex as fallback
    table_content_match = re.search(r"\(\s*(.*?)\s*\)(?:\s*;)?$", table_text, re.DOTALL)
    if table_content_match:
        for col_def in _split_column_definitions(table_content_match.group(1)):
            col_def = col_def.strip()
            if not col_def or col_def.upper().startswith(
                ("PRIMARY KEY", "FOREIGN KEY", "UNIQUE", "INDEX", "KEY")
            ):
                continue
            column = _parse_column_definition(col_def)
            if column:
                columns.append(column)

    # Also try tree-sitter approach as backup
    for node in traverse_nodes(table_node):
        if node.type == "column_definition":
            _process_column_node(node, columns, get_node_text)


def _is_in_sql_comment(source: str, pos: int) -> bool:
    """Return True if ``pos`` falls inside a SQL line (``--``) or block (``/* */``) comment."""
    # Line comment: check for -- between the start of the current line and pos.
    line_start = source.rfind("\n", 0, pos) + 1
    if "--" in source[line_start:pos]:
        return True
    # Block comment: the most recent /* before pos has no matching */ before pos.
    block_start = source.rfind("/*", 0, pos)
    if block_start != -1:
        block_end = source.find("*/", block_start)
        if block_end == -1 or block_end > pos:
            return True
    return False


def fill_missing_sql_tables_from_regex(
    source_code: str,
    sql_elements: list[Any],
) -> None:
    """Regex fallback: add CREATE TABLE statements absorbed by ERROR nodes (#808).

    tree-sitter parse-recovery can absorb an entire CREATE TABLE statement into
    an ERROR node when a preceding multi-line FOREIGN KEY clause (with ON DELETE /
    ON UPDATE) triggers grammar ambiguity.  The AST traversal then sees an ERROR
    node instead of a ``create_table`` node and the table is silently dropped.

    This function scans the raw source text for ``CREATE TABLE`` patterns and
    appends any tables that the AST pass missed.  It never removes tables already
    found, so it is safe to call unconditionally.

    De-duplicates by ``(schema_name, table_name)`` so that the same table name
    in two different schemas (e.g. ``tenant_a.users`` and ``tenant_b.users``) is
    not collapsed into one entry.  Matches inside SQL comments are skipped.
    """
    found_keys: set[tuple[str | None, str]] = {
        (
            e.schema_name.lower() if e.schema_name else None,
            e.name.lower(),
        )
        for e in sql_elements
        if isinstance(e, SQLTable)
    }
    for match in _CREATE_TABLE_RE.finditer(source_code):
        if _is_in_sql_comment(source_code, match.start()):
            continue
        raw_schema = match.group(1)  # optional, may be None; may be quoted
        raw_table = match.group(2)
        if not raw_table or not is_valid_identifier(raw_table):
            continue
        schema_name = _strip_sql_delimiters(raw_schema) if raw_schema else None
        table_name = _strip_sql_delimiters(raw_table)
        key = (schema_name.lower() if schema_name else None, table_name.lower())
        if key in found_keys:
            continue
        start_line = source_code[: match.start()].count("\n") + 1
        end_line = _find_statement_end_line(source_code, match.start())
        raw_text = _extract_statement_text(source_code, match.start())
        columns = _parse_columns_from_raw_text(raw_text)
        try:
            sql_elements.append(
                SQLTable(
                    name=table_name,
                    start_line=start_line,
                    end_line=end_line,
                    raw_text=raw_text,
                    language="sql",
                    schema_name=schema_name,
                    columns=columns,
                )
            )
        except Exception as exc:
            log_debug(f"regex fallback: failed to append table {table_name!r}: {exc}")
        found_keys.add(key)


def _find_statement_end_line(source: str, start: int) -> int:
    """Return the 1-based line number of the closing ``;`` for the statement at ``start``."""
    depth = 0
    for i in range(start, len(source)):
        ch = source[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == ";" and depth <= 0:
            return source[: i + 1].count("\n") + 1
    return source.count("\n") + 1


def _extract_statement_text(source: str, start: int) -> str:
    """Return the full CREATE TABLE statement text starting at ``start``."""
    depth = 0
    for i in range(start, len(source)):
        ch = source[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == ";" and depth <= 0:
            return source[start : i + 1]
    return source[start : start + 2000]


def _parse_columns_from_raw_text(raw_text: str) -> list[SQLColumn]:
    """Extract SQLColumn list from a CREATE TABLE raw text string (#880)."""
    body_match = re.search(r"\(\s*(.*?)\s*\)(?:\s*;)?$", raw_text, re.DOTALL)
    if not body_match:
        return []
    columns: list[SQLColumn] = []
    for col_def in _split_column_definitions(body_match.group(1)):
        col_def = col_def.strip()
        if not col_def or col_def.upper().startswith(
            (
                "PRIMARY KEY",
                "FOREIGN KEY",
                "UNIQUE",
                "INDEX",
                "KEY",
                "CONSTRAINT",
                "CHECK",
            )
        ):
            continue
        column = _parse_column_definition(col_def)
        if column:
            columns.append(column)
    return columns


def _split_column_definitions(content: str) -> list[str]:
    """Split column definitions by commas, handling nested parentheses."""
    definitions = []
    current_def = ""
    paren_count = 0

    for char in content:
        if char == "(":
            paren_count += 1
        elif char == ")":
            paren_count -= 1
        elif char == "," and paren_count == 0:
            if current_def.strip():
                definitions.append(current_def.strip())
            current_def = ""
            continue

        current_def += char

    if current_def.strip():
        definitions.append(current_def.strip())

    return definitions


# Parse input into structured data: _parse_column_definition
def _parse_column_definition(col_def: str) -> SQLColumn | None:
    """Parse a single column definition string."""
    match = re.match(
        r"^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s+([A-Z]+(?:\([^)]*\))?)",
        col_def,
        re.IGNORECASE,
    )
    if not match:
        return None

    column_name = match.group(1)
    data_type = match.group(2)

    col_def_upper = col_def.upper()
    nullable = "NOT NULL" not in col_def_upper
    is_primary_key = "PRIMARY KEY" in col_def_upper or "AUTO_INCREMENT" in col_def_upper
    is_foreign_key = "REFERENCES" in col_def_upper

    foreign_key_reference = None
    if is_foreign_key:
        ref_match = re.search(
            r"REFERENCES\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(([^)]+)\)",
            col_def,
            re.IGNORECASE,
        )
        if ref_match:
            foreign_key_reference = f"{ref_match.group(1)}({ref_match.group(2)})"

    return SQLColumn(
        name=column_name,
        data_type=data_type,
        nullable=nullable,
        is_primary_key=is_primary_key,
        is_foreign_key=is_foreign_key,
        foreign_key_reference=foreign_key_reference,
    )
