"""
Integration tests for Code Graph MCP Tools.

Tests the MCP tool interface for Code Graph functionality.
"""

import tempfile
from pathlib import Path


class TestAnalyzeCodeGraphTool:
    """Tests for AnalyzeCodeGraphTool MCP tool."""

    def test_tool_initialization(self):
        """Test tool initializes correctly."""
        from tree_sitter_analyzer_v2.mcp.tools.code_graph import AnalyzeCodeGraphTool

        tool = AnalyzeCodeGraphTool()
        assert tool.get_name() == "analyze_code_graph"
        assert "code structure" in tool.get_description().lower()

    def test_tool_schema(self):
        """Test tool schema is valid."""
        from tree_sitter_analyzer_v2.mcp.tools.code_graph import AnalyzeCodeGraphTool

        tool = AnalyzeCodeGraphTool()
        schema = tool.get_schema()

        assert schema["type"] == "object"
        assert "file_path" in schema["properties"]
        assert "directory" in schema["properties"]
        assert "detail_level" in schema["properties"]
        # Note: file_path and directory are mutually exclusive, so no required field

    def test_analyze_simple_file(self):
        """Test analyzing a simple Python file."""
        from tree_sitter_analyzer_v2.mcp.tools.code_graph import AnalyzeCodeGraphTool

        code = """
def helper():
    return 42

def main():
    return helper()
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            temp_path = f.name

        try:
            tool = AnalyzeCodeGraphTool()
            result = tool.execute({"file_path": temp_path})

            assert result["success"] is True
            assert result["file_path"] == temp_path
            assert "statistics" in result
            assert result["statistics"]["functions"] == 2
            assert "structure" in result
            assert "TOON" in result["structure"] or "MODULE" in result["structure"]
        finally:
            Path(temp_path).unlink()

    def test_analyze_with_detail_levels(self):
        """Test different detail levels."""
        from tree_sitter_analyzer_v2.mcp.tools.code_graph import AnalyzeCodeGraphTool

        code = """
def func(a: int, b: str) -> bool:
    return True
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            temp_path = f.name

        try:
            tool = AnalyzeCodeGraphTool()

            # Summary mode
            summary_result = tool.execute({"file_path": temp_path, "detail_level": "summary"})
            assert summary_result["success"] is True

            # Detailed mode
            detailed_result = tool.execute({"file_path": temp_path, "detail_level": "detailed"})
            assert detailed_result["success"] is True

            # Detailed should have more info (params, return types)
            # This is reflected in the TOON output length
            assert len(detailed_result["structure"]) >= len(summary_result["structure"])

        finally:
            Path(temp_path).unlink()

    def test_analyze_with_private_functions(self):
        """Test private function filtering."""
        from tree_sitter_analyzer_v2.mcp.tools.code_graph import AnalyzeCodeGraphTool

        code = """
def public_func():
    return 1

def _private_func():
    return 2
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            temp_path = f.name

        try:
            tool = AnalyzeCodeGraphTool()

            # Without private functions
            result_no_private = tool.execute({"file_path": temp_path, "include_private": False})
            assert result_no_private["success"] is True
            # Should not include _private_func in summary mode
            assert "_private_func" not in result_no_private["structure"]

            # With private functions
            result_with_private = tool.execute({"file_path": temp_path, "include_private": True})
            assert result_with_private["success"] is True

        finally:
            Path(temp_path).unlink()

    def test_analyze_file_not_found(self):
        """Test error handling for missing file."""
        from tree_sitter_analyzer_v2.mcp.tools.code_graph import AnalyzeCodeGraphTool

        tool = AnalyzeCodeGraphTool()
        result = tool.execute({"file_path": "/nonexistent/file.py"})

        assert result["success"] is False
        assert "error" in result
        assert "not found" in result["error"].lower()

    def test_analyze_with_cross_file_disabled(self):
        """Test that cross_file=False only includes intra-file calls (backward compatible)."""
        from tree_sitter_analyzer_v2.mcp.tools.code_graph import AnalyzeCodeGraphTool

        # Create a test project structure
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create main.py
            main_code = """
from utils import helper

def main():
    result = helper("test")
    return result
"""
            (tmpdir_path / "main.py").write_text(main_code)

            # Create utils.py
            utils_code = """
def helper(data):
    return process_data(data)

def process_data(data):
    return data.upper()
"""
            (tmpdir_path / "utils.py").write_text(utils_code)

            tool = AnalyzeCodeGraphTool()
            result = tool.execute(
                {
                    "directory": str(tmpdir_path),
                    "cross_file": False,  # Explicitly disabled
                }
            )

            assert result["success"] is True
            assert "statistics" in result
            # Should NOT have cross_file_calls key when disabled
            assert (
                "cross_file_calls" not in result["statistics"]
                or result["statistics"]["cross_file_calls"] == 0
            )

    def test_analyze_with_cross_file_enabled(self):
        """Test that cross_file=True adds cross-file CALLS edges."""
        from tree_sitter_analyzer_v2.mcp.tools.code_graph import AnalyzeCodeGraphTool

        # Create a test project structure
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create main.py
            main_code = """
from utils import helper

def main():
    result = helper("test")
    return result
"""
            (tmpdir_path / "main.py").write_text(main_code)

            # Create utils.py
            utils_code = """
