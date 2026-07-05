from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tree_sitter_analyzer.mcp.tools.analyze_scale_tool_cli_compatible import (
    AnalyzeScaleToolCLICompatible,
)


@pytest.fixture
def tool():
    with patch(
        "tree_sitter_analyzer.mcp.tools.analyze_scale_tool_cli_compatible.get_analysis_engine"
    ):
        return AnalyzeScaleToolCLICompatible()


class TestInit:
    def test_initializes(self, tool):
        assert isinstance(tool, AnalyzeScaleToolCLICompatible)
        assert tool.analysis_engine is not None  # mocked by fixture


class TestGetToolSchema:
    def test_schema_structure(self, tool):
        schema = tool.get_tool_schema()
        assert schema["type"] == "object"
        assert "file_path" in schema["properties"]
        assert "required" in schema
        assert "file_path" in schema["required"]

    def test_schema_optional_fields(self, tool):
        schema = tool.get_tool_schema()
        assert "language" in schema["properties"]
        assert "include_complexity" in schema["properties"]
        assert "include_details" in schema["properties"]

    def test_schema_no_additional_properties(self, tool):
        schema = tool.get_tool_schema()
        assert schema["additionalProperties"] is False


class TestGetToolDefinition:
    def test_returns_definition_with_mcp(self, tool):
        defn = tool.get_tool_definition()
        assert defn.name == "analyze_code_scale"
        assert defn.description is not None
        assert defn.inputSchema is not None

    def test_returns_definition_as_dict_without_mcp(self, tool):
        with patch.dict("sys.modules", {"mcp": None, "mcp.types": None}):
            defn = tool.get_tool_definition()
            assert defn["name"] == "analyze_code_scale"
            assert "inputSchema" in defn


class TestValidateArguments:
    def test_valid_arguments(self, tool):
        assert tool.validate_arguments({"file_path": "test.py"}) is True

    def test_valid_with_all_fields(self, tool):
        args = {
            "file_path": "test.py",
            "language": "python",
            "include_complexity": True,
            "include_details": False,
        }
        assert tool.validate_arguments(args) is True

    def test_missing_required_field(self, tool):
        with pytest.raises(ValueError, match="Required field 'file_path' is missing"):
            tool.validate_arguments({})

    def test_file_path_not_string(self, tool):
        with pytest.raises(ValueError, match="file_path must be a string"):
            tool.validate_arguments({"file_path": 123})

    def test_file_path_empty(self, tool):
        with pytest.raises(ValueError, match="file_path cannot be empty"):
            tool.validate_arguments({"file_path": "  "})

    def test_language_not_string(self, tool):
        with pytest.raises(ValueError, match="language must be a string"):
            tool.validate_arguments({"file_path": "test.py", "language": 42})

    def test_include_complexity_not_bool(self, tool):
        with pytest.raises(ValueError, match="include_complexity must be a boolean"):
            tool.validate_arguments(
                {"file_path": "test.py", "include_complexity": "yes"}
            )

    def test_include_details_not_bool(self, tool):
        with pytest.raises(ValueError, match="include_details must be a boolean"):
            tool.validate_arguments({"file_path": "test.py", "include_details": 1})


