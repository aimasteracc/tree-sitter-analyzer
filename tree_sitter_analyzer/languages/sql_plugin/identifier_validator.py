"""SQL identifier validation — extracted from sql_plugin/extractor.py."""

import re

_SQL_STATEMENT_PREFIXES = (
    "CREATE ",
    "SELECT ",
    "INSERT ",
    "UPDATE ",
    "DELETE ",
    "DROP ",
    "ALTER ",
    "TABLE ",
    "VIEW ",
    "PROCEDURE ",
    "FUNCTION ",
    "TRIGGER ",
)

_COMMON_COLUMN_NAMES = frozenset(
    {
        "PRICE",
        "QUANTITY",
        "TOTAL",
        "AMOUNT",
        "COUNT",
        "SUM",
        "CREATED_AT",
        "UPDATED_AT",
        "ID",
        "NAME",
        "EMAIL",
        "STATUS",
        "VALUE",
        "DATE",
        "TIME",
        "TIMESTAMP",
        "USER_ID",
        "ORDER_ID",
        "PRODUCT_ID",
    }
)

_SQL_KEYWORDS = frozenset(
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
        "AVG",
        "MAX",
        "MIN",
        "AND",
        "OR",
        "IN",
        "LIKE",
        "BETWEEN",
        "JOIN",
        "LEFT",
        "RIGHT",
        "INNER",
        "OUTER",
        "CROSS",
        "ON",
        "USING",
        "GROUP",
        "BY",
        "ORDER",
        "HAVING",
        "LIMIT",
        "OFFSET",
        "DISTINCT",
        "ALL",
        "UNION",
        "INTERSECT",
        "EXCEPT",
        "INSERT",
        "UPDATE",
        "DELETE",
        "CREATE",
        "DROP",
        "ALTER",
        "TABLE",
        "VIEW",
        "INDEX",
        "TRIGGER",
        "PROCEDURE",
        "FUNCTION",
        "PRIMARY",
        "FOREIGN",
        "KEY",
        "UNIQUE",
        "CHECK",
        "DEFAULT",
        "REFERENCES",
        "CASCADE",
        "RESTRICT",
        "SET",
        "NO",
        "ACTION",
        "INTO",
        "VALUES",
        "BEGIN",
        "END",
        "DECLARE",
        "RETURN",
        "RETURNS",
        "READS",
        "SQL",
        "DATA",
        "DETERMINISTIC",
        "BEFORE",
        "AFTER",
        "EACH",
        "ROW",
        "FOR",
        "COALESCE",
        "CASE",
        "WHEN",
        "THEN",
        "ELSE",
    }
)

_SIMPLE_ID_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
_QUOTED_ID_RE = re.compile(r'^[`"\[].*[`"\]]$')


def is_valid_identifier(name: str) -> bool:
    """Validate that a name is a valid SQL identifier."""
    if not name:
        return False

    if "\n" in name or "\r" in name or "\t" in name:
        return False

    name_upper = name.upper()

    if any(name_upper.startswith(p) for p in _SQL_STATEMENT_PREFIXES):
        return False

    if name_upper in _COMMON_COLUMN_NAMES:
        return False

    if name_upper in _SQL_KEYWORDS:
        return False

    if "(" in name or ")" in name:
        return False

    if len(name) > 128:
        return False

    if _SIMPLE_ID_RE.match(name):
        return True

    if _QUOTED_ID_RE.match(name):
        return True

    return False
