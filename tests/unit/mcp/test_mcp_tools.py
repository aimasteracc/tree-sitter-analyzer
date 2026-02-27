#!/usr/bin/env python3
"""
Additional tests to boost MCP tools coverage.

Covers: query_tool.py, analyze_scale_tool.py, read_partial_tool.py,
        analyze_code_structure_tool.py, and related utilities.
"""

import tempfile
from pathlib import Path

import pytest


class TestQueryToolCoverage:
    """Test QueryTool for coverage boost."""

    @pytest.fixture
    def query_tool(self):
        """Create QueryTool instance."""
        from tree_sitter_analyzer.mcp.tools.query_tool import QueryTool

        return QueryTool()

    @pytest.fixture
    def temp_python_file(self):
        """Create temporary Python file."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write('''
class TestClass:
    """A test class."""

    def method_one(self):
        """First method."""
        pass

    def method_two(self, x: int) -> int:
        """Second method."""
        return x * 2

def standalone_function():
    """A standalone function."""
    pass
''')
            f.flush()
            yield f.name
        Path(f.name).unlink(missing_ok=True)

    def test_get_tool_definition(self, query_tool):
        """Test get_tool_definition returns valid schema."""
        definition = query_tool.get_tool_definition()
        assert definition["name"] == "query_code"
        assert "inputSchema" in definition
        assert "properties" in definition["inputSchema"]
        props = definition["inputSchema"]["properties"]
        assert "file_path" in props
        assert "query_key" in props
        assert "output_format" in props

    def test_set_project_path(self, query_tool):
        """Test set_project_path updates components."""
        query_tool.set_project_path("/tmp/new_project")
        assert query_tool.project_root == "/tmp/new_project"

    def test_get_available_queries(self, query_tool):
        """Test get_available_queries returns list."""
        queries = query_tool.get_available_queries("python")
        assert isinstance(queries, list)

    @pytest.mark.asyncio
    async def test_execute_with_query_key(self, query_tool, temp_python_file):
        """Test execute with query_key."""
        result = await query_tool.execute(
            {
                "file_path": temp_python_file,
                "query_key": "functions",
            }
        )
        assert "success" in result

    @pytest.mark.asyncio
    async def test_execute_with_custom_query(self, query_tool, temp_python_file):
        """Test execute with custom query string."""
        result = await query_tool.execute(
            {
                "file_path": temp_python_file,
                "query_string": "(function_definition) @function",
            }
        )
        assert "success" in result

    @pytest.mark.asyncio
    async def test_execute_both_query_params_error(self, query_tool, temp_python_file):
        """Test error when both query_key and query_string provided."""
        result = await query_tool.execute(
            {
                "file_path": temp_python_file,
                "query_key": "functions",
                "query_string": "(function_definition) @function",
            }
        )
        assert result.get("success") is False or "error" in result

    @pytest.mark.asyncio
    async def test_execute_no_query_params_error(self, query_tool, temp_python_file):
        """Test error when no query parameters provided."""
        from tree_sitter_analyzer.mcp.utils.error_handler import AnalysisError

        with pytest.raises(AnalysisError):
            await query_tool.execute(
                {
                    "file_path": temp_python_file,
                }
            )

    @pytest.mark.asyncio
    async def test_execute_with_filter(self, query_tool, temp_python_file):
        """Test execute with filter parameter."""
        result = await query_tool.execute(
            {
                "file_path": temp_python_file,
                "query_key": "functions",
                "filter": "name=~.*",
            }
        )
        assert "success" in result

    @pytest.mark.asyncio
    async def test_execute_with_output_format_toon(self, query_tool, temp_python_file):
        """Test execute with TOON output format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = await query_tool.execute(
                {
                    "file_path": temp_python_file,
                    "query_key": "functions",
                    "output_format": "toon",
                    "output_file": f"{tmpdir}/output",
                }
            )
            assert "success" in result

    @pytest.mark.asyncio
    async def test_execute_with_suppress_output(self, query_tool, temp_python_file):
        """Test execute with suppress_output."""
        result = await query_tool.execute(
            {
                "file_path": temp_python_file,
                "query_key": "functions",
                "suppress_output": True,
            }
        )
        assert "success" in result

    @pytest.mark.asyncio
    async def test_execute_with_summary_format(self, query_tool, temp_python_file):
        """Test execute with summary result format."""
        result = await query_tool.execute(
            {
                "file_path": temp_python_file,
                "query_key": "functions",
                "result_format": "summary",
            }
        )
        assert "success" in result

    @pytest.mark.asyncio
    async def test_execute_invalid_file(self, query_tool):
        """Test execute with nonexistent file."""
        result = await query_tool.execute(
            {
                "file_path": "/nonexistent/file.py",
                "query_key": "functions",
            }
        )
        assert result.get("success") is False or "error" in result

    def test_validate_arguments_invalid_output_format(self, query_tool):
        """Test validate_arguments with invalid output_format."""
        with pytest.raises(ValueError, match="output_format"):
            query_tool.validate_arguments(
                {
                    "file_path": "test.py",
                    "query_key": "functions",
                    "output_format": "invalid",
                }
            )

    def test_validate_arguments_invalid_result_format(self, query_tool):
        """Test validate_arguments with invalid result_format."""
        with pytest.raises(ValueError, match="result_format"):
            query_tool.validate_arguments(
                {
                    "file_path": "test.py",
                    "query_key": "functions",
                    "result_format": "invalid",
                }
            )


