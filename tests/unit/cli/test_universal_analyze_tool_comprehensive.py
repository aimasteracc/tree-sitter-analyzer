#!/usr/bin/env python3
"""
Comprehensive tests for UniversalAnalyzeTool

This test module provides comprehensive coverage for the UniversalAnalyzeTool class,
including initialization, argument validation, execution, and edge cases.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tree_sitter_analyzer.mcp.tools.universal_analyze_tool import UniversalAnalyzeTool
from tree_sitter_analyzer.mcp.utils.error_handler import AnalysisError


class TestUniversalAnalyzeToolInitialization:
    """Test UniversalAnalyzeTool initialization"""

    def test_init_without_project_root(self):
        """Test initialization without project root"""
        tool = UniversalAnalyzeTool()
        assert tool.analysis_engine is not None
        assert tool.path_resolver is not None
        assert tool.security_validator is not None

    def test_init_with_project_root(self, tmp_path):
        """Test initialization with project root"""
        tool = UniversalAnalyzeTool(str(tmp_path))
        assert tool.analysis_engine is not None
        assert tool.project_root == str(tmp_path)

    def test_set_project_path(self, tmp_path):
        """Test setting project path"""
        tool = UniversalAnalyzeTool()
        new_path = str(tmp_path / "project")
        tool.set_project_path(new_path)
        assert tool.project_root == new_path


class TestToolDefinition:
    """Test tool definition and schema"""

    def test_get_tool_definition_structure(self):
        """Test tool definition has correct structure"""
        tool = UniversalAnalyzeTool()
        definition = tool.get_tool_definition()

        assert "name" in definition
        assert "description" in definition
        assert "inputSchema" in definition
        assert definition["name"] == "analyze_code_universal"

    def test_tool_definition_schema(self):
        """Test input schema structure"""
        tool = UniversalAnalyzeTool()
        definition = tool.get_tool_definition()
        schema = definition["inputSchema"]

        assert schema["type"] == "object"
        assert "file_path" in schema["required"]
        assert "file_path" in schema["properties"]
        assert "language" in schema["properties"]
        assert "analysis_type" in schema["properties"]
        assert "include_ast" in schema["properties"]
        assert "include_queries" in schema["properties"]

    def test_analysis_type_enum(self):
        """Test analysis_type has correct enum values"""
        tool = UniversalAnalyzeTool()
        definition = tool.get_tool_definition()
        analysis_type_prop = definition["inputSchema"]["properties"]["analysis_type"]

        assert "enum" in analysis_type_prop
        assert set(analysis_type_prop["enum"]) == {
            "basic",
            "detailed",
            "structure",
            "metrics",
        }


class TestArgumentValidation:
    """Test argument validation"""

    def test_validate_arguments_valid_minimal(self):
        """Test validation with minimal valid arguments"""
        tool = UniversalAnalyzeTool()
        args = {"file_path": "test.py"}
        assert tool.validate_arguments(args) is True

    def test_validate_arguments_valid_complete(self):
        """Test validation with all arguments"""
        tool = UniversalAnalyzeTool()
        args = {
            "file_path": "test.py",
            "language": "python",
            "analysis_type": "detailed",
            "include_ast": True,
            "include_queries": True,
        }
        assert tool.validate_arguments(args) is True

    def test_validate_arguments_missing_file_path(self):
        """Test validation fails without file_path"""
        tool = UniversalAnalyzeTool()
        args = {"language": "python"}

        with pytest.raises(ValueError, match="file_path.*missing"):
            tool.validate_arguments(args)

    def test_validate_arguments_invalid_file_path_type(self):
        """Test validation fails with non-string file_path"""
        tool = UniversalAnalyzeTool()
        args = {"file_path": 123}

        with pytest.raises(ValueError, match="file_path must be a string"):
            tool.validate_arguments(args)

    def test_validate_arguments_empty_file_path(self):
        """Test validation fails with empty file_path"""
        tool = UniversalAnalyzeTool()
        args = {"file_path": "   "}

        with pytest.raises(ValueError, match="file_path cannot be empty"):
            tool.validate_arguments(args)

    def test_validate_arguments_invalid_language_type(self):
        """Test validation fails with non-string language"""
        tool = UniversalAnalyzeTool()
        args = {"file_path": "test.py", "language": 123}

        with pytest.raises(ValueError, match="language must be a string"):
            tool.validate_arguments(args)

    def test_validate_arguments_invalid_analysis_type(self):
        """Test validation fails with invalid analysis_type"""
        tool = UniversalAnalyzeTool()
        args = {"file_path": "test.py", "analysis_type": "invalid"}

        with pytest.raises(ValueError, match="analysis_type must be one of"):
            tool.validate_arguments(args)

    def test_validate_arguments_invalid_include_ast_type(self):
        """Test validation fails with non-boolean include_ast"""
        tool = UniversalAnalyzeTool()
        args = {"file_path": "test.py", "include_ast": "true"}

        with pytest.raises(ValueError, match="include_ast must be a boolean"):
            tool.validate_arguments(args)

    def test_validate_arguments_invalid_include_queries_type(self):
        """Test validation fails with non-boolean include_queries"""
        tool = UniversalAnalyzeTool()
        args = {"file_path": "test.py", "include_queries": "true"}

        with pytest.raises(ValueError, match="include_queries must be a boolean"):
            tool.validate_arguments(args)


class TestExecution:
    """Test tool execution"""

    @pytest.mark.asyncio
    async def test_execute_missing_file_path(self):
        """Test execution fails without file_path"""
        tool = UniversalAnalyzeTool()
        args = {}

        with pytest.raises(AnalysisError, match="file_path is required"):
            await tool.execute(args)

    @pytest.mark.asyncio
    async def test_execute_file_not_found(self, tmp_path):
        """Test execution fails when file doesn't exist"""
        tool = UniversalAnalyzeTool(str(tmp_path))
        args = {"file_path": "nonexistent.py"}

        with pytest.raises(AnalysisError, match="file does not exist"):
            await tool.execute(args)

    @pytest.mark.asyncio
    async def test_execute_language_detection_failure(self, tmp_path):
        """Test execution fails when language detection fails"""
        # Create file with unknown extension
        test_file = tmp_path / "test.unknown"
        test_file.write_text("content")

        tool = UniversalAnalyzeTool(str(tmp_path))
        args = {"file_path": str(test_file)}

        with pytest.raises(AnalysisError, match="Could not detect language"):
            await tool.execute(args)

    @pytest.mark.asyncio
    async def test_execute_unsupported_language(self, tmp_path):
        """Test execution fails with unsupported language"""
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')")

        tool = UniversalAnalyzeTool(str(tmp_path))
        args = {"file_path": str(test_file), "language": "unsupported_lang"}

        with pytest.raises(AnalysisError, match="not supported"):
            await tool.execute(args)

    @pytest.mark.asyncio
    async def test_execute_invalid_analysis_type(self, tmp_path):
        """Test execution fails with invalid analysis_type"""
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')")

        tool = UniversalAnalyzeTool(str(tmp_path))
        args = {"file_path": str(test_file), "analysis_type": "invalid_type"}

        with pytest.raises(AnalysisError, match="Invalid analysis_type"):
            await tool.execute(args)

    @pytest.mark.asyncio
    @patch(
        "tree_sitter_analyzer.mcp.tools.universal_analyze_tool.detect_language_from_file"
    )
    @patch(
        "tree_sitter_analyzer.mcp.tools.universal_analyze_tool.is_language_supported"
    )
    async def test_execute_basic_analysis_python(
        self, mock_supported, mock_detect, tmp_path
    ):
        """Test basic analysis execution for Python"""
        test_file = tmp_path / "test.py"
        test_file.write_text("def hello():\n    print('hello')\n")

        mock_detect.return_value = "python"
        mock_supported.return_value = True

        tool = UniversalAnalyzeTool(str(tmp_path))

        # Mock the analysis engine
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.to_dict.return_value = {
            "elements": [],
            "line_count": 2,
            "query_results": {},
        }

        with patch.object(
            tool.analysis_engine, "analyze", AsyncMock(return_value=mock_result)
        ):
            args = {"file_path": str(test_file), "analysis_type": "basic"}
            result = await tool.execute(args)

            assert "file_path" in result
            assert "language" in result
            assert result["analyzer_type"] == "universal"
            assert result["analysis_type"] == "basic"
            assert "metrics" in result

    @pytest.mark.asyncio
    @patch(
        "tree_sitter_analyzer.mcp.tools.universal_analyze_tool.detect_language_from_file"
    )
    @patch(
        "tree_sitter_analyzer.mcp.tools.universal_analyze_tool.is_language_supported"
    )
    async def test_execute_detailed_analysis(
        self, mock_supported, mock_detect, tmp_path
    ):
        """Test detailed analysis execution"""
        test_file = tmp_path / "test.py"
        test_file.write_text("def hello():\n    print('hello')\n")

        mock_detect.return_value = "python"
        mock_supported.return_value = True

        tool = UniversalAnalyzeTool(str(tmp_path))

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.to_dict.return_value = {
            "elements": [],
            "line_count": 2,
            "query_results": {"functions": []},
        }

        with patch.object(
            tool.analysis_engine, "analyze", AsyncMock(return_value=mock_result)
        ):
            args = {"file_path": str(test_file), "analysis_type": "detailed"}
            result = await tool.execute(args)

            assert result["analysis_type"] == "detailed"
            assert "metrics" in result

    @pytest.mark.asyncio
    @patch(
        "tree_sitter_analyzer.mcp.tools.universal_analyze_tool.detect_language_from_file"
    )
    @patch(
        "tree_sitter_analyzer.mcp.tools.universal_analyze_tool.is_language_supported"
    )
    async def test_execute_with_include_ast(
        self, mock_supported, mock_detect, tmp_path
    ):
        """Test execution with include_ast option"""
        test_file = tmp_path / "test.py"
        test_file.write_text("def hello():\n    print('hello')\n")

        mock_detect.return_value = "python"
        mock_supported.return_value = True

        tool = UniversalAnalyzeTool(str(tmp_path))

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.to_dict.return_value = {
            "elements": [],
            "line_count": 2,
            "ast_info": {"node_count": 10},
        }

        with patch.object(
            tool.analysis_engine, "analyze", AsyncMock(return_value=mock_result)
        ):
            args = {
                "file_path": str(test_file),
                "analysis_type": "basic",
                "include_ast": True,
                "output_format": "json",
            }
            result = await tool.execute(args)

            assert "ast_info" in result

    @pytest.mark.asyncio
    @patch(
        "tree_sitter_analyzer.mcp.tools.universal_analyze_tool.detect_language_from_file"
    )
    @patch(
        "tree_sitter_analyzer.mcp.tools.universal_analyze_tool.is_language_supported"
    )
    async def test_execute_with_include_queries(
        self, mock_supported, mock_detect, tmp_path
    ):
        """Test execution with include_queries option"""
        test_file = tmp_path / "test.py"
        test_file.write_text("def hello():\n    print('hello')\n")

        mock_detect.return_value = "python"
        mock_supported.return_value = True

        tool = UniversalAnalyzeTool(str(tmp_path))

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.to_dict.return_value = {
            "elements": [],
            "line_count": 2,
        }

        with patch.object(
            tool.analysis_engine, "analyze", AsyncMock(return_value=mock_result)
        ):
            args = {
                "file_path": str(test_file),
                "analysis_type": "basic",
                "include_queries": True,
                "output_format": "json",
            }
            result = await tool.execute(args)

            assert "available_queries" in result

    @pytest.mark.asyncio
    @patch(
        "tree_sitter_analyzer.mcp.tools.universal_analyze_tool.detect_language_from_file"
    )
    @patch(
        "tree_sitter_analyzer.mcp.tools.universal_analyze_tool.is_language_supported"
    )
    async def test_execute_structure_analysis(
        self, mock_supported, mock_detect, tmp_path
    ):
        """Test structure analysis type"""
        test_file = tmp_path / "test.py"
        test_file.write_text("class MyClass:\n    pass\n")

        mock_detect.return_value = "python"
        mock_supported.return_value = True

        tool = UniversalAnalyzeTool(str(tmp_path))

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.to_dict.return_value = {
            "elements": [],
            "line_count": 2,
            "structure": {},
        }

        with patch.object(
            tool.analysis_engine, "analyze", AsyncMock(return_value=mock_result)
        ):
            args = {"file_path": str(test_file), "analysis_type": "structure"}
            result = await tool.execute(args)

            assert result["analysis_type"] == "structure"
            assert "structure" in result

    @pytest.mark.asyncio
    @patch(
        "tree_sitter_analyzer.mcp.tools.universal_analyze_tool.detect_language_from_file"
    )
    @patch(
        "tree_sitter_analyzer.mcp.tools.universal_analyze_tool.is_language_supported"
    )
    async def test_execute_metrics_analysis(
        self, mock_supported, mock_detect, tmp_path
    ):
        """Test metrics analysis type"""
        test_file = tmp_path / "test.py"
        test_file.write_text("class MyClass:\n    pass\n")

        mock_detect.return_value = "python"
        mock_supported.return_value = True

        tool = UniversalAnalyzeTool(str(tmp_path))

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.to_dict.return_value = {
            "elements": [],
            "line_count": 2,
            "structure": {},
        }

        with patch.object(
            tool.analysis_engine, "analyze", AsyncMock(return_value=mock_result)
        ):
            args = {"file_path": str(test_file), "analysis_type": "metrics"}
            result = await tool.execute(args)

            assert result["analysis_type"] == "metrics"


