#!/usr/bin/env python3
"""SearchContentTool initialization, path, definition, and format determination tests."""


import pytest

from tree_sitter_analyzer.mcp.tools.search_content_tool import (
    SearchContentTool,
)


@pytest.fixture
def tool():
    return SearchContentTool()


class TestSearchContentToolInitialization:
    """Tests for tool initialization."""

    def test_init_creates_tool(self, tool):
        assert tool is not None
        assert hasattr(tool, "cache")
        assert hasattr(tool, "file_output_manager")

    def test_init_with_project_root(self):
        tool = SearchContentTool(project_root="/test/path")
        assert tool.project_root == "/test/path"

    def test_init_with_cache_disabled(self):
        tool = SearchContentTool(enable_cache=False)
        assert tool.cache is None

    def test_init_multiple_instances(self):
        tool1 = SearchContentTool()
        tool2 = SearchContentTool()
        assert tool1 is not tool2


class TestSetProjectPath:
    """Tests for set_project_path method."""

    def test_set_project_path_updates_all_components(self, tool):
        new_path = "/new/project/path"
        tool.set_project_path(new_path)
        assert tool.project_root == new_path

    def test_set_project_path_recreates_file_manager(self, tool):
        old_manager = tool.file_output_manager
        tool.set_project_path("/new/path")
        assert tool.file_output_manager is not old_manager


class TestGetToolDefinition:
    """Tests for get_tool_definition method."""

    def test_tool_definition_structure(self, tool):
        definition = tool.get_tool_definition()
        assert isinstance(definition, dict)
        assert "name" in definition
        assert "description" in definition
        assert "inputSchema" in definition

    def test_tool_definition_name(self, tool):
        definition = tool.get_tool_definition()
        assert definition["name"] == "search_content"

    def test_required_fields(self, tool):
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        required = schema.get("required", [])
        assert "query" in required
        assert len(required) == 1

    def test_roots_property(self, tool):
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "roots" in properties
        assert properties["roots"]["type"] == "array"

    def test_files_property(self, tool):
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "files" in properties
        assert properties["files"]["type"] == "array"

    def test_query_property(self, tool):
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "query" in properties
        assert properties["query"]["type"] == "string"

    def test_case_property(self, tool):
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "case" in properties
        assert properties["case"]["enum"] == ["smart", "insensitive", "sensitive"]
        assert properties["case"]["default"] == "smart"

    def test_total_only_property(self, tool):
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "total_only" in properties
        assert properties["total_only"]["type"] == "boolean"
        assert properties["total_only"]["default"] is False

    def test_count_only_matches_property(self, tool):
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "count_only_matches" in properties
        assert properties["count_only_matches"]["type"] == "boolean"
        assert properties["count_only_matches"]["default"] is False

    def test_summary_only_property(self, tool):
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "summary_only" in properties
        assert properties["summary_only"]["type"] == "boolean"
        assert properties["summary_only"]["default"] is False

    def test_group_by_file_property(self, tool):
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "group_by_file" in properties
        assert properties["group_by_file"]["type"] == "boolean"
        assert properties["group_by_file"]["default"] is False

    def test_optimize_paths_property(self, tool):
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "optimize_paths" in properties
        assert properties["optimize_paths"]["type"] == "boolean"
        assert properties["optimize_paths"]["default"] is False


class TestDetermineRequestedFormat:
    """Tests for _determine_requested_format method."""

    def test_determine_total_only_format(self, tool):
        arguments = {"total_only": True}
        format_type = tool._determine_requested_format(arguments)
        assert format_type == "total_only"

    def test_determine_count_only_format(self, tool):
        arguments = {"count_only_matches": True}
        format_type = tool._determine_requested_format(arguments)
        assert format_type == "count_only"

    def test_determine_summary_format(self, tool):
        arguments = {"summary_only": True}
        format_type = tool._determine_requested_format(arguments)
        assert format_type == "summary"

    def test_determine_group_by_file_format(self, tool):
        arguments = {"group_by_file": True}
        format_type = tool._determine_requested_format(arguments)
        assert format_type == "group_by_file"

    def test_determine_normal_format(self, tool):
        arguments = {}
        format_type = tool._determine_requested_format(arguments)
        assert format_type == "normal"
