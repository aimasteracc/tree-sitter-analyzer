#!/usr/bin/env python3
"""
Tests for the Query MCP Tool.

This module tests the QueryTool class which provides
tree-sitter query functionality.
"""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from tree_sitter_analyzer.mcp.tools.query_tool import QueryTool


@pytest.fixture
def tool():
    """Create a fresh tool instance for each test."""
    return QueryTool()


@pytest.fixture
def sample_python_file(tmp_path: Path):
    """Create a sample Python file for testing."""
    python_file = tmp_path / "sample.py"
    python_file.write_text(
        """import os

class SampleClass:
    def __init__(self):
        self.value = 0

    def method1(self):
        return self.value

    def method2(self, x):
        return x * 2

def standalone_function():
    return "hello"
"""
    )
    return python_file


@pytest.fixture
def mock_query_results():
    """Create mock query results."""
    return [
        {
            "capture_name": "method",
            "content": "def method1(self):\n    return self.value",
            "start_line": 6,
            "end_line": 7,
            "node_type": "function_definition",
        },
        {
            "capture_name": "method",
            "content": "def method2(self, x):\n    return x * 2",
            "start_line": 9,
            "end_line": 10,
            "node_type": "function_definition",
        },
    ]


class TestQueryToolInitialization:
    """Tests for tool initialization."""

    def test_init_creates_tool(self, tool):
        """Test that initialization creates a tool instance."""
        assert tool is not None
        assert hasattr(tool, "query_service")
        assert hasattr(tool, "file_output_manager")

    def test_init_with_project_root(self):
        """Test initialization with project root."""
        tool = QueryTool(project_root="/test/path")
        assert tool.project_root == "/test/path"

    def test_init_multiple_instances(self):
        """Test that multiple instances are independent."""
        tool1 = QueryTool()
        tool2 = QueryTool()
        assert tool1 is not tool2


class TestSetProjectPath:
    """Tests for set_project_path method."""

    def test_set_project_path_updates_all_components(self, tool):
        """Test that set_project_path updates all components."""
        new_path = "/new/project/path"
        tool.set_project_path(new_path)
        assert tool.project_root == new_path
        assert tool.query_service.project_root == new_path

    def test_set_project_path_recreates_services(self, tool):
        """Test that set_project_path recreates services."""
        old_service = tool.query_service
        tool.set_project_path("/new/path")
        assert tool.query_service is not old_service


class TestGetToolDefinition:
    """Tests for get_tool_definition method."""

    def test_tool_definition_structure(self, tool):
        """Test that tool definition has correct structure."""
        definition = tool.get_tool_definition()
        assert isinstance(definition, dict)
        assert "name" in definition
        assert "description" in definition
        assert "inputSchema" in definition

    def test_tool_definition_name(self, tool):
        """Test that tool definition has correct name."""
        definition = tool.get_tool_definition()
        assert definition["name"] == "query_code"

    def test_tool_definition_description(self, tool):
        """Test that tool definition has description."""
        definition = tool.get_tool_definition()
        assert definition["description"] is not None
        assert isinstance(definition["description"], str)

    def test_input_schema_structure(self, tool):
        """Test that input schema has correct structure."""
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        assert schema["type"] == "object"
        assert "properties" in schema
        assert "required" in schema

    def test_required_fields(self, tool):
        """Test that required fields are correctly defined."""
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        required = schema.get("required", [])
        assert "file_path" in required
        assert len(required) == 1

    def test_file_path_property(self, tool):
        """Test that file_path property is correctly defined."""
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "file_path" in properties
        assert properties["file_path"]["type"] == "string"

    def test_language_property(self, tool):
        """Test that language property is correctly defined."""
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "language" in properties
        assert properties["language"]["type"] == "string"

    def test_query_key_property(self, tool):
        """Test that query_key property is correctly defined."""
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "query_key" in properties
        assert properties["query_key"]["type"] == "string"

    def test_query_string_property(self, tool):
        """Test that query_string property is correctly defined."""
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "query_string" in properties
        assert properties["query_string"]["type"] == "string"

    def test_filter_property(self, tool):
        """Test that filter property is correctly defined."""
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "filter" in properties
        assert properties["filter"]["type"] == "string"

    def test_result_format_property(self, tool):
        """Test that result_format property is correctly defined."""
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "result_format" in properties
        assert properties["result_format"]["type"] == "string"
        assert properties["result_format"]["enum"] == ["json", "summary"]
        assert properties["result_format"]["default"] == "json"

    def test_output_format_property(self, tool):
        """Test that output_format property is correctly defined."""
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "output_format" in properties
        assert properties["output_format"]["type"] == "string"
        assert properties["output_format"]["enum"] == ["json", "toon"]
        assert properties["output_format"]["default"] == "toon"

    def test_output_file_property(self, tool):
        """Test that output_file property is correctly defined."""
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "output_file" in properties
        assert properties["output_file"]["type"] == "string"

    def test_suppress_output_property(self, tool):
        """Test that suppress_output property is correctly defined."""
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "suppress_output" in properties
        assert properties["suppress_output"]["type"] == "boolean"
        assert properties["suppress_output"]["default"] is False


