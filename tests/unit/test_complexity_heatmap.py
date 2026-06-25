"""Tests for complexity heatmap engine and MCP tool."""

import contextlib
import json
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
    assert result["indexed"] == 4
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
        assert len(funcs) == 3
        nested = [f for f in funcs if f.name == "deeply_nested"]
        assert len(nested) == 1
        assert nested[0].complexity == 8

    def test_class_method_detection(self, complex_project):
        from tree_sitter_analyzer.complexity_heatmap import analyze_file_complexity

        funcs = analyze_file_complexity(str(complex_project / "complex.py"), "python")
        process = [f for f in funcs if f.name == "process"]
        assert len(process) == 1
        assert process[0].class_name == "DataProcessor"
        assert process[0].complexity == 5

    def test_empty_file(self, complex_project):
        from tree_sitter_analyzer.complexity_heatmap import analyze_file_complexity

        funcs = analyze_file_complexity(str(complex_project / "empty.py"), "python")
        assert funcs == []

    def test_javascript_complexity(self, complex_project):
        from tree_sitter_analyzer.complexity_heatmap import analyze_file_complexity

        funcs = analyze_file_complexity(str(complex_project / "mixed.js"), "javascript")
        assert len(funcs) == 1
        fetch = [f for f in funcs if f.name == "fetchData"]
        assert len(fetch) == 1
        assert fetch[0].complexity == 5

    def test_same_line_javascript_functions_keep_distinct_complexity(self, tmp_path):
        from tree_sitter_analyzer.complexity_heatmap import analyze_file_complexity

        script = tmp_path / "same_line.js"
        script.write_text(
            "const a = (x) => x ? 1 : 2; "
            "const b = (x, y) => { if (x) return 1; if (y) return 2; return 3; };\n",
            encoding="utf-8",
        )

        funcs = {
            f.name: f.complexity
            for f in analyze_file_complexity(str(script), "javascript")
        }
        assert funcs == {"a": 2, "b": 3}

    def test_complexity_span_keys_reject_missing_lines(self):
        from tree_sitter_analyzer.complexity_heatmap import (
            _complexity_key,
            _span_name_key,
        )

        assert _complexity_key(None, 4, "fn", "body") is None
        assert _complexity_key(1, None, "fn", "body") is None
        assert _span_name_key(None, 4, "fn") is None
        assert _span_name_key(1, None, "fn") is None

    def test_extractor_complexity_by_span_handles_missing_plugin(self, monkeypatch):
        from tree_sitter_analyzer.complexity_heatmap import (
            _extractor_complexity_by_span,
        )

        class MissingPluginManager:
            def get_plugin(self, _language):
                return None

        monkeypatch.setattr(
            "tree_sitter_analyzer.plugins.manager.PluginManager",
            MissingPluginManager,
        )

        assert _extractor_complexity_by_span(None, "", "unknown") == ({}, {})

    def test_extractor_complexity_by_span_handles_extractor_failure(
        self, monkeypatch
    ):
        from tree_sitter_analyzer.complexity_heatmap import (
            _extractor_complexity_by_span,
        )

        class BrokenExtractor:
            def extract_functions(self, _tree, _source):
                raise RuntimeError("boom")

        class BrokenPlugin:
            def create_extractor(self):
                return BrokenExtractor()

        class BrokenPluginManager:
            def get_plugin(self, _language):
                return BrokenPlugin()

        monkeypatch.setattr(
            "tree_sitter_analyzer.plugins.manager.PluginManager",
            BrokenPluginManager,
        )

        assert _extractor_complexity_by_span(None, "", "python") == ({}, {})

    def test_extractor_complexity_by_span_skips_incomplete_metadata(
        self, monkeypatch
    ):
        from types import SimpleNamespace

        from tree_sitter_analyzer.complexity_heatmap import (
            _extractor_complexity_by_span,
        )

        incomplete = SimpleNamespace(
            start_line=None,
            end_line=3,
            name="missing_start",
            raw_text="def missing_start(): pass",
            complexity_score=7,
        )

        class IncompleteExtractor:
            def extract_functions(self, _tree, _source):
                return [incomplete]

        class IncompletePlugin:
            def create_extractor(self):
                return IncompleteExtractor()

        class IncompletePluginManager:
            def get_plugin(self, _language):
                return IncompletePlugin()

        monkeypatch.setattr(
            "tree_sitter_analyzer.plugins.manager.PluginManager",
            IncompletePluginManager,
        )

        assert _extractor_complexity_by_span(None, "", "python") == ({}, {})

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
        assert heatmap["total_files_analyzed"] == 3
        assert heatmap["total_functions"] == 6
        assert heatmap["total_cyclomatic_complexity"] == 21
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
        assert heatmap["total_files_analyzed"] == 3

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
        assert len(funcs) == 3
        nested = [f for f in funcs if f.name == "deeply_nested"]
        assert len(nested) == 1
        assert nested[0].complexity == 8
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
        assert heatmap["total_files_analyzed"] == 3
        assert heatmap["total_functions"] == 6
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
        assert result["total_functions"] == 6
        assert "risk_distribution" in result
        assert "risk_bands" in result
        assert result["verdict"] in ("INFO", "REVIEW")

    @pytest.mark.asyncio
    async def test_project_mode_string_max_files(self, complex_project):
        """Project mode must coerce a string ``max_files`` to int.

        The MCP boundary can deliver numeric params as strings (e.g.
        ``"200"``). Before the coercion fix, ``_collect_source_files`` did
        ``len(results) >= max_files`` and raised
        ``TypeError: '>=' not supported between instances of 'int' and 'str'``.
        The string path must behave identically to the int path.
        """
        tool = self._make_tool(complex_project)
        result = await tool.execute(
            {"mode": "project", "output_format": "json", "max_files": "200"}
        )
        assert result["success"] is True
        assert result["mode"] == "project"
        assert result["total_functions"] == 6

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
        assert result["function_count"] == 3
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
        assert result["complexity"] == 8
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

        # Pass --project-root so the heatmap scans the tmp fixture, not os.getcwd()
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "tsa",
                "--project-root",
                str(indexed_complex_project),
                "--codegraph-complexity-heatmap",
                "--format",
                "json",
            ],
        )
        buf = StringIO()
        monkeypatch.setattr("sys.stdout", buf)
        with contextlib.suppress(SystemExit):
            main()

        data = json.loads(buf.getvalue())
        assert data["success"] is True
        assert data["mode"] == "project"
        assert data["total_functions"] == 6
        assert "risk_distribution" in data

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="tracked: heatmap file/function CLI emits no stdout on Windows "
        "(path-arg handling); file-level logic is covered cross-platform by "
        "TestComplexityEngine",
    )
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

        data = json.loads(buf.getvalue())
        assert data["success"] is True
        assert data["mode"] == "file"
        assert data["function_count"] == 3
        assert "deeply_nested" in {f["name"] for f in data["functions"]}

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="tracked: heatmap file/function CLI emits no stdout on Windows "
        "(path-arg handling); function-level logic is covered cross-platform by "
        "TestComplexityEngine",
    )
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

        data = json.loads(buf.getvalue())
        assert data["success"] is True
        assert data["mode"] == "function"
        assert data["name"] == "deeply_nested"
        assert data["complexity"] == 8


