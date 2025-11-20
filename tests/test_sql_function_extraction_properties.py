#!/usr/bin/env python3
"""
Property-based tests for SQL function extraction fix.

Feature: sql-function-extraction-fix
Tests correctness properties for SQL function extraction to ensure:
- Function body content is not extracted as function names
- Regex pattern precision prevents false matches
- Function boundaries are correctly detected
"""

import pytest
import tree_sitter
from hypothesis import given, settings
from hypothesis import strategies as st

from tree_sitter_analyzer.languages.sql_plugin import SQLPlugin


# Helper function to create SQL code with functions
def create_sql_with_function(func_name: str, body_content: str) -> str:
    """Create a SQL CREATE FUNCTION statement with given name and body."""
    return f"""
CREATE FUNCTION {func_name}(param INT)
RETURNS INT
READS SQL DATA
DETERMINISTIC
BEGIN
    {body_content}
    RETURN 0;
END;
"""


# Strategy for valid SQL identifiers
valid_identifiers = st.text(
    alphabet=st.characters(
        whitelist_categories=("Lu", "Ll"), min_codepoint=65, max_codepoint=122
    ),
    min_size=1,
    max_size=20,
).filter(lambda x: x and x[0].isalpha() and x.replace("_", "").isalnum())

# Strategy for column names that should NOT be extracted as functions
column_names = st.sampled_from(
    [
        "price",
        "quantity",
        "total",
        "amount",
        "count",
        "sum",
        "created_at",
        "updated_at",
        "id",
        "name",
        "email",
        "status",
    ]
)


