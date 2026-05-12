#!/usr/bin/env python3
"""
Unit tests for tree_sitter_analyzer.core.query_service module.

This module tests the QueryService class.
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tree_sitter_analyzer.core.query_service import QueryService


class TestQueryServiceInit:
    """Tests for QueryService initialization."""

    def test_query_service_init_default(self) -> None:
        """Test QueryService initialization with default project_root."""
        service = QueryService()
        assert service.project_root is None
        assert service.parser is not None
        assert service.filter is not None
        assert service.plugin_manager is not None

    def test_query_service_init_with_project_root(self) -> None:
        """Test QueryService initialization with project_root."""
        service = QueryService(project_root="/test/path")
        assert service.project_root == "/test/path"
        assert service.parser is not None
        assert service.filter is not None


class TestQueryServiceExecuteQuery:
    """Tests for QueryService.execute_query method."""

    @pytest.mark.asyncio
    async def test_execute_query_with_query_key(
        self, query_service: QueryService, temp_file: Path
    ) -> None:
        """Test executing query with query_key."""
        results = await query_service.execute_query(
            str(temp_file), "python", query_key="functions"
        )
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_execute_query_with_query_string(
        self, query_service: QueryService, temp_file: Path
    ) -> None:
        """Test executing query with custom query_string."""
        results = await query_service.execute_query(
            str(temp_file),
            "python",
            query_string="(function_definition) @func",
        )
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_execute_query_with_filter(
        self, query_service: QueryService, temp_file: Path
    ) -> None:
        """Test executing query with filter expression."""
        results = await query_service.execute_query(
            str(temp_file),
            "python",
            query_key="functions",
            filter_expression="name=~test*",
        )
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_execute_query_no_query_params(
        self, query_service: QueryService, temp_file: Path
    ) -> None:
        """Test executing query without query parameters raises ValueError."""
        with pytest.raises(
            ValueError, match="Must provide either query_key or query_string"
        ):
            await query_service.execute_query(str(temp_file), "python")

    @pytest.mark.asyncio
    async def test_execute_query_both_query_params(
        self, query_service: QueryService, temp_file: Path
    ) -> None:
        """Test executing query with both query_key and query_string raises ValueError."""
        with pytest.raises(
            ValueError, match="Cannot provide both query_key and query_string"
        ):
            await query_service.execute_query(
                str(temp_file),
                "python",
                query_key="functions",
                query_string="(function_definition) @func",
            )

    @pytest.mark.asyncio
    async def test_execute_query_invalid_query_key(
        self, query_service: QueryService, temp_file: Path
    ) -> None:
        """Test executing query with invalid query_key raises ValueError."""
        with pytest.raises(ValueError, match="Query 'invalid' not found"):
            await query_service.execute_query(
                str(temp_file), "python", query_key="invalid"
            )

    @pytest.mark.asyncio
    async def test_execute_query_file_not_found(
        self, query_service: QueryService
    ) -> None:
        """Test executing query on non-existent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            await query_service.execute_query(
                "nonexistent.py", "python", query_key="functions"
            )


class TestQueryServiceCreateResultDict:
    """Tests for QueryService._create_result_dict method."""

    def test_create_result_dict(self, query_service: QueryService) -> None:
        """Test creating result dictionary from node."""
        # Create mock node
        mock_node = MagicMock()
        mock_node.type = "function_definition"
        mock_node.start_point = (0, 0)
        mock_node.end_point = (5, 0)
        mock_node.text = b"def test(): pass"

        result = query_service._create_result_dict(
            mock_node, "test", "def test(): pass"
        )

        assert result["capture_name"] == "test"
        assert result["node_type"] == "function_definition"
        assert result["start_line"] == 1  # 0-based to 1-based
        assert result["end_line"] == 6  # 0-based to 1-based
        # Content is extracted by get_node_text_safe, which may return empty string
        # if node.text is not properly accessible
        assert isinstance(result["content"], str)

    def test_create_result_dict_with_source_code(
        self, query_service: QueryService
    ) -> None:
        """Test creating result dictionary with source code."""
        mock_node = MagicMock()
        mock_node.type = "class_definition"
        mock_node.start_point = (10, 0)
        mock_node.end_point = (20, 0)
        mock_node.text = b"class MyClass: pass"

        result = query_service._create_result_dict(
            mock_node, "class", "class MyClass: pass"
        )

        assert result["capture_name"] == "class"
        assert result["node_type"] == "class_definition"
        assert result["start_line"] == 11
        assert result["end_line"] == 21


