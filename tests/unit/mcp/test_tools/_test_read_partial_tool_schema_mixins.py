"""Private mixins for read_partial_tool tests.

These modules keep the collected pytest node IDs anchored in test_read_partial_tool.py.
"""

import pytest

from tree_sitter_analyzer.mcp.tools.read_partial_tool import ReadPartialTool


class ReadPartialToolInitMixin:
    """Tests for ReadPartialTool initialization."""

    def test_init_without_project_root(self):
        """Test initialization without project root."""
        tool = ReadPartialTool()
        assert tool is not None
        assert tool.project_root is None
        assert tool.file_output_manager is not None

    def test_init_without_project_root_attributes(self):
        tool = ReadPartialTool()
        assert hasattr(tool, "project_root")
        assert hasattr(tool, "file_output_manager")

    def test_init_with_project_root(self):
        """Test initialization with project root."""
        tool = ReadPartialTool(project_root="/test/path")
        assert tool is not None
        assert tool.project_root == "/test/path"
        assert tool.file_output_manager is not None


class ReadPartialToolGetToolSchemaMixin:
    """Tests for get_tool_schema method."""

    def test_get_tool_schema_structure(self):
        """Test that schema has correct structure."""
        tool = ReadPartialTool()
        schema = tool.get_tool_schema()
        assert isinstance(schema, dict)
        assert "type" in schema
        assert schema["type"] == "object"
        assert "properties" in schema

    def test_get_tool_schema_has_required(self):
        tool = ReadPartialTool()
        schema = tool.get_tool_schema()
        assert isinstance(schema, dict)
        assert schema.get("type") == "object"

    def test_get_tool_schema_has_requests_property(self):
        """Test that schema has requests property for batch mode."""
        tool = ReadPartialTool()
        schema = tool.get_tool_schema()
        assert "requests" in schema["properties"]
        requests_prop = schema["properties"]["requests"]
        assert requests_prop["type"] == "array"

    def test_get_tool_schema_has_file_path_property(self):
        """Test that schema has file_path property."""
        tool = ReadPartialTool()
        schema = tool.get_tool_schema()
        assert "file_path" in schema["properties"]
        assert schema["properties"]["file_path"]["type"] == "string"


class ReadPartialToolGetToolDefinitionMixin:
    """Tests for get_tool_definition method."""

    def test_get_tool_definition_name(self):
        """Test that tool definition has correct name."""
        tool = ReadPartialTool()
        definition = tool.get_tool_definition()
        assert definition["name"] == "extract_code_section"

    def test_get_tool_definition_has_description(self):
        """Test that tool definition has description."""
        tool = ReadPartialTool()
        definition = tool.get_tool_definition()
        assert "description" in definition
        assert isinstance(definition["description"], str)

    def test_get_tool_definition_has_input_schema(self):
        """Test that tool definition has inputSchema."""
        tool = ReadPartialTool()
        definition = tool.get_tool_definition()
        assert "inputSchema" in definition
        assert isinstance(definition["inputSchema"], dict)

    def test_get_tool_definition_schema_has_properties(self):
        tool = ReadPartialTool()
        definition = tool.get_tool_definition()
        assert "inputSchema" in definition
        schema = definition["inputSchema"]
        assert "properties" in schema or "type" in schema

    def test_get_tool_definition_name_correct(self):
        tool = ReadPartialTool()
        definition = tool.get_tool_definition()
        assert definition["name"] == "extract_code_section"
        assert len(definition["description"]) > 0