class TestValidateArguments:
    """Tests for validate_arguments method."""

    def test_validate_valid_arguments_with_query_key(self, tool):
        """Test validation with valid arguments using query_key."""
        arguments = {
            "file_path": "test.py",
            "query_key": "methods",
        }
        assert tool.validate_arguments(arguments) is True

    def test_validate_valid_arguments_with_query_string(self, tool):
        """Test validation with valid arguments using query_string."""
        arguments = {
            "file_path": "test.py",
            "query_string": "(function_definition) @func",
        }
        assert tool.validate_arguments(arguments) is True

    def test_validate_missing_file_path(self, tool):
        """Test validation fails when file_path is missing."""
        arguments = {"query_key": "methods"}
        with pytest.raises(ValueError, match="file_path is required"):
            tool.validate_arguments(arguments)

    def test_validate_empty_file_path(self, tool):
        """Test validation fails when file_path is empty."""
        arguments = {"file_path": "", "query_key": "methods"}
        with pytest.raises(ValueError, match="file_path cannot be empty"):
            tool.validate_arguments(arguments)

    def test_validate_whitespace_file_path(self, tool):
        """Test validation fails when file_path is only whitespace."""
        arguments = {"file_path": "   ", "query_key": "methods"}
        with pytest.raises(ValueError, match="file_path cannot be empty"):
            tool.validate_arguments(arguments)

    def test_validate_invalid_file_path_type(self, tool):
        """Test validation fails when file_path is not a string."""
        arguments = {"file_path": 123, "query_key": "methods"}
        with pytest.raises(ValueError, match="file_path must be a string"):
            tool.validate_arguments(arguments)

    def test_validate_missing_both_query_params(self, tool):
        """Test validation fails when both query_key and query_string are missing."""
        arguments = {"file_path": "test.py"}
        with pytest.raises(
            ValueError, match="Either query_key or query_string must be provided"
        ):
            tool.validate_arguments(arguments)

    def test_validate_invalid_query_key_type(self, tool):
        """Test validation fails when query_key is not a string."""
        arguments = {"file_path": "test.py", "query_key": 123}
        with pytest.raises(ValueError, match="query_key must be a string"):
            tool.validate_arguments(arguments)

    def test_validate_invalid_query_string_type(self, tool):
        """Test validation fails when query_string is not a string."""
        arguments = {"file_path": "test.py", "query_string": 123}
        with pytest.raises(ValueError, match="query_string must be a string"):
            tool.validate_arguments(arguments)

    def test_validate_invalid_language_type(self, tool):
        """Test validation fails when language is not a string."""
        arguments = {
            "file_path": "test.py",
            "query_key": "methods",
            "language": 123,
        }
        with pytest.raises(ValueError, match="language must be a string"):
            tool.validate_arguments(arguments)

    def test_validate_invalid_filter_type(self, tool):
        """Test validation fails when filter is not a string."""
        arguments = {
            "file_path": "test.py",
            "query_key": "methods",
            "filter": 123,
        }
        with pytest.raises(ValueError, match="filter must be a string"):
            tool.validate_arguments(arguments)

    def test_validate_invalid_result_format_type(self, tool):
        """Test validation fails when result_format is not a string."""
        arguments = {
            "file_path": "test.py",
            "query_key": "methods",
            "result_format": 123,
        }
        with pytest.raises(ValueError, match="result_format must be a string"):
            tool.validate_arguments(arguments)

    def test_validate_invalid_result_format_value(self, tool):
        """Test validation fails when result_format has invalid value."""
        arguments = {
            "file_path": "test.py",
            "query_key": "methods",
            "result_format": "invalid",
        }
        with pytest.raises(
            ValueError, match="result_format must be one of: json, summary"
        ):
            tool.validate_arguments(arguments)

    def test_validate_invalid_output_format_type(self, tool):
        """Test validation fails when output_format is not a string."""
        arguments = {
            "file_path": "test.py",
            "query_key": "methods",
            "output_format": 123,
        }
        with pytest.raises(ValueError, match="output_format must be a string"):
            tool.validate_arguments(arguments)

    def test_validate_invalid_output_format_value(self, tool):
        """Test validation fails when output_format has invalid value."""
        arguments = {
            "file_path": "test.py",
            "query_key": "methods",
            "output_format": "invalid",
        }
        with pytest.raises(
            ValueError, match="output_format must be one of: json, toon"
        ):
            tool.validate_arguments(arguments)

    def test_validate_invalid_output_file_type(self, tool):
        """Test validation fails when output_file is not a string."""
        arguments = {
            "file_path": "test.py",
            "query_key": "methods",
            "output_file": 123,
        }
        with pytest.raises(ValueError, match="output_file must be a string"):
            tool.validate_arguments(arguments)

    def test_validate_empty_output_file(self, tool):
        """Test validation fails when output_file is empty."""
        arguments = {
            "file_path": "test.py",
            "query_key": "methods",
            "output_file": "",
        }
        with pytest.raises(ValueError, match="output_file cannot be empty"):
            tool.validate_arguments(arguments)

    def test_validate_invalid_suppress_output_type(self, tool):
        """Test validation fails when suppress_output is not a boolean."""
        arguments = {
            "file_path": "test.py",
            "query_key": "methods",
            "suppress_output": "true",
        }
        with pytest.raises(ValueError, match="suppress_output must be a boolean"):
            tool.validate_arguments(arguments)

    def test_validate_all_optional_fields_valid(self, tool):
        """Test validation passes with all optional fields set."""
        arguments = {
            "file_path": "test.py",
            "query_key": "methods",
            "language": "python",
            "filter": "name=main",
            "result_format": "summary",
            "output_format": "json",
            "output_file": "output.json",
            "suppress_output": True,
        }
        assert tool.validate_arguments(arguments) is True

    def test_validate_suppress_output_valid(self, tool):
        """Test validation passes with valid suppress_output."""
        arguments = {
            "file_path": "test.py",
            "query_key": "methods",
            "suppress_output": False,
        }
        assert tool.validate_arguments(arguments) is True