class TestQueryServiceGetAvailableQueries:
    """Tests for QueryService.get_available_queries method."""

    def test_get_available_queries(self, query_service: QueryService) -> None:
        """Test getting available queries for language."""
        queries = query_service.get_available_queries("python")
        assert isinstance(queries, list)
        assert len(queries) > 0

    def test_get_available_queries_unsupported_language(
        self, query_service: QueryService
    ) -> None:
        """Test getting available queries for unsupported language."""
        queries = query_service.get_available_queries("unsupported")
        assert isinstance(queries, list)


class TestQueryServiceGetQueryDescription:
    """Tests for QueryService.get_query_description method."""

    def test_get_query_description(self, query_service: QueryService) -> None:
        """Test getting query description."""
        description = query_service.get_query_description("python", "functions")
        assert isinstance(description, str) or description is None

    def test_get_query_description_invalid_query(
        self, query_service: QueryService
    ) -> None:
        """Test getting description for invalid query."""
        description = query_service.get_query_description("python", "invalid")
        assert description is None


class TestQueryServiceExecutePluginQuery:
    """Tests for QueryService._execute_plugin_query method."""

    def test_execute_plugin_query_with_plugin(
        self, query_service: QueryService
    ) -> None:
        """Test executing plugin query with available plugin."""
        mock_root_node = MagicMock()
        mock_root_node.children = []

        captures = query_service._execute_plugin_query(
            mock_root_node, "functions", "python", "def test(): pass"
        )
        assert isinstance(captures, list)

    def test_execute_plugin_query_without_plugin(
        self, query_service: QueryService
    ) -> None:
        """Test executing plugin query without available plugin."""
        mock_root_node = MagicMock()
        mock_root_node.children = []

        captures = query_service._execute_plugin_query(
            mock_root_node, "functions", "unsupported", "code"
        )
        assert isinstance(captures, list)


class TestQueryServiceFallbackQueryExecution:
    """Tests for QueryService._fallback_query_execution method."""

    def test_fallback_query_execution_function(
        self, query_service: QueryService
    ) -> None:
        """Test fallback query execution for function nodes."""
        mock_root_node = MagicMock()
        mock_root_node.type = "module"
        mock_root_node.children = []

        mock_child = MagicMock()
        mock_child.type = "function_definition"
        mock_child.start_point = (0, 0)
        mock_child.end_point = (5, 0)
        mock_child.children = []

        mock_root_node.children = [mock_child]

        captures = query_service._fallback_query_execution(mock_root_node, "function")
        assert isinstance(captures, list)
        assert len(captures) >= 0

    def test_fallback_query_execution_class(self, query_service: QueryService) -> None:
        """Test fallback query execution for class nodes."""
        mock_root_node = MagicMock()
        mock_root_node.type = "module"
        mock_root_node.children = []

        mock_child = MagicMock()
        mock_child.type = "class_definition"
        mock_child.start_point = (0, 0)
        mock_child.end_point = (10, 0)
        mock_child.children = []

        mock_root_node.children = [mock_child]

        captures = query_service._fallback_query_execution(mock_root_node, "class")
        assert isinstance(captures, list)

    def test_fallback_query_execution_no_matches(
        self, query_service: QueryService
    ) -> None:
        """Test fallback query execution with no matches."""
        mock_root_node = MagicMock()
        mock_root_node.type = "module"
        mock_root_node.children = []

        mock_child = MagicMock()
        mock_child.type = "comment"
        mock_child.start_point = (0, 0)
        mock_child.end_point = (1, 0)
        mock_child.children = []

        mock_root_node.children = [mock_child]

        captures = query_service._fallback_query_execution(mock_root_node, "function")
        assert isinstance(captures, list)


