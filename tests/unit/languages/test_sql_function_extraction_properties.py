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
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from tests.unit.languages._test_sql_function_extraction_properties_helpers import (
    assert_deterministic_extraction,
    assert_extraction_count_consistency,
    assert_function_body_content_exclusion,
    assert_function_boundary_detection,
    assert_invalid_identifier_rejected,
    assert_output_ordering_preservation,
    assert_regex_pattern_precision,
    assert_sql_keywords_exclusion,
    assert_valid_vs_invalid_identifier_extraction,
)


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


valid_identifiers = st.text(
    alphabet=st.characters(
        whitelist_categories=("Lu", "Ll"), min_codepoint=65, max_codepoint=122
    ),
    min_size=1,
    max_size=20,
).filter(lambda x: x and x[0].isalpha() and x.replace("_", "").isalnum())

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

    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
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
        assert_function_body_content_exclusion(func_name, column_name)

    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
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
        assert_sql_keywords_exclusion(func_name, keyword)

    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
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
        assert_regex_pattern_precision(func_name, line_content)

    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
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
        assert_function_boundary_detection(func_name, body_lines)

    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    @given(
        invalid_name=st.sampled_from(
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
                "value",
                "date",
                "time",
                "timestamp",
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
        assert_invalid_identifier_rejected(invalid_name)

    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
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
        assert_valid_vs_invalid_identifier_extraction(valid_name, invalid_name)

    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
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
        assert_extraction_count_consistency(num_functions, func_names)

    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    @given(func_names=st.lists(valid_identifiers, min_size=2, max_size=5, unique=True))
    def test_property_6_output_ordering_preservation(self, func_names: list[str]):
        """
        Feature: sql-function-extraction-fix, Property 6: Output ordering preservation

        For any SQL file with multiple functions, the extracted functions should appear
        in the same order as they appear in the source file.

        Validates: Requirements 3.3
        """
        assert_output_ordering_preservation(func_names)

    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    @given(
        func_names=st.lists(valid_identifiers, min_size=1, max_size=3, unique=True),
        num_runs=st.just(3),
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
        assert_deterministic_extraction(func_names, num_runs)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