class TestExecute:
    """Tests for execute method."""

    @pytest.mark.asyncio
    async def test_execute_empty_arguments(self, tool):
        """Test execute fails with empty arguments."""
        with pytest.raises(Exception, match="file_path is required"):
            await tool.execute({})

    @pytest.mark.asyncio
    async def test_execute_missing_file_path(self, tool):
        """Test execute fails when file_path is missing."""
        arguments = {"query_key": "methods"}
        with pytest.raises(Exception, match="file_path is required"):
            await tool.execute(arguments)

    @pytest.mark.asyncio
    async def test_execute_missing_both_query_params(self, tool):
        """Test execute fails when both query_key and query_string are missing."""
        arguments = {"file_path": "test.py"}
        with pytest.raises(
            Exception, match="Either query_key or query_string must be provided"
        ):
            await tool.execute(arguments)

    @pytest.mark.asyncio
    async def test_execute_both_query_params_provided(self, tool, sample_python_file):
        """Test execute fails when both query_key and query_string are provided."""
        arguments = {
            "file_path": str(sample_python_file),
            "query_key": "methods",
            "query_string": "(function_definition) @func",
        }
        result = await tool.execute(arguments)
        assert result["success"] is False
        assert "Cannot provide both" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_language_detection_fails(self, tool, sample_python_file):
        """Test execute fails when language detection fails."""
        with patch(
            "tree_sitter_analyzer.mcp.tools.query_tool.detect_language_from_file",
            return_value=None,
        ):
            arguments = {
                "file_path": str(sample_python_file),
                "query_key": "methods",
            }
            result = await tool.execute(arguments)
            assert result["success"] is False
            assert "Could not detect language" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_success_with_query_key(
        self, tool, sample_python_file, mock_query_results
    ):
        """Test successful execution with query_key."""
        with patch.object(
            tool.query_service, "execute_query", new_callable=AsyncMock
        ) as mock_query:
            mock_query.return_value = mock_query_results

            arguments = {
                "file_path": str(sample_python_file),
                "query_key": "methods",
                "language": "python",
            }

            result = await tool.execute(arguments)

            assert result["success"] is True
            assert result["count"] == len(mock_query_results)
            assert "toon_content" in result
            assert result["file_path"] == str(sample_python_file)
            assert result["language"] == "python"
            assert result["query"] == "methods"

    @pytest.mark.asyncio
    async def test_execute_success_with_query_string(
        self, tool, sample_python_file, mock_query_results
    ):
        """Test successful execution with query_string."""
        with patch.object(
            tool.query_service, "execute_query", new_callable=AsyncMock
        ) as mock_query:
            mock_query.return_value = mock_query_results

            arguments = {
                "file_path": str(sample_python_file),
                "query_string": "(function_definition) @func",
                "language": "python",
            }

            result = await tool.execute(arguments)

            assert result["success"] is True
            assert result["query"] == "(function_definition) @func"

    @pytest.mark.asyncio
    async def test_execute_no_results(self, tool, sample_python_file):
        """Test execution when no results are found."""
        with patch.object(
            tool.query_service, "execute_query", new_callable=AsyncMock
        ) as mock_query:
            mock_query.return_value = []

            arguments = {
                "file_path": str(sample_python_file),
                "query_key": "methods",
                "language": "python",
            }

            result = await tool.execute(arguments)

            assert result["success"] is True
            assert result["count"] == 0
            assert "No results" in result["message"]

    @pytest.mark.asyncio
    async def test_execute_with_summary_format(
        self, tool, sample_python_file, mock_query_results
    ):
        """Test execution with summary result format."""
        with patch.object(
            tool.query_service, "execute_query", new_callable=AsyncMock
        ) as mock_query:
            mock_query.return_value = mock_query_results

            arguments = {
                "file_path": str(sample_python_file),
                "query_key": "methods",
                "language": "python",
                "result_format": "summary",
            }

            result = await tool.execute(arguments)

            assert result["success"] is True
            assert "query_type" in result
            assert "captures" in result
            assert "total_count" in result

    @pytest.mark.asyncio
    async def test_execute_with_file_output(
        self, tool, sample_python_file, mock_query_results
    ):
        """Test execution with file output."""
        with patch.object(
            tool.query_service, "execute_query", new_callable=AsyncMock
        ) as mock_query:
            mock_query.return_value = mock_query_results

            with patch.object(tool.file_output_manager, "save_to_file") as mock_save:
                mock_save.return_value = "/output/query_results.json"

                arguments = {
                    "file_path": str(sample_python_file),
                    "query_key": "methods",
                    "language": "python",
                    "output_file": "results.json",
                }

                result = await tool.execute(arguments)

                assert result["success"] is True
                assert "output_file_path" in result
                assert result["output_file_path"] == "/output/query_results.json"
                assert result["file_saved"] is True

    @pytest.mark.asyncio
    async def test_execute_with_suppress_output(
        self, tool, sample_python_file, mock_query_results
    ):
        """Test execution with suppress_output."""
        with patch.object(
            tool.query_service, "execute_query", new_callable=AsyncMock
        ) as mock_query:
            mock_query.return_value = mock_query_results

            with patch.object(tool.file_output_manager, "save_to_file") as mock_save:
                mock_save.return_value = "/output/query_results.json"

                arguments = {
                    "file_path": str(sample_python_file),
                    "query_key": "methods",
                    "language": "python",
                    "output_file": "results.json",
                    "suppress_output": True,
                }

                result = await tool.execute(arguments)

                assert result["success"] is True
                assert "output_file_path" in result
                # Results should not be in response when suppressed
                assert "results" not in result

    @pytest.mark.asyncio
    async def test_execute_with_toon_format(
        self, tool, sample_python_file, mock_query_results
    ):
        """Test execution with toon output format."""
        with patch.object(
            tool.query_service, "execute_query", new_callable=AsyncMock
        ) as mock_query:
            mock_query.return_value = mock_query_results

            with patch(
                "tree_sitter_analyzer.mcp.tools.query_tool.apply_toon_format_to_response"
            ) as mock_toon:
                mock_toon.return_value = {"toon": "formatted"}

                arguments = {
                    "file_path": str(sample_python_file),
                    "query_key": "methods",
                    "language": "python",
                    "output_format": "toon",
                }

                result = await tool.execute(arguments)

                assert mock_toon.called
                assert result == {"toon": "formatted"}

    @pytest.mark.asyncio
    async def test_execute_exception_handling(self, tool, sample_python_file):
        """Test execution when an exception occurs."""
        with patch.object(
            tool.query_service, "execute_query", new_callable=AsyncMock
        ) as mock_query:
            mock_query.side_effect = Exception("Unexpected error")

            arguments = {
                "file_path": str(sample_python_file),
                "query_key": "methods",
                "language": "python",
            }

            result = await tool.execute(arguments)

            assert result["success"] is False
            assert "error" in result

    @pytest.mark.asyncio
    async def test_execute_file_save_error(
        self, tool, sample_python_file, mock_query_results
    ):
        """Test execution when file save fails."""
        with patch.object(
            tool.query_service, "execute_query", new_callable=AsyncMock
        ) as mock_query:
            mock_query.return_value = mock_query_results

            with patch.object(tool.file_output_manager, "save_to_file") as mock_save:
                mock_save.side_effect = Exception("Save failed")

                arguments = {
                    "file_path": str(sample_python_file),
                    "query_key": "methods",
                    "language": "python",
                    "output_file": "results.json",
                }

                result = await tool.execute(arguments)

                assert result["success"] is True
                assert result["file_saved"] is False
                assert "file_save_error" in result

    @pytest.mark.asyncio
    async def test_execute_auto_language_detection(
        self, tool, sample_python_file, mock_query_results
    ):
        """Test execution with automatic language detection."""
        with patch(
            "tree_sitter_analyzer.mcp.tools.query_tool.detect_language_from_file",
            return_value="python",
        ):
            with patch.object(
                tool.query_service, "execute_query", new_callable=AsyncMock
            ) as mock_query:
                mock_query.return_value = mock_query_results

                arguments = {
                    "file_path": str(sample_python_file),
                    "query_key": "methods",
                }

                result = await tool.execute(arguments)

                assert result["success"] is True
                assert result["language"] == "python"

    @pytest.mark.asyncio
    async def test_execute_suppress_output_with_file_save_error(
        self, tool, sample_python_file, mock_query_results
    ):
        """Test suppress_output when file save also failed."""
        with patch.object(
            tool.query_service, "execute_query", new_callable=AsyncMock
        ) as mock_query:
            mock_query.return_value = mock_query_results

            with patch.object(tool.file_output_manager, "save_to_file") as mock_save:
                mock_save.side_effect = Exception("Disk full")

                arguments = {
                    "file_path": str(sample_python_file),
                    "query_key": "methods",
                    "language": "python",
                    "output_file": "results.json",
                    "suppress_output": True,
                }

                result = await tool.execute(arguments)

                assert result["success"] is True
                assert result["file_saved"] is False
                assert "file_save_error" in result

    @pytest.mark.asyncio
    async def test_execute_with_empty_output_file_string(
        self, tool, sample_python_file, mock_query_results
    ):
        """Test execution with whitespace output_file generates base name from file path."""
        with patch.object(
            tool.query_service, "execute_query", new_callable=AsyncMock
        ) as mock_query:
            mock_query.return_value = mock_query_results

            with patch.object(tool.file_output_manager, "save_to_file") as mock_save:
                mock_save.return_value = "/output/sample_query_methods.json"

                arguments = {
                    "file_path": str(sample_python_file),
                    "query_key": "methods",
                    "language": "python",
                    "output_file": "   ",
                }

                result = await tool.execute(arguments)

                assert result["success"] is True
                assert result["file_saved"] is True
                mock_save.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_with_query_string_and_file_output(
        self, tool, sample_python_file, mock_query_results
    ):
        """Test execution with query_string and file output using auto base name."""
        with patch.object(
            tool.query_service, "execute_query", new_callable=AsyncMock
        ) as mock_query:
            mock_query.return_value = mock_query_results

            with patch.object(tool.file_output_manager, "save_to_file") as mock_save:
                mock_save.return_value = "/output/custom_query.json"

                arguments = {
                    "file_path": str(sample_python_file),
                    "query_string": "(function_definition) @func",
                    "language": "python",
                    "output_file": "   ",
                }

                result = await tool.execute(arguments)

                assert result["success"] is True
                assert result["file_saved"] is True


