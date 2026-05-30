#!/usr/bin/env python3
"""ListFilesTool initialization, definition, validation, and agent summary tests."""

from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.list_files_tool import (
    ListFilesTool,
    _build_agent_summary,
)


@pytest.fixture
def tool():
    return ListFilesTool()


@pytest.fixture
def sample_project_structure(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / ".git").mkdir()
    (tmp_path / "README.md").write_text("# Test Project")
    (tmp_path / "src" / "main.py").write_text("print('hello')")
    (tmp_path / "src" / "utils.py").write_text("def helper(): pass")
    (tmp_path / "tests" / "test_main.py").write_text("def test(): pass")
    (tmp_path / "docs" / "guide.md").write_text("# Guide")
    (tmp_path / ".env").write_text("KEY=value")
    (tmp_path / ".gitignore").write_text("*.pyc\n__pycache__/")
    return tmp_path


class TestListFilesToolInitialization:
    def test_init_creates_tool(self, tool):
        assert tool is not None
        assert hasattr(tool, "project_root")

    def test_init_multiple_instances(self):
        tool1 = ListFilesTool()
        tool2 = ListFilesTool()
        assert tool1 is not tool2


class TestGetToolDefinition:
    def test_tool_definition_description(self, tool):
        definition = tool.get_tool_definition()
        assert definition["description"] is not None
        assert isinstance(definition["description"], str)

    def test_input_schema_structure(self, tool):
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        assert schema["type"] == "object"
        assert "properties" in schema
        assert "required" in schema

    def test_required_fields(self, tool):
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        required = schema.get("required", [])
        assert "roots" in required
        assert len(required) == 1

    def test_roots_property(self, tool):
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "roots" in properties
        assert properties["roots"]["type"] == "array"
        assert properties["roots"]["items"]["type"] == "string"

    def test_pattern_property(self, tool):
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "pattern" in properties
        assert properties["pattern"]["type"] == "string"

    def test_glob_property(self, tool):
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "glob" in properties
        assert properties["glob"]["type"] == "boolean"
        assert properties["glob"]["default"] is False

    def test_types_property(self, tool):
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "types" in properties
        assert properties["types"]["type"] == "array"
        assert properties["types"]["items"]["type"] == "string"

    def test_extensions_property(self, tool):
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "extensions" in properties
        assert properties["extensions"]["type"] == "array"

    def test_exclude_property(self, tool):
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "exclude" in properties
        assert properties["exclude"]["type"] == "array"

    def test_depth_property(self, tool):
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "depth" in properties
        assert properties["depth"]["type"] == "integer"

    def test_follow_symlinks_property(self, tool):
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "follow_symlinks" in properties
        assert properties["follow_symlinks"]["type"] == "boolean"
        assert properties["follow_symlinks"]["default"] is False

    def test_hidden_property(self, tool):
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "hidden" in properties
        assert properties["hidden"]["type"] == "boolean"
        assert properties["hidden"]["default"] is False

    def test_no_ignore_property(self, tool):
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "no_ignore" in properties
        assert properties["no_ignore"]["type"] == "boolean"
        assert properties["no_ignore"]["default"] is False

    def test_size_property(self, tool):
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "size" in properties
        assert properties["size"]["type"] == "array"

    def test_changed_within_property(self, tool):
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "changed_within" in properties
        assert properties["changed_within"]["type"] == "string"

    def test_changed_before_property(self, tool):
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "changed_before" in properties
        assert properties["changed_before"]["type"] == "string"

    def test_full_path_match_property(self, tool):
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "full_path_match" in properties
        assert properties["full_path_match"]["type"] == "boolean"
        assert properties["full_path_match"]["default"] is False

    def test_absolute_property(self, tool):
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "absolute" in properties
        assert properties["absolute"]["type"] == "boolean"
        assert properties["absolute"]["default"] is True

    def test_limit_property(self, tool):
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "limit" in properties
        assert properties["limit"]["type"] == "integer"

    def test_count_only_property(self, tool):
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "count_only" in properties
        assert properties["count_only"]["type"] == "boolean"
        assert properties["count_only"]["default"] is False

    def test_output_file_property(self, tool):
        """F5: ``output_file`` is read by ``list_files_helpers`` and used
        to save the result to disk — it must be declared in the schema
        so strict-parameter validation accepts it."""
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "output_file" in properties

    def test_suppress_output_property(self, tool):
        """F5: ``suppress_output`` pairs with ``output_file`` to omit
        the detailed payload from the response. Now declared in schema
        for strict-parameter validation."""
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "suppress_output" in properties

    def test_output_format_property(self, tool):
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "output_format" in properties
        assert properties["output_format"]["type"] == "string"
        assert properties["output_format"]["enum"] == ["json", "toon"]
        assert properties["output_format"]["default"] == "toon"


class TestValidateRoots:
    def test_validate_roots_success(self, tool, sample_project_structure):
        roots = [str(sample_project_structure)]
        validated = tool._validate_roots(roots)
        assert len(validated) == 1
        assert Path(validated[0]).is_absolute()

    def test_validate_roots_multiple(self, tool, sample_project_structure):
        roots = [
            str(sample_project_structure),
            str(sample_project_structure / "src"),
        ]
        validated = tool._validate_roots(roots)
        assert len(validated) == 2

    def test_validate_roots_empty_list(self, tool):
        roots = []
        with pytest.raises(ValueError, match="roots must be a non-empty array"):
            tool._validate_roots(roots)

    def test_validate_roots_not_a_list(self, tool):
        roots = "not_a_list"
        with pytest.raises(ValueError, match="roots must be a non-empty array"):
            tool._validate_roots(roots)

    def test_validate_roots_empty_string(self, tool):
        roots = [""]
        with pytest.raises(ValueError, match="root entries must be non-empty strings"):
            tool._validate_roots(roots)

    def test_validate_roots_whitespace_string(self, tool):
        roots = ["   "]
        with pytest.raises(ValueError, match="root entries must be non-empty strings"):
            tool._validate_roots(roots)

    def test_validate_roots_invalid_directory(self, tool):
        roots = ["/nonexistent/directory"]
        with pytest.raises(ValueError, match="Invalid root"):
            tool._validate_roots(roots)


