#!/usr/bin/env python3
"""
Tests for TOON format integration with MCP tools.

Validates that MCP tools correctly support the output_format parameter
and produce valid TOON output when requested.
"""

import pytest

from tree_sitter_analyzer.mcp.utils.file_output_manager import FileOutputManager
from tree_sitter_analyzer.mcp.utils.format_helper import (
    format_as_json,
    format_as_toon,
    format_for_file_output,
    format_output,
    get_formatter,
)


class TestFormatHelper:
    """Test format helper functions."""

    def test_format_output_json(self):
        """Test format_output with JSON format."""
        data = {"key": "value", "count": 42}
        result = format_output(data, "json")

        assert '"key"' in result
        assert '"value"' in result
        assert "42" in result

    def test_format_output_toon(self):
        """Test format_output with TOON format."""
        data = {"key": "value", "count": 42}
        result = format_output(data, "toon")

        # TOON format uses "key: value" syntax
        assert "key: value" in result
        assert "count: 42" in result

    def test_format_as_json(self):
        """Test format_as_json function."""
        data = {"name": "test", "items": [1, 2, 3]}
        result = format_as_json(data)

        assert '"name"' in result
        assert '"test"' in result
        assert "[1, 2, 3]" in result or "[" in result

    def test_format_as_toon(self):
        """Test format_as_toon function."""
        data = {"name": "test", "active": True}
        result = format_as_toon(data)

        assert "name: test" in result
        assert "active: true" in result

    def test_format_for_file_output_json(self):
        """Test format_for_file_output with JSON format."""
        data = {"file": "test.py", "lines": 100}
        content, ext = format_for_file_output(data, "json")

        assert ext == ".json"
        assert '"file"' in content
        assert '"test.py"' in content

    def test_format_for_file_output_toon(self):
        """Test format_for_file_output with TOON format."""
        data = {"file": "test.py", "lines": 100}
        content, ext = format_for_file_output(data, "toon")

        assert ext == ".toon"
        assert "file: test.py" in content
        assert "lines: 100" in content

    def test_get_formatter_json(self):
        """Test get_formatter returns JSON formatter by default."""
        formatter = get_formatter("json")

        assert hasattr(formatter, "format")
        result = formatter.format({"key": "value"})
        assert '"key"' in result

    def test_get_formatter_toon(self):
        """Test get_formatter returns TOON formatter."""
        formatter = get_formatter("toon")

        assert hasattr(formatter, "format")
        result = formatter.format({"key": "value"})
        assert "key: value" in result


class TestFileOutputManagerToonSupport:
    """Test FileOutputManager TOON format support."""

    def test_detect_toon_format(self):
        """Test TOON format detection."""
        manager = FileOutputManager()

        # TOON content with key-value pairs
        toon_content = """file_path: test.py
language: python
line_count: 100
methods:
[3]{name,lines}:
  method1,10-20
  method2,25-35
  method3,40-50"""

        content_type = manager.detect_content_type(toon_content)
        assert content_type == "toon"

    def test_detect_toon_array_table(self):
        """Test TOON array table format detection."""
        manager = FileOutputManager()

        # TOON array table format
        toon_content = """results:
[5]{path,size,mtime}:
  /path/file1.py,1024,1234567890
  /path/file2.py,2048,1234567891
  /path/file3.py,512,1234567892
  /path/file4.py,4096,1234567893
  /path/file5.py,256,1234567894"""

        content_type = manager.detect_content_type(toon_content)
        assert content_type == "toon"

    def test_toon_extension_mapping(self):
        """Test .toon extension is returned for TOON content type."""
        manager = FileOutputManager()

        extension = manager.get_file_extension("toon")
        assert extension == ".toon"

    def test_detect_json_not_toon(self):
        """Test that JSON is not misdetected as TOON."""
        manager = FileOutputManager()

        json_content = '{"key": "value", "count": 42}'
        content_type = manager.detect_content_type(json_content)
        assert content_type == "json"

    def test_detect_simple_kv_as_toon(self):
        """Test simple key-value content is detected as TOON."""
        manager = FileOutputManager()

        toon_content = """success: true
count: 42
file_path: test.py
language: python"""

        content_type = manager.detect_content_type(toon_content)
        assert content_type == "toon"