class TestFormatSummary:
    """Tests for _format_summary method."""

    def test_format_summary_basic(self, tool, mock_query_results):
        """Test basic summary formatting."""
        summary = tool._format_summary(mock_query_results, "methods", "python")
        assert summary["success"] is True
        assert summary["query_type"] == "methods"
        assert summary["language"] == "python"
        assert summary["total_count"] == len(mock_query_results)
        assert "captures" in summary

    def test_format_summary_grouping(self, tool, mock_query_results):
        """Test that results are grouped by capture name."""
        summary = tool._format_summary(mock_query_results, "methods", "python")
        assert "method" in summary["captures"]
        assert summary["captures"]["method"]["count"] == 2

    def test_format_summary_item_structure(self, tool, mock_query_results):
        """Test that summary items have correct structure."""
        summary = tool._format_summary(mock_query_results, "methods", "python")
        items = summary["captures"]["method"]["items"]
        for item in items:
            assert "name" in item
            assert "line_range" in item
            assert "node_type" in item

    def test_format_summary_multiple_captures(self, tool):
        """Test summary with multiple capture types."""
        results = [
            {
                "capture_name": "class",
                "content": "class Foo:\n    pass",
                "start_line": 1,
                "end_line": 2,
                "node_type": "class_definition",
            },
            {
                "capture_name": "function",
                "content": "def bar():\n    pass",
                "start_line": 4,
                "end_line": 5,
                "node_type": "function_definition",
            },
        ]
        summary = tool._format_summary(results, "all", "python")
        assert summary["total_count"] == 2
        assert "class" in summary["captures"]
        assert "function" in summary["captures"]
        assert summary["captures"]["class"]["count"] == 1
        assert summary["captures"]["function"]["count"] == 1


class TestExtractNameFromContent:
    """Tests for _extract_name_from_content method."""

    def test_extract_method_name(self, tool):
        """Test extracting method name from content."""
        content = "def method_name(self, arg1):\n    pass"
        name = tool._extract_name_from_content(content)
        assert name == "method_name"

    def test_extract_class_name(self, tool):
        """Test extracting class name from content."""
        content = "public class ClassName {\n    // class body\n}"
        name = tool._extract_name_from_content(content)
        assert name == "ClassName"

    def test_extract_function_name(self, tool):
        """Test extracting function name from content."""
        content = "function_name()"
        name = tool._extract_name_from_content(content)
        assert name == "function_name"

    def test_extract_markdown_header(self, tool):
        """Test extracting markdown header."""
        content = "# Main Title\n\nContent here"
        name = tool._extract_name_from_content(content)
        assert name == "Main Title"

    def test_extract_unnamed(self, tool):
        """Test extraction when no pattern matches."""
        content = "random content without patterns"
        name = tool._extract_name_from_content(content)
        assert name == "unnamed"

    def test_extract_empty_content(self, tool):
        """Test extraction with empty content."""
        name = tool._extract_name_from_content("")
        assert name == "unnamed"

    def test_extract_whitespace_only_content(self, tool):
        """Test extraction with whitespace-only content."""
        name = tool._extract_name_from_content("   \n   \n   ")
        assert name == "unnamed"

    def test_extract_private_method(self, tool):
        """Test extracting private method name."""
        content = "private static void doSomething(int x) {"
        name = tool._extract_name_from_content(content)
        assert name == "doSomething"

    def test_extract_protected_method(self, tool):
        """Test extracting protected method name."""
        content = "protected String getName() {"
        name = tool._extract_name_from_content(content)
        assert name == "getName"

    def test_extract_subheading(self, tool):
        """Test extracting subheading."""
        content = "## Sub Heading\nMore content"
        name = tool._extract_name_from_content(content)
        assert name == "Sub Heading"


