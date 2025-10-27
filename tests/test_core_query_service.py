#!/usr/bin/env python3
"""
Tests for QueryService

Comprehensive tests for the unified query service functionality.
"""

from unittest.mock import Mock, patch

import pytest

from tree_sitter_analyzer.core.parser import ParseResult
from tree_sitter_analyzer.core.query_service import QueryService


class TestQueryService:
    """Test cases for QueryService"""

    def setup_method(self):
        """Set up test fixtures"""
        self.query_service = QueryService()

        # Mock parser and parse result
        self.mock_parser = Mock()
        self.mock_tree = Mock()
        self.mock_language_obj = Mock()
        self.mock_parse_result = ParseResult(
            tree=self.mock_tree,
            source_code="public class Test {}",
            language="java",
            file_path="test.java",
            success=True,
            error_message=None,
        )

        # Configure mocks
        self.mock_tree.language = self.mock_language_obj
        self.mock_parser.parse_code.return_value = self.mock_parse_result

    @pytest.mark.asyncio
    async def test_execute_query_with_key_success(self):
        """Test successful query execution with predefined key"""
        # Mock dependencies
        with (
            patch(
                "tree_sitter_analyzer.core.query_service.read_file_safe"
            ) as mock_read,
            patch(
                "tree_sitter_analyzer.core.query_service.Parser"
            ) as mock_parser_class,
            patch(
                "tree_sitter_analyzer.core.query_service.query_loader"
            ) as mock_loader,
            patch(
                "tree_sitter_analyzer.core.query_service.Query"
            ) as mock_query_class,
            patch(
                "tree_sitter_analyzer.core.query_service.QueryCursor"
            ) as mock_cursor_class,
        ):
            # Setup mocks
            mock_read.return_value = (
                "public class Test { public void main() {} }",
                "utf-8",
            )
            mock_parser_class.return_value = self.mock_parser
            mock_loader.get_query.return_value = "(method_declaration) @method"

            # Mock tree-sitter query and cursor (new API)
            mock_node = Mock()
            mock_node.type = "method_declaration"
            mock_node.start_point = (0, 0)
            mock_node.end_point = (0, 20)
            mock_node.text = b"public void main() {}"

            # Mock QueryCursor to use new matches() API
            mock_cursor = Mock()
            # matches() returns [(pattern_index, {capture_name: [nodes]})]
            mock_cursor.matches.return_value = [(0, {"method": [mock_node]})]
            mock_cursor_class.return_value = mock_cursor

            # Execute query
            result = await self.query_service.execute_query(
                "test.java", "java", query_key="methods"
            )

            # Verify results
            assert result is not None
            assert len(result) == 1
            assert result[0]["capture_name"] == "method"
            assert result[0]["node_type"] == "method_declaration"
            assert result[0]["start_line"] == 1
            assert result[0]["end_line"] == 1
            assert result[0]["content"] == "public void main() {}"

    @pytest.mark.asyncio
    async def test_execute_query_with_string_success(self):
        """Test successful query execution with custom string"""
        # Mock dependencies
        with (
            patch(
                "tree_sitter_analyzer.core.query_service.read_file_safe"
            ) as mock_read,
            patch(
                "tree_sitter_analyzer.core.query_service.Parser"
            ) as mock_parser_class,
            patch(
                "tree_sitter_analyzer.core.query_service.Query"
            ) as mock_query_class,
            patch(
                "tree_sitter_analyzer.core.query_service.QueryCursor"
            ) as mock_cursor_class,
        ):
            # Setup mocks
            mock_read.return_value = ("class Test {}", "utf-8")
            mock_parser_class.return_value = self.mock_parser

            # Mock tree-sitter query and cursor (new API)
            mock_node = Mock()
            mock_node.type = "class_declaration"
            mock_node.start_point = (0, 0)
            mock_node.end_point = (0, 12)
            mock_node.text = b"class Test {}"

            # Mock QueryCursor to use new matches() API
            mock_cursor = Mock()
            # matches() returns [(pattern_index, {capture_name: [nodes]})]
            mock_cursor.matches.return_value = [(0, {"class": [mock_node]})]
            mock_cursor_class.return_value = mock_cursor

            # Execute query
            result = await self.query_service.execute_query(
                "test.java", "java", query_string="(class_declaration) @class"
            )

            # Verify results
            assert result is not None
            assert len(result) == 1
            assert result[0]["capture_name"] == "class"
            assert result[0]["node_type"] == "class_declaration"

    @pytest.mark.asyncio
    async def test_execute_query_with_filter(self):
        """Test query execution with filter expression"""
        # Mock dependencies
        with (
            patch(
                "tree_sitter_analyzer.core.query_service.read_file_safe"
            ) as mock_read,
            patch(
                "tree_sitter_analyzer.core.query_service.Parser"
            ) as mock_parser_class,
            patch(
                "tree_sitter_analyzer.core.query_service.query_loader"
            ) as mock_loader,
            patch(
                "tree_sitter_analyzer.core.query_service.Query"
            ) as mock_query_class,
            patch(
                "tree_sitter_analyzer.core.query_service.QueryCursor"
            ) as mock_cursor_class,
        ):
            # Setup mocks
            mock_read.return_value = (
                "public class Test { public void main() {} }",
                "utf-8",
            )
            mock_parser_class.return_value = self.mock_parser
            mock_loader.get_query.return_value = "(method_declaration) @method"

            # Mock tree-sitter query with multiple results (new API)
            mock_node1 = Mock()
            mock_node1.type = "method_declaration"
            mock_node1.start_point = (0, 0)
            mock_node1.end_point = (0, 20)
            mock_node1.text = b"public void main() {}"

            mock_node2 = Mock()
            mock_node2.type = "method_declaration"
            mock_node2.start_point = (1, 0)
            mock_node2.end_point = (1, 25)
            mock_node2.text = b"public void helper() {}"

            # Mock QueryCursor to use new matches() API
            mock_cursor = Mock()
            # matches() returns [(pattern_index, {capture_name: [nodes]})]
            mock_cursor.matches.return_value = [
                (0, {"method": [mock_node1, mock_node2]})
            ]
            mock_cursor_class.return_value = mock_cursor

            # Mock filter to return only first result
            mock_filter = Mock()
            mock_filter.filter_results.return_value = [
                {
                    "capture_name": "method",
                    "node_type": "method_declaration",
                    "start_line": 1,
                    "end_line": 1,
                    "content": "public void main() {}",
                }
            ]
            self.query_service.filter = mock_filter

            # Execute query with filter
            result = await self.query_service.execute_query(
                "test.java", "java", query_key="methods", filter_expression="name=main"
            )

            # Verify filter was called
            mock_filter.filter_results.assert_called_once()
            assert len(result) == 1
            assert result[0]["content"] == "public void main() {}"

    @pytest.mark.asyncio
    async def test_execute_query_no_parameters_error(self):
        """Test error when no query parameters provided"""
        with pytest.raises(
            ValueError, match="Must provide either query_key or query_string"
        ):
            await self.query_service.execute_query("test.java", "java")

    @pytest.mark.asyncio
    async def test_execute_query_both_parameters_error(self):
        """Test error when both query parameters provided"""
        with pytest.raises(
            ValueError, match="Cannot provide both query_key and query_string"
        ):
            await self.query_service.execute_query(
                "test.java",
                "java",
                query_key="methods",
                query_string="(method_declaration) @method",
            )

    @pytest.mark.asyncio
    async def test_execute_query_file_not_found(self):
        """Test error handling when file doesn't exist"""
        with patch(
            "tree_sitter_analyzer.core.query_service.read_file_safe"
        ) as mock_read:
            mock_read.side_effect = FileNotFoundError("File not found")

            with pytest.raises(FileNotFoundError):
                await self.query_service.execute_query(
                    "nonexistent.java", "java", query_key="methods"
                )

    @pytest.mark.asyncio
    async def test_execute_query_parse_failure(self):
        """Test error handling when file parsing fails"""
        with patch(
            "tree_sitter_analyzer.core.query_service.read_file_safe"
        ) as mock_read:
            mock_read.return_value = ("invalid code", "utf-8")
            # Mock the parser instance method directly
            self.query_service.parser.parse_code = Mock(return_value=None)

            with pytest.raises(Exception, match="Failed to parse file"):
                await self.query_service.execute_query(
                    "invalid.java", "java", query_key="methods"
                )

    @pytest.mark.asyncio
    async def test_execute_query_invalid_query_key(self):
        """Test error handling when query key is not found"""
        with (
            patch(
                "tree_sitter_analyzer.core.query_service.read_file_safe"
            ) as mock_read,
            patch(
                "tree_sitter_analyzer.core.query_service.Parser"
            ) as mock_parser_class,
            patch(
                "tree_sitter_analyzer.core.query_service.query_loader"
            ) as mock_loader,
        ):
            mock_read.return_value = ("public class Test {}", "utf-8")
            mock_parser_class.return_value = self.mock_parser
            mock_loader.get_query.return_value = None

            with pytest.raises(ValueError, match="Query 'nonexistent' not found"):
                await self.query_service.execute_query(
                    "test.java", "java", query_key="nonexistent"
                )

    def test_get_available_queries(self):
        """Test getting available queries"""
        with patch(
            "tree_sitter_analyzer.core.query_service.query_loader"
        ) as mock_loader:
            mock_loader.list_queries.return_value = ["methods", "class", "imports"]

            result = self.query_service.get_available_queries("java")

            assert result == ["methods", "class", "imports"]
            mock_loader.list_queries.assert_called_once_with("java")

    def test_get_query_description(self):
        """Test getting query description"""
        with patch(
            "tree_sitter_analyzer.core.query_service.query_loader"
        ) as mock_loader:
            mock_loader.get_query_description.return_value = (
                "Extract method declarations"
            )

            result = self.query_service.get_query_description("java", "methods")

            assert result == "Extract method declarations"
            mock_loader.get_query_description.assert_called_once_with("java", "methods")

    def test_get_query_description_exception(self):
        """Test query description when exception occurs"""
        with patch(
            "tree_sitter_analyzer.core.query_service.query_loader"
        ) as mock_loader:
            mock_loader.get_query_description.side_effect = Exception("Test error")

            result = self.query_service.get_query_description("java", "methods")

            assert result is None

    def test_create_result_dict(self):
        """Test creating result dictionary from node"""
        mock_node = Mock()
        mock_node.type = "method_declaration"
        mock_node.start_point = (10, 4)
        mock_node.end_point = (15, 8)
        mock_node.text = b"public void test() {}"

        result = self.query_service._create_result_dict(mock_node, "method")

        assert result["capture_name"] == "method"
        assert result["node_type"] == "method_declaration"
        assert result["start_line"] == 11  # 0-based to 1-based
        assert result["end_line"] == 16  # 0-based to 1-based
        assert result["content"] == "public void test() {}"

    def test_create_result_dict_missing_attributes(self):
        """Test creating result dictionary when node has missing attributes"""
        mock_node = Mock(spec=[])  # Empty spec means no attributes

        result = self.query_service._create_result_dict(mock_node, "test")

        assert result["capture_name"] == "test"
        assert result["node_type"] == "unknown"
        assert result["start_line"] == 0
        assert result["end_line"] == 0
        assert result["content"] == ""


if __name__ == "__main__":
    pytest.main([__file__])