class TestMetricsExtraction:
    """Test metrics extraction methods"""

    def test_extract_universal_basic_metrics(self):
        """Test basic metrics extraction from universal analyzer"""
        tool = UniversalAnalyzeTool()
        analysis_result = {
            "elements": [
                MagicMock(element_type="class"),
                MagicMock(element_type="function"),
                MagicMock(element_type="function"),
            ],
            "line_count": 50,
        }

        metrics = tool._extract_universal_basic_metrics(analysis_result)

        assert "metrics" in metrics
        assert metrics["metrics"]["lines_total"] == 50
        assert "elements" in metrics["metrics"]

    def test_extract_universal_detailed_metrics(self):
        """Test detailed metrics extraction"""
        tool = UniversalAnalyzeTool()
        analysis_result = {
            "elements": [],
            "line_count": 50,
            "query_results": {"classes": [], "functions": []},
        }

        metrics = tool._extract_universal_detailed_metrics(analysis_result)

        assert "metrics" in metrics
        assert "query_results" in metrics

    def test_extract_universal_structure_info(self):
        """Test structure info extraction"""
        tool = UniversalAnalyzeTool()
        analysis_result = {
            "structure": {"classes": [], "functions": []},
            "queries_executed": ["class", "function"],
        }

        structure = tool._extract_universal_structure_info(analysis_result)

        assert "structure" in structure
        assert "queries_executed" in structure

    def test_extract_universal_comprehensive_metrics(self):
        """Test comprehensive metrics extraction"""
        tool = UniversalAnalyzeTool()
        analysis_result = {
            "elements": [],
            "line_count": 50,
            "structure": {},
            "query_results": {},
            "queries_executed": [],
        }

        metrics = tool._extract_universal_comprehensive_metrics(analysis_result)

        assert "metrics" in metrics
        assert "structure" in metrics


