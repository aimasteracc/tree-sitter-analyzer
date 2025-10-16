#!/usr/bin/env python3
"""
Tests for Query Service

Tests for the unified query service that provides tree-sitter query functionality
for both CLI and MCP interfaces, including plugin-based query execution.
"""

from unittest.mock import Mock, patch

import pytest

from tree_sitter_analyzer.core.query_service import QueryService


class TestQueryService:
    """Test QueryService functionality"""

    def setup_method(self):
        """Setup for each test method"""
        self.service = QueryService()

    def test_query_service_initialization(self):
        """Test QueryService initialization"""
        assert self.service.project_root is None
        assert self.service.parser is not None
        assert self.service.filter is not None
        assert self.service.plugin_manager is not None

    def test_query_service_initialization_with_project_root(self):
        """Test QueryService initialization with project root"""
        project_root = "/test/project"
        service = QueryService(project_root)
        assert service.project_root == project_root

    @pytest.mark.asyncio
    async def test_execute_query_missing_parameters(self):
        """Test execute_query with missing parameters"""
        with pytest.raises(
            ValueError, match="Must provide either query_key or query_string"
        ):
            await self.service.execute_query("test.py", "python")

    @pytest.mark.asyncio
    async def test_execute_query_both_parameters(self):
        """Test execute_query with both query_key and query_string"""
        with pytest.raises(
            ValueError, match="Cannot provide both query_key and query_string"
        ):
            await self.service.execute_query(
                "test.py",
                "python",
                query_key="methods",
                query_string="(method_declaration) @method",
            )

    @pytest.mark.asyncio
    async def test_execute_query_file_not_found(self):
        """Test execute_query with non-existent file"""
        with patch.object(self.service, "_read_file_async") as mock_read:
            mock_read.side_effect = FileNotFoundError("File not found")

            with pytest.raises(FileNotFoundError):
                await self.service.execute_query(
                    "nonexistent.py", "python", query_key="methods"
                )

    @pytest.mark.asyncio
    async def test_execute_query_parse_failure(self):
        """Test execute_query with parse failure"""
        with patch.object(self.service, "_read_file_async") as mock_read:
            mock_read.return_value = ("def test(): pass", "utf-8")

            with patch.object(self.service.parser, "parse_code") as mock_parse:
                mock_parse.return_value = None

                with pytest.raises(Exception, match="Failed to parse file"):
                    await self.service.execute_query(
                        "test.py", "python", query_key="methods"
                    )

    @pytest.mark.asyncio
    async def test_execute_query_no_language_object(self):
        """Test execute_query with no language object"""
        with patch.object(self.service, "_read_file_async") as mock_read:
            mock_read.return_value = ("def test(): pass", "utf-8")

            mock_tree = Mock()
            mock_tree.language = None
            mock_parse_result = Mock()
            mock_parse_result.tree = mock_tree

            with patch.object(self.service.parser, "parse_code") as mock_parse:
                mock_parse.return_value = mock_parse_result

                with pytest.raises(Exception, match="Language object not available"):
                    await self.service.execute_query(
                        "test.py", "python", query_key="methods"
                    )

    @pytest.mark.asyncio
    async def test_execute_query_with_query_key_success(self):
        """Test successful execute_query with query_key"""
        test_content = "def test_function(): pass"

        with patch.object(self.service, "_read_file_async") as mock_read:
            mock_read.return_value = (test_content, "utf-8")

            # Mock parse result
            mock_language = Mock()
            mock_tree = Mock()
            mock_tree.language = mock_language
            mock_tree.root_node = Mock()
            mock_parse_result = Mock()
            mock_parse_result.tree = mock_tree

            with patch.object(self.service.parser, "parse_code") as mock_parse:
                mock_parse.return_value = mock_parse_result

                # Mock query loader
                with patch(
                    "tree_sitter_analyzer.core.query_service.query_loader"
                ) as mock_loader:
                    mock_loader.get_query.return_value = (
                        "(function_definition) @function"
                    )

                    # Mock TreeSitterQueryCompat.safe_execute_query
                    with patch(
                        "tree_sitter_analyzer.core.query_service.TreeSitterQueryCompat.safe_execute_query"
                    ) as mock_execute:
                        # Mock node for capture result
                        mock_node = Mock()
                        mock_node.type = "function_definition"
                        mock_node.start_point = (0, 4)
                        mock_node.end_point = (0, 17)
                        mock_node.start_byte = 4  # "test_function" starts at position 4
                        mock_node.end_byte = 17  # "test_function" ends at position 17

                        mock_execute.return_value = [(mock_node, "function")]

                        result = await self.service.execute_query(
                            "test.py", "python", query_key="functions"
                        )

                        assert isinstance(result, list)
                        assert len(result) == 1
                        assert result[0]["capture_name"] == "function"
                        assert result[0]["node_type"] == "function_definition"
                        assert result[0]["content"] == "test_function"

    @pytest.mark.asyncio
    async def test_execute_query_with_custom_query_string(self):
        """Test execute_query with custom query string"""
        test_content = "class TestClass: pass"

        with patch.object(self.service, "_read_file_async") as mock_read:
            mock_read.return_value = (test_content, "utf-8")

            # Mock parse result
            mock_language = Mock()
            mock_tree = Mock()
            mock_tree.language = mock_language
            mock_tree.root_node = Mock()
            mock_parse_result = Mock()
            mock_parse_result.tree = mock_tree

            with patch.object(self.service.parser, "parse_code") as mock_parse:
                mock_parse.return_value = mock_parse_result

                # Mock TreeSitterQueryCompat.safe_execute_query
                with patch(
                    "tree_sitter_analyzer.core.query_service.TreeSitterQueryCompat.safe_execute_query"
                ) as mock_execute:
                    # Mock node for capture result
                    mock_node = Mock()
                    mock_node.type = "class_definition"
                    mock_node.start_point = (0, 0)
                    mock_node.end_point = (0, 20)
                    mock_node.start_byte = 0
                    mock_node.end_byte = 9

                    mock_execute.return_value = [(mock_node, "class")]

                    result = await self.service.execute_query(
                        "test.py", "python", query_string="(class_definition) @class"
                    )

                    assert isinstance(result, list)
                    assert len(result) == 1
                    assert result[0]["capture_name"] == "class"
                    assert result[0]["node_type"] == "class_definition"

    @pytest.mark.asyncio
    async def test_execute_query_with_filter(self):
        """Test execute_query with filter expression"""
        test_content = "def test_function(): pass\ndef another_function(): pass"

        with patch.object(self.service, "_read_file_async") as mock_read:
            mock_read.return_value = (test_content, "utf-8")

            # Mock parse result
            mock_language = Mock()
            mock_tree = Mock()
            mock_tree.language = mock_language
            mock_tree.root_node = Mock()
            mock_parse_result = Mock()
            mock_parse_result.tree = mock_tree

            with patch.object(self.service.parser, "parse_code") as mock_parse:
                mock_parse.return_value = mock_parse_result

                # Mock query loader
                with patch(
                    "tree_sitter_analyzer.core.query_service.query_loader"
                ) as mock_loader:
                    mock_loader.get_query.return_value = (
                        "(function_definition) @function"
                    )

                    # Mock TreeSitterQueryCompat.safe_execute_query
                    with patch(
                        "tree_sitter_analyzer.core.query_service.TreeSitterQueryCompat.safe_execute_query"
                    ) as mock_execute:
                        # Mock nodes for capture results
                        mock_node1 = Mock()
                        mock_node1.type = "function_definition"
                        mock_node1.start_point = (0, 0)
                        mock_node1.end_point = (0, 20)
                        mock_node1.start_byte = 0
                        mock_node1.end_byte = 13

                        mock_node2 = Mock()
                        mock_node2.type = "function_definition"
                        mock_node2.start_point = (1, 0)
                        mock_node2.end_point = (1, 25)
                        mock_node2.start_byte = 21
                        mock_node2.end_byte = 37

                        mock_execute.return_value = [
                            (mock_node1, "function"),
                            (mock_node2, "function"),
                        ]

                        # Mock filter
                        with patch.object(
                            self.service.filter, "filter_results"
                        ) as mock_filter:
                            mock_filter.return_value = [
                                {
                                    "capture_name": "function",
                                    "node_type": "function_definition",
                                    "start_line": 1,
                                    "end_line": 1,
                                    "content": "test_function",
                                }
                            ]

                            result = await self.service.execute_query(
                                "test.py",
                                "python",
                                query_key="functions",
                                filter_expression="name=test_function",
                            )

                            assert isinstance(result, list)
                            assert len(result) == 1
                            assert result[0]["content"] == "test_function"
                            mock_filter.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_query_manual_fallback(self):
        """Test execute_query with manual fallback when tree-sitter fails"""
        test_content = "def test_function(): pass"

        with patch.object(self.service, "_read_file_async") as mock_read:
            mock_read.return_value = (test_content, "utf-8")

            # Mock parse result
            mock_language = Mock()
            mock_tree = Mock()
            mock_tree.language = mock_language
            mock_tree.root_node = Mock()
            mock_parse_result = Mock()
            mock_parse_result.tree = mock_tree

            with patch.object(self.service.parser, "parse_code") as mock_parse:
                mock_parse.return_value = mock_parse_result

                # Mock query loader
                with patch(
                    "tree_sitter_analyzer.core.query_service.query_loader"
                ) as mock_loader:
                    mock_loader.get_query.return_value = (
                        "(function_definition) @function"
                    )

                    # Mock TreeSitterQueryCompat.safe_execute_query to return empty (triggering plugin fallback)
                    with patch(
                        "tree_sitter_analyzer.core.query_service.TreeSitterQueryCompat.safe_execute_query"
                    ) as mock_execute:
                        mock_execute.return_value = []

                        # Mock plugin query execution
                        with patch.object(
                            self.service, "_execute_plugin_query"
                        ) as mock_plugin:
                            mock_node = Mock()
                            mock_node.type = "function_definition"
                            mock_node.start_point = (0, 0)
                            mock_node.end_point = (0, 20)
                            mock_node.start_byte = 0
                            mock_node.end_byte = 13

                            mock_plugin.return_value = [(mock_node, "function")]

                            result = await self.service.execute_query(
                                "test.py", "python", query_key="functions"
                            )

                            assert isinstance(result, list)
                            assert len(result) == 1
                            mock_plugin.assert_called()

    @pytest.mark.asyncio
    async def test_execute_query_unknown_query_key(self):
        """Test execute_query with unknown query key"""
        with patch.object(self.service, "_read_file_async") as mock_read:
            mock_read.return_value = ("def test(): pass", "utf-8")

            # Mock parse result
            mock_language = Mock()
            mock_tree = Mock()
            mock_tree.language = mock_language
            mock_tree.root_node = Mock()
            mock_parse_result = Mock()
            mock_parse_result.tree = mock_tree

            with patch.object(self.service.parser, "parse_code") as mock_parse:
                mock_parse.return_value = mock_parse_result

                # Mock query loader to return None
                with patch(
                    "tree_sitter_analyzer.core.query_service.query_loader"
                ) as mock_loader:
                    mock_loader.get_query.return_value = None

                    with pytest.raises(ValueError, match="Query 'unknown' not found"):
                        await self.service.execute_query(
                            "test.py", "python", query_key="unknown"
                        )

    def test_get_available_queries(self):
        """Test get_available_queries method"""
        with patch(
            "tree_sitter_analyzer.core.query_service.query_loader"
        ) as mock_loader:
            mock_loader.list_queries.return_value = ["functions", "classes", "methods"]

            result = self.service.get_available_queries("python")

            assert result == ["functions", "classes", "methods"]
            mock_loader.list_queries.assert_called_once_with("python")

    def test_get_query_description(self):
        """Test get_query_description method"""
        with patch(
            "tree_sitter_analyzer.core.query_service.query_loader"
        ) as mock_loader:
            mock_loader.get_query_description.return_value = (
                "Extract function definitions"
            )

            result = self.service.get_query_description("python", "functions")

            assert result == "Extract function definitions"
            mock_loader.get_query_description.assert_called_once_with(
                "python", "functions"
            )

    def test_get_query_description_not_found(self):
        """Test get_query_description with not found query"""
        with patch(
            "tree_sitter_analyzer.core.query_service.query_loader"
        ) as mock_loader:
            mock_loader.get_query_description.side_effect = Exception("Not found")

            result = self.service.get_query_description("python", "unknown")

            assert result is None

    def test_create_result_dict(self):
        """Test _create_result_dict method"""
        mock_node = Mock()
        mock_node.type = "function_definition"
        mock_node.start_point = (5, 0)
        mock_node.end_point = (10, 0)
        mock_node.start_byte = 0
        mock_node.end_byte = 13

        source_code = "test_function"
        result = self.service._create_result_dict(mock_node, "function", source_code)

        expected = {
            "capture_name": "function",
            "node_type": "function_definition",
            "start_line": 6,  # 0-based to 1-based
            "end_line": 11,  # 0-based to 1-based
            "content": "test_function",
        }

        assert result == expected

    def test_create_result_dict_no_text(self):
        """Test _create_result_dict with node without text"""
        mock_node = Mock()
        mock_node.type = "function_definition"
        mock_node.start_point = (5, 0)
        mock_node.end_point = (10, 0)
        # No start_byte/end_byte attributes to simulate missing text

        result = self.service._create_result_dict(mock_node, "function", "")

        assert result["content"] == ""

    def test_create_result_dict_missing_attributes(self):
        """Test _create_result_dict with missing node attributes"""
        mock_node = Mock()
        # Remove attributes to simulate missing node attributes
        if hasattr(mock_node, "type"):
            del mock_node.type
        if hasattr(mock_node, "start_point"):
            del mock_node.start_point
        if hasattr(mock_node, "end_point"):
            del mock_node.end_point

        result = self.service._create_result_dict(mock_node, "function", "")

        expected = {
            "capture_name": "function",
            "node_type": "unknown",
            "start_line": 0,
            "end_line": 0,
            "content": "",
        }

        assert result == expected


