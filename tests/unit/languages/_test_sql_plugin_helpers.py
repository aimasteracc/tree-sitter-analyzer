"""Shared helpers for SQL plugin unit tests."""

import os
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

SAMPLE_DATABASE_EXPECTED_CLASSES = {
    "active_users",
    "order_summary",
    "orders",
    "products",
    "users",
}
SAMPLE_DATABASE_EXPECTED_FUNCTIONS = {
    "calculate_order_total",
    "get_user_orders",
    "is_user_active",
    "log_user_changes",
    "update_order_total",
    "update_product_stock",
}
SAMPLE_DATABASE_EXPECTED_INDEXES = {
    "idx_orders_date",
    "idx_orders_user_date",
    "idx_orders_user_id",
    "idx_products_category",
    "idx_products_name",
    "idx_users_email",
    "idx_users_status",
}

SQL_CONSTRUCT_CASES = [
    {
        "name": "CREATE TABLE",
        "sql": "CREATE TABLE test_table (id INT PRIMARY KEY, name VARCHAR(100));",
        "expected_classes": {"test_table"},
        "expected_functions": set(),
        "expected_variables": set(),
    },
    {
        "name": "CREATE VIEW",
        "sql": "CREATE VIEW test_view AS SELECT id, name FROM test_table;",
        "expected_classes": {"test_view"},
        "expected_functions": set(),
        "expected_variables": set(),
    },
    {
        "name": "CREATE INDEX",
        "sql": "CREATE INDEX idx_test ON test_table(name);",
        "expected_classes": set(),
        "expected_functions": set(),
        "expected_variables": {"idx_test"},
    },
    {
        "name": "CREATE FUNCTION",
        "sql": """CREATE FUNCTION calculate_test(order_id_param INT)
RETURNS DECIMAL(10, 2)
READS SQL DATA
DETERMINISTIC
BEGIN
    DECLARE total DECIMAL(10, 2);
    SELECT COALESCE(SUM(price * quantity), 0) INTO total
    FROM order_items
    WHERE order_id = order_id_param;
    RETURN total;
END;""",
        "expected_classes": set(),
        "expected_functions": {"calculate_test"},
        "expected_variables": set(),
    },
]

E2E_SQL_CONTENT = """
-- Sample database schema
CREATE TABLE customers (
    id INTEGER PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(255) UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE VIEW active_customers AS
SELECT * FROM customers WHERE active = 1;

CREATE INDEX idx_customer_email ON customers(email);

CREATE FUNCTION get_customer_count()
RETURNS INTEGER
BEGIN
    DECLARE count_val INTEGER;
    SELECT COUNT(*) INTO count_val FROM customers;
    RETURN count_val;
END;
"""
SIMPLE_SQL_CONTENT = "CREATE TABLE test (id INT);"
SQL_FALLBACK_ERROR_MESSAGES = ("not available", "Failed", "Unsupported")


def build_sql_parser() -> Any:
    """Build a tree-sitter SQL parser across supported tree-sitter APIs."""
    import tree_sitter_sql
    from tree_sitter import Language

    language = Language(tree_sitter_sql.language())
    return build_parser_for_language(language)


def build_parser_for_language(language: Any) -> Any:
    """Build a parser for an already-loaded tree-sitter language."""
    import tree_sitter

    parser = tree_sitter.Parser()
    if hasattr(parser, "set_language"):
        parser.set_language(language)
    elif hasattr(parser, "language"):
        parser.language = language
    else:
        parser = tree_sitter.Parser(language)
    return parser


def parse_sql(sql_content: str) -> Any:
    """Parse SQL content using tree-sitter-sql."""
    return build_sql_parser().parse(sql_content.encode("utf-8"))


def extract_sql_elements(plugin: Any, sql_content: str) -> list[Any]:
    """Parse SQL content and return SQL-specific elements."""
    return plugin.extractor.extract_sql_elements(parse_sql(sql_content), sql_content)


