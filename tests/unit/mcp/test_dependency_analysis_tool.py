"""Unit tests for dependency_analysis_tool."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.dependency_analysis_tool import (
    DependencyAnalysisTool,
    _blast_recommendation,
    _cycles,
    _file_deps,
    _summary,
)
from tree_sitter_analyzer.project_graph import DependencyGraph


def _run(coro):
    return asyncio.run(coro)


def _write(tmp_path: Path, rel: str, content: str) -> Path:
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return p


@pytest.fixture
def project(tmp_path):
    _write(tmp_path, "main.py", "from pkg import utils\nfrom lib import helper\n")
    _write(tmp_path, "pkg/__init__.py", "")
    _write(tmp_path, "pkg/utils.py", "from pkg import core\n")
    _write(tmp_path, "pkg/core.py", "import os\n")
    _write(tmp_path, "lib/__init__.py", "")
    _write(tmp_path, "lib/helper.py", "import json\n")
    return tmp_path


@pytest.fixture
def tool(project):
    t = DependencyAnalysisTool(project_root=str(project))
    t.set_project_path(str(project))
    return t


class TestToolDefinition:
    def test_definition_has_name(self, tool):
        defn = tool.get_tool_definition()
        assert defn["name"] == "analyze_dependencies"
        assert "dependency" in defn["description"].lower()

    def test_schema_has_mode(self, tool):
        schema = tool.get_tool_schema()
        assert "mode" in schema["properties"]
        assert "file_path" in schema["properties"]
        assert "output_format" in schema["properties"]

    def test_schema_modes_include_required(self, tool):
        schema = tool.get_tool_schema()
        modes = schema["properties"]["mode"]["enum"]
        assert "summary" in modes
        assert "blast_radius" in modes
        assert "file_deps" in modes
        assert "cycles" in modes


class TestValidation:
    def test_summary_needs_no_file_path(self, tool):
        assert tool.validate_arguments({"mode": "summary"}) is True

    def test_cycles_needs_no_file_path(self, tool):
        assert tool.validate_arguments({"mode": "cycles"}) is True

    def test_blast_radius_requires_file_path(self, tool):
        with pytest.raises(ValueError, match="file_path is required"):
            tool.validate_arguments({"mode": "blast_radius"})

    def test_file_deps_requires_file_path(self, tool):
        with pytest.raises(ValueError, match="file_path is required"):
            tool.validate_arguments({"mode": "file_deps"})

    def test_blast_radius_passes_with_file_path(self, tool):
        assert (
            tool.validate_arguments({"mode": "blast_radius", "file_path": "main.py"})
            is True
        )

    def test_file_deps_passes_with_file_path(self, tool):
        assert (
            tool.validate_arguments({"mode": "file_deps", "file_path": "main.py"})
            is True
        )

    def test_default_mode_is_summary(self, tool):
        assert tool.validate_arguments({}) is True

    def test_blast_is_alias_for_blast_radius(self, tool):
        # Wave 1b (audit health-02): 'blast' is a natural short form; it must
        # normalise to 'blast_radius' instead of raising "Unknown mode: blast".
        assert DependencyAnalysisTool._normalize_mode("blast") == "blast_radius"
        # validation now treats it as blast_radius (which requires file_path).
        assert tool.validate_arguments({"mode": "blast", "file_path": "x.py"}) is True
        with pytest.raises(ValueError, match="file_path is required"):
            tool.validate_arguments({"mode": "blast"})


class TestSummaryMode:
    def test_summary_returns_node_and_edge_count(self, tool, project):
        result = _run(tool.execute({"mode": "summary", "output_format": "json"}))
        assert result["success"] is True
        assert result["mode"] == "summary"
        assert result["node_count"] == 6
        assert result["edge_count"] == 3
        assert "top_hub_files" in result
        assert "high_dependency_files" in result

    def test_summary_with_toon_format(self, tool, project):
        result = _run(tool.execute({"mode": "summary", "output_format": "toon"}))
        assert result["success"] is True
        assert "toon_content" in result

    def test_summary_empty_project(self, tmp_path):
        t = DependencyAnalysisTool(project_root=str(tmp_path))
        t.set_project_path(str(tmp_path))
        result = _run(t.execute({"mode": "summary", "output_format": "json"}))
        assert result["success"] is True
        assert result["node_count"] == 0

    def test_summary_identifies_hub_files(self, tool, project):
        result = _run(tool.execute({"mode": "summary", "output_format": "json"}))
        hub_files = result["top_hub_files"]
        if hub_files:
            assert "file" in hub_files[0]
            assert "dependents" in hub_files[0]


class TestFileDepsMode:
    def test_file_deps_returns_dependencies(self, tool, project):
        result = _run(
            tool.execute(
                {"mode": "file_deps", "file_path": "main.py", "output_format": "json"}
            )
        )
        assert result["success"] is True
        assert result["mode"] == "file_deps"
        assert result["file"] == "main.py"
        assert isinstance(result["depends_on"], list)
        assert isinstance(result["depended_by"], list)
        assert "dependency_count" in result
        assert "dependent_count" in result

    def test_file_deps_with_toon(self, tool, project):
        result = _run(
            tool.execute(
                {
                    "mode": "file_deps",
                    "file_path": "main.py",
                    "output_format": "toon",
                }
            )
        )
        assert result["success"] is True
        assert "toon_content" in result

    def test_file_deps_file_not_found(self, tool, project):
        with pytest.raises(ValueError, match="not found"):
            _run(
                tool.execute(
                    {
                        "mode": "file_deps",
                        "file_path": "nonexistent.py",
                        "output_format": "json",
                    }
                )
            )

    def test_file_deps_absolute_path(self, tool, project):
        abs_path = str(project / "main.py")
        result = _run(
            tool.execute(
                {"mode": "file_deps", "file_path": abs_path, "output_format": "json"}
            )
        )
        assert result["success"] is True

    def test_file_deps_isolated_file(self, tool, tmp_path):
        _write(tmp_path, "isolated.py", "x = 1\n")
        t = DependencyAnalysisTool(project_root=str(tmp_path))
        t.set_project_path(str(tmp_path))
        result = _run(
            t.execute(
                {
                    "mode": "file_deps",
                    "file_path": "isolated.py",
                    "output_format": "json",
                }
            )
        )
        assert result["success"] is True
        assert result["dependency_count"] == 0
        assert result["dependent_count"] == 0


class TestBlastRadiusMode:
    def test_blast_radius_returns_impact(self, tool, project):
        result = _run(
            tool.execute(
                {
                    "mode": "blast_radius",
                    "file_path": "pkg/core.py",
                    "output_format": "json",
                }
            )
        )
        assert result["success"] is True
        assert result["mode"] == "blast_radius"
        assert isinstance(result["forward_impact_count"], int)
        assert isinstance(result["reverse_dependency_count"], int)
        assert isinstance(result["forward_impact"], list)
        assert isinstance(result["reverse_dependencies"], list)
        assert "recommendation" in result

    def test_blast_radius_isolated_file(self, tool, tmp_path):
        _write(tmp_path, "solo.py", "y = 2\n")
        t = DependencyAnalysisTool(project_root=str(tmp_path))
        t.set_project_path(str(tmp_path))
        result = _run(
            t.execute(
                {
                    "mode": "blast_radius",
                    "file_path": "solo.py",
                    "output_format": "json",
                }
            )
        )
        assert result["success"] is True
        assert result["forward_impact_count"] == 0

    def test_blast_radius_file_not_found(self, tool, project):
        with pytest.raises(ValueError, match="not found"):
            _run(
                tool.execute(
                    {
                        "mode": "blast_radius",
                        "file_path": "ghost.py",
                        "output_format": "json",
                    }
                )
            )

    def test_blast_radius_with_toon(self, tool, project):
        result = _run(
            tool.execute(
                {
                    "mode": "blast_radius",
                    "file_path": "main.py",
                    "output_format": "toon",
                }
            )
        )
        assert result["success"] is True
        assert "toon_content" in result


class TestCyclesMode:
    def test_cycles_no_cycles(self, tool, project):
        result = _run(tool.execute({"mode": "cycles", "output_format": "json"}))
        assert result["success"] is True
        assert result["mode"] == "cycles"
        assert isinstance(result["cycle_count"], int)
        assert isinstance(result["cycles"], list)

    def test_cycles_with_cycle(self, tmp_path):
        _write(tmp_path, "a.py", "import b\n")
        _write(tmp_path, "b.py", "import a\n")
        t = DependencyAnalysisTool(project_root=str(tmp_path))
        t.set_project_path(str(tmp_path))
        result = _run(t.execute({"mode": "cycles", "output_format": "json"}))
        assert result["success"] is True
        assert result["cycle_count"] == 1

    def test_cycles_with_toon(self, tool, project):
        result = _run(tool.execute({"mode": "cycles", "output_format": "toon"}))
        assert result["success"] is True
        assert "toon_content" in result

    def test_cycles_clean_project(self, tmp_path):
        _write(tmp_path, "main.py", "import os\n")
        _write(tmp_path, "utils.py", "import json\n")
        t = DependencyAnalysisTool(project_root=str(tmp_path))
        t.set_project_path(str(tmp_path))
        result = _run(t.execute({"mode": "cycles", "output_format": "json"}))
        assert result["success"] is True
        assert result["cycle_count"] == 0


class TestResolveFile:
    def test_resolves_by_filename_fuzzy(self, tool, project):
        resolved = tool._resolve_file("core.py", tool._get_graph())
        assert "core" in resolved

    def test_resolves_relative_path(self, tool, project):
        resolved = tool._resolve_file("main.py", tool._get_graph())
        assert resolved == "main.py"

    def test_raises_on_missing(self, tool, project):
        with pytest.raises(ValueError, match="not found"):
            tool._resolve_file("does_not_exist.py", tool._get_graph())


class TestBlastRecommendation:
    def test_isolated_file(self):
        rec = _blast_recommendation({"forward_count": 0, "reverse_count": 0})
        assert "Isolated" in rec

    def test_high_impact(self):
        rec = _blast_recommendation({"forward_count": 25, "reverse_count": 5})
        assert "High-impact" in rec

    def test_moderate_impact(self):
        rec = _blast_recommendation({"forward_count": 8, "reverse_count": 2})
        assert "Moderate" in rec

    def test_low_impact(self):
        rec = _blast_recommendation({"forward_count": 2, "reverse_count": 0})
        assert "Low impact" in rec

    def test_no_downstream(self):
        rec = _blast_recommendation({"forward_count": 0, "reverse_count": 3})
        assert "No downstream" in rec


class TestSummaryHelper:
    def test_summary_populates_hubs(self, project):
        graph = DependencyGraph(str(project))
        result = _summary(graph)
        assert result["success"] is True
        assert result["node_count"] == 6
        assert isinstance(result["top_hub_files"], list)

    def test_summary_empty_graph(self, tmp_path):
        graph = DependencyGraph(str(tmp_path))
        result = _summary(graph)
        assert result["node_count"] == 0
        assert result["edge_count"] == 0


class TestCyclesHelper:
    def test_cycles_helper_no_cycles(self, project):
        graph = DependencyGraph(str(project))
        result = _cycles(graph)
        assert result["success"] is True
        assert isinstance(result["cycles"], list)

    def test_cycles_helper_with_cycle(self, tmp_path):
        _write(tmp_path, "x.py", "import y\n")
        _write(tmp_path, "y.py", "import x\n")
        graph = DependencyGraph(str(tmp_path))
        result = _cycles(graph)
        assert result["cycle_count"] == 1  # x.py → y.py → x.py = 1 cycle


class TestFileDepsHelper:
    def test_file_deps_helper(self, project):
        graph = DependencyGraph(str(project))
        result = _file_deps(graph, "main.py")
        assert result["success"] is True
        assert result["file"] == "main.py"

    def test_file_deps_helper_counts(self, project):
        graph = DependencyGraph(str(project))
        result = _file_deps(graph, "main.py")
        assert result["dependency_count"] == 2
        assert result["dependent_count"] == 0


class TestGraphResetOnPathChange:
    def test_set_project_path_resets_graph(self, tool, project):
        tool._graph = DependencyGraph(str(project))
        tool.set_project_path(str(project))
        assert tool._graph is None

    def test_graph_rebuilt_after_reset(self, tool, project):
        tool._graph = DependencyGraph(str(project))
        tool.set_project_path(str(project))
        new_graph = tool._get_graph()
        assert new_graph is not None


class TestNoProjectRoot:
    def test_execute_without_project_root_raises(self):
        t = DependencyAnalysisTool(project_root=None)
        with pytest.raises(ValueError, match="Project root"):
            _run(t.execute({"mode": "summary"}))

    def test_get_graph_without_root_raises(self):
        t = DependencyAnalysisTool(project_root=None)
        with pytest.raises(ValueError, match="Project root"):
            t._get_graph()


class TestDefaultArguments:
    def test_default_mode_is_summary(self, tool, project):
        result = _run(tool.execute({"output_format": "json"}))
        assert result["mode"] == "summary"

    def test_default_format_is_toon(self, tool, project):
        result = _run(tool.execute({}))
        assert "toon_content" in result


class TestUnknownMode:
    def test_unknown_mode_raises(self, tool, project):
        with pytest.raises(ValueError, match="Unknown mode"):
            _run(tool.execute({"mode": "nonexistent", "output_format": "json"}))


class TestBug784CyclesScope:
    """Bug #784: cycles mode must include a scope label explaining that its
    count may differ from health action=imports mode=cycles because the two
    tools walk different graphs (file-dependency vs import-resolution).

    The fix adds ``scope`` and ``scope_note`` to the cycles response so agents
    and humans understand the difference without reading source code.
    """

    def test_cycles_response_has_scope_field(self, tmp_path):
        _write(tmp_path, "a.py", "import b\n")
        _write(tmp_path, "b.py", "import a\n")
        t = DependencyAnalysisTool(project_root=str(tmp_path))
        t.set_project_path(str(tmp_path))
        result = _run(t.execute({"mode": "cycles", "output_format": "json"}))
        assert result["scope"] == "file_dependency_graph"

    def test_cycles_response_has_scope_note(self, tmp_path):
        _write(tmp_path, "x.py", "import os\n")
        t = DependencyAnalysisTool(project_root=str(tmp_path))
        t.set_project_path(str(tmp_path))
        result = _run(t.execute({"mode": "cycles", "output_format": "json"}))
        assert "scope_note" in result
        assert "import" in result["scope_note"].lower()

    def test_cycles_helper_has_scope(self, tmp_path):
        """_cycles() helper must include scope at the dict level."""
        _write(tmp_path, "main.py", "import os\n")
        graph = DependencyGraph(str(tmp_path))
        result = _cycles(graph)
        assert result["scope"] == "file_dependency_graph"
        assert "scope_note" in result

    def test_summary_response_has_scope_field(self, tmp_path):
        """summary mode must also include scope so a consumer comparing
        cycle_count from summary vs import-graph-summary sees an explanation."""
        _write(tmp_path, "a.py", "import b\n")
        _write(tmp_path, "b.py", "import a\n")
        t = DependencyAnalysisTool(project_root=str(tmp_path))
        t.set_project_path(str(tmp_path))
        result = _run(t.execute({"mode": "summary", "output_format": "json"}))
        assert result["scope"] == "file_dependency_graph"

    def test_summary_response_has_scope_note(self, tmp_path):
        """summary mode scope_note must reference the import-graph alternative."""
        _write(tmp_path, "x.py", "import os\n")
        t = DependencyAnalysisTool(project_root=str(tmp_path))
        t.set_project_path(str(tmp_path))
        result = _run(t.execute({"mode": "summary", "output_format": "json"}))
        assert "scope_note" in result
        assert "import" in result["scope_note"].lower()
