"""Helpers for SQL function extraction property tests."""

from __future__ import annotations

from typing import Any

import pytest
import tree_sitter

from tree_sitter_analyzer.languages.sql_plugin import SQLPlugin

COMMON_COLUMN_NAMES = {
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

SQL_KEYWORDS = {
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

INVALID_FUNCTION_NAMES = COMMON_COLUMN_NAMES | SQL_KEYWORDS
BODY_KEYWORDS = [
    "SELECT",
    "INSERT",
    "UPDATE",
    "DELETE",
    "FROM",
    "WHERE",
    "VALUES",
    "SET",
]


def is_invalid_function_name(name: str) -> bool:
    """Return true when a candidate should be rejected as a function name."""
    return name.upper() in INVALID_FUNCTION_NAMES


def select_valid_function_names(
    names: list[str], limit: int | None = None
) -> list[str]:
    """Filter property-generated identifiers using the extractor's invalid-name set."""
    valid_names = [name for name in names if not is_invalid_function_name(name)]
    return valid_names if limit is None else valid_names[:limit]


def extract_sql_elements(sql_code: str) -> list[Any]:
    """Parse SQL and return extracted elements using a fresh plugin instance."""
    plugin = SQLPlugin()
    language = plugin.get_tree_sitter_language()
    if language is None:
        pytest.skip("tree-sitter-sql not available")

    parser = tree_sitter.Parser()
    if hasattr(parser, "set_language"):
        parser.set_language(language)
    else:
        parser.language = language

    tree = parser.parse(sql_code.encode("utf-8"))
    return plugin.extractor.extract_sql_elements(tree, sql_code)


def extract_functions(sql_code: str) -> list[Any]:
    """Extract only SQL function elements from source."""
    return [
        elem
        for elem in extract_sql_elements(sql_code)
        if hasattr(elem, "sql_element_type")
        and elem.sql_element_type.value == "function"
    ]


def extract_function_names(sql_code: str) -> list[str]:
    """Extract function names from source."""
    return [func.name for func in extract_functions(sql_code)]


def lower_names(names: list[str]) -> list[str]:
    """Return lower-cased function names for case-insensitive checks."""
    return [name.lower() for name in names]


def build_single_function_sql(
    func_name: str, body: str, parameter: str = "param INT"
) -> str:
    """Build a MySQL-style CREATE FUNCTION block."""
    return f"""
CREATE FUNCTION {func_name}({parameter})
RETURNS INT
READS SQL DATA
DETERMINISTIC
BEGIN
{body}
END;
"""


def build_multiple_function_sql(
    names: list[str], body_template: str = "    RETURN param * 2;"
) -> str:
    """Build a SQL source containing CREATE FUNCTION declarations in order."""
    chunks = []
    for index, name in enumerate(names):
        chunks.append(
            build_single_function_sql(name, body_template.format(index=index)) + "\n"
        )
    return "".join(chunks)


def assert_function_body_content_exclusion(func_name: str, column_name: str) -> None:
    if is_invalid_function_name(func_name):
        return

    sql_code = f"""
CREATE FUNCTION {func_name}(order_id INT)
RETURNS DECIMAL(10, 2)
READS SQL DATA
DETERMINISTIC
BEGIN
    DECLARE result DECIMAL(10, 2);

    SELECT COALESCE(SUM({column_name} * quantity), 0) INTO result
    FROM order_items
    WHERE order_id = order_id;

    RETURN result;
END;
"""
    function_names = extract_function_names(sql_code)

    assert func_name in function_names, (
        f"Expected function '{func_name}' to be extracted"
    )
    assert column_name not in function_names, (
        f"Column name '{column_name}' should not be extracted as a function"
    )
    assert len(function_names) == 1, (
        f"Expected exactly 1 function, got {len(function_names)}: {function_names}"
    )


def assert_sql_keywords_exclusion(func_name: str, keyword: str) -> None:
    if is_invalid_function_name(func_name):
        return

    sql_code = f"""
CREATE FUNCTION {func_name}(user_id INT)
RETURNS BOOLEAN
READS SQL DATA
DETERMINISTIC
BEGIN
    DECLARE user_status VARCHAR(50);

    {keyword} status INTO user_status
    FROM users
    WHERE id = user_id;

    RETURN user_status = 'active';
END;
"""
    function_names = extract_function_names(sql_code)

    assert func_name in function_names, (
        f"Expected function '{func_name}' to be extracted"
    )
    assert keyword.lower() not in lower_names(function_names), (
        f"SQL keyword '{keyword}' should not be extracted as a function"
    )
    assert len(function_names) == 1, (
        f"Expected exactly 1 function, got {len(function_names)}: {function_names}"
    )


def assert_regex_pattern_precision(func_name: str, line_content: str) -> None:
    if is_invalid_function_name(func_name):
        return

    sql_code = f"""
CREATE FUNCTION {func_name}(param INT)
RETURNS INT
READS SQL DATA
DETERMINISTIC
BEGIN
    {line_content};
    RETURN 1;
END;
"""
    function_names = extract_function_names(sql_code)
    lower_function_names = lower_names(function_names)

    assert func_name in function_names, (
        f"Expected function '{func_name}' to be extracted"
    )
    assert len(function_names) == 1, (
        f"Expected exactly 1 function, got {len(function_names)}: {function_names}"
    )
    for keyword in BODY_KEYWORDS:
        assert keyword.lower() not in lower_function_names, (
            f"Keyword '{keyword}' from function body should not be extracted as a function"
        )


def assert_function_boundary_detection(func_name: str, body_lines: int) -> None:
    if is_invalid_function_name(func_name):
        return

    body_content = "\n".join(
        f"    DECLARE var{i} INT DEFAULT {i};" for i in range(body_lines)
    )
    sql_code = f"""-- Comment line 1
-- Comment line 2
CREATE FUNCTION {func_name}(param INT)
RETURNS INT
READS SQL DATA
DETERMINISTIC
BEGIN
{body_content}
    RETURN 0;
END;
-- Comment after function
"""
    functions = extract_functions(sql_code)

    assert len(functions) == 1, f"Expected exactly 1 function, got {len(functions)}"
    func = functions[0]
    create_function_line, end_line = expected_function_lines(sql_code)

    assert func.start_line == create_function_line, (
        f"Expected start_line to be {create_function_line} "
        f"(CREATE FUNCTION line), got {func.start_line}"
    )
    assert func.end_line == end_line, (
        f"Expected end_line to be {end_line} (END statement line), got {func.end_line}"
    )
    assert func.end_line > func.start_line, (
        f"Expected end_line ({func.end_line}) to be greater than "
        f"start_line ({func.start_line})"
    )


def expected_function_lines(sql_code: str) -> tuple[int | None, int | None]:
    """Return expected CREATE FUNCTION and END lines for generated SQL."""
    create_function_line = None
    end_line = None
    for index, line in enumerate(sql_code.split("\n")):
        if "CREATE FUNCTION" in line.upper():
            create_function_line = index + 1
        if line.strip().upper() in ["END;", "END"]:
            end_line = index + 1
    return create_function_line, end_line


def assert_invalid_identifier_rejected(invalid_name: str) -> None:
    sql_code = f"""
CREATE FUNCTION {invalid_name}(param INT)
RETURNS INT
READS SQL DATA
DETERMINISTIC
BEGIN
    DECLARE result INT;
    SELECT 1 INTO result;
    RETURN result;
END;
"""
    function_names = extract_function_names(sql_code)

    assert invalid_name not in function_names, (
        f"Invalid identifier '{invalid_name}' should not be extracted as a function name"
    )
    assert invalid_name.lower() not in lower_names(function_names), (
        f"Invalid identifier '{invalid_name}' (case-insensitive) should not be "
        "extracted as a function name"
    )
    assert len(function_names) == 0, (
        f"Expected 0 functions with invalid name '{invalid_name}', "
        f"got {len(function_names)}: {function_names}"
    )


def assert_valid_vs_invalid_identifier_extraction(
    valid_name: str, invalid_name: str
) -> None:
    if is_invalid_function_name(valid_name):
        return

    sql_code = f"""
CREATE FUNCTION {valid_name}(param1 INT)
RETURNS INT
READS SQL DATA
DETERMINISTIC
BEGIN
    RETURN 1;
END;

CREATE FUNCTION {invalid_name}(param2 INT)
RETURNS INT
READS SQL DATA
DETERMINISTIC
BEGIN
    RETURN 2;
END;
"""
    function_names = extract_function_names(sql_code)

    assert valid_name in function_names, (
        f"Valid function name '{valid_name}' should be extracted"
    )
    assert invalid_name not in function_names, (
        f"Invalid function name '{invalid_name}' should not be extracted"
    )
    assert invalid_name.lower() not in lower_names(function_names), (
        f"Invalid function name '{invalid_name}' (case-insensitive) should not be extracted"
    )
    assert len(function_names) == 1, (
        f"Expected exactly 1 function (valid one), "
        f"got {len(function_names)}: {function_names}"
    )


def assert_extraction_count_consistency(
    num_functions: int, func_names: list[str]
) -> None:
    valid_func_names = select_valid_function_names(func_names, limit=num_functions)
    if len(valid_func_names) < num_functions:
        return

    function_names = extract_function_names(
        build_multiple_function_sql(valid_func_names)
    )

    assert len(function_names) == len(valid_func_names), (
        f"Expected {len(valid_func_names)} functions, "
        f"got {len(function_names)}: {function_names}"
    )
    for expected_name in valid_func_names:
        assert expected_name in function_names, (
            f"Expected function '{expected_name}' not found in extracted functions: "
            f"{function_names}"
        )


def assert_output_ordering_preservation(func_names: list[str]) -> None:
    valid_func_names = select_valid_function_names(func_names)
    if len(valid_func_names) < 2:
        return

    sql_code = build_multiple_function_sql(
        valid_func_names, body_template="    RETURN param + {index};"
    )
    extracted_functions = extract_functions(sql_code)
    extracted_names = [func.name for func in extracted_functions]

    assert extracted_names == valid_func_names, (
        f"Function order mismatch. Expected: {valid_func_names}, Got: {extracted_names}"
    )

    start_lines = [func.start_line for func in extracted_functions]
    assert start_lines == sorted(start_lines), (
        f"Function start lines are not in ascending order: {start_lines}"
    )


def assert_deterministic_extraction(func_names: list[str], num_runs: int) -> None:
    valid_func_names = select_valid_function_names(func_names)
    if len(valid_func_names) < 1:
        return

    sql_code = build_multiple_function_sql(
        valid_func_names,
        body_template=(
            "    DECLARE result INT;\n"
            "    SELECT param * 2 INTO result;\n"
            "    RETURN result;"
        ),
    )
    all_results = [extract_function_tuples(sql_code) for _ in range(num_runs)]

    first_result = all_results[0]
    for index, result in enumerate(all_results[1:], start=1):
        assert result == first_result, (
            f"Run {index + 1} produced different results than run 1.\n"
            f"Run 1: {first_result}\nRun {index + 1}: {result}"
        )

    extracted_names = [name for name, _, _ in first_result]
    assert extracted_names == valid_func_names, (
        f"Expected functions {valid_func_names}, got {extracted_names}"
    )


def extract_function_tuples(sql_code: str) -> list[tuple[str, int, int]]:
    """Create a deterministic representation of function extraction results."""
    return [
        (func.name, func.start_line, func.end_line)
        for func in extract_functions(sql_code)
    ]
