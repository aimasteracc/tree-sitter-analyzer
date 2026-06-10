"""Tests for README-exclusive codegraph tools: dead_code, dependency_matrix, complexity_heatmap."""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.mcp.tools.complexity_heatmap_tool import (
    CodeGraphComplexityHeatmapTool as ComplexityHeatmapTool,
)
from tree_sitter_analyzer.mcp.tools.dead_code_tool import (
    CodeGraphDeadCodeTool as DeadCodeTool,
)
from tree_sitter_analyzer.mcp.tools.dependency_matrix_tool import (
    CodeGraphDependencyMatrixTool as DependencyMatrixTool,
)


@pytest.fixture
def project(tmp_path):
    (tmp_path / "app.py").write_text(
        "import os\n\ndef used():\n    return 1\n\ndef unused():\n    return 2\n"
    )
    return tmp_path


# ---------------------------------------------------------------------------
# Dead Code Tool
# ---------------------------------------------------------------------------


class TestDeadCodeToolDefinition:
    def test_tool_name(self):
        assert DeadCodeTool().get_tool_definition()["name"] == "codegraph_dead_code"

    def test_schema_mode_enum(self):
        mode = DeadCodeTool().get_tool_schema()["properties"]["mode"]
        assert "all" in mode["enum"]
        assert "dead_functions" in mode["enum"]

    def test_toon_default(self):
        fmt = DeadCodeTool().get_tool_schema()["properties"]["output_format"]
        assert fmt["default"] == "toon"


@pytest.mark.asyncio
class TestDeadCodeToolExecute:
    async def test_runs_on_project(self, project):
        tool = DeadCodeTool(str(project))
        result = await tool.execute({"output_format": "json"})
        assert result["success"] is True

    async def test_toon_format_default(self, project):
        tool = DeadCodeTool(str(project))
        result = await tool.execute({})
        assert result["format"] == "toon"
        assert "toon_content" in result

    async def test_emits_actionable_next_step(self, project):
        # Wave 1b (audit health-10): dead_code must emit a next_step (the boundary
        # mirrors it into agent_summary.next_step) instead of leaving it empty.
        tool = DeadCodeTool(str(project))
        result = await tool.execute({"output_format": "json"})
        assert result.get("next_step")
        assert isinstance(result["next_step"], str) and result["next_step"].strip()

    async def test_issues_branch_next_step_has_count_and_guard(
        self, project, monkeypatch
    ):
        # Cover the findings branch deterministically: inject one unused import so
        # the CAUTION/REVIEW path runs (the project fixture itself yields none).
        import tree_sitter_analyzer.mcp.tools.dead_code_tool as mod
        from tree_sitter_analyzer.dead_code_analyzer import (
            DeadCodeResult,
            UnusedImport,
        )

        fake = DeadCodeResult(
            dead_functions=[],
            unused_imports=[
                UnusedImport(
                    file="m.py", line=1, import_text="import os", unused_names=["os"]
                )
            ],
            unreferenced_variables=[],
            stats={},
        )
        monkeypatch.setattr(mod, "analyze_dead_code", lambda *a, **k: fake)
        tool = DeadCodeTool(str(project))
        result = await tool.execute({"output_format": "json"})
        assert result["verdict"] in ("CAUTION", "REVIEW")
        assert "1 candidate" in result["next_step"]
        assert "guard" in result["next_step"]

    async def test_no_issues_branch_next_step(self, project, monkeypatch):
        # Cover the clean (0-issues) branch deterministically: inject an empty
        # result so verdict=INFO and the "no dead code" next_step runs.
        import tree_sitter_analyzer.mcp.tools.dead_code_tool as mod
        from tree_sitter_analyzer.dead_code_analyzer import DeadCodeResult

        empty = DeadCodeResult(
            dead_functions=[],
            unused_imports=[],
            unreferenced_variables=[],
            stats={},
        )
        monkeypatch.setattr(mod, "analyze_dead_code", lambda *a, **k: empty)
        tool = DeadCodeTool(str(project))
        result = await tool.execute({"output_format": "json"})
        assert result["verdict"] == "INFO"
        assert "No dead code" in result["next_step"]


# ---------------------------------------------------------------------------
# Dependency Matrix Tool
# ---------------------------------------------------------------------------


class TestDependencyMatrixToolDefinition:
    def test_tool_name(self):
        assert (
            DependencyMatrixTool().get_tool_definition()["name"]
            == "codegraph_dependency_matrix"
        )

    def test_schema_mode_enum(self):
        mode = DependencyMatrixTool().get_tool_schema()["properties"]["mode"]
        assert "summary" in mode["enum"]
        assert mode["default"] == "summary"

    def test_toon_default(self):
        fmt = DependencyMatrixTool().get_tool_schema()["properties"]["output_format"]
        assert fmt["default"] == "toon"


@pytest.mark.asyncio
class TestDependencyMatrixToolExecute:
    async def test_runs_on_project(self, project):
        tool = DependencyMatrixTool(str(project))
        result = await tool.execute({"output_format": "json"})
        assert result["success"] is True

    async def test_toon_format_default(self, project):
        tool = DependencyMatrixTool(str(project))
        result = await tool.execute({})
        assert result["format"] == "toon"
        assert "toon_content" in result


# ---------------------------------------------------------------------------
# Complexity Heatmap Tool
# ---------------------------------------------------------------------------


class TestComplexityHeatmapToolDefinition:
    def test_tool_name(self):
        assert (
            ComplexityHeatmapTool().get_tool_definition()["name"]
            == "codegraph_complexity_heatmap"
        )

    def test_toon_default(self):
        fmt = ComplexityHeatmapTool().get_tool_schema()["properties"]["output_format"]
        assert fmt["default"] == "toon"


@pytest.mark.asyncio
class TestComplexityHeatmapToolExecute:
    async def test_runs_on_project(self, project):
        tool = ComplexityHeatmapTool(str(project))
        result = await tool.execute({"output_format": "json"})
        assert result["success"] is True

    async def test_toon_format_default(self, project):
        tool = ComplexityHeatmapTool(str(project))
        result = await tool.execute({})
        assert result["format"] == "toon"
        assert "toon_content" in result
