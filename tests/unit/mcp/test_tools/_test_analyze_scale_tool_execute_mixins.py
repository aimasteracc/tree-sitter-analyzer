"""Private mixins for analyze_scale_tool execute-related tests.

The split keeps `test_analyze_scale_tool.py` small while preserving node IDs for
test collection and review parity.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class AnalyzeScaleToolExecuteMixin:
    """Tests for execute method (single mode)."""

    @pytest.mark.asyncio
    async def test_execute_missing_file_path(self, tool):
        """Test execute fails when file_path is missing."""
        arguments = {"language": "python"}
        with pytest.raises(ValueError, match="file_path is required"):
            await tool.execute(arguments)

    @pytest.mark.asyncio
    async def test_execute_file_not_found(self, tool):
        """Test execute fails when file doesn't exist."""
        with (
            patch.object(
                tool, "resolve_and_validate_file_path", return_value="/nonexistent.py"
            ),
            patch("pathlib.Path.exists", return_value=False),
        ):
            arguments = {"file_path": "test.py"}
            with pytest.raises(ValueError, match="Invalid file path: File not found"):
                await tool.execute(arguments)

    @pytest.mark.asyncio
    async def test_execute_unsupported_language(self, tool):
        """Test execute fails when language is not supported."""
        with (
            patch.object(
                tool, "resolve_and_validate_file_path", return_value="/test.unknown"
            ),
            patch("pathlib.Path.exists", return_value=True),
            patch(
                "tree_sitter_analyzer.mcp.tools.analyze_scale_tool.detect_language_from_file",
                return_value="unknown",
            ),
        ):
            arguments = {"file_path": "test.unknown"}
            with pytest.raises(ValueError, match="Unsupported language"):
                await tool.execute(arguments)

    @pytest.mark.asyncio
    async def test_execute_json_file(self, tool):
        """Test execute handles JSON files specially."""
        with (
            patch.object(
                tool, "resolve_and_validate_file_path", return_value="/test.json"
            ),
            patch("pathlib.Path.exists", return_value=True),
            patch.object(
                tool,
                "_calculate_file_metrics",
                return_value={
                    "total_lines": 10,
                    "code_lines": 10,
                    "comment_lines": 0,
                    "blank_lines": 0,
                    "estimated_tokens": 40,
                    "file_size_bytes": 100,
                },
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.analyze_scale_tool.apply_toon_format_to_response",
                return_value={"formatted": True},
            ),
            patch(
                "tree_sitter_analyzer.mcp.utils.format_helper.apply_toon_format_to_response",
                return_value={"formatted": True},
            ),
        ):
            arguments = {"file_path": "test.json", "include_guidance": True}
            result = await tool.execute(arguments)
            assert "formatted" in result

    @pytest.mark.asyncio
    async def test_execute_success_python(self, tool):
        """Test execute succeeds for Python file."""
        mock_analysis_result = MagicMock()
        mock_analysis_result.elements = []
        mock_package = MagicMock()
        mock_package.name = "test_package"
        mock_analysis_result.package = mock_package
        mock_analysis_result.success = True
        mock_analysis_result.get_statistics = MagicMock(return_value={})

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
                return_value=mock_analysis_result,
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.analyze_scale_tool.apply_toon_format_to_response",
                return_value={"formatted": True},
            ),
        ):
            arguments = {"file_path": "test.py", "include_guidance": True}
            result = await tool.execute(arguments)
            assert "formatted" in result

    @pytest.mark.asyncio
    async def test_execute_with_include_details(self, tool):
        """Test execute with include_details=True."""
        mock_analysis_result = MagicMock()
        mock_analysis_result.elements = []
        mock_package = MagicMock()
        mock_package.name = "test_package"
        mock_analysis_result.package = mock_package
        mock_analysis_result.success = True
        mock_analysis_result.get_statistics = MagicMock(return_value={})

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
                return_value=mock_analysis_result,
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.analyze_scale_tool.apply_toon_format_to_response",
                return_value={"formatted": True},
            ),
        ):
            arguments = {"file_path": "test.py", "include_details": True}
            result = await tool.execute(arguments)
            assert "formatted" in result

    @pytest.mark.asyncio
    async def test_execute_without_include_guidance(self, tool):
        """Test execute with include_guidance=False."""
        mock_analysis_result = MagicMock()
        mock_analysis_result.elements = []
        mock_package = MagicMock()
        mock_package.name = "test_package"
        mock_analysis_result.package = mock_package
        mock_analysis_result.success = True
        mock_analysis_result.get_statistics = MagicMock(return_value={})

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
                return_value=mock_analysis_result,
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.analyze_scale_tool.apply_toon_format_to_response",
                return_value={"formatted": True},
            ),
        ):
            arguments = {"file_path": "test.py", "include_guidance": False}
            result = await tool.execute(arguments)
            assert "formatted" in result

    @pytest.mark.asyncio
    async def test_execute_with_json_output_format(self, tool):
        """Test execute with output_format='json'."""
        mock_analysis_result = MagicMock()
        mock_analysis_result.elements = []
        mock_package = MagicMock()
        mock_package.name = "test_package"
        mock_analysis_result.package = mock_package
        mock_analysis_result.success = True
        mock_analysis_result.get_statistics = MagicMock(return_value={})

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
                return_value=mock_analysis_result,
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.analyze_scale_tool.apply_toon_format_to_response",
                return_value={"formatted": True},
            ),
        ):
            arguments = {"file_path": "test.py", "output_format": "json"}
            result = await tool.execute(arguments)
            assert "formatted" in result

    @pytest.mark.asyncio
    async def test_execute_analysis_failure(self, tool):
        """Test execute handles analysis engine failure."""
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