class TestGetAvailableQueries:
    """Tests for get_available_queries method."""

    def test_get_available_queries(self, tool):
        """Test getting available queries."""
        with patch.object(
            tool.query_service,
            "get_available_queries",
            return_value=["methods", "classes"],
        ):
            queries = tool.get_available_queries("python")
            assert queries == ["methods", "classes"]


class TestExecuteAdditionalCoverage:
    """Additional tests targeting uncovered branches in execute."""

    @pytest.mark.asyncio
    async def test_execute_none_arguments(self, tool):
        """Test execute with None as arguments."""
        with pytest.raises(Exception, match="file_path is required"):
            await tool.execute(None)

    @pytest.mark.asyncio
    async def test_execute_summary_format_with_file_output(
        self, tool, sample_python_file, mock_query_results
    ):
        """Test execute with summary format and file output combined."""
        with patch.object(
            tool.query_service, "execute_query", new_callable=AsyncMock
        ) as mock_query:
            mock_query.return_value = mock_query_results

            with patch.object(tool.file_output_manager, "save_to_file") as mock_save:
                mock_save.return_value = "/output/summary_results.json"

                arguments = {
                    "file_path": str(sample_python_file),
                    "query_key": "methods",
                    "language": "python",
                    "result_format": "summary",
                    "output_file": "summary_results.json",
                }

                result = await tool.execute(arguments)

                assert result["success"] is True
                assert result["output_file_path"] == "/output/summary_results.json"
                assert result["file_saved"] is True

    @pytest.mark.asyncio
    async def test_execute_summary_format_file_save_error(
        self, tool, sample_python_file, mock_query_results
    ):
        """Test execute with summary format when file save fails."""
        with patch.object(
            tool.query_service, "execute_query", new_callable=AsyncMock
        ) as mock_query:
            mock_query.return_value = mock_query_results

            with patch.object(tool.file_output_manager, "save_to_file") as mock_save:
                mock_save.side_effect = OSError("Permission denied")

                arguments = {
                    "file_path": str(sample_python_file),
                    "query_key": "methods",
                    "language": "python",
                    "result_format": "summary",
                    "output_file": "results.json",
                }

                result = await tool.execute(arguments)

                assert result["success"] is True
                assert result["file_saved"] is False
                assert "file_save_error" in result

    @pytest.mark.asyncio
    async def test_execute_suppress_output_with_file_save_info(
        self, tool, sample_python_file, mock_query_results
    ):
        """Test suppress_output preserves file output info in minimal result."""
        with patch.object(
            tool.query_service, "execute_query", new_callable=AsyncMock
        ) as mock_query:
            mock_query.return_value = mock_query_results

            with patch.object(tool.file_output_manager, "save_to_file") as mock_save:
                mock_save.return_value = "/output/suppressed_results.json"

                arguments = {
                    "file_path": str(sample_python_file),
                    "query_key": "methods",
                    "language": "python",
                    "output_file": "results.json",
                    "suppress_output": True,
                }

                result = await tool.execute(arguments)

                assert result["success"] is True
                assert result["output_file_path"] == "/output/suppressed_results.json"
                assert result["file_saved"] is True
                assert "results" not in result

    @pytest.mark.asyncio
    async def test_execute_suppress_output_with_save_error_info(
        self, tool, sample_python_file, mock_query_results
    ):
        """Test suppress_output preserves file save error info."""
        with patch.object(
            tool.query_service, "execute_query", new_callable=AsyncMock
        ) as mock_query:
            mock_query.return_value = mock_query_results

            with patch.object(tool.file_output_manager, "save_to_file") as mock_save:
                mock_save.side_effect = Exception("No space left")

                arguments = {
                    "file_path": str(sample_python_file),
                    "query_key": "methods",
                    "language": "python",
                    "output_file": "results.json",
                    "suppress_output": True,
                }

                result = await tool.execute(arguments)

                assert result["success"] is True
                assert result["file_saved"] is False
                assert "file_save_error" in result
                assert "No space left" in result["file_save_error"]

    @pytest.mark.asyncio
    async def test_execute_analysis_error_reraise(self, tool, sample_python_file):
        """Test that AnalysisError is re-raised, not caught as generic."""
        from tree_sitter_analyzer.mcp.utils.error_handler import AnalysisError

        with patch.object(
            tool,
            "resolve_and_validate_file_path",
            side_effect=AnalysisError("bad file", operation="query_code"),
        ):
            arguments = {
                "file_path": str(sample_python_file),
                "query_key": "methods",
            }
            with pytest.raises(AnalysisError, match="bad file"):
                await tool.execute(arguments)

    @pytest.mark.asyncio
    async def test_execute_with_output_format_json(
        self, tool, sample_python_file, mock_query_results
    ):
        """Test execute with output_format json (no toon transform)."""
        with patch.object(
            tool.query_service, "execute_query", new_callable=AsyncMock
        ) as mock_query:
            mock_query.return_value = mock_query_results

            arguments = {
                "file_path": str(sample_python_file),
                "query_key": "methods",
                "language": "python",
                "output_format": "json",
            }

            result = await tool.execute(arguments)

            assert result["success"] is True
            assert result["count"] == len(mock_query_results)
            assert "results" in result

    @pytest.mark.asyncio
    async def test_execute_no_language_provided_auto_detect(
        self, tool, sample_python_file, mock_query_results
    ):
        """Test execute without explicit language triggers auto-detection."""
        with patch(
            "tree_sitter_analyzer.mcp.tools.query_tool.detect_language_from_file",
            return_value="python",
        ):
            with patch.object(
                tool.query_service, "execute_query", new_callable=AsyncMock
            ) as mock_query:
                mock_query.return_value = mock_query_results

                arguments = {
                    "file_path": str(sample_python_file),
                    "query_key": "methods",
                    "output_format": "json",
                }

                result = await tool.execute(arguments)

                assert result["success"] is True
                assert result["language"] == "python"