class TestSQLFunctionExtractionProperties:
    """Property-based tests for SQL function extraction."""

    @settings(max_examples=100)
    @given(func_name=valid_identifiers, column_name=column_names)
    def test_property_1_function_body_content_exclusion(
        self, func_name: str, column_name: str
    ):
        """
        Feature: sql-function-extraction-fix, Property 1: Function body content exclusion

        For any SQL source file containing CREATE FUNCTION statements with column names
        or SQL keywords in their bodies, the extracted function names should not include
        any of those column names or keywords - only the identifier immediately following
        "CREATE FUNCTION" in the declaration line.

        Validates: Requirements 1.1, 1.2, 1.3
        """
        # Skip if function name matches a column name or SQL keyword (would be filtered out)
        if func_name.upper() in [
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
        ]:
            return

        # Create SQL with a function that has column references in the body
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

        # Parse the SQL code
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

        # Extract SQL elements
        sql_elements = plugin.extractor.extract_sql_elements(tree, sql_code)

        # Extract function names
        function_names = [
            elem.name
            for elem in sql_elements
            if hasattr(elem, "sql_element_type")
            and elem.sql_element_type.value == "function"
        ]

        # Property: Only the actual function name should be extracted, not column names
        assert (
            func_name in function_names
        ), f"Expected function '{func_name}' to be extracted"
        assert (
            column_name not in function_names
        ), f"Column name '{column_name}' should not be extracted as a function"
        assert (
            len(function_names) == 1
        ), f"Expected exactly 1 function, got {len(function_names)}: {function_names}"

    @settings(max_examples=100)
    @given(
        func_name=valid_identifiers,
        keyword=st.sampled_from(
            ["SELECT", "FROM", "WHERE", "INSERT", "UPDATE", "DELETE"]
        ),
    )
    def test_property_1_sql_keywords_exclusion(self, func_name: str, keyword: str):
        """
        Feature: sql-function-extraction-fix, Property 1: Function body content exclusion (SQL keywords)

        For any SQL source file containing CREATE FUNCTION statements with SQL keywords
        in their bodies, the extracted function names should not include those keywords.

        Validates: Requirements 1.1, 1.2, 1.3
        """
        # Skip if function name matches a reserved keyword or common column name
        if func_name.upper() in [
            "SELECT",
            "FROM",
            "WHERE",
            "INSERT",
            "UPDATE",
            "DELETE",
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
        ]:
            return

        # Create SQL with a function that has SQL keywords in the body
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

        # Parse the SQL code
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

        # Extract SQL elements
        sql_elements = plugin.extractor.extract_sql_elements(tree, sql_code)

        # Extract function names
        function_names = [
            elem.name
            for elem in sql_elements
            if hasattr(elem, "sql_element_type")
            and elem.sql_element_type.value == "function"
        ]

        # Property: Only the actual function name should be extracted, not SQL keywords
        assert (
            func_name in function_names
        ), f"Expected function '{func_name}' to be extracted"
        assert keyword.lower() not in [
            name.lower() for name in function_names
        ], f"SQL keyword '{keyword}' should not be extracted as a function"
        assert (
            len(function_names) == 1
        ), f"Expected exactly 1 function, got {len(function_names)}: {function_names}"

    @settings(max_examples=100)
    @given(
        func_name=valid_identifiers,
        line_content=st.sampled_from(
            [
                "SELECT * FROM table WHERE column = value",
                "INSERT INTO table VALUES (1, 2, 3)",
                "UPDATE table SET column = value",
                "DELETE FROM table WHERE id = 1",
            ]
        ),
    )
    def test_property_3_regex_pattern_precision(
        self, func_name: str, line_content: str
    ):
        """
        Feature: sql-function-extraction-fix, Property 3: Regex pattern precision

        For any line of SQL code, the CREATE FUNCTION regex pattern should only match lines
        that begin with CREATE FUNCTION (ignoring whitespace) and should not match lines
        within function bodies or lines where CREATE and FUNCTION are separated by other tokens.

        Validates: Requirements 2.1, 2.2, 2.5
        """
        # Skip if function name matches reserved keywords or common column names
        if func_name.upper() in [
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
        ]:
            return

        # Create SQL with a function that has SQL statements in the body
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

        # Parse the SQL code
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

        # Extract SQL elements
        sql_elements = plugin.extractor.extract_sql_elements(tree, sql_code)

        # Extract function names
        function_names = [
            elem.name
            for elem in sql_elements
            if hasattr(elem, "sql_element_type")
            and elem.sql_element_type.value == "function"
        ]

        # Property: Only the CREATE FUNCTION declaration should be matched, not lines in the body
        assert (
            func_name in function_names
        ), f"Expected function '{func_name}' to be extracted"
        assert (
            len(function_names) == 1
        ), f"Expected exactly 1 function, got {len(function_names)}: {function_names}"

        # Verify that keywords from the body are not extracted
        body_keywords = [
            "SELECT",
            "INSERT",
            "UPDATE",
            "DELETE",
            "FROM",
            "WHERE",
            "VALUES",
            "SET",
        ]
        for keyword in body_keywords:
            assert (
                keyword.lower() not in [name.lower() for name in function_names]
            ), f"Keyword '{keyword}' from function body should not be extracted as a function"

    @settings(max_examples=100)
    @given(
        func_name=valid_identifiers, body_lines=st.integers(min_value=1, max_value=20)
    )
    def test_property_2_function_boundary_detection(
        self, func_name: str, body_lines: int
    ):
        """
        Feature: sql-function-extraction-fix, Property 2: Function boundary detection

        For any CREATE FUNCTION statement, the start line should be the line containing
        "CREATE FUNCTION" and the end line should be the line containing the matching
        "END" statement.

        Validates: Requirements 1.5
        """
        # Skip if function name matches reserved keywords or common column names
        if func_name.upper() in [
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
        ]:
            return

        # Generate body content with variable number of lines
        body_statements = []
        for i in range(body_lines):
            body_statements.append(f"    DECLARE var{i} INT DEFAULT {i};")
        body_content = "\n".join(body_statements)

        # Create SQL with a function
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

        # Parse the SQL code
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

        # Extract SQL elements
        sql_elements = plugin.extractor.extract_sql_elements(tree, sql_code)

        # Find the function element
        functions = [
            elem
            for elem in sql_elements
            if hasattr(elem, "sql_element_type")
            and elem.sql_element_type.value == "function"
        ]

        assert len(functions) == 1, f"Expected exactly 1 function, got {len(functions)}"

        func = functions[0]

        # Calculate expected line numbers
        lines = sql_code.split("\n")
        create_function_line = None
        end_line = None

        for i, line in enumerate(lines):
            if "CREATE FUNCTION" in line.upper():
                create_function_line = i + 1  # 1-indexed
            if line.strip().upper() in ["END;", "END"]:
                end_line = i + 1  # 1-indexed

        # Property: start_line should be the CREATE FUNCTION line
        assert (
            func.start_line == create_function_line
        ), f"Expected start_line to be {create_function_line} (CREATE FUNCTION line), got {func.start_line}"

        # Property: end_line should be the END statement line
        assert (
            func.end_line == end_line
        ), f"Expected end_line to be {end_line} (END statement line), got {func.end_line}"

        # Property: end_line should be greater than start_line
        assert (
            func.end_line > func.start_line
        ), f"Expected end_line ({func.end_line}) to be greater than start_line ({func.start_line})"

    @settings(max_examples=100)
    @given(
        invalid_name=st.sampled_from(
            [
                # Common column names
                "price",
                "quantity",
                "total",
                "amount",
                "count",
                "sum",
                "created_at",
                "updated_at",
                "id",
                "name",
                "email",
                "status",
                "value",
                "date",
                "time",
                "timestamp",
                # SQL reserved keywords
                "SELECT",
                "FROM",
                "WHERE",
                "INSERT",
                "UPDATE",
                "DELETE",
                "CREATE",
                "DROP",
                "ALTER",
                "TABLE",
                "VIEW",
                "INDEX",
                "PRIMARY",
                "FOREIGN",
                "KEY",
                "UNIQUE",
                "NULL",
                "BEGIN",
                "END",
                "RETURN",
                "DECLARE",
                # Case variations
                "Price",
                "QUANTITY",
                "Total",
                "AMOUNT",
            ]
        )
    )
    def test_property_4_identifier_validation(self, invalid_name: str):
        """
        Feature: sql-function-extraction-fix, Property 4: Identifier validation

        For any potential function name extracted by the regex, if that name is a common
        SQL column name or SQL reserved keyword, it should be rejected by the validation logic.

        Validates: Requirements 2.3, 2.4
        """
        # Create SQL code that attempts to use an invalid name as a function name
        # This simulates what might happen if the regex incorrectly matches something
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

        # Parse the SQL code
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

        # Extract SQL elements
        sql_elements = plugin.extractor.extract_sql_elements(tree, sql_code)

        # Extract function names
        function_names = [
            elem.name
            for elem in sql_elements
            if hasattr(elem, "sql_element_type")
            and elem.sql_element_type.value == "function"
        ]

        # Property: Invalid identifiers (column names and keywords) should be rejected
        # The function should NOT be extracted if it has an invalid name
        assert (
            invalid_name not in function_names
        ), f"Invalid identifier '{invalid_name}' should not be extracted as a function name"
        assert (
            invalid_name.lower() not in [name.lower() for name in function_names]
        ), f"Invalid identifier '{invalid_name}' (case-insensitive) should not be extracted as a function name"

        # The extraction should result in 0 functions since the name is invalid
        assert (
            len(function_names) == 0
        ), f"Expected 0 functions with invalid name '{invalid_name}', got {len(function_names)}: {function_names}"

    @settings(max_examples=100)
    @given(
        valid_name=valid_identifiers,
        invalid_name=st.sampled_from(
            ["price", "quantity", "total", "SELECT", "FROM", "WHERE"]
        ),
    )
    def test_property_4_valid_vs_invalid_identifiers(
        self, valid_name: str, invalid_name: str
    ):
        """
        Feature: sql-function-extraction-fix, Property 4: Identifier validation (contrast test)

        For any SQL code with both valid and invalid function names, only the valid
        function names should be extracted, while invalid ones (column names and keywords)
        should be rejected.

        Validates: Requirements 2.3, 2.4
        """
        # Skip if valid name happens to be invalid (common column names)
        if valid_name.upper() in [
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
        ]:
            return

        # Skip if valid name is a SQL reserved keyword
        sql_keywords = {
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
        if valid_name.upper() in sql_keywords:
            return

        # Create SQL with two functions: one with valid name, one with invalid name
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

        # Parse the SQL code
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

        # Extract SQL elements
        sql_elements = plugin.extractor.extract_sql_elements(tree, sql_code)

        # Extract function names
        function_names = [
            elem.name
            for elem in sql_elements
            if hasattr(elem, "sql_element_type")
            and elem.sql_element_type.value == "function"
        ]

        # Property: Only valid identifiers should be extracted
        assert (
            valid_name in function_names
        ), f"Valid function name '{valid_name}' should be extracted"
        assert (
            invalid_name not in function_names
        ), f"Invalid function name '{invalid_name}' should not be extracted"
        assert (
            invalid_name.lower() not in [name.lower() for name in function_names]
        ), f"Invalid function name '{invalid_name}' (case-insensitive) should not be extracted"

        # Should extract exactly 1 function (the valid one)
        assert (
            len(function_names) == 1
        ), f"Expected exactly 1 function (valid one), got {len(function_names)}: {function_names}"

    @settings(max_examples=100)
    @given(
        num_functions=st.integers(min_value=1, max_value=5),
        func_names=st.lists(valid_identifiers, min_size=1, max_size=5, unique=True),
    )
    def test_property_5_extraction_count_consistency(
        self, num_functions: int, func_names: list[str]
    ):
        """
        Feature: sql-function-extraction-fix, Property 5: Extraction count consistency

        For any SQL file, the number of extracted functions should equal the number of
        CREATE FUNCTION declarations in the file.

        Validates: Requirements 1.4
        """
        # Filter out invalid function names
        valid_func_names = [
            name
            for name in func_names
            if name.upper()
            not in [
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
            ]
        ]

        # Take only the number of functions we want
        valid_func_names = valid_func_names[:num_functions]

        # Skip if we don't have enough valid names
        if len(valid_func_names) < num_functions:
            return

        # Create SQL with multiple functions
        sql_code = ""
        for func_name in valid_func_names:
            sql_code += f"""
CREATE FUNCTION {func_name}(param INT)
RETURNS INT
READS SQL DATA
DETERMINISTIC
BEGIN
    RETURN param * 2;
END;

"""

        # Parse the SQL code
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

        # Extract SQL elements
        sql_elements = plugin.extractor.extract_sql_elements(tree, sql_code)

        # Extract function names
        function_names = [
            elem.name
            for elem in sql_elements
            if hasattr(elem, "sql_element_type")
            and elem.sql_element_type.value == "function"
        ]

        # Property: Number of extracted functions should equal number of CREATE FUNCTION declarations
        assert (
            len(function_names) == len(valid_func_names)
        ), f"Expected {len(valid_func_names)} functions, got {len(function_names)}: {function_names}"

        # Verify all expected functions are present
        for expected_name in valid_func_names:
            assert (
                expected_name in function_names
            ), f"Expected function '{expected_name}' not found in extracted functions: {function_names}"

    @settings(max_examples=100)
    @given(func_names=st.lists(valid_identifiers, min_size=2, max_size=5, unique=True))
    def test_property_6_output_ordering_preservation(self, func_names: list[str]):
        """
        Feature: sql-function-extraction-fix, Property 6: Output ordering preservation

        For any SQL file with multiple functions, the extracted functions should appear
        in the same order as they appear in the source file.

        Validates: Requirements 3.3
        """
        # Filter out invalid function names
        valid_func_names = [
            name
            for name in func_names
            if name.upper()
            not in [
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
            ]
        ]

        # Skip if we don't have at least 2 valid names
        if len(valid_func_names) < 2:
            return

        # Create SQL with multiple functions in a specific order
        sql_code = ""
        for i, func_name in enumerate(valid_func_names):
            sql_code += f"""
CREATE FUNCTION {func_name}(param INT)
RETURNS INT
READS SQL DATA
DETERMINISTIC
BEGIN
    RETURN param + {i};
END;

"""

        # Parse the SQL code
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

        # Extract SQL elements
        sql_elements = plugin.extractor.extract_sql_elements(tree, sql_code)

        # Extract functions (preserving order)
        extracted_functions = [
            elem
            for elem in sql_elements
            if hasattr(elem, "sql_element_type")
            and elem.sql_element_type.value == "function"
        ]

        # Extract function names in order
        extracted_names = [func.name for func in extracted_functions]

        # Property: Functions should appear in the same order as in the source file
        assert (
            extracted_names == valid_func_names
        ), f"Function order mismatch. Expected: {valid_func_names}, Got: {extracted_names}"

        # Also verify that start_line values are in ascending order
        start_lines = [func.start_line for func in extracted_functions]
        assert start_lines == sorted(
            start_lines
        ), f"Function start lines are not in ascending order: {start_lines}"

    @settings(max_examples=100)
    @given(
        func_names=st.lists(valid_identifiers, min_size=1, max_size=3, unique=True),
        num_runs=st.just(3),  # Run extraction 3 times to verify determinism
    )
    def test_property_7_deterministic_extraction(
        self, func_names: list[str], num_runs: int
    ):
        """
        Feature: sql-function-extraction-fix, Property 7: Deterministic extraction

        For any given SQL input file, running the extraction multiple times should produce
        identical output regardless of execution context.

        Validates: Requirements 3.5
        """
        # Filter out invalid function names
        valid_func_names = [
            name
            for name in func_names
            if name.upper()
            not in [
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
            ]
        ]

        # Skip if we don't have any valid names
        if len(valid_func_names) < 1:
            return

        # Create SQL with functions
        sql_code = ""
        for func_name in valid_func_names:
            sql_code += f"""
CREATE FUNCTION {func_name}(param INT)
RETURNS INT
READS SQL DATA
DETERMINISTIC
BEGIN
    DECLARE result INT;
    SELECT param * 2 INTO result;
    RETURN result;
END;

"""

        # Run extraction multiple times
        all_results = []

        for _ in range(num_runs):
            # Create a fresh plugin instance for each run
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

            # Extract SQL elements
            sql_elements = plugin.extractor.extract_sql_elements(tree, sql_code)

            # Extract function information
            functions = [
                elem
                for elem in sql_elements
                if hasattr(elem, "sql_element_type")
                and elem.sql_element_type.value == "function"
            ]

            # Create a deterministic representation of the extraction result
            result = [(func.name, func.start_line, func.end_line) for func in functions]

            all_results.append(result)

        # Property: All runs should produce identical results
        first_result = all_results[0]
        for i, result in enumerate(all_results[1:], start=1):
            assert (
                result == first_result
            ), f"Run {i+1} produced different results than run 1.\nRun 1: {first_result}\nRun {i+1}: {result}"

        # Verify that we got the expected functions
        extracted_names = [name for name, _, _ in first_result]
        assert (
            extracted_names == valid_func_names
        ), f"Expected functions {valid_func_names}, got {extracted_names}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
