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
        assert "anyOf" in schema

    def test_required_fields(self, tool):
        """Test that required fields are correctly defined."""
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        required = schema.get("required", [])
        assert "file_path" in required
        assert len(required) == 1

    def test_anyof_validation(self, tool):
        """Test that anyOf validation is correctly defined."""
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        anyof = schema.get("anyOf", [])
        assert len(anyof) == 2
        # First option: query_key required
        assert "query_key" in anyof[0]["required"]
        # Second option: query_string required
        assert "query_string" in anyof[1]["required"]

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
            assert "No results found" in result["message"]

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