class AnalyzeScaleToolExecuteMetricsBatchMixin:
    """Tests for _execute_metrics_batch method."""

    @pytest.mark.asyncio
    async def test_execute_batch_missing_metrics_only(self, tool):
        """Test batch mode fails when metrics_only is False."""
        arguments = {"file_paths": ["test1.py", "test2.py"], "metrics_only": False}
        with pytest.raises(ValueError, match="metrics_only must be true"):
            await tool._execute_metrics_batch(arguments)

    @pytest.mark.asyncio
    async def test_execute_batch_empty_file_paths(self, tool):
        """Test batch mode fails when file_paths is empty."""
        arguments = {"file_paths": [], "metrics_only": True}
        with pytest.raises(ValueError, match="file_paths must be a non-empty list"):
            await tool._execute_metrics_batch(arguments)

    @pytest.mark.asyncio
    async def test_execute_batch_invalid_file_paths_type(self, tool):
        """Test batch mode fails when file_paths is not a list."""
        arguments = {"file_paths": "test.py", "metrics_only": True}
        with pytest.raises(ValueError, match="file_paths must be a non-empty list"):
            await tool._execute_metrics_batch(arguments)

    @pytest.mark.asyncio
    async def test_execute_batch_too_many_files(self, tool):
        """Test batch mode fails when too many files."""
        arguments = {
            "file_paths": [f"test{i}.py" for i in range(201)],
            "metrics_only": True,
        }
        with pytest.raises(ValueError, match="Too many files"):
            await tool._execute_metrics_batch(arguments)

    @pytest.mark.asyncio
    async def test_execute_batch_success(self, tool):
        """Test batch mode succeeds."""
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
                return_value={"formatted": True},
            ),
        ):
            arguments = {"file_paths": ["test1.py", "test2.py"], "metrics_only": True}
            result = await tool._execute_metrics_batch(arguments)
            assert "formatted" in result

    @pytest.mark.asyncio
    async def test_execute_batch_with_errors(self, tool):
        """Test batch mode handles errors gracefully."""
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
                return_value={"formatted": True},
            ),
        ):
            arguments = {"file_paths": ["test.py", ""], "metrics_only": True}
            result = await tool._execute_metrics_batch(arguments)
            assert "formatted" in result

    @pytest.mark.asyncio
    async def test_execute_batch_file_not_found(self, tool):
        """Test batch mode handles file not found."""
        with (
            patch.object(
                tool, "resolve_and_validate_file_path", return_value="/test.py"
            ),
            patch("pathlib.Path.exists", return_value=False),
            patch(
                "tree_sitter_analyzer.mcp.tools.analyze_scale_tool.apply_toon_format_to_response",
                return_value={"formatted": True},
            ),
        ):
            arguments = {"file_paths": ["test.py"], "metrics_only": True}
            result = await tool._execute_metrics_batch(arguments)
            assert "formatted" in result


