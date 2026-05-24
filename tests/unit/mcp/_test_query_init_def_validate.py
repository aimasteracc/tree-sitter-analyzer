"""Mixins for query tool: init, set_path, definition, and validate tests."""


import pytest

from tree_sitter_analyzer.mcp.tools.query_tool import QueryTool


class TestQueryToolInitializationTestMixin:
    """Tests for tool initialization."""

    def test_init_creates_tool(self, tool):
        assert tool is not None
        assert hasattr(tool, "query_service")
        assert hasattr(tool, "file_output_manager")

    def test_init_with_project_root(self):
        tool = QueryTool(project_root="/test/path")
        assert tool.project_root == "/test/path"

    def test_init_multiple_instances(self):
        tool1 = QueryTool()
        tool2 = QueryTool()
        assert tool1 is not tool2


class TestSetProjectPathTestMixin:
    """Tests for set_project_path method."""

    def test_set_project_path_updates_all_components(self, tool):
        new_path = "/new/project/path"
        tool.set_project_path(new_path)
        assert tool.project_root == new_path
        assert tool.query_service.project_root == new_path

    def test_set_project_path_recreates_services(self, tool):
        old_service = tool.query_service
        tool.set_project_path("/new/path")
        assert tool.query_service is not old_service


class TestGetToolDefinitionTestMixin:
    """Tests for get_tool_definition method."""

    def test_tool_definition_structure(self, tool):
        definition = tool.get_tool_definition()
        assert isinstance(definition, dict)
        assert "name" in definition
        assert "description" in definition
        assert "inputSchema" in definition

    def test_tool_definition_name(self, tool):
        definition = tool.get_tool_definition()
        assert definition["name"] == "query_code"

    def test_tool_definition_description(self, tool):
        definition = tool.get_tool_definition()
        assert definition["description"] is not None
        assert isinstance(definition["description"], str)

    def test_input_schema_structure(self, tool):
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        assert schema["type"] == "object"
        assert "properties" in schema
        assert "file_path" in schema["properties"]
        assert "symbol" in schema["properties"]

    def test_required_fields(self, tool):
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "file_path" in properties
        assert "symbol" in properties

    def test_file_path_property(self, tool):
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "file_path" in properties
        assert properties["file_path"]["type"] == "string"

    def test_language_property(self, tool):
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "language" in properties
        assert properties["language"]["type"] == "string"

    def test_query_key_property(self, tool):
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "query_key" in properties
        assert properties["query_key"]["type"] == "string"

    def test_query_string_property(self, tool):
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "query_string" in properties
        assert properties["query_string"]["type"] == "string"

    def test_filter_property(self, tool):
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "filter" in properties
        assert properties["filter"]["type"] == "string"

    def test_result_format_property(self, tool):
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "result_format" in properties
        assert properties["result_format"]["type"] == "string"
        assert properties["result_format"]["enum"] == ["json", "summary"]
        assert properties["result_format"]["default"] == "json"

    def test_output_format_property(self, tool):
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "output_format" in properties
        assert properties["output_format"]["type"] == "string"
        assert properties["output_format"]["enum"] == ["json", "toon"]
        assert properties["output_format"]["default"] == "toon"

    def test_output_file_property(self, tool):
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "output_file" in properties
        assert properties["output_file"]["type"] == "string"
        assert "save output to file" in properties["output_file"]["description"]

    def test_suppress_output_property(self, tool):
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]
        properties = schema.get("properties", {})
        assert "suppress_output" in properties
        assert properties["suppress_output"]["type"] == "boolean"
        assert properties["suppress_output"]["default"] is False
        assert (
            "suppress detailed output" in properties["suppress_output"]["description"]
        )


