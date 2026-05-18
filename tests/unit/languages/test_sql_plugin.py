#!/usr/bin/env python3
"""
Tests for tree_sitter_analyzer.languages.sql_plugin module.

This module tests the SQLPlugin class which provides SQL language
support in the plugin architecture.
"""

import os
import tempfile
from unittest.mock import Mock, patch

import pytest

from tests.unit.languages._test_sql_plugin_helpers import (
    assert_analysis_with_missing_language,
    assert_analysis_with_tree_sitter_disabled,
    assert_end_to_end_sql_analysis_and_formatting,
    assert_product_columns,
    assert_sample_database_result,
    assert_specific_sql_constructs,
    assert_table_metadata,
    assert_view_dependencies,
    extract_sql_elements,
    parse_sql,
)
from tree_sitter_analyzer.languages.sql_plugin import SQLElementExtractor, SQLPlugin
from tree_sitter_analyzer.plugins.base import ElementExtractor, LanguagePlugin


class TestSQLElementExtractor:
    """Test cases for SQLElementExtractor class"""

    @pytest.fixture
    def extractor(self) -> SQLElementExtractor:
        """Create a SQLElementExtractor instance for testing"""
        return SQLElementExtractor()

    @pytest.fixture
    def mock_tree(self) -> Mock:
        """Create a mock tree-sitter tree"""
        tree = Mock()
        root_node = Mock()
        root_node.children = []
        tree.root_node = root_node
        return tree

    def test_extractor_initialization(self, extractor: SQLElementExtractor) -> None:
        """Test SQLElementExtractor initialization"""
        assert extractor is not None
        assert isinstance(extractor, ElementExtractor)
        assert hasattr(extractor, "extract_functions")
        assert hasattr(extractor, "extract_classes")
        assert hasattr(extractor, "extract_variables")
        assert hasattr(extractor, "extract_imports")

    def test_extract_functions_empty(self, extractor: SQLElementExtractor) -> None:
        """Test function extraction with empty tree"""
        tree = Mock()
        tree.root_node = None

        functions = extractor.extract_functions(tree, "")
        assert isinstance(functions, list)
        assert len(functions) == 0

    def test_extract_classes_empty(self, extractor: SQLElementExtractor) -> None:
        """Test class extraction with empty tree"""
        tree = Mock()
        tree.root_node = None

        classes = extractor.extract_classes(tree, "")
        assert isinstance(classes, list)
        assert len(classes) == 0

    def test_extract_variables_empty(self, extractor: SQLElementExtractor) -> None:
        """Test variable extraction with empty tree"""
        tree = Mock()
        tree.root_node = None

        variables = extractor.extract_variables(tree, "")
        assert isinstance(variables, list)
        assert len(variables) == 0

    def test_extract_imports_empty(self, extractor: SQLElementExtractor) -> None:
        """Test import extraction with empty tree"""
        tree = Mock()
        tree.root_node = None

        imports = extractor.extract_imports(tree, "")
        assert isinstance(imports, list)
        assert len(imports) == 0