class TestExecute:
    @pytest.mark.asyncio
    async def test_missing_file_path(self, tool):
        with pytest.raises(ValueError, match="file_path is required"):
            await tool.execute({})

    @pytest.mark.asyncio
    async def test_file_not_found(self, tool):
        with patch("pathlib.Path.exists", return_value=False):
            with pytest.raises(FileNotFoundError, match="File not found"):
                await tool.execute({"file_path": "/nonexistent.py"})

    @pytest.mark.asyncio
    async def test_unknown_language(self, tool):
        with (
            patch("pathlib.Path.exists", return_value=True),
            patch(
                "tree_sitter_analyzer.mcp.tools.analyze_scale_tool_cli_compatible.detect_language_from_file",
                return_value="unknown",
            ),
        ):
            with pytest.raises(ValueError, match="Could not detect language"):
                await tool.execute({"file_path": "/test.xyz"})

    @pytest.mark.asyncio
    async def test_success_with_elements(self, tool):
        elem1 = MagicMock()
        elem1.element_type = "class"
        elem2 = MagicMock()
        elem2.element_type = "function"
        elem3 = MagicMock()
        elem3.element_type = "import"
        elem4 = MagicMock()
        elem4.element_type = "variable"
        elem5 = MagicMock()
        elem5.element_type = "annotation"

        mock_pkg = MagicMock()
        mock_pkg.name = "com.example"

        mock_result = MagicMock()
        mock_result.elements = [elem1, elem2, elem3, elem4, elem5]
        mock_result.package = mock_pkg
        mock_result.success = True
        mock_result.error_message = None

        with (
            patch("pathlib.Path.exists", return_value=True),
            patch(
                "tree_sitter_analyzer.mcp.tools.analyze_scale_tool_cli_compatible.detect_language_from_file",
                return_value="python",
            ),
            patch(
                "tree_sitter_analyzer.core.analysis_engine.AnalysisRequest"
            ) as MockReq,
            patch.object(
                tool.analysis_engine,
                "analyze",
                new_callable=AsyncMock,
                return_value=mock_result,
            ),
        ):
            MockReq.return_value = MagicMock()
            result = await tool.execute({"file_path": "/test.py"})

        assert result["success"] is True
        assert result["file_path"] == "/test.py"
        assert result["package_name"] == "com.example"
        assert result["element_counts"]["classes"] == 1
        assert result["element_counts"]["imports"] == 1
        assert result["element_counts"]["methods"] == 1
        assert result["element_counts"]["fields"] == 1
        assert result["element_counts"]["annotations"] == 1
        assert result["analysis_time_ms"] >= 0  # ratchet: nondeterministic timing value

    @pytest.mark.asyncio
    async def test_success_no_package(self, tool):
        mock_result = MagicMock()
        mock_result.elements = []
        mock_result.package = None
        mock_result.success = True
        mock_result.error_message = None

        with (
            patch("pathlib.Path.exists", return_value=True),
            patch(
                "tree_sitter_analyzer.mcp.tools.analyze_scale_tool_cli_compatible.detect_language_from_file",
                return_value="python",
            ),
            patch(
                "tree_sitter_analyzer.core.analysis_engine.AnalysisRequest"
            ) as MockReq,
            patch.object(
                tool.analysis_engine,
                "analyze",
                new_callable=AsyncMock,
                return_value=mock_result,
            ),
        ):
            MockReq.return_value = MagicMock()
            result = await tool.execute({"file_path": "/test.py"})

        assert result["success"] is True
        assert result["package_name"] is None
        assert result["element_counts"]["classes"] == 0

    @pytest.mark.asyncio
    async def test_analysis_failure_with_error_message(self, tool):
        mock_result = MagicMock()
        mock_result.elements = []
        mock_result.package = None
        mock_result.success = False
        mock_result.error_message = "parse error"

        with (
            patch("pathlib.Path.exists", return_value=True),
            patch(
                "tree_sitter_analyzer.mcp.tools.analyze_scale_tool_cli_compatible.detect_language_from_file",
                return_value="python",
            ),
            patch(
                "tree_sitter_analyzer.core.analysis_engine.AnalysisRequest"
            ) as MockReq,
            patch.object(
                tool.analysis_engine,
                "analyze",
                new_callable=AsyncMock,
                return_value=mock_result,
            ),
        ):
            MockReq.return_value = MagicMock()
            result = await tool.execute({"file_path": "/test.py"})

        assert result["success"] is False
        assert result["error_message"] == "parse error"

    @pytest.mark.asyncio
    async def test_analysis_failure_without_error_message(self, tool):
        mock_result = MagicMock()
        mock_result.elements = []
        mock_result.package = None
        mock_result.success = False
        mock_result.error_message = None

        with (
            patch("pathlib.Path.exists", return_value=True),
            patch(
                "tree_sitter_analyzer.mcp.tools.analyze_scale_tool_cli_compatible.detect_language_from_file",
                return_value="python",
            ),
            patch(
                "tree_sitter_analyzer.core.analysis_engine.AnalysisRequest"
            ) as MockReq,
            patch.object(
                tool.analysis_engine,
                "analyze",
                new_callable=AsyncMock,
                return_value=mock_result,
            ),
        ):
            MockReq.return_value = MagicMock()
            result = await tool.execute({"file_path": "/test.py"})

        assert result["success"] is False
        assert "Failed to analyze file" in result["error_message"]

    @pytest.mark.asyncio
    async def test_exception_returns_error_format(self, tool):
        with (
            patch("pathlib.Path.exists", return_value=True),
            patch(
                "tree_sitter_analyzer.mcp.tools.analyze_scale_tool_cli_compatible.detect_language_from_file",
                return_value="python",
            ),
            patch(
                "tree_sitter_analyzer.core.analysis_engine.AnalysisRequest"
            ) as MockReq,
            patch.object(
                tool.analysis_engine,
                "analyze",
                new_callable=AsyncMock,
                side_effect=RuntimeError("boom"),
            ),
        ):
            MockReq.return_value = MagicMock()
            result = await tool.execute({"file_path": "/test.py"})

        assert result["success"] is False
        assert result["error_message"] == "boom"
        assert result["element_counts"]["classes"] == 0
        assert result["analysis_time_ms"] == 0.0

    @pytest.mark.asyncio
    async def test_explicit_language(self, tool):
        mock_result = MagicMock()
        mock_result.elements = []
        mock_result.package = None
        mock_result.success = True
        mock_result.error_message = None

        with (
            patch("pathlib.Path.exists", return_value=True),
            patch(
                "tree_sitter_analyzer.core.analysis_engine.AnalysisRequest"
            ) as MockReq,
            patch.object(
                tool.analysis_engine,
                "analyze",
                new_callable=AsyncMock,
                return_value=mock_result,
            ),
        ):
            MockReq.return_value = MagicMock()
            result = await tool.execute({"file_path": "/test.py", "language": "java"})

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_method_count_includes_method_type(self, tool):
        func_elem = MagicMock()
        func_elem.element_type = "function"
        method_elem = MagicMock()
        method_elem.element_type = "method"

        mock_result = MagicMock()
        mock_result.elements = [func_elem, method_elem]
        mock_result.package = None
        mock_result.success = True
        mock_result.error_message = None

        with (
            patch("pathlib.Path.exists", return_value=True),
            patch(
                "tree_sitter_analyzer.mcp.tools.analyze_scale_tool_cli_compatible.detect_language_from_file",
                return_value="python",
            ),
            patch(
                "tree_sitter_analyzer.core.analysis_engine.AnalysisRequest"
            ) as MockReq,
            patch.object(
                tool.analysis_engine,
                "analyze",
                new_callable=AsyncMock,
                return_value=mock_result,
            ),
        ):
            MockReq.return_value = MagicMock()
            result = await tool.execute({"file_path": "/test.py"})

        assert result["element_counts"]["methods"] == 2
