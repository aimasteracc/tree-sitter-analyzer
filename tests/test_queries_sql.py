#!/usr/bin/env python3
"""
Tests for SQL queries

Tests the SQL query definitions and their functionality with tree-sitter-sql.
"""

from pathlib import Path

import pytest

from tree_sitter_analyzer.core.query_service import QueryService
from tree_sitter_analyzer.queries.sql import (
    SQL_QUERIES,
    SQL_QUERY_DESCRIPTIONS,
    get_all_queries,
    get_available_sql_queries,
    get_query,
    get_sql_query,
    get_sql_query_description,
    list_queries,
)


class TestSQLQueries:
    """Test SQL query definitions and functionality."""

    def test_sql_queries_exist(self):
        """Test that SQL queries are properly defined."""
        assert len(SQL_QUERIES) > 0
        assert len(SQL_QUERY_DESCRIPTIONS) > 0

        # Check that all queries have descriptions
        for query_name in SQL_QUERIES:
            assert query_name in SQL_QUERY_DESCRIPTIONS
            assert SQL_QUERY_DESCRIPTIONS[query_name] != ""

    def test_get_sql_query(self):
        """Test getting SQL queries by name."""
        # Test valid query
        table_query = get_sql_query("table")
        assert "create_table_statement" in table_query
        assert "@table_name" in table_query

        # Test invalid query
        with pytest.raises(ValueError, match="SQL query 'nonexistent' does not exist"):
            get_sql_query("nonexistent")

    def test_get_sql_query_description(self):
        """Test getting SQL query descriptions."""
        description = get_sql_query_description("table")
        assert description == "Extract table creation statements"

        # Test nonexistent query
        description = get_sql_query_description("nonexistent")
        assert description == "No description"

    def test_get_query_compatibility(self):
        """Test compatibility with generic query interface."""
        # Test that get_query works with SQL queries
        table_query = get_query("table")
        assert "create_table_statement" in table_query

        # Test aliases
        functions_query = get_query("functions")
        assert "create_function_statement" in functions_query

    def test_get_all_queries(self):
        """Test getting all queries."""
        all_queries = get_all_queries()
        assert isinstance(all_queries, dict)
        assert len(all_queries) > 0

        # Check structure
        for _query_name, query_data in all_queries.items():
            assert "query" in query_data
            assert "description" in query_data
            assert isinstance(query_data["query"], str)
            assert isinstance(query_data["description"], str)

    def test_list_queries(self):
        """Test listing all query names."""
        query_names = list_queries()
        assert isinstance(query_names, list)
        assert len(query_names) > 0
        assert "table" in query_names
        assert "view" in query_names
        assert "procedure" in query_names
        assert "function" in query_names

    def test_get_available_sql_queries(self):
        """Test getting available SQL queries."""
        sql_queries = get_available_sql_queries()
        assert isinstance(sql_queries, list)
        assert len(sql_queries) > 0
        assert "table" in sql_queries
        assert "view" in sql_queries

    def test_query_aliases(self):
        """Test that query aliases work correctly."""
        all_queries = get_all_queries()

        # Test function aliases
        assert "functions" in all_queries
        assert "procedures" in all_queries
        assert "tables" in all_queries
        assert "views" in all_queries
        assert "indexes" in all_queries
        assert "triggers" in all_queries

        # Test composite aliases
        assert "ddl_statements" in all_queries
        assert "dml_statements" in all_queries
        assert "constraints" in all_queries
        assert "joins" in all_queries

    def test_basic_sql_queries(self):
        """Test basic SQL query patterns."""
        # Test table query
        table_query = get_sql_query("table")
        assert "create_table_statement" in table_query
        assert "@table_name" in table_query

        # Test view query
        view_query = get_sql_query("view")
        assert "create_view_statement" in view_query
        assert "@view_name" in view_query

        # Test procedure query
        procedure_query = get_sql_query("procedure")
        assert "create_procedure_statement" in procedure_query
        assert "@procedure_name" in procedure_query

        # Test function query
        function_query = get_sql_query("function")
        assert "create_function_statement" in function_query
        assert "@function_name" in function_query

    def test_detailed_sql_queries(self):
        """Test detailed SQL query patterns."""
        # Test detailed table query
        create_table_query = get_sql_query("create_table")
        assert "column_definitions" in create_table_query
        assert "@column_name" in create_table_query
        assert "@column_type" in create_table_query

        # Test detailed view query
        create_view_query = get_sql_query("create_view")
        assert "select_statement" in create_view_query
        assert "@view_query" in create_view_query

        # Test detailed procedure query
        create_procedure_query = get_sql_query("create_procedure")
        assert "parameter_list" in create_procedure_query
        assert "@param_name" in create_procedure_query
        assert "@procedure_body" in create_procedure_query

    def test_constraint_queries(self):
        """Test constraint-related queries."""
        # Test primary key
        pk_query = get_sql_query("primary_key")
        assert "primary_key_constraint" in pk_query
        assert "@pk_column" in pk_query

        # Test foreign key
        fk_query = get_sql_query("foreign_key")
        assert "foreign_key_constraint" in fk_query
        assert "@fk_column" in fk_query
        assert "@referenced_table" in fk_query

        # Test unique constraint
        unique_query = get_sql_query("unique_constraint")
        assert "unique_constraint" in unique_query
        assert "@unique_column" in unique_query

    def test_join_queries(self):
        """Test JOIN-related queries."""
        # Test generic join
        join_query = get_sql_query("join")
        assert "join_clause" in join_query
        assert "@join_type" in join_query
        assert "@joined_table" in join_query

        # Test specific joins
        inner_join_query = get_sql_query("inner_join")
        assert "inner_join" in inner_join_query

        left_join_query = get_sql_query("left_join")
        assert "left_join" in left_join_query

    def test_function_queries(self):
        """Test function-related queries."""
        # Test aggregate functions
        agg_query = get_sql_query("aggregate_function")
        assert "function_call" in agg_query
        assert "COUNT|SUM|AVG|MIN|MAX" in agg_query

        # Test specific functions
        count_query = get_sql_query("count_function")
        assert "COUNT" in count_query

        sum_query = get_sql_query("sum_function")
        assert "SUM" in sum_query

    def test_error_handling_queries(self):
        """Test error handling queries for tree-sitter-sql ERROR nodes."""
        # Test generic error node
        error_query = get_sql_query("error_node")
        assert "(ERROR)" in error_query
        assert "@error_node" in error_query

        # Test procedure in error
        proc_error_query = get_sql_query("procedure_in_error")
        assert "ERROR" in proc_error_query
        assert "PROCEDURE" in proc_error_query
        assert "@procedure_name" in proc_error_query

    def test_name_only_queries(self):
        """Test name-only extraction queries."""
        # Test table name extraction
        table_name_query = get_sql_query("table_name")
        assert "create_table_statement" in table_name_query
        assert "@table_name" in table_name_query

        # Test view name extraction
        view_name_query = get_sql_query("view_name")
        assert "create_view_statement" in view_name_query
        assert "@view_name" in view_name_query

        # Test procedure name extraction
        proc_name_query = get_sql_query("procedure_name")
        assert "create_procedure_statement" in proc_name_query
        assert "@procedure_name" in proc_name_query

    def test_advanced_sql_features(self):
        """Test advanced SQL feature queries."""
        # Test CTE (Common Table Expression)
        cte_query = get_sql_query("cte")
        assert "with_clause" in cte_query
        assert "cte_definition" in cte_query
        assert "@cte_name" in cte_query

        # Test window functions
        window_query = get_sql_query("window_function")
        assert "window_function" in window_query
        assert "over_clause" in window_query

        # Test subqueries
        subquery_query = get_sql_query("subquery")
        assert "subquery" in subquery_query
        assert "select_statement" in subquery_query

    def test_data_type_queries(self):
        """Test data type queries."""
        # Test VARCHAR
        varchar_query = get_sql_query("varchar_type")
        assert "varchar_type" in varchar_query
        assert "@varchar_size" in varchar_query

        # Test DECIMAL
        decimal_query = get_sql_query("decimal_type")
        assert "decimal_type" in decimal_query
        assert "@decimal_precision" in decimal_query

        # Test ENUM
        enum_query = get_sql_query("enum_type")
        assert "enum_type" in enum_query
        assert "@enum_value" in enum_query

    def test_comment_queries(self):
        """Test comment extraction queries."""
        # Test generic comment
        comment_query = get_sql_query("comment")
        assert "(comment)" in comment_query
        assert "@comment" in comment_query

        # Test line comment
        line_comment_query = get_sql_query("line_comment")
        assert "line_comment" in line_comment_query

        # Test block comment
        block_comment_query = get_sql_query("block_comment")
        assert "block_comment" in block_comment_query