def assert_sample_database_result(result: Any) -> None:
    """Assert broad sample_database.sql extraction expectations."""
    if not result.success:
        return

    elements_by_type = elements_grouped_by_model_type(result.elements)
    actual_classes = {cls.name for cls in elements_by_type["classes"]}
    assert SAMPLE_DATABASE_EXPECTED_CLASSES.issubset(actual_classes), (
        f"Missing classes: {SAMPLE_DATABASE_EXPECTED_CLASSES - actual_classes}"
    )

    actual_functions = {func.name for func in elements_by_type["functions"]}
    assert actual_functions & SAMPLE_DATABASE_EXPECTED_FUNCTIONS, (
        f"No expected functions found. Got: {actual_functions}"
    )

    actual_indexes = {var.name for var in elements_by_type["variables"]}
    assert actual_indexes & SAMPLE_DATABASE_EXPECTED_INDEXES, (
        f"No expected indexes found. Got: {actual_indexes}"
    )


def elements_grouped_by_model_type(elements: list[Any]) -> dict[str, list[Any]]:
    """Group generic analysis elements by their model class name."""
    elements_by_type: dict[str, list[Any]] = {
        "classes": [],
        "functions": [],
        "variables": [],
        "imports": [],
    }

    for element in elements:
        element_type = type(element).__name__.lower()
        if element_type == "class":
            elements_by_type["classes"].append(element)
        elif element_type == "function":
            elements_by_type["functions"].append(element)
        elif element_type == "variable":
            elements_by_type["variables"].append(element)
        elif element_type == "import":
            elements_by_type["imports"].append(element)

    return elements_by_type


def assert_specific_sql_constructs(plugin: Any) -> None:
    """Assert extraction for a table, view, index, and SQL function."""
    for test_case in SQL_CONSTRUCT_CASES:
        tree = parse_sql(test_case["sql"])
        elements = plugin.extract_elements(tree, test_case["sql"])

        actual_classes = {cls.name for cls in elements["classes"]}
        actual_functions = {func.name for func in elements["functions"]}
        actual_variables = {var.name for var in elements["variables"]}

        assert actual_classes == test_case["expected_classes"], (
            f"{test_case['name']}: Expected classes "
            f"{test_case['expected_classes']}, got {actual_classes}"
        )
        assert actual_functions == test_case["expected_functions"], (
            f"{test_case['name']}: Expected functions "
            f"{test_case['expected_functions']}, got {actual_functions}"
        )
        assert actual_variables == test_case["expected_variables"], (
            f"{test_case['name']}: Expected variables "
            f"{test_case['expected_variables']}, got {actual_variables}"
        )


def assert_table_metadata(sql_elements: list[Any]) -> None:
    """Assert at least one SQL table element exposes metadata fields."""
    assert sql_elements
    tables = [elem for elem in sql_elements if hasattr(elem, "columns")]
    if tables:
        table = tables[0]
        assert hasattr(table, "sql_element_type")
        assert hasattr(table, "columns")
        assert hasattr(table, "constraints")


def assert_product_columns(sql_elements: list[Any]) -> None:
    """Assert products table column extraction covers known columns."""
    tables = [
        elem
        for elem in sql_elements
        if hasattr(elem, "columns") and elem.name == "products"
    ]
    if tables:
        actual_columns = {col.name for col in tables[0].columns}
        expected_columns = {"id", "name", "price", "category_id", "created_at"}
        assert actual_columns & expected_columns


def assert_view_dependencies(sql_elements: list[Any]) -> None:
    """Assert user_orders view exposes dependency metadata when extracted."""
    views = [
        elem
        for elem in sql_elements
        if hasattr(elem, "source_tables") and elem.name == "user_orders"
    ]
    if views:
        view = views[0]
        assert hasattr(view, "source_tables")
        assert hasattr(view, "dependencies")


async def assert_end_to_end_sql_analysis_and_formatting(plugin: Any) -> None:
    """Assert the SQL plugin can analyze and format one realistic SQL file."""
    temp_path = write_temp_sql_file(E2E_SQL_CONTENT)

    try:
        from tree_sitter_analyzer.core.analysis_engine import AnalysisRequest

        request = AnalysisRequest(file_path=temp_path)
        result = await plugin.analyze_file(temp_path, request)

        assert result is not None
        assert result.language == "sql"

        if result.success and len(result.elements) > 0:
            assert_e2e_sql_formatting(plugin, E2E_SQL_CONTENT, temp_path)
    finally:
        os.unlink(temp_path)