class TestFormatSummaryAdditional:
    """Additional tests for _format_summary."""

    def test_format_summary_empty_results(self, tool):
        """Test summary formatting with empty results list."""
        summary = tool._format_summary([], "methods", "python")
        assert summary["success"] is True
        assert summary["total_count"] == 0
        assert summary["captures"] == {}

    def test_format_summary_single_result(self, tool):
        """Test summary formatting with a single result."""
        results = [
            {
                "capture_name": "class",
                "content": "class MyClass:\n    pass",
                "start_line": 1,
                "end_line": 2,
                "node_type": "class_definition",
            },
        ]
        summary = tool._format_summary(results, "class", "java")
        assert summary["total_count"] == 1
        assert "class" in summary["captures"]
        assert summary["captures"]["class"]["count"] == 1
        item = summary["captures"]["class"]["items"][0]
        assert "name" in item
        assert item["line_range"] == "1-2"
        assert item["node_type"] == "class_definition"


class TestExtractNameAdditional:
    """Additional tests for _extract_name_from_content."""

    def test_extract_interface_name(self, tool):
        """Test extracting interface name."""
        content = "public interface MyService {\n    void process();\n}"
        name = tool._extract_name_from_content(content)
        assert name == "MyService"

    def test_extract_static_method_name(self, tool):
        """Test extracting static method name."""
        content = "public static void main(String[] args) {"
        name = tool._extract_name_from_content(content)
        assert name == "main"

    def test_extract_deep_subheading(self, tool):
        """Test extracting deep markdown subheading."""
        content = "### Deep Section Title\nSome details"
        name = tool._extract_name_from_content(content)
        assert name == "Deep Section Title"


class TestValidateArgumentsAdditional:
    """Additional tests targeting uncovered validation branches."""

    def test_validate_query_key_empty_string(self, tool):
        """Test validation with empty string query_key (falsy)."""
        arguments = {"file_path": "test.py", "query_key": ""}
        with pytest.raises(
            ValueError, match="Either query_key or query_string must be provided"
        ):
            tool.validate_arguments(arguments)

    def test_validate_query_string_empty_string(self, tool):
        """Test validation with empty string query_string (falsy)."""
        arguments = {"file_path": "test.py", "query_string": ""}
        with pytest.raises(
            ValueError, match="Either query_key or query_string must be provided"
        ):
            tool.validate_arguments(arguments)

    def test_validate_output_file_whitespace_only(self, tool):
        """Test validation with whitespace-only output_file."""
        arguments = {
            "file_path": "test.py",
            "query_key": "methods",
            "output_file": "   ",
        }
        with pytest.raises(ValueError, match="output_file cannot be empty"):
            tool.validate_arguments(arguments)

    def test_validate_result_format_summary_valid(self, tool):
        """Test validation passes with result_format='summary'."""
        arguments = {
            "file_path": "test.py",
            "query_key": "methods",
            "result_format": "summary",
        }
        assert tool.validate_arguments(arguments) is True

    def test_validate_output_format_toon_valid(self, tool):
        """Test validation passes with output_format='toon'."""
        arguments = {
            "file_path": "test.py",
            "query_key": "methods",
            "output_format": "toon",
        }
        assert tool.validate_arguments(arguments) is True


class TestExecuteCoverageBoost:
    """Tests targeting specific uncovered lines in execute()."""

    @pytest.mark.asyncio
    async def test_execute_generic_exception_returns_error(
        self, tool, sample_python_file
    ):
        """Test execute catches generic Exception and returns error dict (lines 277-283)."""
        with patch.object(
            tool,
            "resolve_and_validate_file_path",
            side_effect=RuntimeError("file resolve boom"),
        ):
            arguments = {
                "file_path": str(sample_python_file),
                "query_key": "methods",
                "language": "python",
            }
            result = await tool.execute(arguments)
            assert result["success"] is False
            assert "file resolve boom" in result["error"]
            assert result["file_path"] == str(sample_python_file)
            assert result["language"] == "python"

    @pytest.mark.asyncio
    async def test_execute_suppress_output_without_file_save(
        self, tool, sample_python_file, mock_query_results
    ):
        """Test suppress_output=True but output_file not triggering file save path (line 243)."""
        with patch.object(
            tool.query_service, "execute_query", new_callable=AsyncMock
        ) as mock_query:
            mock_query.return_value = mock_query_results

            arguments = {
                "file_path": str(sample_python_file),
                "query_key": "methods",
                "language": "python",
                "output_file": "results.json",
                "suppress_output": True,
            }

            with patch.object(tool.file_output_manager, "save_to_file") as mock_save:
                mock_save.return_value = "/output/results.json"

                result = await tool.execute(arguments)

                assert result["success"] is True
                assert result["output_file_path"] == "/output/results.json"
                assert result["file_saved"] is True
                assert "results" not in result

    @pytest.mark.asyncio
    async def test_execute_file_output_with_toon_format(
        self, tool, sample_python_file, mock_query_results
    ):
        """Test file output with toon output_format (line 222-224)."""
        with patch.object(
            tool.query_service, "execute_query", new_callable=AsyncMock
        ) as mock_query:
            mock_query.return_value = mock_query_results

            with patch.object(tool.file_output_manager, "save_to_file") as mock_save:
                mock_save.return_value = "/output/toon_results.txt"

                arguments = {
                    "file_path": str(sample_python_file),
                    "query_key": "methods",
                    "language": "python",
                    "output_file": "toon_results",
                    "output_format": "toon",
                }

                result = await tool.execute(arguments)

                assert result["success"] is True
                assert result["file_saved"] is True
                assert result["output_file_path"] == "/output/toon_results.txt"

    @pytest.mark.asyncio
    async def test_execute_empty_arguments_dict_triggers_error(self, tool):
        """Test execute with empty dict triggers file_path required (line 134)."""
        with pytest.raises(Exception, match="file_path is required"):
            await tool.execute({})

    @pytest.mark.asyncio
    async def test_execute_none_file_path_triggers_error(self, tool):
        """Test execute with None file_path triggers error (line 134)."""
        with pytest.raises(Exception, match="file_path is required"):
            await tool.execute({"file_path": None})


