"""Tests for CodeGraph Import Graph MCP tool — file-level dependency analysis."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tree_sitter_analyzer.import_graph import ImportGraph, ImportGraphResult
from tree_sitter_analyzer.mcp.tools.import_graph_tool import CodeGraphImportGraphTool


@pytest.fixture
def tool(tmp_path):
    return CodeGraphImportGraphTool(project_root=str(tmp_path))


@pytest.fixture
def mock_graph():
    g = MagicMock(spec=ImportGraph)
    g.project_root = "/fake"
    return g


class TestToolDefinition:
    def test_name(self, tool):
        defn = tool.get_tool_definition()
        assert defn["name"] == "codegraph_import_graph"

    def test_schema_modes(self, tool):
        schema = tool.get_tool_schema()
        modes = schema["properties"]["mode"]["enum"]
        assert "summary" in modes
        assert "deps" in modes
        assert "dependents" in modes
        assert "blast_radius" in modes
        assert "cycles" in modes
        assert "coupling" in modes


class TestValidation:
    @pytest.mark.asyncio
    async def test_deps_requires_file_path(self, tool):
        with pytest.raises(ValueError, match="file_path is required"):
            await tool.execute({"mode": "deps"})

    @pytest.mark.asyncio
    async def test_dependents_requires_file_path(self, tool):
        with pytest.raises(ValueError, match="file_path is required"):
            await tool.execute({"mode": "dependents"})

    @pytest.mark.asyncio
    async def test_blast_radius_requires_file_path(self, tool):
        with pytest.raises(ValueError, match="file_path is required"):
            await tool.execute({"mode": "blast_radius"})

    @pytest.mark.asyncio
    async def test_invalid_mode(self, tool):
        with pytest.raises(ValueError, match="Invalid mode"):
            await tool.execute({"mode": "nonexistent"})


class TestSummaryMode:
    @pytest.mark.asyncio
    async def test_summary_success(self, tool, mock_graph):
        mock_graph.build.return_value = ImportGraphResult(
            edges=[], file_count=10, edge_count=5, cycles=[]
        )
        mock_graph.summary.return_value = {
            "file_count": 10,
            "edge_count": 5,
            "files_with_imports": 8,
            "files_imported_by_others": 4,
            "cycle_count": 0,
            "most_imported": [("models.py", 7)],
            "most_importing": [("main.py", 12)],
        }
        with patch.object(tool, "_get_graph", return_value=mock_graph):
            result = await tool.execute({"mode": "summary"})
        assert result["success"] is True
        assert result["verdict"] == "INFO"
        assert result["mode"] == "summary"
        assert result["file_count"] == 10


class TestDepsMode:
    @pytest.mark.asyncio
    async def test_deps_with_results(self, tool, mock_graph, tmp_path):
        test_file = tmp_path / "a.py"
        test_file.write_text("x = 1")
        mock_graph.dependencies_of.return_value = [
            {"source": "a.py", "target": "b.py", "import": "import b", "line": 0}
        ]
        with patch.object(tool, "_get_graph", return_value=mock_graph):
            result = await tool.execute({"mode": "deps", "file_path": str(test_file)})
        assert result["success"] is True
        assert result["verdict"] == "INFO"
        assert result["dependency_count"] == 1

    @pytest.mark.asyncio
    async def test_deps_no_results(self, tool, mock_graph, tmp_path):
        test_file = tmp_path / "a.py"
        test_file.write_text("x = 1")
        mock_graph.dependencies_of.return_value = []
        with patch.object(tool, "_get_graph", return_value=mock_graph):
            result = await tool.execute({"mode": "deps", "file_path": str(test_file)})
        assert result["verdict"] == "NOT_FOUND"


class TestDependentsMode:
    @pytest.mark.asyncio
    async def test_dependents_with_results(self, tool, mock_graph, tmp_path):
        test_file = tmp_path / "a.py"
        test_file.write_text("x = 1")
        mock_graph.dependents_of.return_value = [
            {"source": "main.py", "target": "a.py", "import": "import a", "line": 0}
        ]
        with patch.object(tool, "_get_graph", return_value=mock_graph):
            result = await tool.execute({"mode": "dependents", "file_path": str(test_file)})
        assert result["success"] is True
        assert result["dependent_count"] == 1


class TestBlastRadiusMode:
    @pytest.mark.asyncio
    async def test_blast_radius_small(self, tool, mock_graph, tmp_path):
        test_file = tmp_path / "a.py"
        test_file.write_text("x = 1")
        mock_graph.blast_radius.return_value = {
            "file": "a.py",
            "direct_dependents": 2,
            "transitive_dependents": 3,
            "affected_files": [
                {"file": "b.py", "depth": 1},
                {"file": "c.py", "depth": 1},
                {"file": "d.py", "depth": 2},
            ],
        }
        with patch.object(tool, "_get_graph", return_value=mock_graph):
            result = await tool.execute({"mode": "blast_radius", "file_path": str(test_file)})
        assert result["success"] is True
        assert result["verdict"] == "INFO"
        assert result["transitive_dependents"] == 3

    @pytest.mark.asyncio
    async def test_blast_radius_large(self, tool, mock_graph, tmp_path):
        test_file = tmp_path / "a.py"
        test_file.write_text("x = 1")
        mock_graph.blast_radius.return_value = {
            "file": "a.py",
            "direct_dependents": 10,
            "transitive_dependents": 15,
            "affected_files": [{"file": f"f{i}.py", "depth": 1} for i in range(8)],
        }
        with patch.object(tool, "_get_graph", return_value=mock_graph):
            result = await tool.execute({"mode": "blast_radius", "file_path": str(test_file)})
        assert result["verdict"] == "REVIEW"


class TestCyclesMode:
    @pytest.mark.asyncio
    async def test_no_cycles(self, tool, mock_graph):
        mock_graph.build.return_value = ImportGraphResult(
            edges=[], file_count=5, edge_count=4, cycles=[]
        )
        with patch.object(tool, "_get_graph", return_value=mock_graph):
            result = await tool.execute({"mode": "cycles"})
        assert result["success"] is True
        assert result["verdict"] == "INFO"
        assert result["cycle_count"] == 0

    @pytest.mark.asyncio
    async def test_with_cycles(self, tool, mock_graph):
        mock_graph.build.return_value = ImportGraphResult(
            edges=[],
            file_count=3,
            edge_count=3,
            cycles=[["a.py", "b.py", "c.py", "a.py"]],
        )
        with patch.object(tool, "_get_graph", return_value=mock_graph):
            result = await tool.execute({"mode": "cycles"})
        assert result["verdict"] == "CAUTION"
        assert result["cycle_count"] == 1


class TestCouplingMode:
    @pytest.mark.asyncio
    async def test_coupling(self, tool, mock_graph):
        mock_graph.build.return_value = ImportGraphResult(
            edges=[], file_count=5, edge_count=4, cycles=[]
        )
        mock_graph.summary.return_value = {
            "most_imported": [("models.py", 7), ("utils.py", 5)],
            "most_importing": [("main.py", 12), ("cli.py", 8)],
        }
        with patch.object(tool, "_get_graph", return_value=mock_graph):
            result = await tool.execute({"mode": "coupling"})
        assert result["success"] is True
        assert len(result["most_imported"]) == 2
        assert len(result["most_importing"]) == 2


class TestToonFormat:
    @pytest.mark.asyncio
    async def test_toon_output(self, tool, mock_graph):
        mock_graph.build.return_value = ImportGraphResult(
            edges=[], file_count=1, edge_count=0, cycles=[]
        )
        mock_graph.summary.return_value = {
            "file_count": 1,
            "edge_count": 0,
            "most_imported": [],
            "most_importing": [],
        }
        with patch.object(tool, "_get_graph", return_value=mock_graph):
            result = await tool.execute({"mode": "summary", "output_format": "toon"})
        assert "toon_content" in result
