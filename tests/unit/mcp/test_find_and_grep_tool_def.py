#!/usr/bin/env python3
"""
Tests for FindAndGrepTool definition, initialization, and argument validation.
"""

from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.find_and_grep_tool import (
    FindAndGrepTool,
)


@pytest.fixture
def tool():
    """Create a fresh tool instance for each test."""
    return FindAndGrepTool()


@pytest.fixture
def sample_project_structure(tmp_path: Path):
    """Create a sample project structure for testing."""
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "docs").mkdir()

    (tmp_path / "README.md").write_text("# Test Project")
    (tmp_path / "src" / "main.py").write_text("def main():\n    print('hello')")
    (tmp_path / "src" / "utils.py").write_text("def helper():\n    return 42")
    (tmp_path / "tests" / "test_main.py").write_text("def test():\n    assert True")
    (tmp_path / "docs" / "guide.md").write_text("# Guide")

    return tmp_path


class TestFindAndGrepToolInitialization:
    """Tests for tool initialization."""

    def test_init_creates_tool(self, tool):
        """Test that initialization creates a tool instance."""
        assert tool is not None
        assert hasattr(tool, "file_output_manager")

    def test_init_multiple_instances(self):
        """Test that multiple instances are independent."""
        tool1 = FindAndGrepTool()
        tool2 = FindAndGrepTool()
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
        assert "roots" in required
        assert "query" in required
        assert len(required) == 2

    def test_file_stage_parameters(self, tool):
        """Test that file stage parameters are defined."""
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})

        assert "roots" in properties
        assert "pattern" in properties
        assert "glob" in properties
        assert "types" in properties
        assert "extensions" in properties
        assert "exclude" in properties
        assert "depth" in properties
        assert "follow_symlinks" in properties
        assert "hidden" in properties
        assert "no_ignore" in properties
        assert "size" in properties
        assert "changed_within" in properties
        assert "changed_before" in properties
        assert "full_path_match" in properties
        assert "file_limit" in properties
        assert "sort" in properties

    def test_content_stage_parameters(self, tool):
        """Test that content stage parameters are defined."""
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})

        assert "query" in properties
        assert "case" in properties
        assert "fixed_strings" in properties
        assert "word" in properties
        assert "multiline" in properties
        assert "include_globs" in properties
        assert "exclude_globs" in properties
        assert "max_filesize" in properties
        assert "context_before" in properties
        assert "context_after" in properties
        # F5: ``encoding`` is now declared in the schema. The fd_rg_utils
        # layer accepts ``arguments['encoding']`` and forwards it to
        # ripgrep as ``--encoding``, so the schema must list it for
        # strict-parameter validation to allow it.
        assert "encoding" in properties
        assert "max_count" in properties
        assert "timeout_ms" in properties

    def test_output_format_parameters(self, tool):
        """Test that output format parameters are defined."""
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})

        assert "count_only_matches" in properties
        assert "summary_only" in properties
        assert "optimize_paths" in properties
        assert "group_by_file" in properties
        assert "total_only" in properties
        assert "output_file" in properties
        assert "suppress_output" in properties
        assert "output_format" in properties

    def test_sort_enum_values(self, tool):
        """Test that sort parameter has correct enum values."""
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert properties["sort"]["enum"] == ["path", "mtime", "size"]

    def test_case_enum_values(self, tool):
        """Test that case parameter has correct enum values."""
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert properties["case"]["enum"] == ["smart", "insensitive", "sensitive"]
        assert properties["case"]["default"] == "smart"

    def test_output_format_enum_values(self, tool):
        """Test that output_format parameter has correct enum values."""
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert properties["output_format"]["enum"] == ["json", "toon"]
        assert properties["output_format"]["default"] == "toon"


class TestValidateRoots:
    """Tests for _validate_roots method."""

    def test_validate_roots_success(self, tool, sample_project_structure):
        """Test successful roots validation."""
        roots = [str(sample_project_structure)]
        validated = tool._validate_roots(roots)
        assert len(validated) == 1
        assert Path(validated[0]).is_absolute()

    def test_validate_roots_multiple(self, tool, sample_project_structure):
        """Test validation of multiple roots."""
        roots = [
            str(sample_project_structure),
            str(sample_project_structure / "src"),
        ]
        validated = tool._validate_roots(roots)
        assert len(validated) == 2

    def test_validate_roots_invalid_directory(self, tool):
        """Test validation fails when directory doesn't exist."""
        roots = ["/nonexistent/directory"]
        with pytest.raises(ValueError, match="Invalid root"):
            tool._validate_roots(roots)


class TestValidateArguments:
    """Tests for validate_arguments method."""

    def test_validate_valid_arguments(self, tool):
        """Test validation with valid arguments."""
        arguments = {
            "roots": ["."],
            "query": "test",
        }
        assert tool.validate_arguments(arguments) is True

    def test_validate_missing_roots(self, tool):
        """Test validation fails when roots is missing."""
        arguments = {"query": "test"}
        with pytest.raises(ValueError, match="roots is required"):
            tool.validate_arguments(arguments)

    def test_validate_roots_not_array(self, tool):
        """Test validation fails when roots is not an array."""
        arguments = {"roots": ".", "query": "test"}
        with pytest.raises(ValueError, match="roots is required and must be an array"):
            tool.validate_arguments(arguments)

    def test_validate_missing_query(self, tool):
        """Test validation fails when query is missing."""
        arguments = {"roots": ["."]}
        with pytest.raises(ValueError, match="query is required"):
            tool.validate_arguments(arguments)

    def test_validate_query_not_string(self, tool):
        """Test validation fails when query is not a string."""
        arguments = {"roots": ["."], "query": 123}
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

    def test_validate_invalid_file_limit_type(self, tool):
        """Test validation fails when file_limit is not an integer."""
        arguments = {"roots": ["."], "query": "test", "file_limit": "100"}
        with pytest.raises(ValueError, match="file_limit must be an integer"):
            tool.validate_arguments(arguments)