class TestFormatSummaryCoverageBoost:
    """Tests targeting uncovered _format_summary branches."""

    def test_format_summary_multi_capture_with_items(self, tool):
        """Test summary formatting with multiple captures and item extraction (lines 316-329)."""
        results = [
            {
                "capture_name": "class",
                "content": "class MyClass:\n    pass",
                "start_line": 1,
                "end_line": 2,
                "node_type": "class_definition",
            },
            {
                "capture_name": "class",
                "content": "class OtherClass:\n    pass",
                "start_line": 10,
                "end_line": 11,
                "node_type": "class_definition",
            },
            {
                "capture_name": "method",
                "content": "def my_method(self):\n    pass",
                "start_line": 5,
                "end_line": 6,
                "node_type": "function_definition",
            },
        ]
        summary = tool._format_summary(results, "all", "python")

        assert summary["total_count"] == 3
        assert summary["captures"]["class"]["count"] == 2
        assert summary["captures"]["method"]["count"] == 1
        class_items = summary["captures"]["class"]["items"]
        assert class_items[0]["name"] == "MyClass"
        assert class_items[1]["name"] == "OtherClass"
        assert class_items[0]["line_range"] == "1-2"
        method_items = summary["captures"]["method"]["items"]
        assert method_items[0]["name"] == "my_method"


class TestExtractNameCoverageBoost:
    """Tests targeting uncovered _extract_name_from_content branches."""

    def test_extract_simple_function_call(self, tool):
        """Test extracting from simple function call pattern (line 355)."""
        name = tool._extract_name_from_content("process(data)")
        assert name == "process"

    def test_extract_private_static_class(self, tool):
        """Test extracting private static class name (line 353)."""
        name = tool._extract_name_from_content("private static class Singleton {")
        assert name == "Singleton"

    def test_extract_unnamed_no_pattern_match(self, tool):
        """Test fallback to 'unnamed' when no pattern matches (line 363)."""
        name = tool._extract_name_from_content("return 42")
        assert name == "unnamed"


class TestValidateArgumentsCoverageBoost:
    """Tests targeting uncovered validate_arguments branches."""

    def test_validate_no_file_path_key(self, tool):
        """Test validation when file_path key is missing (line 392)."""
        with pytest.raises(ValueError, match="file_path is required"):
            tool.validate_arguments({"query_key": "methods"})

    def test_validate_file_path_not_string(self, tool):
        """Test validation when file_path is not a string (line 396)."""
        with pytest.raises(ValueError, match="file_path must be a string"):
            tool.validate_arguments({"file_path": 123, "query_key": "methods"})

    def test_validate_file_path_empty(self, tool):
        """Test validation when file_path is empty string (line 399)."""
        with pytest.raises(ValueError, match="file_path cannot be empty"):
            tool.validate_arguments({"file_path": "   ", "query_key": "methods"})

    def test_validate_query_key_not_string(self, tool):
        """Test validation when query_key is not a string (line 409)."""
        with pytest.raises(ValueError, match="query_key must be a string"):
            tool.validate_arguments({"file_path": "t.py", "query_key": 123})

    def test_validate_query_string_not_string(self, tool):
        """Test validation when query_string is not a string (line 413)."""
        with pytest.raises(ValueError, match="query_string must be a string"):
            tool.validate_arguments({"file_path": "t.py", "query_string": 123})

    def test_validate_language_not_string(self, tool):
        """Test validation when language is not a string (line 418)."""
        with pytest.raises(ValueError, match="language must be a string"):
            tool.validate_arguments(
                {"file_path": "t.py", "query_key": "m", "language": 42}
            )

    def test_validate_filter_not_string(self, tool):
        """Test validation when filter is not a string (line 425)."""
        with pytest.raises(ValueError, match="filter must be a string"):
            tool.validate_arguments(
                {"file_path": "t.py", "query_key": "m", "filter": 42}
            )

    def test_validate_result_format_invalid_value(self, tool):
        """Test validation when result_format has invalid value (line 432)."""
        with pytest.raises(ValueError, match="result_format must be one of"):
            tool.validate_arguments(
                {"file_path": "t.py", "query_key": "m", "result_format": "xml"}
            )

    def test_validate_result_format_not_string(self, tool):
        """Test validation when result_format is not a string (line 429)."""
        with pytest.raises(ValueError, match="result_format must be a string"):
            tool.validate_arguments(
                {"file_path": "t.py", "query_key": "m", "result_format": 123}
            )

    def test_validate_output_format_invalid_value(self, tool):
        """Test validation when output_format has invalid value (line 438)."""
        with pytest.raises(ValueError, match="output_format must be one of"):
            tool.validate_arguments(
                {"file_path": "t.py", "query_key": "m", "output_format": "xml"}
            )

    def test_validate_output_format_not_string(self, tool):
        """Test validation when output_format is not a string (line 436)."""
        with pytest.raises(ValueError, match="output_format must be a string"):
            tool.validate_arguments(
                {"file_path": "t.py", "query_key": "m", "output_format": 123}
            )

    def test_validate_output_file_not_string(self, tool):
        """Test validation when output_file is not a string (line 444)."""
        with pytest.raises(ValueError, match="output_file must be a string"):
            tool.validate_arguments(
                {"file_path": "t.py", "query_key": "m", "output_file": 123}
            )

    def test_validate_suppress_output_not_bool(self, tool):
        """Test validation when suppress_output is not a boolean (line 452)."""
        with pytest.raises(ValueError, match="suppress_output must be a boolean"):
            tool.validate_arguments(
                {"file_path": "t.py", "query_key": "m", "suppress_output": "yes"}
            )

    def test_validate_all_valid_fields(self, tool):
        """Test validation passes with all valid fields (line 455)."""
        arguments = {
            "file_path": "test.py",
            "query_key": "methods",
            "language": "python",
            "filter": "name=foo",
            "result_format": "json",
            "output_format": "toon",
            "output_file": "out.txt",
            "suppress_output": True,
        }
        assert tool.validate_arguments(arguments) is True