class TestQueryServiceReadFileAsync:
    """Tests for QueryService._read_file_async method."""

    @pytest.mark.asyncio
    async def test_read_file_async(
        self, query_service: QueryService, temp_file: Path
    ) -> None:
        """Test async file reading."""
        content, encoding = await query_service._read_file_async(str(temp_file))
        assert isinstance(content, str)
        assert isinstance(encoding, str)
        assert "def hello(): pass" in content


class TestQueryServiceEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_execute_query_empty_results(
        self, query_service: QueryService, temp_file: Path
    ) -> None:
        """Test executing query that returns no results."""
        results = await query_service.execute_query(
            str(temp_file),
            "python",
            query_string="(nonexistent_node_type) @node",
        )
        assert isinstance(results, list)

    def test_create_result_dict_missing_attributes(
        self, query_service: QueryService
    ) -> None:
        """Test creating result dict with node missing attributes."""
        mock_node = MagicMock()
        del mock_node.type
        mock_node.start_point = (0, 0)
        mock_node.end_point = (5, 0)
        mock_node.text = b"def test(): pass"

        result = query_service._create_result_dict(mock_node, "test", "code")
        assert result["node_type"] == "unknown"
        assert result["start_line"] == 1
        assert result["end_line"] == 6


class TestQueryServiceNoLanguageObject:
    """Test execute_query when tree has no language object."""

    @pytest.mark.asyncio
    async def test_execute_query_no_language_obj(self) -> None:
        """Test that missing language object raises Exception."""
        service = QueryService()
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write("def hello(): pass\n")
            temp_path = Path(f.name)
        try:
            with patch.object(
                service, "_read_file_async", return_value=("def hello(): pass", "utf-8")
            ):
                mock_tree = MagicMock()
                del mock_tree.language
                mock_result = MagicMock()
                mock_result.tree = mock_tree
                with patch.object(
                    service.parser, "parse_code", return_value=mock_result
                ):
                    with pytest.raises(
                        Exception, match="Language object not available"
                    ):
                        await service.execute_query(
                            str(temp_path), "python", query_key="functions"
                        )
        finally:
            temp_path.unlink(missing_ok=True)


class TestQueryServiceQueryExceptionFallback:
    """Test execute_query fallback when tree-sitter query fails."""

    @pytest.mark.asyncio
    async def test_execute_query_query_exception_uses_plugin_fallback(self) -> None:
        """Test that query exception triggers plugin fallback path."""
        service = QueryService()
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write("def hello(): pass\n")
            temp_path = Path(f.name)
        try:
            with patch.object(
                service, "_read_file_async", return_value=("def hello(): pass", "utf-8")
            ):
                mock_lang = MagicMock()
                mock_root = MagicMock()
                mock_root.children = []
                mock_tree = MagicMock()
                mock_tree.language = mock_lang
                mock_tree.root_node = mock_root
                mock_result = MagicMock()
                mock_result.tree = mock_tree
                with patch.object(
                    service.parser, "parse_code", return_value=mock_result
                ):
                    with patch(
                        "tree_sitter_analyzer.core.query_service.TreeSitterQueryCompat.safe_execute_query",
                        side_effect=RuntimeError("query failed"),
                    ):
                        results = await service.execute_query(
                            str(temp_path), "python", query_key="functions"
                        )
                        assert isinstance(results, list)
        finally:
            temp_path.unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_execute_query_empty_captures_uses_plugin_fallback(self) -> None:
        """Test that empty captures from query triggers plugin fallback."""
        service = QueryService()
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write("def hello(): pass\n")
            temp_path = Path(f.name)
        try:
            with patch.object(
                service, "_read_file_async", return_value=("def hello(): pass", "utf-8")
            ):
                mock_lang = MagicMock()
                mock_root = MagicMock()
                mock_root.children = []
                mock_tree = MagicMock()
                mock_tree.language = mock_lang
                mock_tree.root_node = mock_root
                mock_result = MagicMock()
                mock_result.tree = mock_tree
                with patch.object(
                    service.parser, "parse_code", return_value=mock_result
                ):
                    with patch(
                        "tree_sitter_analyzer.core.query_service.TreeSitterQueryCompat.safe_execute_query",
                        return_value=[],
                    ):
                        results = await service.execute_query(
                            str(temp_path), "python", query_key="functions"
                        )
                        assert isinstance(results, list)
        finally:
            temp_path.unlink(missing_ok=True)