class TestValidateArguments:
    def test_validate_valid_arguments(self, tool):
        arguments = {
            "roots": ["."],
            "pattern": "*.py",
            "glob": True,
            "types": ["f"],
        }
        assert tool.validate_arguments(arguments) is True

    def test_validate_minimal_arguments(self, tool):
        arguments = {"roots": ["."]}
        assert tool.validate_arguments(arguments) is True

    def test_validate_missing_roots(self, tool):
        arguments = {"pattern": "*.py"}
        with pytest.raises(ValueError, match="roots is required"):
            tool.validate_arguments(arguments)

    def test_validate_roots_not_array(self, tool):
        arguments = {"roots": "."}
        with pytest.raises(ValueError, match="roots must be an array"):
            tool.validate_arguments(arguments)

    def test_validate_pattern_not_string(self, tool):
        arguments = {"roots": ["."], "pattern": 123}
        with pytest.raises(ValueError, match="pattern must be a string"):
            tool.validate_arguments(arguments)

    def test_validate_changed_within_not_string(self, tool):
        arguments = {"roots": ["."], "changed_within": 123}
        with pytest.raises(ValueError, match="changed_within must be a string"):
            tool.validate_arguments(arguments)

    def test_validate_changed_before_not_string(self, tool):
        arguments = {"roots": ["."], "changed_before": 123}
        with pytest.raises(ValueError, match="changed_before must be a string"):
            tool.validate_arguments(arguments)

    def test_validate_glob_not_boolean(self, tool):
        arguments = {"roots": ["."], "glob": "true"}
        with pytest.raises(ValueError, match="glob must be a boolean"):
            tool.validate_arguments(arguments)

    def test_validate_follow_symlinks_not_boolean(self, tool):
        arguments = {"roots": ["."], "follow_symlinks": "true"}
        with pytest.raises(ValueError, match="follow_symlinks must be a boolean"):
            tool.validate_arguments(arguments)

    def test_validate_hidden_not_boolean(self, tool):
        arguments = {"roots": ["."], "hidden": "true"}
        with pytest.raises(ValueError, match="hidden must be a boolean"):
            tool.validate_arguments(arguments)

    def test_validate_no_ignore_not_boolean(self, tool):
        arguments = {"roots": ["."], "no_ignore": "true"}
        with pytest.raises(ValueError, match="no_ignore must be a boolean"):
            tool.validate_arguments(arguments)

    def test_validate_full_path_match_not_boolean(self, tool):
        arguments = {"roots": ["."], "full_path_match": "true"}
        with pytest.raises(ValueError, match="full_path_match must be a boolean"):
            tool.validate_arguments(arguments)

    def test_validate_absolute_not_boolean(self, tool):
        arguments = {"roots": ["."], "absolute": "true"}
        with pytest.raises(ValueError, match="absolute must be a boolean"):
            tool.validate_arguments(arguments)

    def test_validate_depth_not_integer(self, tool):
        arguments = {"roots": ["."], "depth": "1"}
        with pytest.raises(ValueError, match="depth must be an integer"):
            tool.validate_arguments(arguments)

    def test_validate_limit_not_integer(self, tool):
        arguments = {"roots": ["."], "limit": "100"}
        with pytest.raises(ValueError, match="limit must be an integer"):
            tool.validate_arguments(arguments)

    def test_validate_types_not_array(self, tool):
        arguments = {"roots": ["."], "types": "f"}
        with pytest.raises(ValueError, match="types must be an array of strings"):
            tool.validate_arguments(arguments)

    def test_validate_extensions_not_array(self, tool):
        arguments = {"roots": ["."], "extensions": "py"}
        with pytest.raises(ValueError, match="extensions must be an array of strings"):
            tool.validate_arguments(arguments)

    def test_validate_exclude_not_array(self, tool):
        arguments = {"roots": ["."], "exclude": "*.pyc"}
        with pytest.raises(ValueError, match="exclude must be an array of strings"):
            tool.validate_arguments(arguments)

    def test_validate_size_not_array(self, tool):
        arguments = {"roots": ["."], "size": "+10M"}
        with pytest.raises(ValueError, match="size must be an array of strings"):
            tool.validate_arguments(arguments)


class TestAgentSummary:
    def test_agent_summary_for_empty_results(self):
        summary = _build_agent_summary(
            count=0,
            truncated=False,
            count_only=False,
            limit=100,
            no_ignore=False,
        )
        assert summary["risk"] == "low"
        assert summary["suggested_tool"] == "search_content"
        assert summary["next_step"].startswith("Broaden roots")

    def test_agent_summary_for_limit_hit(self):
        summary = _build_agent_summary(
            count=100,
            truncated=False,
            count_only=False,
            limit=100,
            no_ignore=True,
        )
        assert summary["risk"] == "high"
        assert summary["no_ignore"] is True
        assert summary["suggested_tool"] == "list_files"
        assert "Narrow list_files" in summary["next_step"]