class TestCategorizeQueries:
    """Tests for _categorize_queries helper function."""

    def test_common_keys_categorized(self):
        from tree_sitter_analyzer.mcp.tools.query_tool import _categorize_queries

        result = _categorize_queries(
            ["classes", "methods", "functions", "imports", "variables"], "python"
        )
        assert "common" in result
        assert result["common"] == [
            "classes",
            "methods",
            "functions",
            "imports",
            "variables",
        ]

    def test_declaration_keys_categorized(self):
        from tree_sitter_analyzer.mcp.tools.query_tool import _categorize_queries

        result = _categorize_queries(
            ["struct_definitions", "enum_members", "interface_declarations"],
            "typescript",
        )
        assert "declarations" in result
        assert "struct_definitions" in result["declarations"]

    def test_control_flow_keys_categorized(self):
        from tree_sitter_analyzer.mcp.tools.query_tool import _categorize_queries

        result = _categorize_queries(
            ["for_loops", "while_loops", "switch_statements"], "java"
        )
        assert "control_flow" in result
        assert "for_loops" in result["control_flow"]

    def test_framework_keys_categorized(self):
        from tree_sitter_analyzer.mcp.tools.query_tool import _categorize_queries

        result = _categorize_queries(
            ["spring_controller", "react_component", "goroutine_definitions"], "go"
        )
        assert "framework" in result
        assert "spring_controller" in result["framework"]

    def test_other_keys_categorized(self):
        from tree_sitter_analyzer.mcp.tools.query_tool import _categorize_queries

        result = _categorize_queries(["comments", "strings", "misc_stuff"], "python")
        assert "other" in result
        assert "comments" in result["other"]

    def test_empty_categories_removed(self):
        from tree_sitter_analyzer.mcp.tools.query_tool import _categorize_queries

        result = _categorize_queries(["classes"], "python")
        assert "common" in result
        # Categories with no items should not appear
        assert "control_flow" not in result
        assert "framework" not in result

    def test_mixed_categorization(self):
        from tree_sitter_analyzer.mcp.tools.query_tool import _categorize_queries

        result = _categorize_queries(
            ["classes", "for_loops", "spring_service", "struct_defs", "random_thing"],
            "java",
        )
        assert result["common"] == ["classes"]
        assert "for_loops" in result["control_flow"]
        assert "spring_service" in result["framework"]
        assert "struct_defs" in result["declarations"]
        assert "random_thing" in result["other"]

    def test_empty_query_list(self):
        from tree_sitter_analyzer.mcp.tools.query_tool import _categorize_queries

        result = _categorize_queries([], "python")
        assert result == {}


class TestExecuteInvalidQueryKey:
    """Tests for execute with invalid query_key."""

    @pytest.mark.asyncio
    async def test_execute_invalid_query_key_returns_suggestions(
        self, tool, sample_python_file
    ):
        with patch.object(
            tool.query_service,
            "get_available_queries",
            return_value=["methods", "classes"],
        ):
            arguments = {
                "file_path": str(sample_python_file),
                "query_key": "nonexistent",
                "language": "python",
            }
            result = await tool.execute(arguments)
            assert result["success"] is False
            assert "not found" in result["error"]
            assert "available_queries" in result
            assert result["language"] == "python"
            assert "hint" in result

    @pytest.mark.asyncio
    async def test_execute_no_results_with_productive_queries(
        self, tool, sample_python_file
    ):
        """Test no-results path that discovers productive queries via common keys."""
        call_count = 0

        async def mock_execute_query(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            query_key = args[3] if len(args) > 3 else kwargs.get("query_key")
            if query_key == "classes":
                return [
                    {
                        "capture_name": "class",
                        "content": "class Foo",
                        "start_line": 1,
                        "end_line": 1,
                        "node_type": "class",
                    }
                ]
            return []

        with patch.object(
            tool.query_service, "execute_query", side_effect=mock_execute_query
        ):
            arguments = {
                "file_path": str(sample_python_file),
                "query_key": "methods",
                "language": "python",
            }
            result = await tool.execute(arguments)
            assert result["success"] is True
            assert result["count"] == 0
            assert "productive_queries" in result
            assert "classes" in result["productive_queries"]

    @pytest.mark.asyncio
    async def test_execute_no_results_productive_queries_exception(
        self, tool, sample_python_file
    ):
        """Test no-results path where productive query probing raises exception."""
        call_count = 0

        async def mock_execute_query(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return []
            raise RuntimeError("probe failed")

        with patch.object(
            tool.query_service, "execute_query", side_effect=mock_execute_query
        ):
            arguments = {
                "file_path": str(sample_python_file),
                "query_key": "methods",
                "language": "python",
            }
            result = await tool.execute(arguments)
            assert result["success"] is True
            assert result["count"] == 0
            # productive_queries should be empty since probing failed
            assert "productive_queries" not in result

    @pytest.mark.asyncio
    async def test_execute_no_results_with_query_string(self, tool, sample_python_file):
        """Test no-results path uses query_string in hint when provided."""
        with patch.object(
            tool.query_service, "execute_query", new_callable=AsyncMock
        ) as mock_query:
            mock_query.return_value = []

            arguments = {
                "file_path": str(sample_python_file),
                "query_string": "(method_declaration) @m",
                "language": "python",
            }
            result = await tool.execute(arguments)
            assert result["success"] is True
            assert result["count"] == 0
            assert "custom" in result.get(
                "message", ""
            ) or "(method_declaration) @m" in result.get("message", "")

    @pytest.mark.asyncio
    async def test_execute_suppress_output_without_output_file(
        self, tool, sample_python_file, mock_query_results
    ):
        """Test suppress_output=True without output_file skips minimal result path."""
        with patch.object(
            tool.query_service, "execute_query", new_callable=AsyncMock
        ) as mock_query:
            mock_query.return_value = mock_query_results

            arguments = {
                "file_path": str(sample_python_file),
                "query_key": "methods",
                "language": "python",
                "suppress_output": True,
            }
            result = await tool.execute(arguments)
            # suppress_output without output_file falls through to else branch
            assert result["success"] is True