def helper(data):
    return process_data(data)

def process_data(data):
    return data.upper()
"""
            (tmpdir_path / "utils.py").write_text(utils_code)

            tool = AnalyzeCodeGraphTool()
            result = tool.execute(
                {
                    "directory": str(tmpdir_path),
                    "cross_file": True,  # Enable cross-file resolution
                }
            )

            assert result["success"] is True
            assert "statistics" in result
            # Should have cross_file_calls count when enabled
            assert "cross_file_calls" in result["statistics"]
            # Should detect at least 1 cross-file call (main -> helper)
            assert result["statistics"]["cross_file_calls"] > 0


class TestFindFunctionCallersTool:
    """Tests for FindFunctionCallersTool MCP tool."""

    def test_tool_initialization(self):
        """Test tool initializes correctly."""
        from tree_sitter_analyzer_v2.mcp.tools.code_graph import FindFunctionCallersTool

        tool = FindFunctionCallersTool()
        assert tool.get_name() == "find_function_callers"
        assert "caller" in tool.get_description().lower()

    def test_find_callers_basic(self):
        """Test finding function callers."""
        from tree_sitter_analyzer_v2.mcp.tools.code_graph import FindFunctionCallersTool

        code = """
def helper():
    return 42

def main():
    return helper()

def other():
    return helper() + 1
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            temp_path = f.name

        try:
            tool = FindFunctionCallersTool()
            result = tool.execute({"file_path": temp_path, "function_name": "helper"})

            assert result["success"] is True
            assert result["function_name"] == "helper"
            assert len(result["results"]) == 1
            assert result["results"][0]["caller_count"] == 2

            # Check caller names
            caller_names = [c["name"] for c in result["results"][0]["callers"]]
            assert "main" in caller_names
            assert "other" in caller_names

        finally:
            Path(temp_path).unlink()

    def test_find_callers_no_callers(self):
        """Test function with no callers."""
        from tree_sitter_analyzer_v2.mcp.tools.code_graph import FindFunctionCallersTool

        code = """
def unused():
    return 42

def main():
    return 100
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            temp_path = f.name

        try:
            tool = FindFunctionCallersTool()
            result = tool.execute({"file_path": temp_path, "function_name": "unused"})

            assert result["success"] is True
            assert result["results"][0]["caller_count"] == 0

        finally:
            Path(temp_path).unlink()

    def test_find_callers_function_not_found(self):
        """Test error when function doesn't exist."""
        from tree_sitter_analyzer_v2.mcp.tools.code_graph import FindFunctionCallersTool

        code = """
def some_func():
    pass
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            temp_path = f.name

        try:
            tool = FindFunctionCallersTool()
            result = tool.execute({"file_path": temp_path, "function_name": "nonexistent"})

            assert result["success"] is False
            assert "not found" in result["error"].lower()

        finally:
            Path(temp_path).unlink()


class TestQueryCallChainTool:
    """Tests for QueryCallChainTool MCP tool."""

    def test_tool_initialization(self):
        """Test tool initializes correctly."""
        from tree_sitter_analyzer_v2.mcp.tools.code_graph import QueryCallChainTool

        tool = QueryCallChainTool()
        assert tool.get_name() == "query_call_chain"
        assert "call path" in tool.get_description().lower()

    def test_find_call_chain_basic(self):
        """Test finding call chain between functions."""
        from tree_sitter_analyzer_v2.mcp.tools.code_graph import QueryCallChainTool

        code = """
def level3():
    return "done"

def level2():
    return level3()

def level1():
    return level2()

def main():
    return level1()
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            temp_path = f.name

        try:
            tool = QueryCallChainTool()
            result = tool.execute(
                {"file_path": temp_path, "start_function": "main", "end_function": "level3"}
            )

            assert result["success"] is True
            assert result["chains_found"] > 0
            assert len(result["chains"]) > 0

            # Check first chain
            first_chain = result["chains"][0]
            assert first_chain["length"] == 4
            assert first_chain["path"] == ["main", "level1", "level2", "level3"]

        finally:
            Path(temp_path).unlink()

    def test_find_call_chain_no_path(self):
        """Test when no call path exists."""
        from tree_sitter_analyzer_v2.mcp.tools.code_graph import QueryCallChainTool

        code = """
def isolated_a():
    return 1

def isolated_b():
    return 2
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            temp_path = f.name

        try:
            tool = QueryCallChainTool()
            result = tool.execute(
                {
                    "file_path": temp_path,
                    "start_function": "isolated_a",
                    "end_function": "isolated_b",
                }
            )

            assert result["success"] is True
            assert result["chains_found"] == 0

        finally:
            Path(temp_path).unlink()

    def test_find_call_chain_function_not_found(self):
        """Test error when function doesn't exist."""
        from tree_sitter_analyzer_v2.mcp.tools.code_graph import QueryCallChainTool

        code = """
def some_func():
    pass
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            temp_path = f.name

        try:
            tool = QueryCallChainTool()

            # Start function not found
            result = tool.execute(
                {
                    "file_path": temp_path,
                    "start_function": "nonexistent",
                    "end_function": "some_func",
                }
            )
            assert result["success"] is False
            assert "not found" in result["error"].lower()

        finally:
            Path(temp_path).unlink()
