"""Tests for complexity heatmap engine and MCP tool."""

import contextlib
import sys
from io import StringIO

import pytest


@pytest.fixture()
def complex_project(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    (project / "simple.py").write_text(
        "def add(a, b):\n    return a + b\n\ndef sub(a, b):\n    return a - b\n"
    )
    (project / "complex.py").write_text(
        "def deeply_nested(x, y, z):\n"
        "    if x > 0:\n"
        "        if y > 0:\n"
        "            for i in range(x):\n"
        "                if i % 2 == 0:\n"
        "                    while z > 0:\n"
        "                        try:\n"
        "                            if i + z > 100:\n"
        "                                return True\n"
        "                        except ValueError:\n"
        "                            pass\n"
        "                        z -= 1\n"
        "    return False\n\n"
        "class DataProcessor:\n"
        "    def process(self, data):\n"
        "        if not data:\n"
        "            return None\n"
        "        for item in data:\n"
        "            if item.get('active'):\n"
        "                try:\n"
        "                    self._handle(item)\n"
        "                except RuntimeError:\n"
        "                    continue\n"
        "        return data\n\n"
        "    def _handle(self, item):\n"
        "        pass\n"
    )
    (project / "empty.py").write_text("")
    (project / "mixed.js").write_text(
        "function fetchData(url) {\n"
        "  if (!url) return null;\n"
        "  try {\n"
        "    for (let i = 0; i < 10; i++) {\n"
        "      if (i % 2 === 0) {\n"
        "        console.log(i);\n"
        "      }\n"
        "    }\n"
        "  } catch (e) {\n"
        "    return null;\n"
        "  }\n"
        "  return url;\n"
        "}\n"
    )
    return project


@pytest.fixture()
def indexed_complex_project(complex_project):
    from tree_sitter_analyzer.ast_cache import ASTCache

    cache = ASTCache(str(complex_project))
    result = cache.index_project()
    assert result["indexed"] >= 2
    cache.close()
    return complex_project


class TestComplexityEngine:
    def test_analyze_simple_file(self, complex_project):
        from tree_sitter_analyzer.complexity_heatmap import analyze_file_complexity

        funcs = analyze_file_complexity(str(complex_project / "simple.py"), "python")
        assert len(funcs) == 2
        assert all(f.complexity == 1 for f in funcs)

    def test_analyze_complex_file(self, complex_project):
        from tree_sitter_analyzer.complexity_heatmap import analyze_file_complexity

        funcs = analyze_file_complexity(str(complex_project / "complex.py"), "python")
        assert len(funcs) >= 3
        nested = [f for f in funcs if f.name == "deeply_nested"]
        assert len(nested) == 1
        assert nested[0].complexity >= 6

    def test_class_method_detection(self, complex_project):
        from tree_sitter_analyzer.complexity_heatmap import analyze_file_complexity

        funcs = analyze_file_complexity(str(complex_project / "complex.py"), "python")
        process = [f for f in funcs if f.name == "process"]
        assert len(process) == 1
        assert process[0].class_name == "DataProcessor"
        assert process[0].complexity >= 3

    def test_empty_file(self, complex_project):
        from tree_sitter_analyzer.complexity_heatmap import analyze_file_complexity

        funcs = analyze_file_complexity(str(complex_project / "empty.py"), "python")
        assert funcs == []

    def test_javascript_complexity(self, complex_project):
        from tree_sitter_analyzer.complexity_heatmap import analyze_file_complexity

        funcs = analyze_file_complexity(str(complex_project / "mixed.js"), "javascript")
        assert len(funcs) >= 1
        fetch = [f for f in funcs if f.name == "fetchData"]
        assert len(fetch) == 1
        assert fetch[0].complexity >= 3

    def test_risk_bands(self):
        from tree_sitter_analyzer.complexity_heatmap import _risk_band

        assert _risk_band(1) == "low"
        assert _risk_band(5) == "low"
        assert _risk_band(6) == "medium"
        assert _risk_band(10) == "medium"
        assert _risk_band(11) == "high"
        assert _risk_band(20) == "high"
        assert _risk_band(21) == "critical"
        assert _risk_band(50) == "critical"

    def test_project_heatmap(self, complex_project):
        from tree_sitter_analyzer.complexity_heatmap import analyze_project_heatmap

        heatmap = analyze_project_heatmap(str(complex_project))
        assert heatmap["total_files_analyzed"] >= 2
        assert heatmap["total_functions"] >= 3
        assert heatmap["total_cyclomatic_complexity"] > 0
        assert "risk_distribution" in heatmap
        assert "top_hotspots" in heatmap
        assert "file_heatmaps" in heatmap
        assert heatmap["total_cyclomatic_complexity"] == sum(
            h["total_complexity"] for h in heatmap["file_heatmaps"]
        )

    def test_project_heatmap_language_filter(self, complex_project):
        from tree_sitter_analyzer.complexity_heatmap import analyze_project_heatmap

        heatmap = analyze_project_heatmap(
            str(complex_project), language_filter="python"
        )
        for fh in heatmap["file_heatmaps"]:
            assert fh["language"] == "python"

    def test_project_heatmap_directory_filter(self, complex_project):
        from tree_sitter_analyzer.complexity_heatmap import analyze_project_heatmap

        heatmap = analyze_project_heatmap(str(complex_project), directory_filter=".")
        assert heatmap["total_files_analyzed"] >= 1

    def test_decision_points_populated(self, complex_project):
        from tree_sitter_analyzer.complexity_heatmap import analyze_file_complexity

        funcs = analyze_file_complexity(str(complex_project / "complex.py"), "python")
        nested = [f for f in funcs if f.name == "deeply_nested"]
        assert nested[0].decision_points
        assert "if_statement" in nested[0].decision_points


class TestCacheBackedComplexity:
    def test_cache_backed_analyze(self, indexed_complex_project):
        from tree_sitter_analyzer.ast_cache import ASTCache
        from tree_sitter_analyzer.complexity_heatmap import (
            analyze_file_complexity_from_cache,
        )

        cache = ASTCache(str(indexed_complex_project))
        funcs = analyze_file_complexity_from_cache(
            cache, str(indexed_complex_project / "complex.py")
        )
        assert len(funcs) >= 3
        nested = [f for f in funcs if f.name == "deeply_nested"]
        assert len(nested) == 1
        assert nested[0].complexity >= 6
        cache.close()

    def test_cache_backed_fallback(self, complex_project):
        from tree_sitter_analyzer.complexity_heatmap import (
            analyze_file_complexity_from_cache,
        )

        class FakeCache:
            def lookup(self, fp):
                return None

        funcs = analyze_file_complexity_from_cache(
            FakeCache(), str(complex_project / "simple.py")
        )
        assert len(funcs) == 2

    def test_project_heatmap_with_cache(self, indexed_complex_project):
        from tree_sitter_analyzer.ast_cache import ASTCache
        from tree_sitter_analyzer.complexity_heatmap import analyze_project_heatmap

        cache = ASTCache(str(indexed_complex_project))
        heatmap = analyze_project_heatmap(str(indexed_complex_project), cache=cache)
        assert heatmap["total_files_analyzed"] >= 2
        assert heatmap["total_functions"] >= 3
        cache.close()


class TestComplexityHeatmapTool:
    def _make_tool(self, project_root):
        from tree_sitter_analyzer.mcp.tools.complexity_heatmap_tool import (
            CodeGraphComplexityHeatmapTool,
        )

        return CodeGraphComplexityHeatmapTool(project_root=str(project_root))

    @pytest.mark.asyncio
    async def test_project_mode(self, complex_project):
        tool = self._make_tool(complex_project)
        result = await tool.execute({"mode": "project", "output_format": "json"})
        assert result["success"] is True
        assert result["mode"] == "project"
        assert result["total_functions"] >= 3
        assert "risk_distribution" in result
        assert "risk_bands" in result
        assert result["verdict"] in ("INFO", "REVIEW")

    @pytest.mark.asyncio
    async def test_file_mode(self, complex_project):
        tool = self._make_tool(complex_project)
        result = await tool.execute(
            {
                "mode": "file",
                "file_path": str(complex_project / "complex.py"),
                "output_format": "json",
            }
        )
        assert result["success"] is True
        assert result["mode"] == "file"
        assert result["function_count"] >= 3
        assert "functions" in result
        for fn in result["functions"]:
            assert "complexity" in fn
            assert "risk" in fn

    @pytest.mark.asyncio
    async def test_function_mode(self, complex_project):
        tool = self._make_tool(complex_project)
        result = await tool.execute(
            {
                "mode": "function",
                "file_path": str(complex_project / "complex.py"),
                "function_name": "deeply_nested",
                "output_format": "json",
            }
        )
        assert result["success"] is True
        assert result["mode"] == "function"
        assert result["name"] == "deeply_nested"
        assert result["complexity"] >= 6
        assert "decision_points" in result

    @pytest.mark.asyncio
    async def test_function_not_found(self, complex_project):
        tool = self._make_tool(complex_project)
        result = await tool.execute(
            {
                "mode": "function",
                "file_path": str(complex_project / "simple.py"),
                "function_name": "nonexistent",
                "output_format": "json",
            }
        )
        assert result["success"] is False
        assert result["verdict"] == "NOT_FOUND"

    @pytest.mark.asyncio
    async def test_file_not_found(self, complex_project):
        tool = self._make_tool(complex_project)
        result = await tool.execute(
            {
                "mode": "file",
                "file_path": "/nonexistent/file.py",
                "output_format": "json",
            }
        )
        assert result["success"] is False
        assert result["verdict"] == "NOT_FOUND"

    @pytest.mark.asyncio
    async def test_project_with_cache(self, indexed_complex_project):
        tool = self._make_tool(indexed_complex_project)
        result = await tool.execute({"mode": "project", "output_format": "json"})
        assert result["success"] is True
        if result.get("data_source") == "ast_cache":
            assert "file_heatmaps" in result

    @pytest.mark.asyncio
    async def test_language_filter(self, complex_project):
        tool = self._make_tool(complex_project)
        result = await tool.execute(
            {
                "mode": "project",
                "language": "python",
                "output_format": "json",
            }
        )
        assert result["success"] is True

    def test_validate_bad_mode(self, complex_project):
        tool = self._make_tool(complex_project)
        with pytest.raises(ValueError, match="Invalid mode"):
            tool.validate_arguments({"mode": "bogus"})

    def test_validate_file_mode_no_path(self, complex_project):
        tool = self._make_tool(complex_project)
        with pytest.raises(ValueError, match="file_path required"):
            tool.validate_arguments({"mode": "file"})

    def test_tool_definition(self, complex_project):
        tool = self._make_tool(complex_project)
        defn = tool.get_tool_definition()
        assert defn["name"] == "codegraph_complexity_heatmap"
        assert "inputSchema" in defn


class TestComplexityCLI:
    def test_cli_project_mode(self, indexed_complex_project, monkeypatch):

        from tree_sitter_analyzer.cli_main import main

        monkeypatch.setattr(
            sys,
            "argv",
            [
                "tsa",
                str(indexed_complex_project),
                "--codegraph-complexity-heatmap",
                "--format",
                "json",
            ],
        )
        buf = StringIO()
        monkeypatch.setattr("sys.stdout", buf)
        try:
            main()
        except SystemExit:
            pass

    def test_cli_file_mode(self, complex_project, monkeypatch):

        from tree_sitter_analyzer.cli_main import main

        monkeypatch.setattr(
            sys,
            "argv",
            [
                "tsa",
                str(complex_project),
                "--codegraph-complexity-heatmap",
                "file",
                "--codegraph-complexity-file",
                str(complex_project / "complex.py"),
                "--format",
                "json",
            ],
        )
        buf = StringIO()
        monkeypatch.setattr("sys.stdout", buf)
        with contextlib.suppress(SystemExit):
            main()

    def test_cli_function_mode(self, complex_project, monkeypatch):

        from tree_sitter_analyzer.cli_main import main

        monkeypatch.setattr(
            sys,
            "argv",
            [
                "tsa",
                str(complex_project),
                "--codegraph-complexity-heatmap",
                "function",
                "--codegraph-complexity-file",
                str(complex_project / "complex.py"),
                "--codegraph-complexity-function",
                "deeply_nested",
                "--format",
                "json",
            ],
        )
        buf = StringIO()
        monkeypatch.setattr("sys.stdout", buf)
        with contextlib.suppress(SystemExit):
            main()