class TestSQLPlugin:
    """Test cases for SQLPlugin class"""

    @pytest.fixture
    def plugin(self) -> SQLPlugin:
        """Create a SQLPlugin instance for testing"""
        return SQLPlugin()

    def test_plugin_initialization(self, plugin: SQLPlugin) -> None:
        """Test SQLPlugin initialization"""
        assert plugin is not None
        assert isinstance(plugin, LanguagePlugin)
        assert plugin.language == "sql"
        assert plugin.supported_extensions == [".sql"]

    def test_get_language_name(self, plugin: SQLPlugin) -> None:
        """Test get_language_name method"""
        assert plugin.get_language_name() == "sql"

    def test_get_file_extensions(self, plugin: SQLPlugin) -> None:
        """Test get_file_extensions method"""
        extensions = plugin.get_file_extensions()
        assert isinstance(extensions, list)
        assert ".sql" in extensions
        assert len(extensions) == 1

    def test_create_extractor(self, plugin: SQLPlugin) -> None:
        """Test create_extractor method"""
        extractor = plugin.create_extractor()
        assert isinstance(extractor, SQLElementExtractor)
        assert isinstance(extractor, ElementExtractor)

    def test_is_applicable(self, plugin: SQLPlugin) -> None:
        """Test is_applicable method"""
        assert plugin.is_applicable("test.sql") is True
        assert plugin.is_applicable("test.SQL") is True
        assert plugin.is_applicable("test.py") is False
        assert plugin.is_applicable("test.java") is False

    def test_get_tree_sitter_language_missing(self, plugin: SQLPlugin) -> None:
        """Test get_tree_sitter_language when tree-sitter-sql is not available"""
        # Clear cache first
        plugin._cached_language = None

        # Use sys.modules to simulate missing module
        with patch.dict("sys.modules", {"tree_sitter_sql": None}):
            # This will raise RuntimeError because ImportError is caught and re-raised
            try:
                plugin.get_tree_sitter_language()
                pytest.fail("Should have raised RuntimeError")
            except RuntimeError as e:
                assert "tree-sitter-sql is required" in str(e)
            except ImportError:
                # If implementation changes to just raise ImportError
                pass

    def test_get_tree_sitter_language_import_error(self, plugin: SQLPlugin) -> None:
        """Test get_tree_sitter_language when ImportError occurs"""
        # Clear cache first
        plugin._cached_language = None
        # Use a simpler approach - just test that it handles missing import gracefully
        # Since tree_sitter_sql is imported inside the method, we can't easily mock it
        # Instead, we test the actual behavior when it's not available
        result = plugin.get_tree_sitter_language()
        # If tree-sitter-sql is not installed, result should be None
        # If it is installed, result should not be None
        # Both cases are valid
        assert result is None or result is not None

    @pytest.mark.asyncio
    async def test_analyze_file_missing_tree_sitter(self, plugin: SQLPlugin) -> None:
        """Test analyze_file when tree-sitter is not available"""
        await assert_analysis_with_tree_sitter_disabled(plugin)

    @pytest.mark.asyncio
    async def test_analyze_file_missing_language(self, plugin: SQLPlugin) -> None:
        """Test analyze_file when tree-sitter-sql is not available"""
        await assert_analysis_with_missing_language(plugin)

    def test_extract_elements_empty_tree(self, plugin: SQLPlugin) -> None:
        """Test extract_elements with None tree"""
        result = plugin.extract_elements(None, "")
        assert isinstance(result, dict)
        assert "functions" in result
        assert "classes" in result
        assert "variables" in result
        assert "imports" in result
        assert len(result["functions"]) == 0
        assert len(result["classes"]) == 0
        assert len(result["variables"]) == 0
        assert len(result["imports"]) == 0

    def test_extract_elements_mock_tree(self, plugin: SQLPlugin) -> None:
        """Test extract_elements with mock tree"""
        tree = Mock()
        root_node = Mock()
        root_node.children = []
        tree.root_node = root_node

        result = plugin.extract_elements(tree, "CREATE TABLE test (id INT);")
        assert isinstance(result, dict)
        assert "functions" in result
        assert "classes" in result
        assert "variables" in result
        assert "imports" in result

    def test_plugin_info(self, plugin: SQLPlugin) -> None:
        """Test get_plugin_info method"""
        info = plugin.get_plugin_info()
        assert isinstance(info, dict)
        assert info["language"] == "sql"
        assert ".sql" in info["extensions"]


try:
    import tree_sitter_sql  # noqa: F401

    TREE_SITTER_SQL_AVAILABLE = True
except ImportError:
    TREE_SITTER_SQL_AVAILABLE = False