class TestAvailableQueries:
    """Test available queries functionality"""

    @pytest.mark.asyncio
    async def test_get_available_queries_python(self):
        """Test getting available queries for Python"""
        tool = UniversalAnalyzeTool()

        with patch.object(
            tool.analysis_engine,
            "get_supported_languages",
            return_value=["python", "java"],
        ):
            result = await tool._get_available_queries("python")

            assert "language" in result
            assert result["language"] == "python"

    @pytest.mark.asyncio
    async def test_get_available_queries_error_handling(self):
        """Test error handling when getting queries fails"""
        tool = UniversalAnalyzeTool()

        with patch.object(
            tool.analysis_engine,
            "get_supported_languages",
            side_effect=Exception("Test error"),
        ):
            result = await tool._get_available_queries("python")

            assert "error" in result
            assert "queries" in result
            assert result["queries"] == []


class TestEdgeCases:
    """Test edge cases and error handling"""

    @pytest.mark.asyncio
    async def test_execute_with_special_characters_in_path(self, tmp_path):
        """Test execution with special characters in file path"""
        # Create file with special characters
        test_file = tmp_path / "test file (1).py"
        test_file.write_text("print('hello')")

        tool = UniversalAnalyzeTool(str(tmp_path))

        with patch(
            "tree_sitter_analyzer.mcp.tools.universal_analyze_tool.detect_language_from_file"
        ) as mock_detect:
            with patch(
                "tree_sitter_analyzer.mcp.tools.universal_analyze_tool.is_language_supported"
            ) as mock_supported:
                mock_detect.return_value = "python"
                mock_supported.return_value = True

                mock_result = MagicMock()
                mock_result.success = True
                mock_result.to_dict.return_value = {
                    "elements": [],
                    "line_count": 1,
                }

                with patch.object(
                    tool.analysis_engine, "analyze", AsyncMock(return_value=mock_result)
                ):
                    args = {"file_path": str(test_file)}
                    result = await tool.execute(args)

                    assert result["language"] == "python"

    @pytest.mark.asyncio
    async def test_execute_with_empty_file(self, tmp_path):
        """Test execution with empty file"""
        test_file = tmp_path / "empty.py"
        test_file.write_text("")

        tool = UniversalAnalyzeTool(str(tmp_path))

        with patch(
            "tree_sitter_analyzer.mcp.tools.universal_analyze_tool.detect_language_from_file"
        ) as mock_detect:
            with patch(
                "tree_sitter_analyzer.mcp.tools.universal_analyze_tool.is_language_supported"
            ) as mock_supported:
                mock_detect.return_value = "python"
                mock_supported.return_value = True

                mock_result = MagicMock()
                mock_result.success = True
                mock_result.to_dict.return_value = {
                    "elements": [],
                    "line_count": 0,
                }

                with patch.object(
                    tool.analysis_engine, "analyze", AsyncMock(return_value=mock_result)
                ):
                    args = {"file_path": str(test_file)}
                    result = await tool.execute(args)

                    assert result["language"] == "python"
                    assert "metrics" in result

    @pytest.mark.asyncio
    async def test_execute_with_analysis_failure(self, tmp_path):
        """Test execution when analysis fails"""
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')")

        tool = UniversalAnalyzeTool(str(tmp_path))

        with patch(
            "tree_sitter_analyzer.mcp.tools.universal_analyze_tool.detect_language_from_file"
        ) as mock_detect:
            with patch(
                "tree_sitter_analyzer.mcp.tools.universal_analyze_tool.is_language_supported"
            ) as mock_supported:
                mock_detect.return_value = "python"
                mock_supported.return_value = True

                mock_result = MagicMock()
                mock_result.success = False
                mock_result.error_message = "Analysis failed"

                with patch.object(
                    tool.analysis_engine, "analyze", AsyncMock(return_value=mock_result)
                ):
                    args = {"file_path": str(test_file)}

                    with pytest.raises(RuntimeError, match="Failed to analyze"):
                        await tool.execute(args)
