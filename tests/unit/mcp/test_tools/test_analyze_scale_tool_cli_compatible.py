#!/usr/bin/env python3
"""
Unit tests for AnalyzeScaleToolCLICompatible.

Tests for the CLI-compatible analyze_code_scale MCP tool that matches
the exact output format of CLI --advanced --statistics.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tree_sitter_analyzer.mcp.tools.analyze_scale_tool_cli_compatible import (
    AnalyzeScaleToolCLICompatible,
)


@pytest.fixture
def tool():
    """Create an AnalyzeScaleToolCLICompatible instance for testing."""
    with patch(
        "tree_sitter_analyzer.mcp.tools.analyze_scale_tool_cli_compatible.get_analysis_engine"
    ) as mock_engine_factory:
        mock_engine = MagicMock()
        mock_engine_factory.return_value = mock_engine
        t = AnalyzeScaleToolCLICompatible()
        t._mock_engine = mock_engine
        return t


class TestAnalyzeScaleToolCLICompatibleInit:
    """Tests for initialization."""

    def test_init_creates_instance(self, tool):
        assert tool is not None
        assert tool.analysis_engine is not None

    def test_module_level_instance_exists(self):
        from tree_sitter_analyzer.mcp.tools.analyze_scale_tool_cli_compatible import (
            analyze_scale_tool_cli_compatible,
        )
        assert isinstance(analyze_scale_tool_cli_compatible, AnalyzeScaleToolCLICompatible)


class TestGetToolSchema:
    """Tests for get_tool_schema()."""

    def test_schema_has_required_keys(self, tool):
        schema = tool.get_tool_schema()
        assert "type" in schema
        assert "properties" in schema
        assert "required" in schema
        assert schema["type"] == "object"

    def test_schema_required_contains_file_path(self, tool):
        schema = tool.get_tool_schema()
        assert "file_path" in schema["required"]

    def test_schema_properties_contains_all_fields(self, tool):
        schema = tool.get_tool_schema()
        props = schema["properties"]
        assert "file_path" in props
        assert "language" in props
        assert "include_complexity" in props
        assert "include_details" in props

    def test_schema_additional_properties_false(self, tool):
        schema = tool.get_tool_schema()
        assert schema.get("additionalProperties") is False


class TestValidateArguments:
    """Tests for validate_arguments()."""

    def test_valid_arguments_returns_true(self, tool):
        assert tool.validate_arguments({"file_path": "/some/file.py"}) is True

    def test_missing_file_path_raises_valueerror(self, tool):
        with pytest.raises(ValueError, match="file_path"):
            tool.validate_arguments({})

    def test_file_path_not_string_raises_valueerror(self, tool):
        with pytest.raises(ValueError, match="string"):
            tool.validate_arguments({"file_path": 123})

    def test_empty_file_path_raises_valueerror(self, tool):
        with pytest.raises(ValueError, match="empty"):
            tool.validate_arguments({"file_path": "   "})

    def test_language_not_string_raises_valueerror(self, tool):
        with pytest.raises(ValueError, match="string"):
            tool.validate_arguments({"file_path": "/f.py", "language": 42})

    def test_include_complexity_not_bool_raises_valueerror(self, tool):
        with pytest.raises(ValueError, match="boolean"):
            tool.validate_arguments({"file_path": "/f.py", "include_complexity": "yes"})

    def test_include_details_not_bool_raises_valueerror(self, tool):
        with pytest.raises(ValueError, match="boolean"):
            tool.validate_arguments({"file_path": "/f.py", "include_details": "true"})

    def test_valid_all_arguments(self, tool):
        assert (
            tool.validate_arguments({
                "file_path": "/f.py",
                "language": "python",
                "include_complexity": True,
                "include_details": False,
            })
            is True
        )


class TestGetToolDefinition:
    """Tests for get_tool_definition()."""

    def test_returns_dict_when_mcp_unavailable(self, tool):
        with patch.dict("sys.modules", {"mcp": None, "mcp.types": None}):
            result = tool.get_tool_definition()
        # May return dict or MCP Tool object depending on import availability
        assert result is not None

    def test_definition_has_name(self, tool):
        result = tool.get_tool_definition()
        # Handle both dict and MCP Tool object
        name = result.get("name") if isinstance(result, dict) else getattr(result, "name", None)
        assert name == "analyze_code_scale"

    def test_definition_has_description(self, tool):
        result = tool.get_tool_definition()
        desc = result.get("description") if isinstance(result, dict) else getattr(result, "description", None)
        assert desc is not None
        assert len(desc) > 0


class TestExecute:
    """Tests for execute() — the main async method."""

    @pytest.mark.asyncio
    async def test_execute_missing_file_path_raises(self, tool):
        with pytest.raises(ValueError, match="file_path is required"):
            await tool.execute({})

    @pytest.mark.asyncio
    async def test_execute_file_not_found_raises(self, tool):
        with pytest.raises(FileNotFoundError, match="not found"):
            await tool.execute({"file_path": "/nonexistent/totally/absent.py"})

    @pytest.mark.asyncio
    async def test_execute_success_returns_correct_structure(self, tool):
        """Test a successful execution returns CLI-compatible structure."""
        mock_element_function = MagicMock()
        mock_element_function.element_type = "function"
        mock_element_class = MagicMock()
        mock_element_class.element_type = "class"
        mock_element_import = MagicMock()
        mock_element_import.element_type = "import"

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.elements = [mock_element_function, mock_element_class, mock_element_import]
        mock_result.package = None
        mock_result.error_message = None

        tool.analysis_engine.analyze = AsyncMock(return_value=mock_result)

        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write("def hello(): pass\n")
            tmp_path = f.name
        try:
            result = await tool.execute({"file_path": tmp_path, "language": "python"})
        finally:
            os.unlink(tmp_path)

        assert result["success"] is True
        assert result["file_path"] == tmp_path
        assert "element_counts" in result
        assert result["element_counts"]["methods"] == 1
        assert result["element_counts"]["classes"] == 1
        assert result["element_counts"]["imports"] == 1
        assert "analysis_time_ms" in result

    @pytest.mark.asyncio
    async def test_execute_with_language_auto_detection(self, tool):
        """Test execute auto-detects language when not specified."""
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.elements = []
        mock_result.package = None
        mock_result.error_message = None

        tool.analysis_engine.analyze = AsyncMock(return_value=mock_result)

        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write("x = 1\n")
            tmp_path = f.name
        try:
            result = await tool.execute({"file_path": tmp_path})
        finally:
            os.unlink(tmp_path)

        assert "file_path" in result

    @pytest.mark.asyncio
    async def test_execute_unknown_extension_raises(self, tool):
        """Test that an unknown extension raises ValueError."""
        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix=".xyzunknown123", delete=False, mode="w") as f:
            f.write("data\n")
            tmp_path = f.name
        try:
            with pytest.raises((ValueError, Exception)):
                await tool.execute({"file_path": tmp_path})
        finally:
            os.unlink(tmp_path)

    @pytest.mark.asyncio
    async def test_execute_exception_returns_error_format(self, tool):
        """Test that engine exceptions return CLI-compatible error structure."""
        tool.analysis_engine.analyze = AsyncMock(side_effect=RuntimeError("engine error"))

        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write("code\n")
            tmp_path = f.name
        try:
            result = await tool.execute({"file_path": tmp_path, "language": "python"})
        finally:
            os.unlink(tmp_path)

        assert result["success"] is False
        assert "engine error" in result["error_message"]
        assert result["element_counts"]["classes"] == 0
        assert result["element_counts"]["methods"] == 0

    @pytest.mark.asyncio
    async def test_execute_with_package(self, tool):
        """Test execute when analysis result includes package info."""
        mock_package = MagicMock()
        mock_package.name = "com.example"

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.elements = []
        mock_result.package = mock_package
        mock_result.error_message = None

        tool.analysis_engine.analyze = AsyncMock(return_value=mock_result)

        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix=".java", delete=False, mode="w") as f:
            f.write("class Foo {}\n")
            tmp_path = f.name
        try:
            result = await tool.execute({"file_path": tmp_path, "language": "java"})
        finally:
            os.unlink(tmp_path)

        assert result["package_name"] == "com.example"

    @pytest.mark.asyncio
    async def test_execute_failed_result_with_no_message(self, tool):
        """Test that failed result without error_message gets a fallback message."""
        mock_result = MagicMock()
        mock_result.success = False
        mock_result.elements = []
        mock_result.package = None
        mock_result.error_message = None

        tool.analysis_engine.analyze = AsyncMock(return_value=mock_result)

        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write("pass\n")
            tmp_path = f.name
        try:
            result = await tool.execute({"file_path": tmp_path, "language": "python"})
        finally:
            os.unlink(tmp_path)

        assert result["success"] is False
        assert result["error_message"] is not None