async def assert_analysis_with_tree_sitter_disabled(plugin: Any) -> None:
    """Assert analyze_file handles a disabled tree-sitter runtime gracefully."""
    import tree_sitter_analyzer.language_loader as language_loader_module
    import tree_sitter_analyzer.languages.sql_plugin.plugin as sql_plugin_module

    original_value = getattr(sql_plugin_module, "TREE_SITTER_AVAILABLE", True)
    try:
        with (
            patch.object(sql_plugin_module, "TREE_SITTER_AVAILABLE", False),
            patch.object(language_loader_module, "TREE_SITTER_AVAILABLE", False),
        ):
            result = await analyze_temp_sql(plugin, SIMPLE_SQL_CONTENT)
            assert_sql_analysis_result_allows_fallback(result)
    finally:
        sql_plugin_module.TREE_SITTER_AVAILABLE = original_value


async def assert_analysis_with_missing_language(plugin: Any) -> None:
    """Assert analyze_file handles a missing SQL parser language gracefully."""
    with (
        patch(
            "tree_sitter_analyzer.languages.sql_plugin.plugin.TREE_SITTER_AVAILABLE",
            True,
        ),
        patch(
            "tree_sitter_analyzer.language_loader.LanguageLoader.load_language",
            return_value=None,
        ),
    ):
        result = await analyze_temp_sql(plugin, SIMPLE_SQL_CONTENT)
        assert_sql_analysis_result_allows_fallback(result)


async def analyze_temp_sql(plugin: Any, sql_content: str) -> Any:
    """Analyze a temporary SQL file and remove it before returning."""
    temp_path = write_temp_sql_file(sql_content)
    try:
        from tree_sitter_analyzer.core.analysis_engine import AnalysisRequest

        request = AnalysisRequest(file_path=temp_path)
        return await plugin.analyze_file(temp_path, request)
    finally:
        os.unlink(temp_path)


def assert_sql_analysis_result_allows_fallback(result: Any) -> None:
    """Assert the SQL analysis result either succeeds by fallback or fails clearly."""
    assert result is not None
    assert result.language == "sql"
    if not result.success:
        assert any(msg in result.error_message for msg in SQL_FALLBACK_ERROR_MESSAGES)


def write_temp_sql_file(sql_content: str) -> str:
    """Write SQL content to a temporary .sql file and return the path."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".sql", delete=False) as f:
        f.write(sql_content)
        return f.name


def assert_e2e_sql_formatting(
    plugin: Any, sql_content: str, file_path: str | Path
) -> None:
    """Assert all SQL formatters can render extracted SQL elements."""
    extractor = plugin.extractor
    if not hasattr(extractor, "extract_sql_elements"):
        return

    language = plugin.get_tree_sitter_language()
    if not language:
        return

    parser = build_parser_for_language(language)
    tree = parser.parse(sql_content.encode("utf-8"))
    sql_elements = extractor.extract_sql_elements(tree, sql_content)
    if not sql_elements:
        return

    from tree_sitter_analyzer.formatters.sql_formatters import (
        SQLCompactFormatter,
        SQLCSVFormatter,
        SQLFullFormatter,
    )

    formatters = [SQLFullFormatter(), SQLCompactFormatter(), SQLCSVFormatter()]
    for formatter in formatters:
        formatted_result = formatter.format_elements(sql_elements, file_path)
        assert isinstance(formatted_result, str)
        assert formatted_result

        if isinstance(formatter, SQLFullFormatter):
            assert "Database Schema Overview" in formatted_result
        elif isinstance(formatter, SQLCompactFormatter):
            assert "| Element | Type | Lines | Details |" in formatted_result
        elif isinstance(formatter, SQLCSVFormatter):
            assert (
                "Element,Type,Lines,Columns_Parameters,Dependencies" in formatted_result
            )