class TestMCPToolSchemaValidation:
    """Test that MCP tools have output_format parameter in their schemas."""

    def test_list_files_tool_schema(self):
        """Test list_files tool has output_format parameter."""
        from tree_sitter_analyzer.mcp.tools.list_files_tool import ListFilesTool

        tool = ListFilesTool()
        definition = tool.get_tool_definition()

        assert "inputSchema" in definition
        properties = definition["inputSchema"]["properties"]
        assert "output_format" in properties
        assert properties["output_format"]["enum"] == ["json", "toon"]

    def test_search_content_tool_schema(self):
        """Test search_content tool has output_format parameter."""
        from tree_sitter_analyzer.mcp.tools.search_content_tool import SearchContentTool

        tool = SearchContentTool()
        definition = tool.get_tool_definition()

        assert "inputSchema" in definition
        properties = definition["inputSchema"]["properties"]
        assert "output_format" in properties
        assert properties["output_format"]["enum"] == ["json", "toon"]

    def test_find_and_grep_tool_schema(self):
        """Test find_and_grep tool has output_format parameter."""
        from tree_sitter_analyzer.mcp.tools.find_and_grep_tool import FindAndGrepTool

        tool = FindAndGrepTool()
        definition = tool.get_tool_definition()

        assert "inputSchema" in definition
        properties = definition["inputSchema"]["properties"]
        assert "output_format" in properties
        assert properties["output_format"]["enum"] == ["json", "toon"]

    def test_query_tool_schema(self):
        """Test query_code tool has output_format parameter."""
        from tree_sitter_analyzer.mcp.tools.query_tool import QueryTool

        tool = QueryTool()
        definition = tool.get_tool_definition()

        assert "inputSchema" in definition
        properties = definition["inputSchema"]["properties"]
        assert "output_format" in properties
        assert properties["output_format"]["enum"] == ["json", "toon"]

    def test_read_partial_tool_schema(self):
        """Test extract_code_section tool has output_format parameter."""
        from tree_sitter_analyzer.mcp.tools.read_partial_tool import ReadPartialTool

        tool = ReadPartialTool()
        definition = tool.get_tool_definition()

        assert "inputSchema" in definition
        properties = definition["inputSchema"]["properties"]
        assert "output_format" in properties
        assert properties["output_format"]["enum"] == ["json", "toon"]

    def test_table_format_tool_schema(self):
        """Test analyze_code_structure tool has output_format parameter."""
        from tree_sitter_analyzer.mcp.tools.table_format_tool import TableFormatTool

        tool = TableFormatTool()
        definition = tool.get_tool_definition()

        assert "inputSchema" in definition
        properties = definition["inputSchema"]["properties"]
        assert "output_format" in properties
        assert properties["output_format"]["enum"] == ["json", "toon"]

    def test_analyze_scale_tool_schema(self):
        """Test check_code_scale tool has output_format parameter."""
        from tree_sitter_analyzer.mcp.tools.analyze_scale_tool import AnalyzeScaleTool

        tool = AnalyzeScaleTool()
        schema = tool.get_tool_schema()

        assert "properties" in schema
        assert "output_format" in schema["properties"]
        assert schema["properties"]["output_format"]["enum"] == ["json", "toon"]

    def test_universal_analyze_tool_schema(self):
        """Test analyze_code_universal tool has output_format parameter."""
        from tree_sitter_analyzer.mcp.tools.universal_analyze_tool import (
            UniversalAnalyzeTool,
        )

        tool = UniversalAnalyzeTool()
        definition = tool.get_tool_definition()

        assert "inputSchema" in definition
        properties = definition["inputSchema"]["properties"]
        assert "output_format" in properties
        assert properties["output_format"]["enum"] == ["json", "toon"]


class TestToonFormatTokenReduction:
    """Test that TOON format achieves token reduction compared to JSON."""

    def test_simple_dict_token_reduction(self):
        """Test TOON produces shorter output than JSON for simple dict."""
        data = {
            "file_path": "src/main/java/com/example/service/UserService.java",
            "language": "java",
            "line_count": 1419,
            "class_count": 3,
            "method_count": 45,
            "field_count": 12,
        }

        json_output = format_as_json(data)
        toon_output = format_as_toon(data)

        # TOON should be shorter (fewer tokens due to no quotes, braces, etc.)
        assert len(toon_output) < len(json_output)

    def test_nested_dict_token_reduction(self):
        """Test TOON produces shorter output for nested structures."""
        data = {
            "success": True,
            "file_path": "test.py",
            "metrics": {
                "lines_total": 500,
                "lines_code": 400,
                "lines_comment": 80,
                "lines_blank": 20,
            },
            "summary": {
                "classes": 5,
                "methods": 25,
                "functions": 10,
            },
        }

        json_output = format_as_json(data)
        toon_output = format_as_toon(data)

        # TOON should be shorter
        assert len(toon_output) < len(json_output)

    def test_array_table_token_reduction(self):
        """Test TOON array table format reduces tokens significantly."""
        data = {
            "results": [
                {"name": "method1", "visibility": "public", "lines": "10-20"},
                {"name": "method2", "visibility": "private", "lines": "25-35"},
                {"name": "method3", "visibility": "public", "lines": "40-60"},
                {"name": "method4", "visibility": "protected", "lines": "65-80"},
                {"name": "method5", "visibility": "public", "lines": "85-100"},
            ]
        }

        json_output = format_as_json(data)
        toon_output = format_as_toon(data)

        # TOON array table format should be significantly shorter
        assert len(toon_output) < len(json_output)

        # Verify TOON uses array table format
        assert "[5]{" in toon_output or "results:" in toon_output


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
