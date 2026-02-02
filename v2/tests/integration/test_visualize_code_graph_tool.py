"""
Integration tests for VisualizeCodeGraphTool (E4 Enhancement).

Tests the MCP tool interface for code graph visualization.
"""

import tempfile
from pathlib import Path

from tree_sitter_analyzer_v2.mcp.tools.code_graph import VisualizeCodeGraphTool


class TestVisualizeCodeGraphTool:
    """Tests for VisualizeCodeGraphTool MCP tool."""

    def test_tool_initialization(self):
        """Test tool initializes correctly."""
        tool = VisualizeCodeGraphTool()

        assert tool.get_name() == "visualize_code_graph"
        assert "visualize" in tool.get_description().lower()
        assert "mermaid" in tool.get_description().lower()

    def test_tool_schema(self):
        """Test tool schema is valid."""
        tool = VisualizeCodeGraphTool()
        schema = tool.get_schema()

        assert schema["type"] == "object"
        assert "visualization_type" in schema["properties"]
        assert "file_path" in schema["properties"]
        assert "directory" in schema["properties"]

        # Verify visualization types
        viz_types = schema["properties"]["visualization_type"]["enum"]
        assert "flowchart" in viz_types
        assert "call_flow" in viz_types
        assert "dependency" in viz_types

    def test_visualize_flowchart_file(self):
        """Test flowchart visualization for a single file."""
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
            tool = VisualizeCodeGraphTool()
            result = tool.execute({"file_path": temp_path, "visualization_type": "flowchart"})

            # Verify success
            assert result["success"] is True
            assert result["visualization_type"] == "flowchart"
            assert result["format"] == "mermaid"

            # Verify Mermaid output
            mermaid = result["mermaid"]
            assert "graph TD" in mermaid or "graph LR" in mermaid
            assert "helper" in mermaid
            assert "main" in mermaid

        finally:
            Path(temp_path).unlink()

    def test_visualize_flowchart_directory(self):
        """Test flowchart visualization for a directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Create multiple files
            (tmppath / "file1.py").write_text("def func1(): return 1")
            (tmppath / "file2.py").write_text("def func2(): return 2")

            tool = VisualizeCodeGraphTool()
            result = tool.execute({"directory": tmpdir, "visualization_type": "flowchart"})

            # Verify success
            assert result["success"] is True
            assert "mermaid" in result
            assert "graph" in result["mermaid"]

    def test_visualize_call_flow(self):
        """Test call flow visualization."""
        code = """
def level2():
    return "done"

def level1():
    return level2()

def main():
    return level1()
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            temp_path = f.name

        try:
            tool = VisualizeCodeGraphTool()
            result = tool.execute(
                {
                    "file_path": temp_path,
                    "visualization_type": "call_flow",
                    "start_function": "main",
                }
            )

            # Verify success
            assert result["success"] is True
            assert result["visualization_type"] == "call_flow"
            assert result["start_function"] == "main"

            # Verify call flow in diagram
            mermaid = result["mermaid"]
            assert "main" in mermaid
            assert "level1" in mermaid
            assert "start" in mermaid  # Styling

        finally:
            Path(temp_path).unlink()

    def test_visualize_call_flow_missing_start_function(self):
        """Test error when start_function not provided for call_flow."""
        code = """
def helper():
    return 42
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            temp_path = f.name

        try:
            tool = VisualizeCodeGraphTool()
            result = tool.execute(
                {
                    "file_path": temp_path,
                    "visualization_type": "call_flow",
                    # Missing start_function!
                }
            )

            # Verify error
            assert result["success"] is False
            assert "start_function" in result["error"].lower()

        finally:
            Path(temp_path).unlink()

    def test_visualize_dependency_graph(self):
        """Test dependency graph visualization."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Create modules
            (tmppath / "module1.py").write_text("def func1(): return 1")
            (tmppath / "module2.py").write_text("def func2(): return 2")

            tool = VisualizeCodeGraphTool()
            result = tool.execute({"directory": tmpdir, "visualization_type": "dependency"})

            # Verify success
            assert result["success"] is True
            assert result["visualization_type"] == "dependency"
            assert "mermaid" in result

            # Dependency graphs use LR direction
            assert "graph LR" in result["mermaid"]

    def test_visualize_dependency_missing_directory(self):
        """Test error when directory not provided for dependency."""
        tool = VisualizeCodeGraphTool()
        result = tool.execute(
            {
                "visualization_type": "dependency"
                # Missing directory!
            }
        )

        # Verify error
        assert result["success"] is False
        assert "directory" in result["error"].lower()

    def test_visualize_with_max_nodes(self):
        """Test max_nodes parameter limits diagram size."""
        # Create file with many functions
        functions = [f"def func{i}(): return {i}" for i in range(20)]
        code = "\n\n".join(functions)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            temp_path = f.name

        try:
            tool = VisualizeCodeGraphTool()
            result = tool.execute(
                {"file_path": temp_path, "visualization_type": "flowchart", "max_nodes": 5}
            )

            assert result["success"] is True

            # Count nodes in diagram
            mermaid = result["mermaid"]
            bracket_count = mermaid.count("[")

            # Should be limited
            assert bracket_count <= 5

        finally:
            Path(temp_path).unlink()

    def test_visualize_with_max_depth(self):
        """Test max_depth parameter for call_flow."""
        code = """
def level4():
    return "done"

def level3():
    return level4()

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
            tool = VisualizeCodeGraphTool()
            result = tool.execute(
                {
                    "file_path": temp_path,
                    "visualization_type": "call_flow",
                    "start_function": "main",
                    "max_depth": 2,
                }
            )

            assert result["success"] is True

        finally:
            Path(temp_path).unlink()

    def test_visualize_with_show_classes(self):
        """Test show_classes parameter."""
        code = """