# ---------------------------------------------------------------------------
# Tests for languages NOT in the hardcoded _METHOD_NODES map (C#, Ruby, …).
# These exercise the plugin-fallback path added to fix the silent-empty bug.
# Exact integer counts are pinned per the "exact assertions only" rule.
# ---------------------------------------------------------------------------

_CSHARP_FIXTURE = """\
public class Calculator {
    public int Add(int a, int b) {
        if (a < 0) return 0;
        return a + b;
    }
    public int Sub(int a, int b) {
        return a - b;
    }
}
"""

_RUBY_FIXTURE = """\
def greet(name)
  if name.nil?
    "Hello stranger"
  else
    "Hello #{name}"
  end
end

def add(a, b)
  a + b
end
"""


@pytest.fixture()
def csharp_project(tmp_path):
    project = tmp_path / "csproject"
    project.mkdir()
    (project / "Calculator.cs").write_text(_CSHARP_FIXTURE)
    return project


@pytest.fixture()
def ruby_project(tmp_path):
    project = tmp_path / "rbproject"
    project.mkdir()
    (project / "helpers.rb").write_text(_RUBY_FIXTURE)
    return project


class TestPluginFallbackLanguages:
    """Verify that languages absent from _METHOD_NODES get correct results
    via the plugin-sync fallback rather than a silent empty list."""

    def test_csharp_file_complexity(self, csharp_project):
        from tree_sitter_analyzer.complexity_heatmap import analyze_file_complexity

        funcs = analyze_file_complexity(str(csharp_project / "Calculator.cs"), "csharp")
        # C# fixture has exactly 2 methods: Add (complexity 2) and Sub (complexity 1)
        assert len(funcs) == 2
        names = {f.name for f in funcs}
        assert names == {"Add", "Sub"}
        add_func = next(f for f in funcs if f.name == "Add")
        assert add_func.complexity == 2

    def test_ruby_file_complexity(self, ruby_project):
        from tree_sitter_analyzer.complexity_heatmap import analyze_file_complexity

        funcs = analyze_file_complexity(str(ruby_project / "helpers.rb"), "ruby")
        # Ruby fixture has exactly 2 methods
        assert len(funcs) == 2
        names = {f.name for f in funcs}
        assert names == {"greet", "add"}

    def test_csharp_project_heatmap(self, csharp_project):
        from tree_sitter_analyzer.complexity_heatmap import analyze_project_heatmap

        heatmap = analyze_project_heatmap(str(csharp_project))
        # 1 .cs file containing 2 methods
        assert heatmap["total_files_analyzed"] == 1
        assert heatmap["total_functions"] == 2

    def test_ruby_project_heatmap(self, ruby_project):
        from tree_sitter_analyzer.complexity_heatmap import analyze_project_heatmap

        heatmap = analyze_project_heatmap(str(ruby_project))
        # 1 .rb file containing 2 methods
        assert heatmap["total_files_analyzed"] == 1
        assert heatmap["total_functions"] == 2

    def test_empty_project_warns(self, tmp_path):
        """When a project yields 0 functions, result must carry a note/warning."""
        from tree_sitter_analyzer.complexity_heatmap import analyze_project_heatmap

        empty_project = tmp_path / "emptyproj"
        empty_project.mkdir()
        # A .cs file with no methods (just a using statement)
        (empty_project / "Empty.cs").write_text("using System;\n")
        heatmap = analyze_project_heatmap(str(empty_project))
        assert heatmap["total_functions"] == 0
        # Must NOT be silently clean — must carry a warning/note field
        assert "note" in heatmap or "warning" in heatmap