class TestQueryServiceManualExecution:
    """Test manual query execution functionality"""

    def setup_method(self):
        """Setup for each test method"""
        self.service = QueryService()

    def test_manual_query_execution_python(self):
        """Test manual query execution for Python"""
        # Create mock root node with Python function
        mock_function_node = Mock()
        mock_function_node.type = "function_definition"
        mock_function_node.children = []

        mock_root_node = Mock()
        mock_root_node.children = [mock_function_node]

        result = self.service._fallback_query_execution(mock_root_node, "function")

        assert len(result) == 1
        assert result[0][0] == mock_function_node
        assert result[0][1] == "function"

    def test_manual_query_execution_javascript(self):
        """Test manual query execution for JavaScript"""
        # Create mock root node with JavaScript function
        mock_function_node = Mock()
        mock_function_node.type = "function_declaration"
        mock_function_node.children = []

        mock_root_node = Mock()
        mock_root_node.children = [mock_function_node]

        result = self.service._fallback_query_execution(mock_root_node, "function")

        assert len(result) == 1
        assert result[0][0] == mock_function_node
        assert result[0][1] == "function"

    def test_manual_query_execution_java(self):
        """Test manual query execution for Java"""
        # Create mock root node with Java method
        mock_method_node = Mock()
        mock_method_node.type = "method_declaration"
        mock_method_node.children = []

        mock_root_node = Mock()
        mock_root_node.children = [mock_method_node]

        result = self.service._fallback_query_execution(mock_root_node, "method")

        assert len(result) == 1
        assert result[0][0] == mock_method_node
        assert result[0][1] == "method"

    def test_manual_query_execution_html(self):
        """Test manual query execution for HTML"""
        # Create mock root node with HTML element
        mock_element_node = Mock()
        mock_element_node.type = "element"
        mock_element_node.children = []

        mock_root_node = Mock()
        mock_root_node.children = [mock_element_node]

        # The fallback execution doesn't handle generic elements without query_key
        # So we need to test with a specific query or modify the implementation
        result = self.service._fallback_query_execution(mock_root_node, "element")

        # Since the current implementation doesn't handle "element" query_key, result will be empty
        assert len(result) == 0

    def test_manual_query_execution_css(self):
        """Test manual query execution for CSS"""
        # Create mock root node with CSS rule
        mock_rule_node = Mock()
        mock_rule_node.type = "rule_set"
        mock_rule_node.children = []

        mock_root_node = Mock()
        mock_root_node.children = [mock_rule_node]

        # The fallback execution doesn't handle generic rules without query_key
        # So we need to test with a specific query or modify the implementation
        result = self.service._fallback_query_execution(mock_root_node, "rule")

        # Since the current implementation doesn't handle "rule" query_key, result will be empty
        assert len(result) == 0

    def test_manual_query_execution_with_plugin(self):
        """Test manual query execution with plugin support"""
        # Mock plugin
        mock_plugin = Mock()
        mock_plugin.execute_query_strategy.return_value = []  # Plugin strategy returns empty
        mock_plugin.get_element_categories.return_value = {
            "functions": ["function_definition"]
        }

        with patch.object(self.service.plugin_manager, "get_plugin") as mock_get_plugin:
            mock_get_plugin.return_value = mock_plugin

            # Create mock root node
            mock_function_node = Mock()
            mock_function_node.type = "function_definition"
            mock_function_node.children = []

            mock_root_node = Mock()
            mock_root_node.children = [mock_function_node]

            result = self.service._fallback_query_execution(mock_root_node, "functions")

            assert len(result) == 1
            assert result[0][0] == mock_function_node
            assert result[0][1] == "functions"

    def test_manual_query_execution_markdown(self):
        """Test manual query execution for Markdown"""
        # Create mock root node with Markdown header
        mock_header_node = Mock()
        mock_header_node.type = "atx_heading"
        mock_header_node.children = []

        mock_root_node = Mock()
        mock_root_node.children = [mock_header_node]

        result = self.service._fallback_query_execution(mock_root_node, "headers")

        assert len(result) == 1
        assert result[0][0] == mock_header_node
        assert result[0][1] == "headers"

    def test_manual_query_execution_recursive(self):
        """Test manual query execution with nested nodes"""
        # Create nested structure
        mock_inner_function = Mock()
        mock_inner_function.type = "function_definition"
        mock_inner_function.children = []

        mock_class_node = Mock()
        mock_class_node.type = "class_definition"
        mock_class_node.children = [mock_inner_function]

        mock_root_node = Mock()
        mock_root_node.children = [mock_class_node]

        result = self.service._fallback_query_execution(mock_root_node, "function")

        # Should find the nested function
        assert len(result) == 1
        assert result[0][0] == mock_inner_function
        assert result[0][1] == "function"


