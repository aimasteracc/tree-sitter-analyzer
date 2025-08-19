#!/usr/bin/env python3
"""
MCP Query Tool Definition Tests

Tests for MCP query tool metadata and definitions without execution.
"""

from unittest.mock import patch

import pytest

from tree_sitter_analyzer.mcp.tools.query_tool import QueryTool


class TestMCPQueryToolDefinition:
    """Tests for MCP query tool definition and metadata"""

    def setup_method(self):
        """Set up test fixtures"""
        self.query_tool = QueryTool()

    def test_tool_definition_structure(self):
        """Test that tool definition has correct structure"""
        definition = self.query_tool.get_tool_definition()

        assert definition["name"] == "query_code"
        assert "description" in definition
        assert "inputSchema" in definition

        schema = definition["inputSchema"]
        assert schema["type"] == "object"
        assert "properties" in schema

        properties = schema["properties"]
        assert "file_path" in properties
        assert "query_key" in properties
        assert "query_string" in properties
        assert "filter" in properties
        assert "output_format" in properties

    def test_tool_definition_filter_parameter(self):
        """Test that filter parameter is correctly defined"""
        definition = self.query_tool.get_tool_definition()
        properties = definition["inputSchema"]["properties"]

        assert "filter" in properties
        filter_def = properties["filter"]
        assert filter_def["type"] == "string"
        assert "filter expression" in filter_def["description"].lower()

    def test_tool_definition_required_fields(self):
        """Test that required fields are properly defined"""
        definition = self.query_tool.get_tool_definition()
        schema = definition["inputSchema"]

        assert "required" in schema
        assert "file_path" in schema["required"]

        # Check anyOf constraint for query parameters
        assert "anyOf" in schema
        any_of = schema["anyOf"]
        assert len(any_of) == 2
        assert {"required": ["query_key"]} in any_of
        assert {"required": ["query_string"]} in any_of

    def test_tool_definition_properties_types(self):
        """Test that all properties have correct types"""
        definition = self.query_tool.get_tool_definition()
        properties = definition["inputSchema"]["properties"]

        # Check string types
        string_props = ["file_path", "language", "query_key", "query_string", "filter"]
        for prop in string_props:
            assert properties[prop]["type"] == "string"

        # Check output_format enum
        output_format = properties["output_format"]
        assert output_format["type"] == "string"
        assert "enum" in output_format
        assert "json" in output_format["enum"]
        assert "summary" in output_format["enum"]

    def test_get_available_queries(self):
        """Test getting available queries"""
        with patch.object(
            self.query_tool.query_service, "get_available_queries"
        ) as mock_get:
            mock_get.return_value = ["methods", "class", "imports"]

            result = self.query_tool.get_available_queries("java")

            assert result == ["methods", "class", "imports"]
            mock_get.assert_called_once_with("java")

    def test_initialization(self):
        """Test tool initialization"""
        tool = QueryTool()

        assert tool.query_service is not None
        assert tool.security_validator is not None
        assert tool.project_root is None

        # Test with existing project root (use current directory)
        import os

        current_dir = os.getcwd()
        tool_with_root = QueryTool(current_dir)
        assert tool_with_root.project_root == current_dir


class TestMCPQueryToolHelpers:
    """Tests for MCP query tool helper methods"""

    def setup_method(self):
        """Set up test fixtures"""
        self.query_tool = QueryTool()

    def test_extract_name_from_content_java(self):
        """Test extracting names from Java method content"""
        test_cases = [
            ("public void main(String[] args) {", "main"),
            ("private static void helper() {", "helper"),
            ("public class TestClass {", "TestClass"),
            ("public interface ITest {", "ITest"),
            ("authenticate(String user) {", "authenticate"),
        ]

        for content, expected_name in test_cases:
            result = self.query_tool._extract_name_from_content(content)
            assert result == expected_name

    def test_extract_name_from_content_unknown(self):
        """Test extracting name from unrecognized content"""
        result = self.query_tool._extract_name_from_content("some random text")
        assert result == "unnamed"

    def test_format_summary(self):
        """Test formatting summary output"""
        sample_results = [
            {
                "capture_name": "method",
                "node_type": "method_declaration",
                "start_line": 1,
                "end_line": 5,
                "content": "public void main(String[] args) {}",
            },
            {
                "capture_name": "method",
                "node_type": "method_declaration",
                "start_line": 7,
                "end_line": 10,
                "content": "private void helper() {}",
            },
            {
                "capture_name": "class",
                "node_type": "class_declaration",
                "start_line": 12,
                "end_line": 20,
                "content": "public class TestClass {}",
            },
        ]

        summary = self.query_tool._format_summary(sample_results, "methods", "java")

        assert summary["success"]
        assert summary["query_type"] == "methods"
        assert summary["language"] == "java"
        assert summary["total_count"] == 3

        captures = summary["captures"]
        assert "method" in captures
        assert "class" in captures
        assert captures["method"]["count"] == 2
        assert captures["class"]["count"] == 1

        method_items = captures["method"]["items"]
        assert len(method_items) == 2
        assert method_items[0]["name"] == "main"
        assert method_items[1]["name"] == "helper"


if __name__ == "__main__":
    pytest.main([__file__])
