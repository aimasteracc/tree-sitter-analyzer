"""Tests for Mermaid/DOT cycle annotation and multi-language query support."""
from __future__ import annotations

from pathlib import Path

import pytest

from tree_sitter_analyzer.analysis.dependency_graph import DependencyGraph


class TestMermaidCycleAnnotation:
    """Mermaid export highlights cyclic edges."""

    def test_cyclic_edges_dashed(self) -> None:
        graph = DependencyGraph(
            nodes={"A": {}, "B": {}, "C": {}},
            edges=[("A", "B"), ("B", "C"), ("C", "A")],
        )
        mermaid = graph.to_mermaid()
        assert "cycle" in mermaid
        assert "-.->" in mermaid

    def test_acyclic_edges_normal(self) -> None:
        graph = DependencyGraph(
            nodes={"A": {}, "B": {}, "C": {}},
            edges=[("A", "B"), ("B", "C")],
        )
        mermaid = graph.to_mermaid()
        assert "cycle" not in mermaid
        assert "-.->" not in mermaid

    def test_partially_cyclic(self) -> None:
        graph = DependencyGraph(
            nodes={"A": {}, "B": {}, "C": {}, "D": {}},
            edges=[("A", "B"), ("B", "A"), ("C", "D")],
        )
        mermaid = graph.to_mermaid()
        # A-B cycle should be dashed, C-D should be normal
        assert "cycle" in mermaid
        lines = mermaid.split("\n")
        cycle_lines = [line for line in lines if "cycle" in line]
        normal_lines = [line for line in lines if "-->" in line and "cycle" not in line]
        assert len(cycle_lines) >= 1
        assert len(normal_lines) >= 1


class TestDotCycleAnnotation:
    """DOT export highlights cyclic edges."""

    def test_cyclic_edges_red_dashed(self) -> None:
        graph = DependencyGraph(
            nodes={"A": {}, "B": {}},
            edges=[("A", "B"), ("B", "A")],
        )
        dot = graph.to_dot()
        assert "dashed" in dot
        assert "red" in dot
        assert "cycle" in dot

    def test_acyclic_no_style(self) -> None:
        graph = DependencyGraph(
            nodes={"A": {}, "B": {}},
            edges=[("A", "B")],
        )
        dot = graph.to_dot()
        assert "dashed" not in dot
        assert "red" not in dot


class TestDependencyQueryToolMultiLang:
    """Integration test: dependency_query with Go/C#/Kotlin files."""

    @pytest.mark.asyncio
    async def test_csharp_project_health(self, tmp_path: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.dependency_query_tool import (
            DependencyQueryTool,
        )

        (tmp_path / "Controllers").mkdir()
        (tmp_path / "Models").mkdir()
        (tmp_path / "Controllers" / "UserController.cs").write_text(
            "using MyApp.Models;\n"
            "public class UserController : BaseController {\n"
            "  public User GetUser(int id) { return null; }\n"
            "}\n",
            encoding="utf-8",
        )
        (tmp_path / "Models" / "User.cs").write_text(
            "public class User {\n  public string Name { get; set; }\n}\n",
            encoding="utf-8",
        )

        tool = DependencyQueryTool(project_root=str(tmp_path))
        result = await tool.execute({"query_type": "health_scores"})
        assert result["success"] is True
        assert result["total_files"] >= 2
        for score in result["scores"]:
            assert "cyclomatic_complexity" in score
            assert "avg_function_length" in score

    @pytest.mark.asyncio
    async def test_go_project_dependents(self, tmp_path: Path) -> None:
        from tree_sitter_analyzer.mcp.tools.dependency_query_tool import (
            DependencyQueryTool,
        )

        (tmp_path / "main.go").write_text(
            'package main\n\nimport "github.com/myproject/db"\n\nfunc main() { }\n',
            encoding="utf-8",
        )
        (tmp_path / "db.go").write_text(
            'package main\n\nfunc Connect() { }\n',
            encoding="utf-8",
        )

        tool = DependencyQueryTool(project_root=str(tmp_path))
        files = [
            str(tmp_path / "main.go"),
            str(tmp_path / "db.go"),
        ]
        result = await tool.execute({
            "query_type": "dependents",
            "node": "db",
            "file_paths": files,
        })
        assert result["success"] is True