class AnalyzeScaleToolCreateJsonFileAnalysisMixin:
    """Tests for _create_json_file_analysis method."""

    def test_create_json_file_analysis_small(self, tool):
        """Test JSON file analysis for small file."""
        file_metrics = {
            "total_lines": 50,
            "code_lines": 50,
            "comment_lines": 0,
            "blank_lines": 0,
            "estimated_tokens": 200,
            "file_size_bytes": 1000,
        }
        with patch(
            "tree_sitter_analyzer.mcp.utils.format_helper.apply_toon_format_to_response",
            return_value={"formatted": True},
        ):
            result = tool._create_json_file_analysis(
                "/test.json", file_metrics, True, "toon"
            )
            assert "formatted" in result

    def test_create_json_file_analysis_medium(self, tool):
        """Test JSON file analysis for medium file."""
        file_metrics = {
            "total_lines": 500,
            "code_lines": 500,
            "comment_lines": 0,
            "blank_lines": 0,
            "estimated_tokens": 2000,
            "file_size_bytes": 10000,
        }
        with patch(
            "tree_sitter_analyzer.mcp.utils.format_helper.apply_toon_format_to_response",
            return_value={"formatted": True},
        ):
            result = tool._create_json_file_analysis(
                "/test.json", file_metrics, True, "toon"
            )
            assert "formatted" in result

    def test_create_json_file_analysis_large(self, tool):
        """Test JSON file analysis for large file."""
        file_metrics = {
            "total_lines": 1500,
            "code_lines": 1500,
            "comment_lines": 0,
            "blank_lines": 0,
            "estimated_tokens": 6000,
            "file_size_bytes": 30000,
        }
        with patch(
            "tree_sitter_analyzer.mcp.utils.format_helper.apply_toon_format_to_response",
            return_value={"formatted": True},
        ):
            result = tool._create_json_file_analysis(
                "/test.json", file_metrics, True, "toon"
            )
            assert "formatted" in result

    def test_create_json_file_analysis_without_guidance(self, tool):
        """Test JSON file analysis without guidance."""
        file_metrics = {
            "total_lines": 100,
            "code_lines": 100,
            "comment_lines": 0,
            "blank_lines": 0,
            "estimated_tokens": 400,
            "file_size_bytes": 2000,
        }
        with patch(
            "tree_sitter_analyzer.mcp.utils.format_helper.apply_toon_format_to_response",
            return_value={"formatted": True},
        ):
            result = tool._create_json_file_analysis(
                "/test.json", file_metrics, False, "toon"
            )
            assert "formatted" in result

    def test_create_json_file_analysis_json_format(self, tool):
        """Test JSON file analysis with JSON output format."""
        file_metrics = {
            "total_lines": 100,
            "code_lines": 100,
            "comment_lines": 0,
            "blank_lines": 0,
            "estimated_tokens": 400,
            "file_size_bytes": 2000,
        }
        with patch(
            "tree_sitter_analyzer.mcp.utils.format_helper.apply_toon_format_to_response",
            return_value={"formatted": True},
        ):
            result = tool._create_json_file_analysis(
                "/test.json", file_metrics, True, "json"
            )
            assert "formatted" in result