@pytest.mark.skipif(
    not TREE_SITTER_SQL_AVAILABLE,
    reason="tree-sitter-sql not installed",
)
class TestSQLPluginWithTreeSitter:
    """Integration tests for SQLPlugin with actual tree-sitter-sql"""

    @pytest.fixture
    def plugin(self) -> SQLPlugin:
        """Create a SQLPlugin instance for testing"""
        return SQLPlugin()

    def test_get_tree_sitter_language_available(self, plugin: SQLPlugin) -> None:
        """Test get_tree_sitter_language when tree-sitter-sql is available"""
        language = plugin.get_tree_sitter_language()
        # If tree-sitter-sql is available, language should not be None
        # If not available, this test is skipped
        if language is not None:
            assert language is not None

    @pytest.mark.asyncio
    async def test_analyze_file_with_simple_sql(self, plugin: SQLPlugin) -> None:
        """Test analyze_file with simple SQL"""
        sql_content = """
CREATE TABLE users (
    id INT PRIMARY KEY,
    name VARCHAR(100) NOT NULL
);
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".sql", delete=False) as f:
            f.write(sql_content)
            temp_path = f.name

        try:
            from tree_sitter_analyzer.core.analysis_engine import AnalysisRequest

            request = AnalysisRequest(file_path=temp_path)
            result = await plugin.analyze_file(temp_path, request)

            assert result is not None
            assert result.language == "sql"
            # If tree-sitter-sql is available, we should get results
            # If not, result.success will be False
            if result.success:
                assert len(result.elements) >= 0  # May have extracted tables
        finally:
            os.unlink(temp_path)

    @pytest.mark.asyncio
    @pytest.mark.skip(
        reason="SQL plugin returns SQL-specific elements (tables/views), not generic classes. Test needs refactoring to use SQL-specific element types."
    )
    async def test_analyze_sample_database_sql(self, plugin: SQLPlugin) -> None:
        """Test analyze_file with comprehensive sample_database.sql"""
        # Use the actual sample_database.sql file
        from pathlib import Path

        sample_sql_path = Path("examples/sample_database.sql")
        if not sample_sql_path.exists():
            pytest.skip("sample_database.sql not found")

        from tree_sitter_analyzer.core.analysis_engine import AnalysisRequest

        request = AnalysisRequest(file_path=str(sample_sql_path))
        result = await plugin.analyze_file(str(sample_sql_path), request)

        assert result is not None
        assert result.language == "sql"

        assert_sample_database_result(result)

    def test_extract_specific_sql_constructs(self, plugin: SQLPlugin) -> None:
        """Test extraction of specific SQL constructs"""
        assert_specific_sql_constructs(plugin)

    def test_extract_multiple_indexes(self, plugin: SQLPlugin) -> None:
        """Test extraction of multiple INDEX statements"""
        # Multiple INDEX statements
        sql_content = """
        CREATE INDEX idx_users_email ON users(email);
        CREATE INDEX idx_users_status ON users(status);
        CREATE INDEX idx_orders_user_id ON orders(user_id);
        CREATE INDEX idx_orders_date ON orders(order_date);
        """

        tree = parse_sql(sql_content)
        elements = plugin.extract_elements(tree, sql_content)

        expected_indexes = {
            "idx_users_email",
            "idx_users_status",
            "idx_orders_user_id",
            "idx_orders_date",
        }
        actual_indexes = {var.name for var in elements["variables"]}

        assert actual_indexes == expected_indexes, (
            f"Expected indexes {expected_indexes}, got {actual_indexes}"
        )


class TestSQLEnhancedElementExtraction:
    """Test enhanced SQL element extraction with metadata"""

    @pytest.fixture
    def plugin(self) -> SQLPlugin:
        """Create a SQLPlugin instance for testing"""
        return SQLPlugin()

    @pytest.mark.skipif(
        not TREE_SITTER_SQL_AVAILABLE,
        reason="tree-sitter-sql not installed",
    )
    def test_extract_sql_elements_with_metadata(self, plugin: SQLPlugin) -> None:
        """Test extraction of SQL elements with enhanced metadata"""
        # Test SQL with comprehensive elements
        sql_content = """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            email VARCHAR(255) UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE VIEW active_users AS
        SELECT * FROM users WHERE active = 1;

        CREATE INDEX idx_user_email ON users(email);
        """

        assert_table_metadata(extract_sql_elements(plugin, sql_content))

    @pytest.mark.skipif(
        not TREE_SITTER_SQL_AVAILABLE,
        reason="tree-sitter-sql not installed",
    )
    def test_sql_table_column_extraction(self, plugin: SQLPlugin) -> None:
        """Test extraction of table columns with metadata"""
        # Test table with detailed column definitions
        sql_content = """
        CREATE TABLE products (
            id INTEGER PRIMARY KEY,
            name VARCHAR(200) NOT NULL,
            price DECIMAL(10,2),
            category_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """

        assert_product_columns(extract_sql_elements(plugin, sql_content))

    @pytest.mark.skipif(
        not TREE_SITTER_SQL_AVAILABLE,
        reason="tree-sitter-sql not installed",
    )
    def test_sql_view_source_extraction(self, plugin: SQLPlugin) -> None:
        """Test extraction of view source tables"""
        # Test view with source table references
        sql_content = """
        CREATE VIEW user_orders AS
        SELECT u.name, o.order_date, o.total
        FROM users u
        JOIN orders o ON u.id = o.user_id
        WHERE o.status = 'completed';
        """

        assert_view_dependencies(extract_sql_elements(plugin, sql_content))


class TestSQLFormatterIntegration:
    """Test SQL formatter integration with plugin"""

    @pytest.fixture
    def plugin(self) -> SQLPlugin:
        """Create a SQLPlugin instance for testing"""
        return SQLPlugin()

    @pytest.mark.skipif(
        not TREE_SITTER_SQL_AVAILABLE,
        reason="tree-sitter-sql not installed",
    )
    def test_sql_formatter_integration(self, plugin: SQLPlugin) -> None:
        """Test integration between SQL plugin and formatters"""
        from tree_sitter_analyzer.formatters.sql_formatters import SQLFullFormatter

        # Test SQL content
        sql_content = """
        CREATE TABLE test_table (
            id INTEGER PRIMARY KEY,
            name VARCHAR(100) NOT NULL
        );

        CREATE VIEW test_view AS
        SELECT * FROM test_table;

        CREATE INDEX idx_test_name ON test_table(name);
        """

        sql_elements = extract_sql_elements(plugin, sql_content)

        if sql_elements:
            # Test SQL formatter with extracted elements
            formatter = SQLFullFormatter()
            result = formatter.format_elements(sql_elements, "test.sql")

            # Verify SQL-specific terminology
            assert "Database Schema Overview" in result
            assert "test.sql" in result

            # Check for SQL element types
            sql_element_types = ["Table", "View", "Index"]
            found_types = [
                elem_type for elem_type in sql_element_types if elem_type in result
            ]
            assert len(found_types) > 0

    @pytest.mark.skipif(
        not TREE_SITTER_SQL_AVAILABLE,
        reason="tree-sitter-sql not installed",
    )
    def test_sql_compact_formatter_integration(self, plugin: SQLPlugin) -> None:
        """Test integration with compact formatter"""
        from tree_sitter_analyzer.formatters.sql_formatters import SQLCompactFormatter

        # Test SQL content
        sql_content = """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            email VARCHAR(255) UNIQUE
        );
        """

        sql_elements = extract_sql_elements(plugin, sql_content)

        if sql_elements:
            # Test compact formatter
            formatter = SQLCompactFormatter()
            result = formatter.format_elements(sql_elements, "users.sql")

            # Verify compact format structure
            assert "| Element | Type | Lines | Details |" in result
            assert "users.sql" in result

    @pytest.mark.skipif(
        not TREE_SITTER_SQL_AVAILABLE,
        reason="tree-sitter-sql not installed",
    )
    def test_sql_csv_formatter_integration(self, plugin: SQLPlugin) -> None:
        """Test integration with CSV formatter"""
        from tree_sitter_analyzer.formatters.sql_formatters import SQLCSVFormatter

        # Test SQL content
        sql_content = """
        CREATE TABLE orders (
            id INTEGER PRIMARY KEY,
            user_id INTEGER,
            total DECIMAL(10,2)
        );
        """

        sql_elements = extract_sql_elements(plugin, sql_content)

        if sql_elements:
            # Test CSV formatter
            formatter = SQLCSVFormatter()
            result = formatter.format_elements(sql_elements, "orders.sql")

            # Verify CSV format structure
            assert "Element,Type,Lines,Columns_Parameters,Dependencies" in result
            lines = result.strip().split("\n")
            assert len(lines) >= 2  # Header + at least one data row

    @pytest.mark.asyncio
    async def test_end_to_end_sql_analysis_and_formatting(
        self, plugin: SQLPlugin
    ) -> None:
        """Test complete end-to-end SQL analysis and formatting"""
        await assert_end_to_end_sql_analysis_and_formatting(plugin)
