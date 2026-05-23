"""Tests for codegraph_visualize MCP tool — Mermaid call graph rendering."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tree_sitter_analyzer.mcp.tools.codegraph_visualize_tool import (
    CodeGraphVisualizeTool,
    _render_mermaid,
    _safe_node_id,
    _short_label,
)

_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent.parent)


class TestMermaidRenderer:
    def test_empty_edges(self) -> None:
        result = _render_mermaid([], "TD")
        assert "flowchart TD" in result
        assert "empty" in result

    def test_single_edge(self) -> None:
        edges = [("n1", "main.py::foo", "n2", "bar.py::baz")]
        result = _render_mermaid(edges, "TD")
        assert "flowchart TD" in result
        assert 'n1["main.py::foo"]' in result
        assert 'n2["bar.py::baz"]' in result
        assert "n1 --> n2" in result

    def test_direction_lr(self) -> None:
        edges = [("a", "A", "b", "B")]
        result = _render_mermaid(edges, "LR")
        assert "flowchart LR" in result

    def test_deduplication(self) -> None:
        edges = [
            ("a", "A", "b", "B"),
            ("a", "A", "b", "B"),
        ]
        result = _render_mermaid(edges, "TD")
        assert result.count("a --> b") == 1

    def test_node_label_escaping(self) -> None:
        edges = [("n1", 'foo("arg")', "n2", "bar")]
        result = _render_mermaid(edges, "TD")
        assert "'arg'" in result


class TestSafeNodeId:
    def test_simple(self) -> None:
        assert _safe_node_id("foo", "bar.py") == "bar_py__foo"

    def test_special_chars(self) -> None:
        result = _safe_node_id("my-func", "src/dir/file.py")
        assert all(c.isalnum() or c == "_" for c in result)

    def test_consistent(self) -> None:
        a = _safe_node_id("foo", "bar.py")
        b = _safe_node_id("foo", "bar.py")
        assert a == b


class TestShortLabel:
    def test_basename(self) -> None:
        assert _short_label("foo", "src/bar.py") == "bar.py::foo"

    def test_nested(self) -> None:
        assert _short_label("fn", "a/b/c.py") == "c.py::fn"


class TestVisualizeToolSchema:
    def test_tool_definition_has_name(self) -> None:
        tool = CodeGraphVisualizeTool()
        defn = tool.get_tool_definition()
        assert defn["name"] == "codegraph_visualize"
        assert "mermaid" in defn["description"].lower()

    def test_schema_modes(self) -> None:
        tool = CodeGraphVisualizeTool()
        schema = tool.get_tool_schema()
        modes = schema["properties"]["mode"]["enum"]
        assert "full" in modes
        assert "file" in modes
        assert "function" in modes

    def test_validate_file_mode_requires_path(self) -> None:
        tool = CodeGraphVisualizeTool()
        with pytest.raises(ValueError, match="file_path"):
            tool.validate_arguments({"mode": "file"})

    def test_validate_function_mode_requires_name(self) -> None:
        tool = CodeGraphVisualizeTool()
        with pytest.raises(ValueError, match="function"):
            tool.validate_arguments({"mode": "function"})

    def test_validate_full_mode_ok(self) -> None:
        tool = CodeGraphVisualizeTool()
        assert tool.validate_arguments({"mode": "full"})

    def test_validate_bad_max_edges(self) -> None:
        tool = CodeGraphVisualizeTool()
        with pytest.raises(ValueError, match="max_edges"):
            tool.validate_arguments({"mode": "full", "max_edges": 0})

    def test_validate_bad_depth(self) -> None:
        tool = CodeGraphVisualizeTool()
        with pytest.raises(ValueError, match="depth"):
            tool.validate_arguments(
                {"mode": "function", "function": "foo", "depth": -1}
            )


class TestVisualizeToolNoProject:
    @pytest.mark.asyncio
    async def test_no_project_root(self) -> None:
        tool = CodeGraphVisualizeTool()
        result = await tool.execute({"mode": "full"})
        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_mocked_full_mode(self) -> None:
        tool = CodeGraphVisualizeTool(_PROJECT_ROOT)
        with patch.object(tool, "_get_call_graph") as mock_cg:
            cg = MagicMock()
            cg._functions = []
            cg._callers = {}
            cg._callees = {}
            mock_cg.return_value = cg
            result = await tool.execute({"mode": "full", "output_format": "json"})
        assert result["success"] is True
        assert "mermaid" in result
        assert "flowchart" in result["mermaid"]
        assert result["stats"]["mode"] == "full"

    @pytest.mark.asyncio
    async def test_mocked_function_mode(self) -> None:
        tool = CodeGraphVisualizeTool(_PROJECT_ROOT)
        from tree_sitter_analyzer.call_graph import FunctionRef

        fn_a = FunctionRef("a.py", "alpha", 1, "python")
        fn_b = FunctionRef("b.py", "beta", 5, "python")
        cg = MagicMock()
        cg._resolve_targets.return_value = [fn_a]
        cg._callees = {fn_a: [fn_b]}
        cg._callers = {}
        with patch.object(tool, "_get_call_graph", return_value=cg):
            result = await tool.execute(
                {
                    "mode": "function",
                    "function": "alpha",
                    "depth": 2,
                    "output_format": "json",
                }
            )
        assert result["success"] is True
        assert "alpha" in result["mermaid"]
        assert "beta" in result["mermaid"]
        assert result["stats"]["mode"] == "function"

    @pytest.mark.asyncio
    async def test_mocked_file_mode(self) -> None:
        tool = CodeGraphVisualizeTool(_PROJECT_ROOT)
        from tree_sitter_analyzer.call_graph import FunctionRef

        fn_a = FunctionRef("a.py", "alpha", 1, "python")
        fn_b = FunctionRef("b.py", "beta", 5, "python")
        cg = MagicMock()
        cg._func_by_file = {"a.py": [fn_a]}
        cg._callees = {fn_a: [fn_b]}
        cg._callers = {}
        with patch.object(tool, "_get_call_graph", return_value=cg):
            result = await tool.execute(
                {
                    "mode": "file",
                    "file_path": "a.py",
                    "output_format": "json",
                }
            )
        assert result["success"] is True
        assert "alpha" in result["mermaid"]
        assert result["stats"]["mode"] == "file"


class TestVisualizeRealProject:
    @pytest.mark.asyncio
    async def test_full_mode_on_self(self) -> None:
        tool = CodeGraphVisualizeTool(_PROJECT_ROOT)
        result = await tool.execute(
            {
                "mode": "full",
                "max_edges": 10,
                "output_format": "json",
            }
        )
        assert result["success"] is True
        assert "mermaid" in result
        assert "flowchart" in result["mermaid"]
        assert result["stats"]["edge_count"] <= 10

    @pytest.mark.asyncio
    async def test_function_mode_on_real_func(self) -> None:
        tool = CodeGraphVisualizeTool(_PROJECT_ROOT)
        result = await tool.execute(
            {
                "mode": "function",
                "function": "parse_file",
                "depth": 1,
                "max_edges": 20,
                "output_format": "json",
            }
        )
        assert result["success"] is True
        assert "mermaid" in result
