#!/usr/bin/env python3
"""
Tests for Search Content MCP Tool.

This module tests SearchContentTool class which provides
content search capabilities using ripgrep.
"""

from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.search_content_tool import (
    SearchContentTool,
)


@pytest.fixture
def tool():
    """Create a fresh tool instance for each test."""
    return SearchContentTool()


@pytest.fixture
def sample_project_structure(tmp_path: Path):
    """Create a sample project structure for testing."""
    # Create directories
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()

    # Create files
    (tmp_path / "README.md").write_text("# Test Project")
    (tmp_path / "src" / "main.py").write_text("def main():\n    print('hello')")
    (tmp_path / "src" / "utils.py").write_text("def helper():\n    return 42")
    (tmp_path / "tests" / "test_main.py").write_text("def test():\n    assert True")

    return tmp_path


class TestSearchContentToolInitialization:
    """Tests for tool initialization."""

    def test_init_creates_tool(self, tool):
        """Test that initialization creates a tool instance."""
        assert tool is not None
        assert hasattr(tool, "cache")
        assert hasattr(tool, "file_output_manager")

    def test_init_with_project_root(self):
        """Test initialization with project root."""
        tool = SearchContentTool(project_root="/test/path")
        assert tool.project_root == "/test/path"

    def test_init_with_cache_disabled(self):
        """Test initialization with cache disabled."""
        tool = SearchContentTool(enable_cache=False)
        assert tool.cache is None

    def test_init_multiple_instances(self):
        """Test that multiple instances are independent."""
        tool1 = SearchContentTool()
        tool2 = SearchContentTool()
        assert tool1 is not tool2


class TestSetProjectPath:
    """Tests for set_project_path method."""

    def test_set_project_path_updates_all_components(self, tool):
        """Test that set_project_path updates all components."""
        new_path = "/new/project/path"
        tool.set_project_path(new_path)
        assert tool.project_root == new_path

    def test_set_project_path_recreates_file_manager(self, tool):
        """Test that set_project_path recreates file manager."""
        old_manager = tool.file_output_manager
        tool.set_project_path("/new/path")
        assert tool.file_output_manager is not old_manager


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
        assert definition["name"] == "search_content"

    def test_required_fields(self, tool):
        """Test that required fields are correctly defined."""
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        required = schema.get("required", [])
        assert "query" in required
        assert len(required) == 1

    def test_roots_property(self, tool):
        """Test that roots property is correctly defined."""
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "roots" in properties
        assert properties["roots"]["type"] == "array"

    def test_files_property(self, tool):
        """Test that files property is correctly defined."""
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "files" in properties
        assert properties["files"]["type"] == "array"

    def test_query_property(self, tool):
        """Test that query property is correctly defined."""
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "query" in properties
        assert properties["query"]["type"] == "string"

    def test_case_property(self, tool):
        """Test that case property is correctly defined."""
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "case" in properties
        assert properties["case"]["enum"] == ["smart", "insensitive", "sensitive"]
        assert properties["case"]["default"] == "smart"

    def test_total_only_property(self, tool):
        """Test that total_only property is correctly defined."""
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "total_only" in properties
        assert properties["total_only"]["type"] == "boolean"
        assert properties["total_only"]["default"] is False

    def test_count_only_matches_property(self, tool):
        """Test that count_only_matches property is correctly defined."""
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "count_only_matches" in properties
        assert properties["count_only_matches"]["type"] == "boolean"
        assert properties["count_only_matches"]["default"] is False

    def test_summary_only_property(self, tool):
        """Test that summary_only property is correctly defined."""
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "summary_only" in properties
        assert properties["summary_only"]["type"] == "boolean"
        assert properties["summary_only"]["default"] is False

    def test_group_by_file_property(self, tool):
        """Test that group_by_file property is correctly defined."""
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "group_by_file" in properties
        assert properties["group_by_file"]["type"] == "boolean"
        assert properties["group_by_file"]["default"] is False

    def test_optimize_paths_property(self, tool):
        """Test that optimize_paths property is correctly defined."""
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "optimize_paths" in properties
        assert properties["optimize_paths"]["type"] == "boolean"
        assert properties["optimize_paths"]["default"] is False


class TestValidateRoots:
    """Tests for _validate_roots method."""

    def test_validate_roots_success(self, tool, sample_project_structure):
        """Test successful roots validation."""
        roots = [str(sample_project_structure)]
        validated = tool._validate_roots(roots)
        assert len(validated) == 1
        assert Path(validated[0]).is_absolute()

    def test_validate_roots_invalid_directory(self, tool):
        """Test validation fails when directory doesn't exist."""
        roots = ["/nonexistent/directory"]
        with pytest.raises(ValueError, match="Invalid root"):
            tool._validate_roots(roots)


class TestValidateFiles:
    """Tests for _validate_files method."""

    def test_validate_files_success(self, tool, sample_project_structure):
        """Test successful files validation."""
        files = [str(sample_project_structure / "README.md")]
        validated = tool._validate_files(files)
        assert len(validated) == 1

    def test_validate_files_empty_string(self, tool):
        """Test validation fails when file is empty string."""
        files = [""]
        with pytest.raises(ValueError, match="files entries must be non-empty strings"):
            tool._validate_files(files)

    def test_validate_files_not_found(self, tool):
        """Test validation fails when file doesn't exist."""
        files = ["/nonexistent/file.txt"]
        with pytest.raises(ValueError, match="Invalid file path"):
            tool._validate_files(files)


