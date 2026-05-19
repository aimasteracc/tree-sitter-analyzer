"""
Unit tests for AnalyzeScaleTool.

Tests for analyze_code_scale tool which provides code scale analysis
including metrics about complexity, size, and structure.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.unit.mcp.test_tools._test_analyze_scale_tool_execute_mixins import (
    AnalyzeScaleToolExecuteBatchAdvancedMixin,
    AnalyzeScaleToolExecuteJavaMixin,
)
from tree_sitter_analyzer.mcp.tools.analyze_scale_tool import AnalyzeScaleTool


@pytest.fixture
def tool():
    """Create an AnalyzeScaleTool instance for testing."""
    return AnalyzeScaleTool()


@pytest.fixture
def tool_with_project_root():
    """Create an AnalyzeScaleTool instance with a project root."""
    return AnalyzeScaleTool(project_root="/test/project")


class TestAnalyzeScaleToolCountElements:
    """Tests for _count_elements static method."""

    def test_count_elements_java_style(self, tool):
        """Test counting Java-style elements."""
        from tree_sitter_analyzer.constants import ELEMENT_TYPE_CLASS

        mock_elem = MagicMock()
        mock_elem.element_type = "class"
        mock_elem.name = "TestClass"
        count = tool._count_elements([mock_elem], ELEMENT_TYPE_CLASS, "class")
        assert count == 1

    def test_count_elements_universal_style(self, tool):
        """Test counting universal-style elements."""
        from tree_sitter_analyzer.constants import ELEMENT_TYPE_CLASS

        mock_elem = MagicMock(spec=[])
        mock_elem.element_type = "class"
        count = tool._count_elements([mock_elem], ELEMENT_TYPE_CLASS, "class")
        assert count >= 1

    def test_count_elements_no_match(self, tool):
        """Test counting with no matching elements."""
        from tree_sitter_analyzer.constants import ELEMENT_TYPE_CLASS

        mock_elem = MagicMock()
        mock_elem.element_type = "function"
        count = tool._count_elements([mock_elem], ELEMENT_TYPE_CLASS, "class")
        assert count == 0

    def test_count_elements_empty_list(self, tool):
        """Test counting with empty list."""
        from tree_sitter_analyzer.constants import ELEMENT_TYPE_CLASS

        count = tool._count_elements([], ELEMENT_TYPE_CLASS, "class")
        assert count == 0


class TestAnalyzeScaleToolGenerateLLMGuidanceAdvanced:
    """Tests for _generate_llm_guidance advanced branches."""

    def test_generate_guidance_recommended_tools_for_large_file(self, tool):
        """Test recommended tools include extract_code_section for large files."""
        file_metrics = {"total_lines": 250, "language": "python"}
        structural_overview = {
            "classes": [],
            "methods": [],
            "fields": [],
            "imports": [],
            "complexity_hotspots": [],
        }
        guidance = tool._generate_llm_guidance(file_metrics, structural_overview)
        assert "extract_code_section" in guidance["recommended_tools"]
        assert "query_code" in guidance["recommended_tools"]

    def test_generate_guidance_language_queries_java(self, tool):
        """Test language-specific queries for Java."""
        file_metrics = {"total_lines": 100, "language": "java"}
        structural_overview = {
            "classes": [],
            "methods": [],
            "fields": [],
            "imports": [],
            "complexity_hotspots": [],
        }
        guidance = tool._generate_llm_guidance(file_metrics, structural_overview)
        assert "methods" in guidance["suggested_queries"]

    def test_generate_guidance_language_queries_python(self, tool):
        """Test language-specific queries for Python."""
        file_metrics = {"total_lines": 100, "language": "python"}
        structural_overview = {
            "classes": [],
            "methods": [],
            "fields": [],
            "imports": [],
            "complexity_hotspots": [],
        }
        guidance = tool._generate_llm_guidance(file_metrics, structural_overview)
        assert "functions" in guidance["suggested_queries"]

    def test_generate_guidance_language_queries_javascript(self, tool):
        """Test language-specific queries for JavaScript."""
        file_metrics = {"total_lines": 100, "language": "javascript"}
        structural_overview = {
            "classes": [],
            "methods": [],
            "fields": [],
            "imports": [],
            "complexity_hotspots": [],
        }
        guidance = tool._generate_llm_guidance(file_metrics, structural_overview)
        assert "react_component" in guidance["suggested_queries"]

    def test_generate_guidance_language_queries_typescript(self, tool):
        """Test language-specific queries for TypeScript."""
        file_metrics = {"total_lines": 100, "language": "typescript"}
        structural_overview = {
            "classes": [],
            "methods": [],
            "fields": [],
            "imports": [],
            "complexity_hotspots": [],
        }
        guidance = tool._generate_llm_guidance(file_metrics, structural_overview)
        assert "interfaces" in guidance["suggested_queries"]

    def test_generate_guidance_language_queries_go(self, tool):
        """Test language-specific queries for Go."""
        file_metrics = {"total_lines": 100, "language": "go"}
        structural_overview = {
            "classes": [],
            "methods": [],
            "fields": [],
            "imports": [],
            "complexity_hotspots": [],
        }
        guidance = tool._generate_llm_guidance(file_metrics, structural_overview)
        assert "struct" in guidance["suggested_queries"]

    def test_generate_guidance_language_queries_rust(self, tool):
        """Test language-specific queries for Rust."""
        file_metrics = {"total_lines": 100, "language": "rust"}
        structural_overview = {
            "classes": [],
            "methods": [],
            "fields": [],
            "imports": [],
            "complexity_hotspots": [],
        }
        guidance = tool._generate_llm_guidance(file_metrics, structural_overview)
        assert "trait" in guidance["suggested_queries"]

    def test_generate_guidance_language_queries_c(self, tool):
        """Test language-specific queries for C."""
        file_metrics = {"total_lines": 100, "language": "c"}
        structural_overview = {
            "classes": [],
            "methods": [],
            "fields": [],
            "imports": [],
            "complexity_hotspots": [],
        }
        guidance = tool._generate_llm_guidance(file_metrics, structural_overview)
        assert "function" in guidance["suggested_queries"]

    def test_generate_guidance_language_queries_cpp(self, tool):
        """Test language-specific queries for C++."""
        file_metrics = {"total_lines": 100, "language": "cpp"}
        structural_overview = {
            "classes": [],
            "methods": [],
            "fields": [],
            "imports": [],
            "complexity_hotspots": [],
        }
        guidance = tool._generate_llm_guidance(file_metrics, structural_overview)
        assert "namespace" in guidance["suggested_queries"]

    def test_generate_guidance_language_queries_kotlin(self, tool):
        """Test language-specific queries for Kotlin."""
        file_metrics = {"total_lines": 100, "language": "kotlin"}
        structural_overview = {
            "classes": [],
            "methods": [],
            "fields": [],
            "imports": [],
            "complexity_hotspots": [],
        }
        guidance = tool._generate_llm_guidance(file_metrics, structural_overview)
        assert "data_class" in guidance["suggested_queries"]

    def test_generate_guidance_language_queries_ruby(self, tool):
        """Test language-specific queries for Ruby."""
        file_metrics = {"total_lines": 100, "language": "ruby"}
        structural_overview = {
            "classes": [],
            "methods": [],
            "fields": [],
            "imports": [],
            "complexity_hotspots": [],
        }
        guidance = tool._generate_llm_guidance(file_metrics, structural_overview)
        assert "methods" in guidance["suggested_queries"]

    def test_generate_guidance_language_queries_unknown(self, tool):
        """Test no queries for unknown language."""
        file_metrics = {"total_lines": 100, "language": "cobol"}
        structural_overview = {
            "classes": [],
            "methods": [],
            "fields": [],
            "imports": [],
            "complexity_hotspots": [],
        }
        guidance = tool._generate_llm_guidance(file_metrics, structural_overview)
        assert guidance["suggested_queries"] == []

    def test_generate_guidance_workflow_small_file(self, tool):
        """Test workflow steps for small file."""
        file_metrics = {"total_lines": 50, "language": "python"}
        structural_overview = {
            "classes": [],
            "methods": [],
            "fields": [],
            "imports": [],
            "complexity_hotspots": [],
        }
        guidance = tool._generate_llm_guidance(file_metrics, structural_overview)
        assert (
            "analyze_code_structure for full structure table"
            in guidance["workflow_steps"]
        )

    def test_generate_guidance_workflow_very_large_file(self, tool):
        """Test workflow steps for very large file."""
        file_metrics = {"total_lines": 2000, "language": "python"}
        structural_overview = {
            "classes": [],
            "methods": [],
            "fields": [],
            "imports": [],
            "complexity_hotspots": [],
        }
        guidance = tool._generate_llm_guidance(file_metrics, structural_overview)
        assert (
            "extract_code_section for targeted line ranges"
            in guidance["workflow_steps"]
        )

    def test_generate_guidance_missing_structural_fields(self, tool):
        """Test guidance adds missing structural overview fields."""
        file_metrics = {"total_lines": 100, "language": "python"}
        structural_overview = {}
        tool._generate_llm_guidance(file_metrics, structural_overview)
        assert structural_overview["complexity_hotspots"] == []
        assert structural_overview["classes"] == []


class TestAnalyzeScaleToolExecuteJava(AnalyzeScaleToolExecuteJavaMixin):
    """Tests for execute method with Java language path."""

    __test__ = True


class TestAnalyzeScaleToolExecuteBatchAdvanced(
    AnalyzeScaleToolExecuteBatchAdvancedMixin
):
    """Advanced tests for _execute_metrics_batch method."""

    __test__ = True


class TestAnalyzeScaleToolCreateJsonFileAnalysisAdvanced:
    """Advanced tests for _create_json_file_analysis method."""

    def test_create_json_file_analysis_without_toon_mock(self, tool):
        """Test JSON file analysis returns actual structure without mock."""
        file_metrics = {
            "total_lines": 50,
            "code_lines": 50,
            "comment_lines": 0,
            "blank_lines": 5,
            "estimated_tokens": 200,
            "file_size_bytes": 1000,
        }
        result = tool._create_json_file_analysis(
            "/test.json", file_metrics, True, "json"
        )
        assert result["success"] is True
        assert result["language"] == "json"
        assert result["total_lines"] == 50
        assert result["non_empty_lines"] == 45
        assert result["scale_category"] == "small"
        assert "llm_analysis_guidance" in result

    def test_create_json_file_analysis_medium_without_mock(self, tool):
        """Test JSON file analysis for medium file without mock."""
        file_metrics = {
            "total_lines": 500,
            "code_lines": 500,
            "comment_lines": 0,
            "blank_lines": 10,
            "estimated_tokens": 2000,
            "file_size_bytes": 10000,
        }
        result = tool._create_json_file_analysis(
            "/test.json", file_metrics, False, "json"
        )
        assert result["scale_category"] == "medium"
        assert "llm_analysis_guidance" not in result

    def test_create_json_file_analysis_large_without_mock(self, tool):
        """Test JSON file analysis for large file without mock."""
        file_metrics = {
            "total_lines": 1500,
            "code_lines": 1500,
            "comment_lines": 0,
            "blank_lines": 20,
            "estimated_tokens": 6000,
            "file_size_bytes": 30000,
        }
        result = tool._create_json_file_analysis(
            "/test.json", file_metrics, True, "json"
        )
        assert result["scale_category"] == "large"
        assert result["analysis_recommendations"]["suitable_for_full_analysis"] is False


class TestAnalyzeScaleToolValidateArgumentsAdvanced:
    """Additional validation tests for edge cases."""

    def test_validate_arguments_minimal_single(self, tool):
        """Test validation with minimal valid arguments."""
        assert tool.validate_arguments({"file_path": "test.py"}) is True

    def test_validate_arguments_whitespace_file_path(self, tool):
        """Test validation fails for whitespace-only file_path."""
        with pytest.raises(ValueError, match="file_path cannot be empty"):
            tool.validate_arguments({"file_path": "   "})

    def test_validate_arguments_valid_batch_with_all_fields(self, tool):
        """Test valid batch mode with all optional fields."""
        arguments = {
            "file_paths": ["a.py", "b.py"],
            "metrics_only": True,
            "output_format": "json",
        }
        assert tool.validate_arguments(arguments) is True


class TestCountElementsUniversalBranch:
    """Tests targeting the universal elif branch in _count_elements (line 279)."""

    def test_count_elements_matches_via_getattr_not_is_element_of_type(self, tool):
        from tree_sitter_analyzer.constants import ELEMENT_TYPE_FUNCTION

        class FakeElement:
            element_type = "function"

        elem = FakeElement()
        count = tool._count_elements([elem], ELEMENT_TYPE_FUNCTION, "function")
        assert count == 1


class TestGenerateLLMGuidanceQueryLoader:
    """Tests targeting query_loader integration in _generate_llm_guidance (lines 424-431)."""

    def test_guidance_includes_available_queries_from_loader(self, tool):
        file_metrics = {"total_lines": 100, "language": "python"}
        structural_overview = {
            "complexity_hotspots": [],
            "classes": [],
            "methods": [],
            "fields": [],
            "imports": [],
        }
        with patch(
            "tree_sitter_analyzer.query_loader.get_query_loader"
        ) as mock_get_loader:
            mock_loader = MagicMock()
            mock_loader.list_queries_for_language.return_value = [
                "classes",
                "methods",
                "decorator",
            ]
            mock_get_loader.return_value = mock_loader
            guidance = tool._generate_llm_guidance(file_metrics, structural_overview)
            assert guidance["available_queries"] == ["classes", "decorator", "methods"]

    def test_guidance_no_queries_from_loader(self, tool):
        file_metrics = {"total_lines": 100, "language": "brainfuck"}
        structural_overview = {
            "complexity_hotspots": [],
            "classes": [],
            "methods": [],
            "fields": [],
            "imports": [],
        }
        with patch(
            "tree_sitter_analyzer.query_loader.get_query_loader"
        ) as mock_get_loader:
            mock_loader = MagicMock()
            mock_loader.list_queries_for_language.return_value = []
            mock_get_loader.return_value = mock_loader
            guidance = tool._generate_llm_guidance(file_metrics, structural_overview)
            assert "available_queries" not in guidance


class TestExecuteLanguageSanitization:
    """Tests targeting language sanitization path in execute (line 521)."""

    @pytest.mark.asyncio
    async def test_execute_with_language_sanitization(self, tool):
        mock_analysis_result = MagicMock()
        mock_analysis_result.elements = []
        mock_analysis_result.package = None
        mock_analysis_result.success = True
        mock_analysis_result.get_statistics = MagicMock(return_value={})

        with (
            patch.object(
                tool, "resolve_and_validate_file_path", return_value="/test.py"
            ),
            patch("pathlib.Path.exists", return_value=True),
            patch.object(
                tool,
                "_calculate_file_metrics",
                return_value={
                    "total_lines": 50,
                    "code_lines": 40,
                    "comment_lines": 5,
                    "blank_lines": 5,
                    "estimated_tokens": 200,
                    "file_size_bytes": 1024,
                },
            ),
            patch.object(
                tool.analysis_engine,
                "analyze",
                new_callable=AsyncMock,
                return_value=mock_analysis_result,
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.analyze_scale_tool.apply_toon_format_to_response",
                side_effect=lambda r, f: r,
            ),
        ):
            arguments = {"file_path": "test.py", "language": "python"}
            result = await tool.execute(arguments)
            assert result["success"] is True
            assert result["language"] == "python"

    @pytest.mark.asyncio
    async def test_execute_batch_mode_via_execute(self, tool):
        arguments = {"file_paths": ["a.py"], "metrics_only": True}
        with patch.object(
            tool, "_execute_metrics_batch", new_callable=AsyncMock
        ) as mock_batch:
            mock_batch.return_value = {"success": True}
            result = await tool.execute(arguments)
            assert result["success"] is True
            mock_batch.assert_called_once_with(arguments)

    @pytest.mark.asyncio
    async def test_execute_exception_reraise(self, tool):
        with (
            patch.object(
                tool, "resolve_and_validate_file_path", return_value="/test.py"
            ),
            patch("pathlib.Path.exists", return_value=True),
            patch.object(
                tool,
                "_calculate_file_metrics",
                return_value={
                    "total_lines": 50,
                    "code_lines": 40,
                    "comment_lines": 5,
                    "blank_lines": 5,
                    "estimated_tokens": 200,
                    "file_size_bytes": 1024,
                },
            ),
            patch.object(
                tool.analysis_engine,
                "analyze",
                new_callable=AsyncMock,
                side_effect=RuntimeError("engine crashed"),
            ),
        ):
            arguments = {"file_path": "test.py", "language": "python"}
            with pytest.raises(RuntimeError, match="engine crashed"):
                await tool.execute(arguments)


class TestExecuteMetricsBatchFullBody:
    """Tests targeting _execute_metrics_batch body (lines 765-830)."""

    @pytest.mark.asyncio
    async def test_batch_with_resolved_file_not_found(self, tool):
        with (
            patch.object(
                tool, "resolve_and_validate_file_path", return_value="/test.py"
            ),
            patch("pathlib.Path.exists", return_value=False),
            patch(
                "tree_sitter_analyzer.mcp.tools.analyze_scale_tool.apply_toon_format_to_response",
                side_effect=lambda r, f: r,
            ),
        ):
            arguments = {"file_paths": ["missing.py"], "metrics_only": True}
            result = await tool._execute_metrics_batch(arguments)
            assert result["count_errors"] == 1

    @pytest.mark.asyncio
    async def test_batch_with_non_string_path_entry(self, tool):
        with patch(
            "tree_sitter_analyzer.mcp.utils.format_helper.apply_toon_format_to_response",
            side_effect=lambda r, f: r,
        ):
            arguments = {"file_paths": [None], "metrics_only": True}
            result = await tool._execute_metrics_batch(arguments)
            assert result["count_errors"] >= 1

    @pytest.mark.asyncio
    async def test_batch_with_resolved_path_exists(self, tool):
        with (
            patch.object(
                tool, "resolve_and_validate_file_path", return_value="/test.py"
            ),
            patch("pathlib.Path.exists", return_value=True),
            patch(
                "tree_sitter_analyzer.mcp.tools.analyze_scale_tool.detect_language_from_file",
                return_value="python",
            ),
            patch.object(
                tool,
                "_calculate_file_metrics",
                return_value={
                    "total_lines": 100,
                    "code_lines": 80,
                    "comment_lines": 15,
                    "blank_lines": 5,
                    "estimated_tokens": 400,
                    "file_size_bytes": 2048,
                },
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.analyze_scale_tool.apply_toon_format_to_response",
                side_effect=lambda r, f: r,
            ),
        ):
            arguments = {"file_paths": ["test.py"], "metrics_only": True}
            result = await tool._execute_metrics_batch(arguments)
            assert result["count_ok"] == 1
            assert result["results"][0]["language"] == "python"


class TestCreateJsonFileAnalysisGuidance:
    """Tests targeting _create_json_file_analysis guidance and toon paths."""

    def test_json_file_with_guidance_toon_format(self, tool):
        file_metrics = {
            "total_lines": 100,
            "code_lines": 100,
            "comment_lines": 0,
            "blank_lines": 10,
            "estimated_tokens": 400,
            "file_size_bytes": 2000,
        }
        result = tool._create_json_file_analysis(
            "/test.json", file_metrics, True, "json"
        )
        assert result["success"] is True
        assert "llm_analysis_guidance" in result

    def test_json_file_without_guidance(self, tool):
        file_metrics = {
            "total_lines": 100,
            "code_lines": 100,
            "comment_lines": 0,
            "blank_lines": 5,
            "estimated_tokens": 400,
            "file_size_bytes": 2000,
        }
        result = tool._create_json_file_analysis(
            "/test.json", file_metrics, False, "json"
        )
        assert result["success"] is True
        assert "llm_analysis_guidance" not in result


class TestModuleLevelInstance:
    """Test that module-level instance exists."""

    def test_module_level_instance(self):
        from tree_sitter_analyzer.mcp.tools.analyze_scale_tool import (
            analyze_scale_tool,
        )

        assert analyze_scale_tool is not None
        assert isinstance(analyze_scale_tool, AnalyzeScaleTool)


class TestCoverageBoost:
    """Tests targeting the last uncovered lines."""

    def test_count_elements_universal_string_fallback(self, tool):
        """Test _count_elements falls back to string match when is_element_of_type fails."""
        from tree_sitter_analyzer.constants import ELEMENT_TYPE_CLASS

        class _FakeElem:
            pass

        elem = _FakeElem()
        elem.element_type = "class"
        count = tool._count_elements([elem], ELEMENT_TYPE_CLASS, "class")
        assert count == 1

    @pytest.mark.asyncio
    async def test_execute_dispatches_to_batch(self, tool):
        """Test execute() dispatches to _execute_metrics_batch when file_paths given."""
        with patch.object(
            tool,
            "_execute_metrics_batch",
            new_callable=AsyncMock,
            return_value={"success": True, "count_files": 1},
        ):
            result = await tool.execute(
                {"file_paths": ["test.py"], "metrics_only": True}
            )
            assert result["success"] is True

    @pytest.mark.asyncio
    async def test_execute_non_java_none_universal_result(self, tool):
        """Test execute handles None result from universal engine (non-Java)."""
        with (
            patch.object(
                tool, "resolve_and_validate_file_path", return_value="/test.py"
            ),
            patch("pathlib.Path.exists", return_value=True),
            patch(
                "tree_sitter_analyzer.mcp.tools.analyze_scale_tool.detect_language_from_file",
                return_value="python",
            ),
            patch.object(
                tool,
                "_calculate_file_metrics",
                return_value={
                    "total_lines": 100,
                    "code_lines": 80,
                    "comment_lines": 15,
                    "blank_lines": 5,
                    "estimated_tokens": 400,
                    "file_size_bytes": 2048,
                },
            ),
            patch.object(
                tool.analysis_engine,
                "analyze",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            arguments = {"file_path": "test.py"}
            with pytest.raises(RuntimeError, match="Failed to analyze file"):
                await tool.execute(arguments)

    @pytest.mark.asyncio
    async def test_execute_non_java_falsy_result_with_no_error_msg(self, tool):
        """Test execute handles universal result with success=False and no error_message."""
        mock_result = MagicMock()
        mock_result.success = False
        mock_result.error_message = None
        with (
            patch.object(
                tool, "resolve_and_validate_file_path", return_value="/test.py"
            ),
            patch("pathlib.Path.exists", return_value=True),
            patch(
                "tree_sitter_analyzer.mcp.tools.analyze_scale_tool.detect_language_from_file",
                return_value="python",
            ),
            patch.object(
                tool,
                "_calculate_file_metrics",
                return_value={
                    "total_lines": 100,
                    "code_lines": 80,
                    "comment_lines": 15,
                    "blank_lines": 5,
                    "estimated_tokens": 400,
                    "file_size_bytes": 2048,
                },
            ),
            patch.object(
                tool.analysis_engine,
                "analyze",
                new_callable=AsyncMock,
                return_value=mock_result,
            ),
        ):
            arguments = {"file_path": "test.py"}
            with pytest.raises(RuntimeError, match="Failed to analyze file"):
                await tool.execute(arguments)

    @pytest.mark.asyncio
    async def test_execute_non_java_falsy_result_with_error_msg(self, tool):
        """Test execute handles universal result with success=False and error_message."""
        mock_result = MagicMock()
        mock_result.success = False
        mock_result.error_message = "Parse error in file"
        with (
            patch.object(
                tool, "resolve_and_validate_file_path", return_value="/test.py"
            ),
            patch("pathlib.Path.exists", return_value=True),
            patch(
                "tree_sitter_analyzer.mcp.tools.analyze_scale_tool.detect_language_from_file",
                return_value="python",
            ),
            patch.object(
                tool,
                "_calculate_file_metrics",
                return_value={
                    "total_lines": 100,
                    "code_lines": 80,
                    "comment_lines": 15,
                    "blank_lines": 5,
                    "estimated_tokens": 400,
                    "file_size_bytes": 2048,
                },
            ),
            patch.object(
                tool.analysis_engine,
                "analyze",
                new_callable=AsyncMock,
                return_value=mock_result,
            ),
        ):
            arguments = {"file_path": "test.py"}
            with pytest.raises(
                RuntimeError, match="Failed to analyze file with universal engine"
            ):
                await tool.execute(arguments)