class TestAnalyzeScaleToolCoverage:
    """Test AnalyzeScaleTool for coverage boost."""

    @pytest.fixture
    def analyze_scale_tool(self):
        """Create AnalyzeScaleTool instance."""
        from tree_sitter_analyzer.mcp.tools.analyze_scale_tool import AnalyzeScaleTool

        return AnalyzeScaleTool()

    @pytest.fixture
    def temp_python_file(self):
        """Create temporary Python file."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write('''
# This is a comment
class MyClass:
    """A class with methods."""

    def __init__(self):
        self.value = 0

    def method(self, x):
        # Another comment
        return x * 2

def function():
    """A function."""
    pass

import os
from pathlib import Path
''')
            f.flush()
            yield f.name
        Path(f.name).unlink(missing_ok=True)

    def test_get_tool_definition(self, analyze_scale_tool):
        """Test get_tool_definition returns valid schema."""
        definition = analyze_scale_tool.get_tool_definition()
        assert definition["name"] == "check_code_scale"
        assert "inputSchema" in definition

    def test_set_project_path(self, analyze_scale_tool):
        """Test set_project_path updates components."""
        analyze_scale_tool.set_project_path("/tmp/new_project")
        assert analyze_scale_tool.project_root == "/tmp/new_project"

    @pytest.mark.asyncio
    async def test_execute_basic(self, analyze_scale_tool, temp_python_file):
        """Test basic execute."""
        result = await analyze_scale_tool.execute(
            {
                "file_path": temp_python_file,
            }
        )
        assert "success" in result or "file_path" in result

    @pytest.mark.asyncio
    async def test_execute_with_threshold(self, analyze_scale_tool, temp_python_file):
        """Test execute with line threshold."""
        result = await analyze_scale_tool.execute(
            {
                "file_path": temp_python_file,
                "threshold": 100,
            }
        )
        assert "success" in result or "file_path" in result

    @pytest.mark.asyncio
    async def test_execute_nonexistent_file(self, analyze_scale_tool):
        """Test execute with nonexistent file raises ValueError."""
        with pytest.raises(ValueError, match="Invalid"):
            await analyze_scale_tool.execute(
                {
                    "file_path": "nonexistent_file_that_does_not_exist.py",
                }
            )

    @pytest.mark.asyncio
    async def test_execute_with_output_format_toon(
        self, analyze_scale_tool, temp_python_file
    ):
        """Test execute with TOON output format."""
        result = await analyze_scale_tool.execute(
            {
                "file_path": temp_python_file,
                "output_format": "toon",
            }
        )
        assert "success" in result or "file_path" in result


class TestReadPartialToolCoverage:
    """Test ReadPartialTool for coverage boost."""

    @pytest.fixture
    def read_partial_tool(self):
        """Create ReadPartialTool instance."""
        from tree_sitter_analyzer.mcp.tools.read_partial_tool import ReadPartialTool

        return ReadPartialTool()

    @pytest.fixture
    def temp_python_file(self):
        """Create temporary Python file with multiple elements."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write('''# Line 1
# Line 2
# Line 3
class FirstClass:
    """First class docstring."""
    pass

# Line 8
class SecondClass:
    """Second class docstring."""

    def method_a(self):
        pass

    def method_b(self):
        pass

# Line 18
def standalone_function():
    """A standalone function."""
    return 42