class TestValidateArguments:
    """Tests for validate_arguments method."""

    def test_validate_valid_arguments_with_roots(self, tool, sample_project_structure):
        """Test validation with valid arguments using roots."""
        arguments = {
            "roots": [str(sample_project_structure)],
            "query": "test",
        }
        assert tool.validate_arguments(arguments) is True

    def test_validate_valid_arguments_with_files(self, tool, sample_project_structure):
        """Test validation with valid arguments using files."""
        arguments = {
            "files": [str(sample_project_structure / "README.md")],
            "query": "test",
        }
        assert tool.validate_arguments(arguments) is True

    def test_validate_missing_query(self, tool):
        """Test validation fails when query is missing."""
        arguments = {"roots": ["."]}
        with pytest.raises(ValueError, match="query is required"):
            tool.validate_arguments(arguments)

    def test_validate_empty_query(self, tool):
        """Test validation fails when query is empty."""
        arguments = {"roots": ["."], "query": ""}
        with pytest.raises(ValueError, match="query is required"):
            tool.validate_arguments(arguments)

    def test_validate_whitespace_query(self, tool):
        """Test validation fails when query is only whitespace."""
        arguments = {"roots": ["."], "query": "   "}
        with pytest.raises(ValueError, match="query is required"):
            tool.validate_arguments(arguments)

    def test_validate_missing_both_roots_and_files(self, tool):
        """Test validation fails when both roots and files are missing."""
        arguments = {"query": "test"}
        with pytest.raises(ValueError, match="Either roots or files must be provided"):
            tool.validate_arguments(arguments)

    def test_validate_invalid_case_type(self, tool):
        """Test validation fails when case is not a string."""
        arguments = {"roots": ["."], "query": "test", "case": 123}
        with pytest.raises(ValueError, match="case must be a string"):
            tool.validate_arguments(arguments)

    def test_validate_invalid_encoding_type(self, tool):
        """Test validation fails when encoding is not a string."""
        arguments = {
            "roots": ["."],
            "query": "test",
            "encoding": 123,
        }
        with pytest.raises(ValueError, match="encoding must be a string"):
            tool.validate_arguments(arguments)

    def test_validate_invalid_max_filesize_type(self, tool):
        """Test validation fails when max_filesize is not a string."""
        arguments = {
            "roots": ["."],
            "query": "test",
            "max_filesize": 123,
        }
        with pytest.raises(ValueError, match="max_filesize must be a string"):
            tool.validate_arguments(arguments)

    def test_validate_invalid_fixed_strings_type(self, tool):
        """Test validation fails when fixed_strings is not a boolean."""
        arguments = {
            "roots": ["."],
            "query": "test",
            "fixed_strings": "true",
        }
        with pytest.raises(ValueError, match="fixed_strings must be a boolean"):
            tool.validate_arguments(arguments)

    def test_validate_invalid_word_type(self, tool):
        """Test validation fails when word is not a boolean."""
        arguments = {"roots": ["."], "query": "test", "word": "true"}
        with pytest.raises(ValueError, match="word must be a boolean"):
            tool.validate_arguments(arguments)

    def test_validate_invalid_multiline_type(self, tool):
        """Test validation fails when multiline is not a boolean."""
        arguments = {
            "roots": ["."],
            "query": "test",
            "multiline": "true",
        }
        with pytest.raises(ValueError, match="multiline must be a boolean"):
            tool.validate_arguments(arguments)

    def test_validate_invalid_include_globs_type(self, tool):
        """Test validation fails when include_globs is not an array."""
        arguments = {
            "roots": ["."],
            "query": "test",
            "include_globs": "*.py",
        }
        with pytest.raises(
            ValueError, match="include_globs must be an array of strings"
        ):
            tool.validate_arguments(arguments)


class TestDetermineRequestedFormat:
    """Tests for _determine_requested_format method."""

    def test_determine_total_only_format(self, tool):
        """Test format determination for total_only."""
        arguments = {"total_only": True}
        format_type = tool._determine_requested_format(arguments)
        assert format_type == "total_only"

    def test_determine_count_only_format(self, tool):
        """Test format determination for count_only_matches."""
        arguments = {"count_only_matches": True}
        format_type = tool._determine_requested_format(arguments)
        assert format_type == "count_only"

    def test_determine_summary_format(self, tool):
        """Test format determination for summary_only."""
        arguments = {"summary_only": True}
        format_type = tool._determine_requested_format(arguments)
        assert format_type == "summary"

    def test_determine_group_by_file_format(self, tool):
        """Test format determination for group_by_file."""
        arguments = {"group_by_file": True}
        format_type = tool._determine_requested_format(arguments)
        assert format_type == "group_by_file"

    def test_determine_normal_format(self, tool):
        """Test format determination for normal mode."""
        arguments = {}
        format_type = tool._determine_requested_format(arguments)
        assert format_type == "normal"