class AnalyzeScaleToolExecuteJavaMixin:
    """Tests for execute method with Java language path."""

    @pytest.mark.asyncio
    async def test_execute_java_success(self, tool):
        """Test execute succeeds for Java file."""
        mock_class = MagicMock()
        mock_class.name = "TestClass"
        mock_class.element_type = "class"
        mock_class.start_line = 1
        mock_class.end_line = 10
        mock_class.visibility = "public"
        mock_class.extends_class = None
        mock_class.implements_interfaces = []
        mock_class.annotations = []

        mock_method = MagicMock()
        mock_method.name = "doStuff"
        mock_method.element_type = "function"
        mock_method.start_line = 3
        mock_method.end_line = 8
        mock_method.visibility = "public"
        mock_method.return_type = "void"
        mock_method.parameters = []
        mock_method.complexity_score = 3
        mock_method.is_constructor = False
        mock_method.is_static = False
        mock_method.annotations = []

        mock_field = MagicMock()
        mock_field.name = "count"
        mock_field.element_type = "variable"
        mock_field.start_line = 2
        mock_field.end_line = 2
        mock_field.visibility = "private"
        mock_field.field_type = "int"
        mock_field.is_static = False
        mock_field.is_final = False
        mock_field.annotations = []

        mock_import = MagicMock()
        mock_import.element_type = "import"
        mock_import.imported_name = "java.util.List"
        mock_import.import_statement = "import java.util.List"
        mock_import.line_number = 1
        mock_import.is_static = False
        mock_import.is_wildcard = False

        mock_analysis_result = MagicMock()
        mock_analysis_result.elements = [
            mock_class,
            mock_method,
            mock_field,
            mock_import,
        ]
        mock_analysis_result.package = None
        mock_analysis_result.annotations = []
        mock_analysis_result.get_statistics = MagicMock(return_value={"total": 4})

        with (
            patch.object(
                tool, "resolve_and_validate_file_path", return_value="/Test.java"
            ),
            patch("pathlib.Path.exists", return_value=True),
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
                return_value=mock_analysis_result,
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.analyze_scale_tool.apply_toon_format_to_response",
                side_effect=lambda r, f: r,
            ),
        ):
            arguments = {
                "file_path": "Test.java",
                "language": "java",
                "include_details": True,
                "include_guidance": True,
            }
            result = await tool.execute(arguments)
            assert result["success"] is True
            assert result["language"] == "java"
            assert len(result["structural_overview"]["classes"]) == 1
            assert len(result["structural_overview"]["methods"]) == 1
            assert len(result["structural_overview"]["fields"]) == 1
            assert len(result["structural_overview"]["imports"]) == 1
            assert "detailed_analysis" in result
            assert "llm_guidance" in result

    @pytest.mark.asyncio
    async def test_execute_java_analysis_none(self, tool):
        """Test execute handles None result from Java analysis."""
        with (
            patch.object(
                tool, "resolve_and_validate_file_path", return_value="/Test.java"
            ),
            patch("pathlib.Path.exists", return_value=True),
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
            arguments = {"file_path": "Test.java", "language": "java"}
            with pytest.raises(RuntimeError, match="Failed to analyze file"):
                await tool.execute(arguments)

    @pytest.mark.asyncio
    async def test_execute_non_java_universal_failure(self, tool):
        """Test execute handles universal engine failure."""
        mock_result = MagicMock()
        mock_result.success = False
        mock_result.error_message = "Parse error"
        with (
            patch.object(
                tool, "resolve_and_validate_file_path", return_value="/test.py"
            ),
            patch("pathlib.Path.exists", return_value=True),
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


class AnalyzeScaleToolExecuteBatchAdvancedMixin:
    """Advanced tests for _execute_metrics_batch method."""

    @pytest.mark.asyncio
    async def test_execute_batch_with_invalid_path_entries(self, tool):
        """Test batch mode with invalid file path strings."""
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
            arguments = {"file_paths": [123], "metrics_only": True}
            result = await tool._execute_metrics_batch(arguments)
            assert result["count_errors"]

    @pytest.mark.asyncio
    async def test_execute_batch_with_resolve_error(self, tool):
        """Test batch mode handles resolve error."""
        with (
            patch.object(
                tool,
                "resolve_and_validate_file_path",
                side_effect=ValueError("Path traversal detected"),
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.analyze_scale_tool.apply_toon_format_to_response",
                side_effect=lambda r, f: r,
            ),
        ):
            arguments = {"file_paths": ["../etc/passwd"], "metrics_only": True}
            result = await tool._execute_metrics_batch(arguments)
            assert result["count_errors"] == 1
            assert result["count_ok"] == 0

    @pytest.mark.asyncio
    async def test_execute_batch_unknown_language(self, tool):
        """Test batch mode handles unknown language detection."""
        with (
            patch.object(
                tool, "resolve_and_validate_file_path", return_value="/test.xyz"
            ),
            patch("pathlib.Path.exists", return_value=True),
            patch(
                "tree_sitter_analyzer.mcp.tools.analyze_scale_tool.detect_language_from_file",
                return_value="unknown",
            ),
            patch.object(
                tool,
                "_calculate_file_metrics",
                return_value={
                    "total_lines": 50,
                    "code_lines": 50,
                    "comment_lines": 0,
                    "blank_lines": 0,
                    "estimated_tokens": 200,
                    "file_size_bytes": 1024,
                },
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.analyze_scale_tool.apply_toon_format_to_response",
                side_effect=lambda r, f: r,
            ),
        ):
            arguments = {"file_paths": ["test.xyz"], "metrics_only": True}
            result = await tool._execute_metrics_batch(arguments)
            assert result["count_ok"] == 1

    @pytest.mark.asyncio
    async def test_execute_batch_all_errors(self, tool):
        """Test batch mode where all files fail."""
        with (
            patch.object(
                tool,
                "resolve_and_validate_file_path",
                side_effect=ValueError("Invalid"),
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.analyze_scale_tool.apply_toon_format_to_response",
                side_effect=lambda r, f: r,
            ),
        ):
            arguments = {"file_paths": ["a.py", "b.py"], "metrics_only": True}
            result = await tool._execute_metrics_batch(arguments)
            assert result["success"] is False
            assert result["count_errors"] == 2