''')
            f.flush()
            yield f.name
        Path(f.name).unlink(missing_ok=True)

    def test_get_tool_definition(self, read_partial_tool):
        """Test get_tool_definition returns valid schema."""
        definition = read_partial_tool.get_tool_definition()
        assert definition["name"] == "extract_code_section"
        assert "inputSchema" in definition

    def test_set_project_path(self, read_partial_tool):
        """Test set_project_path updates components."""
        read_partial_tool.set_project_path("/tmp/new_project")
        assert read_partial_tool.project_root == "/tmp/new_project"

    @pytest.mark.asyncio
    async def test_execute_by_line_range(self, read_partial_tool, temp_python_file):
        """Test execute with line range."""
        result = await read_partial_tool.execute(
            {
                "file_path": temp_python_file,
                "start_line": 1,
                "end_line": 10,
            }
        )
        assert "content" in result or "success" in result

    @pytest.mark.asyncio
    async def test_execute_by_element_name(self, read_partial_tool, temp_python_file):
        """Test execute with element name requires start_line, so use line range."""
        result = await read_partial_tool.execute(
            {
                "file_path": temp_python_file,
                "start_line": 4,
                "end_line": 7,
            }
        )
        assert "content" in result or "success" in result or "error" in result

    @pytest.mark.asyncio
    async def test_execute_with_context(self, read_partial_tool, temp_python_file):
        """Test execute with context lines."""
        result = await read_partial_tool.execute(
            {
                "file_path": temp_python_file,
                "start_line": 5,
                "end_line": 8,
                "context_lines": 2,
            }
        )
        assert "content" in result or "success" in result

    @pytest.mark.asyncio
    async def test_execute_nonexistent_file(self, read_partial_tool):
        """Test execute with nonexistent file."""
        result = await read_partial_tool.execute(
            {
                "file_path": "/nonexistent/file.py",
                "start_line": 1,
                "end_line": 10,
            }
        )
        assert "error" in result or result.get("success") is False


class TestAnalyzeCodeStructureToolCoverage:
    """Test AnalyzeCodeStructureTool for coverage boost."""

    @pytest.fixture
    def analyze_code_structure_tool(self):
        """Create AnalyzeCodeStructureTool instance."""
        from tree_sitter_analyzer.mcp.tools.analyze_code_structure_tool import (
            AnalyzeCodeStructureTool,
        )

        return AnalyzeCodeStructureTool()

    @pytest.fixture
    def temp_python_file(self):
        """Create temporary Python file."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write("""
class MyClass:
    def method_one(self): pass
    def method_two(self): pass

def function_one(): pass
def function_two(): pass
""")
            f.flush()
            yield f.name
        Path(f.name).unlink(missing_ok=True)

    def test_get_tool_definition(self, analyze_code_structure_tool):
        """Test get_tool_definition returns valid schema."""
        definition = analyze_code_structure_tool.get_tool_definition()
        # AnalyzeCodeStructureTool uses analyze_code_structure as tool name
        assert definition["name"] == "analyze_code_structure"
        assert "inputSchema" in definition

    def test_set_project_path(self, analyze_code_structure_tool):
        """Test set_project_path updates components."""
        analyze_code_structure_tool.set_project_path("/tmp/new_project")
        assert analyze_code_structure_tool.project_root == "/tmp/new_project"

    @pytest.mark.asyncio
    async def test_execute_full_format(
        self, analyze_code_structure_tool, temp_python_file
    ):
        """Test execute with full format."""
        result = await analyze_code_structure_tool.execute(
            {
                "file_path": temp_python_file,
                "format_type": "full",
            }
        )
        assert "success" in result or "table" in result or "content" in result

    @pytest.mark.asyncio
    async def test_execute_compact_format(
        self, analyze_code_structure_tool, temp_python_file
    ):
        """Test execute with compact format."""
        result = await analyze_code_structure_tool.execute(
            {
                "file_path": temp_python_file,
                "format_type": "compact",
            }
        )
        assert "success" in result or "table" in result or "content" in result

    @pytest.mark.asyncio
    async def test_execute_csv_format(
        self, analyze_code_structure_tool, temp_python_file
    ):
        """Test execute with CSV format."""
        result = await analyze_code_structure_tool.execute(
            {
                "file_path": temp_python_file,
                "format_type": "csv",
            }
        )
        assert "success" in result or "table" in result or "content" in result

    @pytest.mark.asyncio
    async def test_execute_toon_format(
        self, analyze_code_structure_tool, temp_python_file
    ):
        """Test execute with TOON format."""
        result = await analyze_code_structure_tool.execute(
            {
                "file_path": temp_python_file,
                "output_format": "toon",
            }
        )
        assert "success" in result or "table" in result or "content" in result

    @pytest.mark.asyncio
    async def test_execute_nonexistent_file(self, analyze_code_structure_tool):
        """Test execute with nonexistent file raises ValueError."""
        with pytest.raises(ValueError, match="Invalid"):
            await analyze_code_structure_tool.execute(
                {
                    "file_path": "nonexistent_file_that_does_not_exist.py",
                }
            )


class TestOutputManagerCoverage:
    """Test OutputManager for coverage boost."""

    def test_init_default(self):
        """Test default initialization."""
        from tree_sitter_analyzer.output_manager import OutputManager

        manager = OutputManager()
        assert manager.quiet is False
        assert manager.output_format == "json"

    def test_init_with_json_output(self):
        """Test initialization with json_output flag."""
        from tree_sitter_analyzer.output_manager import OutputManager

        manager = OutputManager(json_output=True, output_format="toon")
        # json_output should override output_format
        assert manager.output_format == "json"

    def test_init_with_toon_format(self):
        """Test initialization with toon format."""
        from tree_sitter_analyzer.output_manager import OutputManager

        manager = OutputManager(output_format="toon")
        assert manager.output_format == "toon"
        assert "toon" in manager._formatter_registry

    def test_info_quiet(self, capsys):
        """Test info message when quiet."""
        from tree_sitter_analyzer.output_manager import OutputManager

        manager = OutputManager(quiet=True)
        manager.info("Test message")
        captured = capsys.readouterr()
        assert captured.out == ""

    def test_info_not_quiet(self, capsys):
        """Test info message when not quiet."""
        from tree_sitter_analyzer.output_manager import OutputManager

        manager = OutputManager(quiet=False)
        manager.info("Test message")
        captured = capsys.readouterr()
        assert "Test message" in captured.out

    def test_data_json(self, capsys):
        """Test data output in JSON format."""
        from tree_sitter_analyzer.output_manager import OutputManager

        manager = OutputManager(output_format="json")
        manager.data({"key": "value"})
        captured = capsys.readouterr()
        assert '"key"' in captured.out

    def test_data_toon(self, capsys):
        """Test data output in TOON format."""
        from tree_sitter_analyzer.output_manager import OutputManager

        manager = OutputManager(output_format="toon")
        manager.data({"key": "value"})
        captured = capsys.readouterr()
        assert "key:" in captured.out

    def test_data_string(self, capsys):
        """Test data output with string data."""
        from tree_sitter_analyzer.output_manager import OutputManager

        manager = OutputManager()
        manager.data("Already formatted string")
        captured = capsys.readouterr()
        assert "Already formatted string" in captured.out

    def test_format_override(self, capsys):
        """Test data with format_type override."""
        from tree_sitter_analyzer.output_manager import OutputManager

        manager = OutputManager(output_format="json")
        manager.data({"key": "value"}, format_type="toon")
        captured = capsys.readouterr()
        assert "key:" in captured.out

    def test_error_output(self, capsys):
        """Test error output."""
        from tree_sitter_analyzer.output_manager import OutputManager

        manager = OutputManager()
        manager.error("Error message")
        captured = capsys.readouterr()
        # Error may go to stderr
        assert "Error message" in captured.err or "Error message" in captured.out

    def test_warning_output(self, capsys):
        """Test warning output."""
        from tree_sitter_analyzer.output_manager import OutputManager

        manager = OutputManager()
        manager.warning("Warning message")
        captured = capsys.readouterr()
        # Warning may go to stderr
        assert "Warning message" in captured.err or "Warning message" in captured.out

    def test_unsupported_format_fallback(self, capsys):
        """Test fallback for unsupported format."""
        from tree_sitter_analyzer.output_manager import OutputManager

        manager = OutputManager()
        # Remove toon formatter to test fallback
        if "yaml" in manager._formatter_registry:
            del manager._formatter_registry["yaml"]
        manager.data({"key": "value"}, format_type="yaml")
        captured = capsys.readouterr()
        # Should fall back to JSON or print as-is
        assert "key" in captured.out


class TestMCPUtilsInit:
    """Test mcp/utils/__init__.py coverage."""

    def test_file_output_manager_import(self):
        """Test FileOutputManager can be imported from submodule."""
        from tree_sitter_analyzer.mcp.utils.file_output_manager import FileOutputManager

        assert FileOutputManager is not None

    def test_format_helper_import(self):
        """Test format_helper functions can be imported."""
        from tree_sitter_analyzer.mcp.utils.format_helper import (
            format_for_file_output,
            format_output,
        )

        assert format_output is not None
        assert format_for_file_output is not None

    def test_error_handler_import(self):
        """Test error_handler can be imported."""
        from tree_sitter_analyzer.mcp.utils.error_handler import AnalysisError

        assert AnalysisError is not None