class TestValidateArgumentsTestMixin:
    """Tests for validate_arguments method."""

    def test_validate_valid_arguments_with_query_key(self, tool):
        arguments = {
            "file_path": "test.py",
            "query_key": "methods",
        }
        assert tool.validate_arguments(arguments) is True

    def test_validate_valid_arguments_with_query_string(self, tool):
        arguments = {
            "file_path": "test.py",
            "query_string": "(function_definition) @func",
        }
        assert tool.validate_arguments(arguments) is True

    def test_validate_missing_file_path(self, tool):
        arguments = {"query_key": "methods"}
        with pytest.raises(ValueError, match="file_path or symbol is required"):
            tool.validate_arguments(arguments)

    def test_validate_empty_file_path(self, tool):
        arguments = {"file_path": "", "query_key": "methods"}
        with pytest.raises(ValueError, match="file_path cannot be empty"):
            tool.validate_arguments(arguments)

    def test_validate_whitespace_file_path(self, tool):
        arguments = {"file_path": "   ", "query_key": "methods"}
        with pytest.raises(ValueError, match="file_path cannot be empty"):
            tool.validate_arguments(arguments)

    def test_validate_invalid_file_path_type(self, tool):
        arguments = {"file_path": 123, "query_key": "methods"}
        with pytest.raises(ValueError, match="file_path must be a string"):
            tool.validate_arguments(arguments)

    def test_validate_missing_both_query_params(self, tool):
        arguments = {"file_path": "test.py"}
        with pytest.raises(
            ValueError, match="Either query_key or query_string must be provided"
        ):
            tool.validate_arguments(arguments)

    def test_validate_invalid_query_key_type(self, tool):
        arguments = {"file_path": "test.py", "query_key": 123}
        with pytest.raises(ValueError, match="query_key must be a string"):
            tool.validate_arguments(arguments)

    def test_validate_invalid_query_string_type(self, tool):
        arguments = {"file_path": "test.py", "query_string": 123}
        with pytest.raises(ValueError, match="query_string must be a string"):
            tool.validate_arguments(arguments)

    def test_validate_invalid_language_type(self, tool):
        arguments = {
            "file_path": "test.py",
            "query_key": "methods",
            "language": 123,
        }
        with pytest.raises(ValueError, match="language must be a string"):
            tool.validate_arguments(arguments)

    def test_validate_invalid_filter_type(self, tool):
        arguments = {
            "file_path": "test.py",
            "query_key": "methods",
            "filter": 123,
        }
        with pytest.raises(ValueError, match="filter must be a string"):
            tool.validate_arguments(arguments)

    def test_validate_invalid_result_format_type(self, tool):
        arguments = {
            "file_path": "test.py",
            "query_key": "methods",
            "result_format": 123,
        }
        with pytest.raises(ValueError, match="result_format must be a string"):
            tool.validate_arguments(arguments)

    def test_validate_invalid_result_format_value(self, tool):
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
        arguments = {
            "file_path": "test.py",
            "query_key": "methods",
            "output_format": 123,
        }
        with pytest.raises(ValueError, match="output_format must be a string"):
            tool.validate_arguments(arguments)

    def test_validate_invalid_output_format_value(self, tool):
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
        arguments = {
            "file_path": "test.py",
            "query_key": "methods",
            "output_file": 123,
        }
        with pytest.raises(ValueError, match="output_file must be a string"):
            tool.validate_arguments(arguments)

    def test_validate_empty_output_file(self, tool):
        arguments = {
            "file_path": "test.py",
            "query_key": "methods",
            "output_file": "",
        }
        with pytest.raises(ValueError, match="output_file cannot be empty"):
            tool.validate_arguments(arguments)

    def test_validate_invalid_suppress_output_type(self, tool):
        arguments = {
            "file_path": "test.py",
            "query_key": "methods",
            "suppress_output": "true",
        }
        with pytest.raises(ValueError, match="suppress_output must be a boolean"):
            tool.validate_arguments(arguments)

    def test_validate_all_optional_fields_valid(self, tool):
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
        arguments = {
            "file_path": "test.py",
            "query_key": "methods",
            "suppress_output": False,
        }
        assert tool.validate_arguments(arguments) is True