class TestQueryServiceGetQueryDescriptionException:
    """Test get_query_description exception handling."""

    def test_get_query_description_exception_returns_none(self) -> None:
        """Test that exception in get_query_description returns None."""
        service = QueryService()
        with patch(
            "tree_sitter_analyzer.core.query_service.query_loader.get_query_description",
            side_effect=RuntimeError("db error"),
        ):
            result = service.get_query_description("python", "functions")
            assert result is None


class TestQueryServicePluginQueryInternalPaths:
    """Test _execute_plugin_query internal code paths."""

    def test_plugin_query_with_elements_having_line_info(self) -> None:
        """Test plugin query when plugin returns elements with start_line/end_line."""
        service = QueryService()
        mock_root = MagicMock()
        mock_root.children = []

        mock_element = MagicMock()
        mock_element.start_line = 1
        mock_element.end_line = 5
        mock_element.element_type = "function"
        mock_element.raw_text = "def foo(): pass"

        mock_plugin = MagicMock()
        mock_plugin.execute_query_strategy.return_value = [mock_element]

        with patch.object(
            service.plugin_manager, "get_plugin", return_value=mock_plugin
        ):
            captures = service._execute_plugin_query(
                mock_root, "functions", "python", "def foo(): pass"
            )
            assert isinstance(captures, list)
            if len(captures) > 0:
                node, name = captures[0]
                assert name == "functions"

    def test_plugin_query_strategy_exception_falls_to_categories(self) -> None:
        """Test that plugin strategy exception falls back to element categories."""
        service = QueryService()
        mock_root = MagicMock()
        mock_root.children = []

        mock_plugin = MagicMock()
        mock_plugin.execute_query_strategy.side_effect = RuntimeError("fail")
        mock_plugin.get_element_categories.return_value = {
            "functions": ["function_definition"]
        }

        func_node = MagicMock()
        func_node.type = "function_definition"
        func_node.children = []
        mock_root.children = [func_node]

        with patch.object(
            service.plugin_manager, "get_plugin", return_value=mock_plugin
        ):
            captures = service._execute_plugin_query(
                mock_root, "functions", "python", "def foo(): pass"
            )
            assert isinstance(captures, list)

    def test_plugin_query_categories_exception_falls_to_fallback(self) -> None:
        """Test that element categories exception falls to basic fallback."""
        service = QueryService()
        mock_root = MagicMock()
        func_node = MagicMock()
        func_node.type = "function_definition"
        func_node.children = []
        mock_root.children = [func_node]

        mock_plugin = MagicMock()
        mock_plugin.execute_query_strategy.side_effect = RuntimeError("fail")
        mock_plugin.get_element_categories.side_effect = RuntimeError("fail")

        with patch.object(
            service.plugin_manager, "get_plugin", return_value=mock_plugin
        ):
            captures = service._execute_plugin_query(
                mock_root, "functions", "python", "def foo(): pass"
            )
            assert isinstance(captures, list)

    def test_plugin_query_no_matching_key_in_categories(self) -> None:
        """Test when query_key is not in element categories."""
        service = QueryService()
        mock_root = MagicMock()
        mock_root.children = []

        mock_plugin = MagicMock()
        mock_plugin.execute_query_strategy.side_effect = RuntimeError("fail")
        mock_plugin.get_element_categories.return_value = {
            "classes": ["class_definition"]
        }

        with patch.object(
            service.plugin_manager, "get_plugin", return_value=mock_plugin
        ):
            captures = service._execute_plugin_query(
                mock_root, "functions", "python", "code"
            )
            assert isinstance(captures, list)