class MyClass:
    def method(self):
        return 42

def function():
    return MyClass().method()
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            temp_path = f.name

        try:
            tool = VisualizeCodeGraphTool()

            # With classes
            result_with = tool.execute(
                {"file_path": temp_path, "visualization_type": "flowchart", "show_classes": True}
            )

            assert result_with["success"] is True
            assert "subgraph" in result_with["mermaid"]

            # Without classes
            result_without = tool.execute(
                {"file_path": temp_path, "visualization_type": "flowchart", "show_classes": False}
            )

            assert result_without["success"] is True
            assert "subgraph" not in result_without["mermaid"]

        finally:
            Path(temp_path).unlink()

    def test_visualize_with_direction(self):
        """Test direction parameter (TD vs LR)."""
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
            tool = VisualizeCodeGraphTool()

            # Top-down
            result_td = tool.execute(
                {"file_path": temp_path, "visualization_type": "flowchart", "direction": "TD"}
            )

            assert result_td["success"] is True
            assert "graph TD" in result_td["mermaid"]

            # Left-right
            result_lr = tool.execute(
                {"file_path": temp_path, "visualization_type": "flowchart", "direction": "LR"}
            )

            assert result_lr["success"] is True
            assert "graph LR" in result_lr["mermaid"]

        finally:
            Path(temp_path).unlink()

    def test_visualize_file_not_found(self):
        """Test error handling for missing file."""
        tool = VisualizeCodeGraphTool()
        result = tool.execute(
            {"file_path": "/nonexistent/file.py", "visualization_type": "flowchart"}
        )

        assert result["success"] is False
        assert "not found" in result["error"].lower()

    def test_visualize_directory_not_found(self):
        """Test error handling for missing directory."""
        tool = VisualizeCodeGraphTool()
        result = tool.execute(
            {"directory": "/nonexistent/directory", "visualization_type": "dependency"}
        )

        assert result["success"] is False
        assert "not found" in result["error"].lower()

    def test_visualize_flowchart_missing_source(self):
        """Test error when flowchart has no file_path or directory."""
        tool = VisualizeCodeGraphTool()
        result = tool.execute({"visualization_type": "flowchart"})

        assert result["success"] is False
        assert "requires" in result["error"].lower()

    def test_visualize_invalid_visualization_type(self):
        """Test error for invalid visualization type."""
        code = """
def helper():
    return 42
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            temp_path = f.name

        try:
            tool = VisualizeCodeGraphTool()
            result = tool.execute({"file_path": temp_path, "visualization_type": "invalid_type"})

            # Schema validation should catch this
            # But if it doesn't, tool should handle it
            if "success" in result:
                assert result["success"] is False

        finally:
            Path(temp_path).unlink()