class TestValidateArgumentsAdditionalTestMixin:
    """Additional tests targeting uncovered validation branches."""

    def test_validate_query_key_empty_string(self, tool):
        arguments = {"file_path": "test.py", "query_key": ""}
        with pytest.raises(
            ValueError, match="Either query_key or query_string must be provided"
        ):
            tool.validate_arguments(arguments)

    def test_validate_query_string_empty_string(self, tool):
        arguments = {"file_path": "test.py", "query_string": ""}
        with pytest.raises(
            ValueError, match="Either query_key or query_string must be provided"
        ):
            tool.validate_arguments(arguments)

    def test_validate_output_file_whitespace_only(self, tool):
        arguments = {
            "file_path": "test.py",
            "query_key": "methods",
            "output_file": "   ",
        }
        with pytest.raises(ValueError, match="output_file cannot be empty"):
            tool.validate_arguments(arguments)

    def test_validate_result_format_summary_valid(self, tool):
        arguments = {
            "file_path": "test.py",
            "query_key": "methods",
            "result_format": "summary",
        }
        assert tool.validate_arguments(arguments) is True

    def test_validate_output_format_toon_valid(self, tool):
        arguments = {
            "file_path": "test.py",
            "query_key": "methods",
            "output_format": "toon",
        }
        assert tool.validate_arguments(arguments) is True


class TestValidateArgumentsCoverageBoostTestMixin:
    """Tests targeting uncovered validate_arguments branches."""

    def test_validate_no_file_path_key(self, tool):
        with pytest.raises(ValueError, match="file_path or symbol is required"):
            tool.validate_arguments({"query_key": "methods"})

    def test_validate_file_path_not_string(self, tool):
        with pytest.raises(ValueError, match="file_path must be a string"):
            tool.validate_arguments({"file_path": 123, "query_key": "methods"})

    def test_validate_file_path_empty(self, tool):
        with pytest.raises(ValueError, match="file_path cannot be empty"):
            tool.validate_arguments({"file_path": "   ", "query_key": "methods"})

    def test_validate_query_key_not_string(self, tool):
        with pytest.raises(ValueError, match="query_key must be a string"):
            tool.validate_arguments({"file_path": "t.py", "query_key": 123})

    def test_validate_query_string_not_string(self, tool):
        with pytest.raises(ValueError, match="query_string must be a string"):
            tool.validate_arguments({"file_path": "t.py", "query_string": 123})

    def test_validate_language_not_string(self, tool):
        with pytest.raises(ValueError, match="language must be a string"):
            tool.validate_arguments(
                {"file_path": "t.py", "query_key": "m", "language": 42}
            )

    def test_validate_filter_not_string(self, tool):
        with pytest.raises(ValueError, match="filter must be a string"):
            tool.validate_arguments(
                {"file_path": "t.py", "query_key": "m", "filter": 42}
            )

    def test_validate_result_format_invalid_value(self, tool):
        with pytest.raises(ValueError, match="result_format must be one of"):
            tool.validate_arguments(
                {"file_path": "t.py", "query_key": "m", "result_format": "xml"}
            )

    def test_validate_result_format_not_string(self, tool):
        with pytest.raises(ValueError, match="result_format must be a string"):
            tool.validate_arguments(
                {"file_path": "t.py", "query_key": "m", "result_format": 123}
            )

    def test_validate_output_format_invalid_value(self, tool):
        with pytest.raises(ValueError, match="output_format must be one of"):
            tool.validate_arguments(
                {"file_path": "t.py", "query_key": "m", "output_format": "xml"}
            )

    def test_validate_output_format_not_string(self, tool):
        with pytest.raises(ValueError, match="output_format must be a string"):
            tool.validate_arguments(
                {"file_path": "t.py", "query_key": "m", "output_format": 123}
            )

    def test_validate_output_file_not_string(self, tool):
        with pytest.raises(ValueError, match="output_file must be a string"):
            tool.validate_arguments(
                {"file_path": "t.py", "query_key": "m", "output_file": 123}
            )

    def test_validate_suppress_output_not_bool(self, tool):
        with pytest.raises(ValueError, match="suppress_output must be a boolean"):
            tool.validate_arguments(
                {"file_path": "t.py", "query_key": "m", "suppress_output": "yes"}
            )

    def test_validate_all_valid_fields(self, tool):
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