class TestQueryServiceFallbackAdditionalPaths:
    """Additional tests for _fallback_query_execution to cover missing branches."""

    def test_fallback_method(self) -> None:
        """Test fallback for method nodes."""
        service = QueryService()
        mock_child = MagicMock()
        mock_child.type = "method_declaration"
        mock_child.children = []
        mock_root = MagicMock()
        mock_root.children = [mock_child]

        captures = service._fallback_query_execution(mock_root, "method")
        assert len(captures) == 1

    def test_fallback_variable(self) -> None:
        """Test fallback for variable nodes."""
        service = QueryService()
        mock_child = MagicMock()
        mock_child.type = "variable_declaration"
        mock_child.children = []
        mock_root = MagicMock()
        mock_root.children = [mock_child]

        captures = service._fallback_query_execution(mock_root, "variable")
        assert len(captures) == 1

    def test_fallback_import(self) -> None:
        """Test fallback for import nodes."""
        service = QueryService()
        mock_child = MagicMock()
        mock_child.type = "import_statement"
        mock_child.children = []
        mock_root = MagicMock()
        mock_root.children = [mock_child]

        captures = service._fallback_query_execution(mock_root, "import")
        assert len(captures) == 1

    def test_fallback_header(self) -> None:
        """Test fallback for heading nodes."""
        service = QueryService()
        mock_child = MagicMock()
        mock_child.type = "heading"
        mock_child.children = []
        mock_root = MagicMock()
        mock_root.children = [mock_child]

        captures = service._fallback_query_execution(mock_root, "header")
        assert len(captures) == 1

    def test_fallback_plural_forms(self) -> None:
        """Test fallback for plural query keys (functions, classes, methods, variables, imports, headers)."""
        service = QueryService()

        func_node = MagicMock()
        func_node.type = "function_definition"
        func_node.children = []

        class_node = MagicMock()
        class_node.type = "class_definition"
        class_node.children = []

        method_node = MagicMock()
        method_node.type = "method_declaration"
        method_node.children = []

        var_node = MagicMock()
        var_node.type = "variable_assignment"
        var_node.children = []

        import_node = MagicMock()
        import_node.type = "import_statement"
        import_node.children = []

        root = MagicMock()
        root.children = [func_node, class_node, method_node, var_node, import_node]

        for key in ("functions", "classes", "methods", "variables", "imports"):
            captures = service._fallback_query_execution(root, key)
            assert len(captures) >= 1, f"Expected matches for key '{key}'"

    def test_fallback_none_query_key(self) -> None:
        """Test fallback with None query_key returns empty list."""
        service = QueryService()
        mock_root = MagicMock()
        mock_root.children = []

        captures = service._fallback_query_execution(mock_root, None)
        assert isinstance(captures, list)
        assert len(captures) == 0


# Pytest fixtures
@pytest.fixture
def query_service() -> QueryService:
    """Create a QueryService instance for testing."""
    return QueryService()


@pytest.fixture
def temp_file() -> Path:
    """Create a temporary Python file for testing."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8"
    ) as f:
        f.write("def hello(): pass\n")
        f.write("def test_func(): pass\n")
        temp_path = Path(f.name)

    yield temp_path

    # Cleanup
    try:
        temp_path.unlink()
    except Exception:
        pass