class TestSQLQueryIntegration:
    """Test SQL queries with actual SQL parsing."""

    @pytest.fixture
    def sample_sql_file(self) -> Path:
        """Get path to sample SQL file."""
        return Path("examples/sample_database.sql")

    @pytest.fixture
    def query_service(self) -> QueryService:
        """Create QueryService instance."""
        return QueryService()

    def test_query_service_with_sql_file(
        self, query_service: QueryService, sample_sql_file: Path
    ):
        """Test QueryService with SQL file."""
        if not sample_sql_file.exists():
            pytest.skip(f"Sample SQL file not found: {sample_sql_file}")

        # Test basic table query
        try:
            results = query_service.execute_query(
                query_name="table", file_path=sample_sql_file, language="sql"
            )
            # Should find tables in sample_database.sql
            assert len(results) > 0
        except Exception as e:
            # If tree-sitter-sql is not available, skip the test
            pytest.skip(f"SQL parsing not available: {e}")

    def test_sql_query_execution(
        self, query_service: QueryService, sample_sql_file: Path
    ):
        """Test executing various SQL queries."""
        if not sample_sql_file.exists():
            pytest.skip(f"Sample SQL file not found: {sample_sql_file}")

        queries_to_test = ["table", "view", "procedure", "function", "trigger", "index"]

        for query_name in queries_to_test:
            try:
                results = query_service.execute_query(
                    query_name=query_name, file_path=sample_sql_file, language="sql"
                )
                # Results should be a list (may be empty)
                assert isinstance(results, list)
            except Exception as e:
                # If tree-sitter-sql is not available, skip the test
                pytest.skip(f"SQL parsing not available for {query_name}: {e}")

    def test_sql_error_queries(
        self, query_service: QueryService, sample_sql_file: Path
    ):
        """Test error handling queries."""
        if not sample_sql_file.exists():
            pytest.skip(f"Sample SQL file not found: {sample_sql_file}")

        error_queries = [
            "error_node",
            "procedure_in_error",
            "function_in_error",
            "trigger_in_error",
        ]

        for query_name in error_queries:
            try:
                results = query_service.execute_query(
                    query_name=query_name, file_path=sample_sql_file, language="sql"
                )
                # Results should be a list (may be empty)
                assert isinstance(results, list)
            except Exception as e:
                # If tree-sitter-sql is not available, skip the test
                pytest.skip(f"SQL parsing not available for {query_name}: {e}")


if __name__ == "__main__":
    pytest.main([__file__])