class TestQueryServiceIntegration:
    """Test QueryService integration scenarios"""

    def setup_method(self):
        """Setup for each test method"""
        self.service = QueryService("/test/project")

    @pytest.mark.asyncio
    async def test_full_query_workflow(self):
        """Test complete query workflow"""
        test_content = """
def function1():
    pass

class TestClass:
    def method1(self):
        pass
"""

        with patch.object(self.service, "_read_file_async") as mock_read:
            mock_read.return_value = (test_content, "utf-8")

            # Mock successful parsing and query execution
            mock_language = Mock()
            mock_tree = Mock()
            mock_tree.language = mock_language
            mock_tree.root_node = Mock()
            mock_parse_result = Mock()
            mock_parse_result.tree = mock_tree

            with patch.object(self.service.parser, "parse_code") as mock_parse:
                mock_parse.return_value = mock_parse_result

                with patch(
                    "tree_sitter_analyzer.core.query_service.query_loader"
                ) as mock_loader:
                    mock_loader.get_query.return_value = (
                        "(function_definition) @function"
                    )

                    # Mock TreeSitterQueryCompat.safe_execute_query
                    with patch(
                        "tree_sitter_analyzer.core.query_service.TreeSitterQueryCompat.safe_execute_query"
                    ) as mock_execute:
                        # Mock multiple function nodes with correct byte positions based on actual content
                        # test_content positions: "function1" is at byte 5-13, "method1" is at byte 53-59
                        mock_node1 = Mock()
                        mock_node1.type = "function_definition"
                        mock_node1.start_point = (1, 0)
                        mock_node1.end_point = (2, 0)
                        mock_node1.start_byte = 5  # "function1" starts at position 5
                        mock_node1.end_byte = (
                            14  # "function1" ends at position 14 (includes full name)
                        )

                        mock_node2 = Mock()
                        mock_node2.type = "function_definition"
                        mock_node2.start_point = (5, 4)
                        mock_node2.end_point = (6, 0)
                        mock_node2.start_byte = 53  # "method1" starts at position 53
                        mock_node2.end_byte = (
                            60  # "method1" ends at position 60 (includes full name)
                        )

                        mock_execute.return_value = [
                            (mock_node1, "function"),
                            (mock_node2, "function"),
                        ]

                        result = await self.service.execute_query(
                            "test.py", "python", query_key="functions"
                        )

                        assert len(result) == 2
                        assert result[0]["content"] == "function1"
                        assert result[1]["content"] == "method1"

    def test_query_service_error_handling(self):
        """Test QueryService error handling"""
        # Test with invalid project root
        service = QueryService("invalid/path")
        assert service.project_root == "invalid/path"

        # Test available queries with error
        with patch(
            "tree_sitter_analyzer.core.query_service.query_loader"
        ) as mock_loader:
            mock_loader.list_queries.side_effect = Exception("Query loader error")

            # Should raise exception as the current implementation doesn't handle it
            with pytest.raises(Exception, match="Query loader error"):
                service.get_available_queries("python")