class ReadPartialToolValidateArgumentsMixin:
    """Tests for validate_arguments method."""

    def test_validate_arguments_missing_file_path(self):
        """Test that validation fails when file_path is missing."""
        tool = ReadPartialTool()
        args = {"start_line": 1}
        with pytest.raises(ValueError, match="Required field 'file_path' is missing"):
            tool.validate_arguments(args)

    def test_validate_arguments_missing_start_line(self):
        """Test that validation fails when start_line is missing."""
        tool = ReadPartialTool()
        args = {"file_path": "test.py"}
        with pytest.raises(ValueError, match="Required field 'start_line' is missing"):
            tool.validate_arguments(args)

    def test_validate_arguments_invalid_file_path_type(self):
        """Test that validation fails when file_path is not a string."""
        tool = ReadPartialTool()
        args = {"file_path": 123, "start_line": 1}
        with pytest.raises(ValueError, match="file_path must be a string"):
            tool.validate_arguments(args)

    def test_validate_arguments_empty_file_path(self):
        """Test that validation fails when file_path is empty."""
        tool = ReadPartialTool()
        args = {"file_path": "", "start_line": 1}
        with pytest.raises(ValueError, match="file_path cannot be empty"):
            tool.validate_arguments(args)

    def test_validate_arguments_invalid_start_line_type(self):
        """Test that validation fails when start_line is not an integer."""
        tool = ReadPartialTool()
        args = {"file_path": "test.py", "start_line": "1"}
        with pytest.raises(ValueError, match="start_line must be an integer"):
            tool.validate_arguments(args)

    def test_validate_arguments_start_line_below_minimum(self):
        """Test that validation fails when start_line < 1."""
        tool = ReadPartialTool()
        args = {"file_path": "test.py", "start_line": 0}
        with pytest.raises(ValueError, match="start_line must be >= 1"):
            tool.validate_arguments(args)

    def test_validate_arguments_invalid_end_line_type(self):
        """Test that validation fails when end_line is not an integer."""
        tool = ReadPartialTool()
        args = {"file_path": "test.py", "start_line": 1, "end_line": "10"}
        with pytest.raises(ValueError, match="end_line must be an integer"):
            tool.validate_arguments(args)

    def test_validate_arguments_end_line_below_start_line(self):
        """Test that validation fails when end_line < start_line."""
        tool = ReadPartialTool()
        args = {"file_path": "test.py", "start_line": 10, "end_line": 5}
        with pytest.raises(ValueError, match="end_line must be >= start_line"):
            tool.validate_arguments(args)

    def test_validate_arguments_invalid_start_column_type(self):
        """Test that validation fails when start_column is not an integer."""
        tool = ReadPartialTool()
        args = {"file_path": "test.py", "start_line": 1, "start_column": "0"}
        with pytest.raises(ValueError, match="start_column must be an integer"):
            tool.validate_arguments(args)

    def test_validate_arguments_start_column_below_zero(self):
        """Test that validation fails when start_column < 0."""
        tool = ReadPartialTool()
        args = {"file_path": "test.py", "start_line": 1, "start_column": -1}
        with pytest.raises(ValueError, match="start_column must be >= 0"):
            tool.validate_arguments(args)

    def test_validate_arguments_invalid_format(self):
        """Test that validation fails when format is invalid."""
        tool = ReadPartialTool()
        args = {"file_path": "test.py", "start_line": 1, "format": "invalid"}
        with pytest.raises(ValueError, match="format must be 'text', 'json', or 'raw'"):
            tool.validate_arguments(args)

    def test_validate_arguments_valid_single_mode(self):
        """Test that validation passes for valid single mode arguments."""
        tool = ReadPartialTool()
        args = {
            "file_path": "test.py",
            "start_line": 1,
            "end_line": 10,
            "format": "text",
        }
        assert tool.validate_arguments(args) is True

    def test_validate_arguments_valid_batch_mode(self):
        """Test that validation passes for valid batch mode arguments."""
        tool = ReadPartialTool()
        args = {"requests": [{"file_path": "test.py", "sections": [{"start_line": 1}]}]}
        assert tool.validate_arguments(args) is True

    def test_validate_arguments_batch_empty_requests(self):
        tool = ReadPartialTool()
        args = {"requests": []}
        assert tool.validate_arguments(args) is True

    def test_validate_arguments_batch_single_request(self):
        tool = ReadPartialTool()
        args = {"requests": [{"file_path": "t.py", "sections": [{"start_line": 1, "end_line": 5}]}]}
        assert tool.validate_arguments(args) is True

    def test_validate_arguments_mutually_exclusive(self):
        """Test that validation fails when both batch and single mode args are present."""
        tool = ReadPartialTool()
        args = {
            "file_path": "test.py",
            "start_line": 1,
            "requests": [{"file_path": "test.py", "sections": []}],
        }
        with pytest.raises(ValueError, match="mutually exclusive"):
            tool.validate_arguments(args)


class ReadPartialToolValidateExtraMixin:
    """Additional tests for uncovered validate_arguments paths."""

    def test_validate_end_column_below_zero(self):
        tool = ReadPartialTool()
        with pytest.raises(ValueError, match="end_column must be >= 0"):
            tool.validate_arguments(
                {"file_path": "t.py", "start_line": 1, "end_column": -1}
            )

    def test_validate_format_not_string(self):
        tool = ReadPartialTool()
        with pytest.raises(ValueError, match="format must be a string"):
            tool.validate_arguments(
                {"file_path": "t.py", "start_line": 1, "format": 123}
            )

    def test_validate_output_file_not_string(self):
        tool = ReadPartialTool()
        with pytest.raises(ValueError, match="output_file must be a string"):
            tool.validate_arguments(
                {"file_path": "t.py", "start_line": 1, "output_file": 42}
            )

    def test_validate_output_file_empty(self):
        tool = ReadPartialTool()
        with pytest.raises(ValueError, match="output_file cannot be empty"):
            tool.validate_arguments(
                {"file_path": "t.py", "start_line": 1, "output_file": "  "}
            )

    def test_validate_suppress_output_not_bool(self):
        tool = ReadPartialTool()
        with pytest.raises(ValueError, match="suppress_output must be a boolean"):
            tool.validate_arguments(
                {"file_path": "t.py", "start_line": 1, "suppress_output": "yes"}
            )

    def test_validate_end_line_below_one(self):
        tool = ReadPartialTool()
        with pytest.raises(ValueError, match="end_line must be >= 1"):
            tool.validate_arguments(
                {"file_path": "t.py", "start_line": 1, "end_line": 0}
            )

    def test_validate_requests_not_list(self):
        tool = ReadPartialTool()
        with pytest.raises(ValueError, match="requests must be a list"):
            tool.validate_arguments({"requests": "not_list"})

    def test_validate_valid_with_all_optional_fields(self):
        tool = ReadPartialTool()
        args = {
            "file_path": "t.py",
            "start_line": 1,
            "end_line": 10,
            "start_column": 0,
            "end_column": 5,
            "format": "raw",
            "output_file": "out.md",
            "suppress_output": True,
        }
        assert tool.validate_arguments(args) is True
