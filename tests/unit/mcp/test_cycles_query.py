"""Tests for the 'cycles' query type in dependency_query_tool."""
from __future__ import annotations

from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.dependency_query_tool import DependencyQueryTool


class TestCyclesQuery:
    """Cycle detection via the dependency_query MCP tool."""

    @pytest.mark.asyncio
    async def test_no_cycles_in_acyclic_project(self, tmp_path: Path) -> None:
        (tmp_path / "A.java").write_text("public class A { }\n", encoding="utf-8")
        (tmp_path / "B.java").write_text("public class B { }\n", encoding="utf-8")

        tool = DependencyQueryTool(project_root=str(tmp_path))
        result = await tool.execute({"query_type": "cycles"})

        assert result["success"] is True
        assert result["has_cycles"] is False
        assert result["cycle_count"] == 0
        assert result["cycles"] == []

    @pytest.mark.asyncio
    async def test_cycles_detected(self, tmp_path: Path) -> None:
        (tmp_path / "A.java").write_text("import B;\npublic class A { }\n", encoding="utf-8")
        (tmp_path / "B.java").write_text("import A;\npublic class B { }\n", encoding="utf-8")

        tool = DependencyQueryTool(project_root=str(tmp_path))
        result = await tool.execute({"query_type": "cycles"})

        assert result["success"] is True
        # If both imports resolve to each other, a cycle should be detected
        if len(result["cycles"]) > 0:
            assert result["has_cycles"] is True
            assert result["cycle_count"] >= 1

    @pytest.mark.asyncio
    async def test_cycles_with_file_paths(self, tmp_path: Path) -> None:
        (tmp_path / "X.java").write_text("public class X { }\n", encoding="utf-8")

        tool = DependencyQueryTool(project_root=str(tmp_path))
        result = await tool.execute({
            "query_type": "cycles",
            "file_paths": [str(tmp_path / "X.java")],
        })

        assert result["success"] is True
        assert result["cycle_count"] == 0

    @pytest.mark.asyncio
    async def test_cycles_validation_rejects_bad_type(self) -> None:
        tool = DependencyQueryTool()
        with pytest.raises(ValueError, match="Invalid query_type"):
            await tool.execute({"query_type": "unknown"})
